"""Dataset ingestion: validate → store file → profile → physical table → metadata."""

import os
import uuid
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import utcnow
from app.models.dataset import (
    Dataset,
    DatasetColumn,
    DatasetImport,
    DatasetStatus,
    DatasetVersion,
    FileType,
    ImportStatus,
    VersionKind,
)
from app.models.user import User
from app.services.audit import audit
from app.services.datasets import profiling, tables

settings = get_settings()

ALLOWED_EXTENSIONS = {".csv": FileType.CSV, ".xlsx": FileType.XLSX}
INSERT_CHUNK = 5000


def _read_file(path: Path, file_type: FileType) -> pd.DataFrame:
    if file_type == FileType.CSV:
        try:
            return pd.read_csv(path, low_memory=False)
        except UnicodeDecodeError:
            return pd.read_csv(path, low_memory=False, encoding="latin-1")
    return pd.read_excel(path)


def _records(df: pd.DataFrame) -> list[dict]:
    clean = df.where(pd.notna(df), None)
    return clean.to_dict(orient="records")


def write_version(
    db: Session,
    engine: Engine,
    *,
    dataset: Dataset,
    df: pd.DataFrame,
    type_map: dict[str, str],
    kind: VersionKind,
    parent: DatasetVersion | None,
    operations: list | None,
    user: User,
) -> DatasetVersion:
    """Create a physical table for `df`, bulk-insert it, and persist version
    + column-profile metadata."""
    # Release the session's open transaction before DDL/DML on the data-table
    # connection — SQLite serializes writers; harmless commit on Postgres.
    db.commit()
    table_name = tables.new_table_name()
    table = tables.build_table(engine, table_name, [(c, type_map[c]) for c in df.columns])

    records = _records(df)
    with engine.begin() as conn:
        for i in range(0, len(records), INSERT_CHUNK):
            conn.execute(table.insert(), records[i : i + INSERT_CHUNK])

    version = DatasetVersion(
        dataset_id=dataset.id,
        parent_version_id=parent.id if parent else None,
        version_no=(max((v.version_no for v in dataset.versions), default=0)) + 1,
        kind=kind,
        operations=operations,
        table_name=table_name,
        row_count=len(df),
        column_count=len(df.columns),
        created_by=user.id,
    )
    db.add(version)
    db.flush()

    original_names = list(df.columns)
    for ordinal, profile in enumerate(profiling.profile_dataframe(df, type_map)):
        db.add(
            DatasetColumn(
                dataset_id=dataset.id,
                version_id=version.id,
                name=original_names[ordinal],
                normalized_name=profile.name,
                ordinal=ordinal,
                inferred_type=profile.inferred_type,
                null_count=profile.null_count,
                distinct_count=profile.distinct_count,
                min_value=profile.min_value,
                max_value=profile.max_value,
                mean=profile.mean,
                median=profile.median,
                stddev=profile.stddev,
                outlier_count=profile.outlier_count,
                top_values=profile.top_values or None,
            )
        )
    return version


