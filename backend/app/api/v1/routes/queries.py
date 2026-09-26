import time
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.deps import get_current_user, require_analyst
from app.core.errors import AppError
from app.models.analytics import QueryHistory, QuerySource, QueryStatus
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.models.workspace import SavedQuery
from app.schemas.common import ok
from app.schemas.workspace import SavedQueryIn, SavedQueryOut, SavedQueryUpdate
from app.services.ai import sql_validator
from app.services.audit import audit
from app.services.datasets import tables

router = APIRouter(prefix="/queries", tags=["queries"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_query(db: Session, qid: uuid.UUID) -> SavedQuery:
    q = db.get(SavedQuery, qid)
    if q is None:
        raise AppError("Query not found", "NOT_FOUND", 404)
    return q


def _can_view(q: SavedQuery, user: User) -> bool:
    return q.is_shared or q.created_by == user.id or user.role.value == "admin"


def _can_edit(q: SavedQuery, user: User) -> bool:
    return q.created_by == user.id or user.role.value == "admin"


def _dump(q: SavedQuery) -> dict:
    return SavedQueryOut.model_validate(q).model_dump(by_alias=True)


def _allowed_for_dataset(db: Session, ds: Dataset) -> tuple[set[str], set[str], str | None]:
    version = db.get(DatasetVersion, ds.current_version_id) if ds.current_version_id else None
    if version is None:
        return set(), set(), None
    cols = {c.normalized_name for c in version.columns}
    tables_ = {version.table_name, f"{tables.data_schema(engine)}.{version.table_name}" if tables.data_schema(engine) else version.table_name}
    return tables_, cols, version.table_name


def _validate_user_sql(db: Session, ds: Dataset, sql: str) -> str:
    allowed_tables, allowed_cols, _ = _allowed_for_dataset(db, ds)
    if not allowed_tables:
        raise AppError("Dataset has no data version", "BAD_REQUEST", 400)
    return sql_validator.validate(
        sql,
        allowed_tables=allowed_tables,
        allowed_columns=allowed_cols,
        dialect=sql_validator.dialect_for(engine.dialect.name),
    )


@router.get("")
def list_queries(
    dataset_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    stmt = (
        select(SavedQuery)
        .where(or_(SavedQuery.is_shared.is_(True), SavedQuery.created_by == user.id))
        .order_by(SavedQuery.updated_at.desc())
        .limit(200)
    )
    if dataset_id:
        stmt = stmt.where(SavedQuery.dataset_id == dataset_id)
    return ok([_dump(q) for q in db.scalars(stmt).all()])


@router.post("", status_code=201)
def create_query(
    body: SavedQueryIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    ds = db.get(Dataset, body.dataset_id)
    if ds is None or ds.deleted_at is not None:
        raise AppError("Dataset not found", "NOT_FOUND", 404)
    # SQL must validate against this dataset's schema at save time.
    try:
        safe_sql = _validate_user_sql(db, ds, body.sql)
    except sql_validator.SQLValidationError as e:
        raise AppError(f"Query failed safety validation: {e}", "SQL_BLOCKED", 400) from e

    q = SavedQuery(
        name=body.name.strip(), question=body.question, sql=safe_sql,
        dataset_id=ds.id, version_id=body.version_id or ds.current_version_id,
        created_by=user.id, is_shared=body.is_shared,
    )
    db.add(q)
    db.flush()
    audit(db, user_id=user.id, action="queries.save",
          resource_type="saved_query", resource_id=str(q.id), ip=_client_ip(request))
    db.commit()
    db.refresh(q)
    return ok(_dump(q))


@router.patch("/{query_id}")
def update_query(
    query_id: uuid.UUID,
    body: SavedQueryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    q = _get_query(db, query_id)
    if not _can_edit(q, user):
        raise AppError("Only the owner or an admin can edit this query", "FORBIDDEN", 403)
    if body.sql is not None:
        ds = db.get(Dataset, q.dataset_id)
        try:
            q.sql = _validate_user_sql(db, ds, body.sql)
        except sql_validator.SQLValidationError as e:
            raise AppError(f"Query failed safety validation: {e}", "SQL_BLOCKED", 400) from e
    if body.name is not None:
        q.name = body.name.strip()
    if body.is_shared is not None:
        q.is_shared = body.is_shared
    db.commit()
    return ok(_dump(q))


@router.delete("/{query_id}")
def delete_query(
    query_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    q = _get_query(db, query_id)
    if not _can_edit(q, user):
        raise AppError("Only the owner or an admin can delete this query", "FORBIDDEN", 403)
    db.delete(q)
    audit(db, user_id=user.id, action="queries.delete",
          resource_type="saved_query", resource_id=str(query_id), ip=_client_ip(request))
    db.commit()
    return ok(message="Query deleted")


@router.post("/{query_id}/run")
def run_query(
    query_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Re-validate the stored SQL against the CURRENT schema, execute, log."""
    q = _get_query(db, query_id)
    if not _can_view(q, user):
        raise AppError("Query not found", "NOT_FOUND", 404)
    ds = db.get(Dataset, q.dataset_id)
    if ds is None or ds.deleted_at is not None:
        raise AppError("Dataset not found", "NOT_FOUND", 404)

    try:
        safe_sql = _validate_user_sql(db, ds, q.sql)
    except sql_validator.SQLValidationError as e:
        db.add(QueryHistory(
            user_id=user.id, dataset_id=ds.id, sql=q.sql[:10_000],
            status=QueryStatus.BLOCKED, source=QuerySource.MANUAL,
            error_code="SQL_BLOCKED",
        ))
        db.commit()
        raise AppError(f"Stored query no longer validates: {e}", "SQL_BLOCKED", 400) from e

    t0 = time.perf_counter()
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(sa.text("SET statement_timeout TO '10s'"))
            cursor = conn.exec_driver_sql(safe_sql)
            cols = list(cursor.keys())
            raw = cursor.fetchmany(5000)
    except Exception as e:
        db.add(QueryHistory(
            user_id=user.id, dataset_id=ds.id, sql=safe_sql[:10_000],
            status=QueryStatus.FAILED, source=QuerySource.MANUAL,
            error_code="EXEC_FAILED",
        ))
        db.commit()
        raise AppError("Query execution failed", "EXEC_FAILED", 500) from e

    duration = int((time.perf_counter() - t0) * 1000)
    q.last_run_at = datetime.now(timezone.utc)
    db.add(QueryHistory(
        user_id=user.id, dataset_id=ds.id, sql=safe_sql[:10_000],
        status=QueryStatus.SUCCESS, row_count=len(raw),
        duration_ms=duration, source=QuerySource.MANUAL,
    ))
    db.commit()
    rows = [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in zip(cols, r)}
        for r in raw
    ]
    return ok({"columns": cols, "rows": rows, "rowCount": len(rows), "durationMs": duration})
