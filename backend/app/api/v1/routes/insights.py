import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.deps import get_current_user, require_analyst
from app.core.errors import AppError
from app.models.analytics import Forecast
from app.models.copilot import Insight
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.schemas.common import ok
from app.services.ai import anomalies, forecast, insights as insight_service
from app.services.analytics import engine as aengine
from app.services.audit import audit
from app.schemas.user import CamelModel
from pydantic import Field

router = APIRouter(prefix="/insights", tags=["insights"])


class ForecastIn(CamelModel):
    dataset_id: uuid.UUID
    date_column: str
    metric_column: str
    bucket: str = Field(default="month", pattern="^(day|week|month|quarter|year)$")
    horizon: int = Field(default=6, ge=1, le=36)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_dataset(db: Session, dataset_id: uuid.UUID) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None or ds.deleted_at is not None:
        raise AppError("Dataset not found", "NOT_FOUND", 404)
    return ds


def _current_version(db: Session, ds: Dataset) -> DatasetVersion:
    v = db.get(DatasetVersion, ds.current_version_id) if ds.current_version_id else None
    if v is None:
        raise AppError("Dataset has no data version", "BAD_REQUEST", 400)
    return v


def _dump(ins: Insight) -> dict:
    return {
        "id": str(ins.id),
        "type": ins.type.value,
        "title": ins.title,
        "body": ins.body,
        "severity": ins.severity.value,
        "evidence": ins.evidence,
        "generatedBy": ins.generated_by,
        "createdAt": ins.created_at.isoformat() if ins.created_at else None,
    }


@router.get("")
def list_insights(
    dataset_id: uuid.UUID | None = None,
    type: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    stmt = select(Insight).order_by(Insight.created_at.desc()).limit(100)
    if dataset_id:
        stmt = stmt.where(Insight.dataset_id == dataset_id)
    if type:
        stmt = stmt.where(Insight.type == type)
    return ok([_dump(i) for i in db.scalars(stmt).all()])


@router.post("/generate")
def generate_insights(
    request: Request,
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    version = _current_version(db, ds)
    created = insight_service.generate(
        db, engine, dataset=ds, version=version, user=user, ip=_client_ip(request)
    )
    return ok([_dump(i) for i in created])


@router.get("/anomalies")
def get_anomalies(
    dataset_id: uuid.UUID,
    date_column: str,
    metric_column: str,
    bucket: str = Query("day", pattern="^(day|week|month)$"),
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, dataset_id)
    version = _current_version(db, ds)
    return ok(
        anomalies.detect(
            engine, version, date_column=date_column,
            metric_column=metric_column, bucket=bucket, frm=frm, to=to,
        )
    )


@router.post("/forecast")
def create_forecast(
    body: ForecastIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ds = _get_dataset(db, body.dataset_id)
    version = _current_version(db, ds)
    points = aengine.series(
        engine, version, date_column=body.date_column,
        metric_column=body.metric_column, agg="sum",
        bucket=body.bucket, frm=None, to=None,
    )
    try:
        result = forecast.forecast(points, horizon=body.horizon, bucket=body.bucket)
    except ValueError as e:
        raise AppError(str(e), "BAD_REQUEST", 400) from e

    row = Forecast(
        dataset_id=ds.id,
        date_column=body.date_column,
        metric_column=body.metric_column,
        method=result["method"],
        horizon=body.horizon,
        result={"history": points[-60:], **result},
        created_by=user.id,
    )
    db.add(row)
    audit(db, user_id=user.id, action="analytics.forecast",
          resource_type="dataset", resource_id=str(ds.id),
          meta={"method": result["method"], "horizon": body.horizon},
          ip=_client_ip(request))
    db.commit()
    return ok(
        {
            "id": str(row.id),
            "method": result["method"],
            "history": points[-60:],
            "forecast": result["points"],
        }
    )
