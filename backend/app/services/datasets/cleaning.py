"""Data cleaning pipeline. Operations never mutate the source version —
each apply creates a new dataset version (original → cleaned)."""

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.dataset import (
    Dataset,
    DatasetStatus,
    DatasetVersion,
    VersionKind,
)
from app.models.user import User
from app.services.audit import audit
from app.services.datasets import profiling, tables
from app.services.datasets.ingest import write_version

SUPPORTED_OPS = {
    "drop_nulls",
    "fill_nulls",
    "drop_duplicates",
    "cast",
    "rename",
    "normalize_dates",
    "remove_outliers",
}


def read_version_df(engine: Engine, version: DatasetVersion) -> pd.DataFrame:
    table = tables.reflect_table(engine, version.table_name)
    with engine.connect() as conn:
        return pd.read_sql(sa.select(table), conn)


def _validate_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise AppError(f"Unknown column(s): {', '.join(missing)}", "BAD_REQUEST", 400)


def apply_operations(
    df: pd.DataFrame, operations: list[dict]
) -> tuple[pd.DataFrame, dict[str, str], list[dict]]:
    """Returns (cleaned_df, updated_type_map, report)."""
    df = df.copy()
    type_map = dict(profiling.infer_types(df))
    report: list[dict] = []

    for op in operations:
        name = op.get("op")
        if name not in SUPPORTED_OPS:
            raise AppError(f"Unsupported operation '{name}'", "BAD_REQUEST", 400)
        before = len(df)

        if name == "drop_nulls":
            cols = op.get("columns")
            if cols:
                _validate_columns(df, cols)
            df = df.dropna(subset=cols or None)

        elif name == "fill_nulls":
            col = op.get("column")
            _validate_columns(df, [col])
            strategy = op.get("strategy", "value")
            if strategy == "value":
                df[col] = df[col].fillna(op.get("value"))
            elif strategy == "mean":
                df[col] = df[col].fillna(pd.to_numeric(df[col], errors="coerce").mean())
            elif strategy == "median":
                df[col] = df[col].fillna(pd.to_numeric(df[col], errors="coerce").median())
            elif strategy == "mode":
                mode = df[col].mode(dropna=True)
                df[col] = df[col].fillna(mode.iloc[0] if not mode.empty else None)
            else:
                raise AppError(f"Unknown fill strategy '{strategy}'", "BAD_REQUEST", 400)

        elif name == "drop_duplicates":
            df = df.drop_duplicates()

        elif name == "cast":
            col, to = op.get("column"), op.get("to")
            if to not in profiling.INFERRED_TYPES:
                raise AppError(f"Cannot cast to '{to}'", "BAD_REQUEST", 400)
            _validate_columns(df, [col])
            df[[col]] = profiling.coerce_types(df[[col]], {col: to})
            type_map[col] = to

        elif name == "rename":
            col, new_name = op.get("column"), str(op.get("newName", "")).strip()
            _validate_columns(df, [col])
            normalized = profiling.normalize_column_names([new_name])[0]
            if not new_name or normalized in df.columns:
                raise AppError(f"Invalid or duplicate column name '{new_name}'", "BAD_REQUEST", 400)
            df = df.rename(columns={col: normalized})
            type_map[normalized] = type_map.pop(col)

        elif name == "normalize_dates":
            col = op.get("column")
            _validate_columns(df, [col])
            df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed").dt.date
            type_map[col] = "date"

        elif name == "remove_outliers":
            col, method = op.get("column"), op.get("method", "iqr")
            _validate_columns(df, [col])
            numeric = pd.to_numeric(df[col], errors="coerce")
            if method == "zscore":
                std = numeric.std()
                if std and std > 0:
                    mask = ((numeric - numeric.mean()) / std).abs() <= float(op.get("threshold", 3))
                else:
                    mask = pd.Series(True, index=df.index)
            else:  # iqr
                q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
                iqr = q3 - q1
                low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                mask = (numeric >= low) & (numeric <= high) | numeric.isna()
            df = df[mask]

        report.append(
            {"op": name, "rowsBefore": before, "rowsAfter": len(df), "rowsAffected": before - len(df)}
        )

    return df.reset_index(drop=True), type_map, report


def preview_clean(
    engine: Engine, base: DatasetVersion, operations: list[dict], sample: int = 10
) -> dict:
    df = read_version_df(engine, base)
    cleaned, type_map, report = apply_operations(df, operations)
    return {
        "rowsBefore": len(df),
        "rowsAfter": len(cleaned),
        "report": report,
        "beforeSample": df.head(sample).where(pd.notna(df), None).to_dict(orient="records"),
        "afterSample": cleaned.head(sample).where(pd.notna(cleaned), None).to_dict(orient="records"),
        "typeMap": type_map,
    }


def create_cleaned_version(
    db: Session,
    engine: Engine,
    dataset: Dataset,
    base: DatasetVersion,
    operations: list[dict],
    user: User,
    ip: str | None,
) -> DatasetVersion:
    if not operations:
        raise AppError("At least one cleaning operation is required", "BAD_REQUEST", 400)

    df = read_version_df(engine, base)
    cleaned, type_map, _ = apply_operations(df, operations)
    if cleaned.empty:
        raise AppError("Cleaning removed all rows — nothing to save", "BAD_REQUEST", 400)

    # Column display names carry over (renames already applied to headers).
    version = write_version(
        db, engine, dataset=dataset, df=cleaned, type_map=type_map,
        kind=VersionKind.CLEANED, parent=base, operations=operations, user=user,
    )

    dataset.status = DatasetStatus.READY
    dataset.current_version_id = version.id
    dataset.row_count = len(cleaned)
    dataset.column_count = len(cleaned.columns)
    dataset.quality_score = profiling.quality_score(cleaned)
    audit(
        db, user_id=user.id, action="datasets.clean",
        resource_type="dataset", resource_id=str(dataset.id),
        meta={"operations": [o.get("op") for o in operations], "version": version.version_no},
        ip=ip,
    )
    db.commit()
    db.refresh(version)
    return version
