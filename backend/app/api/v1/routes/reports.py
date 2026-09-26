import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import engine, get_db
from app.core.deps import get_current_user, require_analyst
from app.core.errors import AppError
from app.models.analytics import KPI
from app.models.copilot import Insight
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.models.workspace import Report, ReportFormat, ReportStatus
from app.schemas.common import ok
from app.schemas.workspace import ReportIn, ReportOut
from app.services.analytics import engine as aengine
from app.services.audit import audit
from app.services.notifications import notify
from app.services.reports import export

settings = get_settings()
router = APIRouter(tags=["reports"])

# Reports persist under UPLOAD_DIR so Docker's uploads volume covers them.
REPORTS_DIR = Path(settings.UPLOAD_DIR) / "reports"


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


@router.get("/datasets/{dataset_id}/export.csv")
def export_dataset_csv(
    dataset_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> StreamingResponse:
    ds = _get_dataset(db, dataset_id)
    version = _current_version(db, ds)
    audit(db, user_id=user.id, action="datasets.export_csv",
          resource_type="dataset", resource_id=str(ds.id), ip=_client_ip(request))
    db.commit()
    filename = f"{ds.name.replace(' ', '_')}_v{version.version_no}.csv"
    return StreamingResponse(
        export.export_csv(engine, version),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports")
def list_reports(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    stmt = select(Report).order_by(Report.created_at.desc()).limit(100)
    if user.role.value != "admin":
        stmt = stmt.where(Report.owner_id == user.id)
    return ok(
        [
            ReportOut.model_validate(r).model_dump(by_alias=True)
            for r in db.scalars(stmt).all()
        ]
    )


@router.post("/reports/generate", status_code=201)
def generate_report(
    body: ReportIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    ds = _get_dataset(db, body.dataset_id)
    version = _current_version(db, ds)
    name = body.name or f"{ds.name} report"
    report = Report(
        name=name[:200], owner_id=user.id,
        config={"datasetId": str(ds.id), "versionId": str(version.id)},
        format=ReportFormat(body.format), status=ReportStatus.GENERATING,
    )
    db.add(report)
    db.flush()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if report.format == ReportFormat.PDF:
            # KPI values for this dataset.
            kpis = []
            for k in db.scalars(select(KPI).where(KPI.dataset_id == ds.id).limit(6)):
                try:
                    res = aengine.evaluate_kpi(db, engine, k, frm=None, to=None)
                    kpis.append(f"{k.name}: {res['value']:,.0f} {k.unit or ''}")
                except AppError:
                    continue
            ins = db.scalars(
                select(Insight).where(Insight.dataset_id == ds.id)
                .order_by(Insight.created_at.desc()).limit(10)
            ).all()
            data = export.build_pdf_report(
                engine, dataset=ds, version=version, kpis=kpis,
                insights=ins, generated_by=user.email,
            )
            path = REPORTS_DIR / f"{report.id}.pdf"
            path.write_bytes(data)
        else:
            path = REPORTS_DIR / f"{report.id}.csv"
            with path.open("w", encoding="utf-8", newline="") as f:
                for chunk in export.export_csv(engine, version):
                    f.write(chunk)

        report.file_path = str(path)
        report.status = ReportStatus.READY
    except Exception:
        report.status = ReportStatus.FAILED
        db.commit()
        raise

    notify(
        db, user_id=user.id, type="report.ready",
        title=f'Report "{report.name}" is ready',
        body=f"{report.format.value.upper()} export of {ds.name}",
        link="/reports",
    )

    audit(db, user_id=user.id, action="reports.generate",
          resource_type="report", resource_id=str(report.id),
          meta={"format": report.format.value}, ip=_client_ip(request))
    db.commit()
    db.refresh(report)
    return ok(ReportOut.model_validate(report).model_dump(by_alias=True))


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    report = db.get(Report, report_id)
    if report is None or (
        report.owner_id != user.id and user.role.value != "admin"
    ):
        raise AppError("Report not found", "NOT_FOUND", 404)
    if report.status != ReportStatus.READY or not report.file_path:
        raise AppError("Report is not ready", "BAD_REQUEST", 400)
    path = Path(report.file_path)
    if not path.exists():
        raise AppError("Report file is missing", "NOT_FOUND", 404)
    media = "application/pdf" if report.format == ReportFormat.PDF else "text/csv"
    return FileResponse(path, media_type=media, filename=f"{report.name}.{report.format.value}")
