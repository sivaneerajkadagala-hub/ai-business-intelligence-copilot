import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.deps import get_current_user, require_analyst
from app.core.errors import AppError
from app.models.analytics import KPI, Dashboard, QueryHistory
from app.models.audit import AuditLog
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.schemas.analytics import KpiIn, KpiOut, KpiUpdate
from app.schemas.common import ok
from app.services.analytics import engine as aengine
from app.services.audit import audit

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_dataset(db: Session, dataset_id: uuid.UUID) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None or ds.deleted_at is not None:
        raise AppError("Dataset not found", "NOT_FOUND", 404)
    return ds


def _current_version(db: Session, ds: Dataset) -> DatasetVersion:
    version = db.get(DatasetVersion, ds.current_version_id) if ds.current_version_id else None
    if version is None:
        raise AppError("Dataset has no data version yet", "BAD_REQUEST", 400)
    return version


def _kpi_or_404(db: Session, kpi_id: uuid.UUID) -> KPI:
    kpi = db.get(KPI, kpi_id)
    if kpi is None:
        raise AppError("KPI not found", "NOT_FOUND", 404)
    return kpi


def _dump(obj) -> dict:
    return KpiOut.model_validate(obj).model_dump(by_alias=True)


# ── Summary & generic aggregations ─────────────────────────────

@router.get("/summary")
def summary(
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    datasets_count = db.scalar(
        select(func.count()).select_from(Dataset).where(Dataset.deleted_at.is_(None))
    ) or 0
    total_records = db.scalar(
        select(func.coalesce(func.sum(Dataset.row_count), 0)).where(
            Dataset.deleted_at.is_(None)
        )
    ) or 0
    dashboards_count = db.scalar(select(func.count()).select_from(Dashboard)) or 0
    queries_executed = db.scalar(select(func.count()).select_from(QueryHistory)) or 0

    kpis = db.scalars(select(KPI).order_by(KPI.created_at).limit(8)).all()
    kpi_items = []
    for k in kpis:
        entry = _dump(k)
        try:
            entry["result"] = aengine.evaluate_kpi(db, engine, k, frm=frm, to=to)
        except AppError:
            entry["result"] = None
        kpi_items.append(entry)

    activity_rows = db.execute(
        select(AuditLog.action, AuditLog.created_at, User.email)
        .join(User, AuditLog.user_id == User.id, isouter=True)
        .order_by(AuditLog.created_at.desc())
        .limit(10)
    ).all()

    return ok(
        {
            "datasetsCount": datasets_count,
            "totalRecords": int(total_records),
            "dashboardsCount": dashboards_count,
            "queriesExecuted": queries_executed,
            "kpis": kpi_items,
            "recentActivity": [
                {
                    "action": a,
                    "at": c.isoformat() if c else None,
                    "actor": e or "system",
                }
                for a, c, e in activity_rows
            ],
        }
    )


@router.get("/series")
def get_series(
    dataset_id: uuid.UUID,
    date_column: str,
    metric_column: str | None = None,
    agg: str = "sum",
    bucket: str = "month",
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    version = _current_version(db, ds)
    data = aengine.series(
        engine, version,
        date_column=date_column, metric_column=metric_column,
        agg=agg, bucket=bucket, frm=frm, to=to,
    )
    return ok({"points": data})


@router.get("/breakdown")
def get_breakdown(
    dataset_id: uuid.UUID,
    dimension: str,
    metric_column: str | None = None,
    agg: str = "sum",
    limit: int = Query(10, ge=1, le=100),
    date_column: str | None = None,
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    version = _current_version(db, ds)
    data = aengine.breakdown(
        engine, version,
        dimension=dimension, metric_column=metric_column,
        agg=agg, limit=limit, frm=frm, to=to, date_column=date_column,
    )
    return ok({"items": data})


# ── KPI CRUD ───────────────────────────────────────────────────

@router.get("/kpis")
def list_kpis(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    rows = db.scalars(select(KPI).order_by(KPI.created_at)).all()
    return ok([_dump(k) for k in rows])


@router.post("/kpis", status_code=201)
def create_kpi(
    body: KpiIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    _get_dataset(db, body.dataset_id)
    kpi = KPI(
        name=body.name.strip(),
        description=body.description,
        dataset_id=body.dataset_id,
        formula=body.formula.model_dump(by_alias=True, exclude_none=True),
        target=body.target,
        unit=body.unit,
        created_by=user.id,
    )
    db.add(kpi)
    db.flush()
    audit(db, user_id=user.id, action="kpis.create", resource_type="kpi",
          resource_id=str(kpi.id), meta={"name": kpi.name}, ip=_client_ip(request))
    db.commit()
    db.refresh(kpi)
    return ok(_dump(kpi))


@router.get("/kpis/{kpi_id}/value")
def kpi_value(
    kpi_id: uuid.UUID,
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    kpi = _kpi_or_404(db, kpi_id)
    return ok(aengine.evaluate_kpi(db, engine, kpi, frm=frm, to=to))


@router.patch("/kpis/{kpi_id}")
def update_kpi(
    kpi_id: uuid.UUID,
    body: KpiUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    kpi = _kpi_or_404(db, kpi_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "description", "target", "unit"):
        if field in changes:
            setattr(kpi, field, changes[field])
    if "formula" in changes and body.formula:
        kpi.formula = body.formula.model_dump(by_alias=True, exclude_none=True)
    audit(db, user_id=user.id, action="kpis.update", resource_type="kpi",
          resource_id=str(kpi.id), ip=_client_ip(request))
    db.commit()
    db.refresh(kpi)
    return ok(_dump(kpi))


@router.delete("/kpis/{kpi_id}")
def delete_kpi(
    kpi_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    kpi = _kpi_or_404(db, kpi_id)
    db.delete(kpi)
    audit(db, user_id=user.id, action="kpis.delete", resource_type="kpi",
          resource_id=str(kpi_id), ip=_client_ip(request))
    db.commit()
    return ok(message="KPI deleted")
