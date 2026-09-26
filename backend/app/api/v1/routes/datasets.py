import math
import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.deps import get_current_user, require_analyst
from app.core.errors import AppError
from app.models.dataset import (
    Dataset,
    DatasetColumn,
    DatasetImport,
    DatasetStatus,
    DatasetVersion,
)
from app.models.user import User
from app.schemas.common import ok
from app.schemas.dataset import CleanIn, ColumnOut, DatasetOut, ImportOut, VersionOut
from app.services.audit import audit
from app.services.datasets import cleaning, ingest, tables

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_dataset(db: Session, dataset_id: uuid.UUID) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None or ds.deleted_at is not None:
        raise AppError("Dataset not found", "NOT_FOUND", 404)
    return ds


def _resolve_version(db: Session, dataset: Dataset, version_id: uuid.UUID | None) -> DatasetVersion:
    vid = version_id or dataset.current_version_id
    version = db.get(DatasetVersion, vid) if vid else None
    if version is None or version.dataset_id != dataset.id:
        raise AppError("Dataset version not found", "NOT_FOUND", 404)
    return version


def _dump(model, obj) -> dict:
    return model.model_validate(obj).model_dump(by_alias=True)


@router.post("/upload", status_code=201)
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    content = await file.read()
    dataset = ingest.ingest_upload(
        db, engine, user,
        filename=file.filename or "upload", content=content,
        display_name=name, ip=_client_ip(request),
    )
    return ok(_dump(DatasetOut, dataset))


@router.get("")
def list_datasets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    base = select(Dataset).where(Dataset.deleted_at.is_(None))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(Dataset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ok(
        {
            "items": [_dump(DatasetOut, d) for d in rows],
            "total": total,
            "page": page,
            "pages": max(1, math.ceil(total / page_size)),
        }
    )


@router.get("/{dataset_id}")
def get_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    data = _dump(DatasetOut, ds)
    data["versions"] = [_dump(VersionOut, v) for v in ds.versions]
    return ok(data)


@router.get("/{dataset_id}/profile")
def get_profile(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    version = _resolve_version(db, ds, version_id)
    return ok(
        {
            "version": _dump(VersionOut, version),
            "columns": [_dump(ColumnOut, c) for c in sorted(version.columns, key=lambda c: c.ordinal)],
        }
    )


@router.get("/{dataset_id}/preview")
def get_preview(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    version = _resolve_version(db, ds, version_id)
    table = tables.reflect_table(engine, version.table_name)
    first_col = list(table.c)[0]
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(table)).scalar() or 0
        rows = conn.execute(
            sa.select(table)
            .order_by(first_col)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).mappings().all()
    return ok(
        {
            "version": _dump(VersionOut, version),
            "columns": [c.name for c in table.c],
            "rows": [
                {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}
                for r in rows
            ],
            "total": total,
            "page": page,
            "pages": max(1, math.ceil(total / page_size)),
        }
    )


@router.get("/{dataset_id}/versions")
def list_versions(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    return ok([_dump(VersionOut, v) for v in ds.versions])


@router.get("/{dataset_id}/imports")
def list_imports(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    rows = db.scalars(
        select(DatasetImport)
        .where(DatasetImport.dataset_id == ds.id)
        .order_by(DatasetImport.created_at.desc())
        .limit(10)
    ).all()
    return ok([_dump(ImportOut, r) for r in rows])


@router.post("/{dataset_id}/clean/preview")
def preview_clean(
    dataset_id: uuid.UUID,
    body: CleanIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_analyst),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    if ds.status != DatasetStatus.READY:
        raise AppError("Dataset is not ready", "BAD_REQUEST", 400)
    base = _resolve_version(db, ds, body.version_id)
    result = cleaning.preview_clean(
        engine, base, [op.model_dump(by_alias=True, exclude_none=True) for op in body.operations]
    )
    return ok(result)


@router.post("/{dataset_id}/clean", status_code=201)
def apply_clean(
    dataset_id: uuid.UUID,
    body: CleanIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    if ds.status != DatasetStatus.READY:
        raise AppError("Dataset is not ready", "BAD_REQUEST", 400)
    base = _resolve_version(db, ds, body.version_id)
    version = cleaning.create_cleaned_version(
        db, engine, ds, base,
        [op.model_dump(by_alias=True, exclude_none=True) for op in body.operations],
        user, _client_ip(request),
    )
    return ok(_dump(VersionOut, version))


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    if ds.owner_id != user.id and user.role.value != "admin":
        raise AppError("Only the owner or an admin can delete this dataset", "FORBIDDEN", 403)
    ingest.delete_dataset(db, engine, ds, user, _client_ip(request))
    return ok(message="Dataset deleted")