def create_import_stub(
    db: Session,
    user: User,
    *,
    filename: str,
    content: bytes,
    display_name: str | None,
) -> Dataset:
    """Fast part of upload: validate, store the file, create dataset +
    pending import record. The heavy processing happens in
    `process_import` — synchronously or via the job pool."""
    ext = Path(filename).suffix.lower()
    file_type = ALLOWED_EXTENSIONS.get(ext)
    if file_type is None:
        raise AppError("Only .csv and .xlsx files are supported", "BAD_REQUEST", 400)
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise AppError(
            f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit", "PAYLOAD_TOO_LARGE", 413
        )
    if not content:
        raise AppError("The uploaded file is empty", "BAD_REQUEST", 400)

    dataset = Dataset(
        owner_id=user.id,
        name=(display_name or Path(filename).stem)[:200],
        status=DatasetStatus.UPLOADED,
        original_filename=os.path.basename(filename)[:300],
        file_type=file_type,
        file_size_bytes=len(content),
        storage_path="",
    )
    db.add(dataset)
    db.flush()

    upload_dir = Path(settings.UPLOAD_DIR) / str(dataset.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"source{ext}"
    file_path.write_bytes(content)
    dataset.storage_path = str(file_path)

    db.add(
        DatasetImport(
            dataset_id=dataset.id, imported_by=user.id,
            status=ImportStatus.PENDING, started_at=utcnow(),
        )
    )
    db.commit()
    db.refresh(dataset)
    return dataset


def process_import(
    db: Session,
    engine: Engine,
    *,
    dataset: Dataset,
    import_record: DatasetImport,
    user: User,
    ip: str | None,
    df: pd.DataFrame | None = None,
) -> Dataset:
    """Read/normalize → infer → coerce → physical table → profile →
    ready. `df` may be supplied directly (source imports). Emits a
    notification on success/failure."""
    from app.services.notifications import notify

    try:
        import_record.status = ImportStatus.RUNNING
        import_record.started_at = utcnow()
        dataset.status = DatasetStatus.PROFILING
        db.commit()

        if df is None:
            df = _read_file(Path(dataset.storage_path), dataset.file_type)
        if df.empty or len(df.columns) == 0:
            raise ValueError("No readable rows found")

        normalized = profiling.normalize_column_names(list(df.columns))
        df.columns = normalized
        type_map = profiling.infer_types(df)
        df = profiling.coerce_types(df, type_map)

        dataset.status = DatasetStatus.IMPORTING
        db.flush()
        version = write_version(
            db, engine, dataset=dataset, df=df, type_map=type_map,
            kind=VersionKind.ORIGINAL, parent=None, operations=None, user=user,
        )

        dataset.status = DatasetStatus.READY
        dataset.row_count = len(df)
        dataset.column_count = len(df.columns)
        dataset.quality_score = profiling.quality_score(df)
        dataset.current_version_id = version.id
        import_record.status = ImportStatus.SUCCESS
        import_record.version_id = version.id
        import_record.rows_imported = len(df)
        import_record.finished_at = utcnow()

        audit(
            db, user_id=user.id, action="datasets.upload",
            resource_type="dataset", resource_id=str(dataset.id),
            meta={"rows": len(df), "columns": len(df.columns),
                  "file": dataset.original_filename},
            ip=ip,
        )
        notify(
            db, user_id=user.id, type="ingest.success",
            title=f'"{dataset.name}" is ready',
            body=f"{len(df):,} rows · {len(df.columns)} columns · "
                 f"quality {dataset.quality_score:.0f}/100",
            link=f"/datasets/{dataset.id}",
        )
        db.commit()
        db.refresh(dataset)
        return dataset

    except Exception as exc:
        dataset.status = DatasetStatus.FAILED
        import_record.status = ImportStatus.FAILED
        import_record.error_log = [{"error": str(exc)[:500]}]
        import_record.finished_at = utcnow()
        notify(
            db, user_id=user.id, type="ingest.failed",
            title=f'"{dataset.name}" import failed',
            body=str(exc)[:300], link=f"/datasets/{dataset.id}",
        )
        db.commit()
        raise AppError("Could not process the uploaded file", "INGEST_FAILED", 422) from exc


def ingest_upload(
    db: Session,
    engine: Engine,
    user: User,
    *,
    filename: str,
    content: bytes,
    display_name: str | None,
    ip: str | None,
) -> Dataset:
    dataset = create_import_stub(
        db, user, filename=filename, content=content, display_name=display_name
    )
    import_record = db.scalars(
        sa.select(DatasetImport)
        .where(DatasetImport.dataset_id == dataset.id)
        .order_by(DatasetImport.started_at.desc())
        .limit(1)
    ).first()
    return process_import(
        db, engine, dataset=dataset, import_record=import_record, user=user, ip=ip
    )


def delete_dataset(
    db: Session, engine: Engine, dataset: Dataset, user: User, ip: str | None
) -> None:
    """Soft-delete metadata; drop physical data tables (source file retained)."""
    db.commit()  # release read txn before DDL on SQLite
    for version in dataset.versions:
        try:
            tables.drop_table(engine, version.table_name)
        except Exception:
            pass
    dataset.deleted_at = utcnow()
    audit(
        db, user_id=user.id, action="datasets.delete",
        resource_type="dataset", resource_id=str(dataset.id), ip=ip,
    )
    db.commit()
