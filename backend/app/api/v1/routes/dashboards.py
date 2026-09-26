import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_analyst
from app.core.errors import AppError
from app.models.analytics import Dashboard
from app.models.user import User
from app.models.workspace import DashboardWidget
from app.schemas.common import ok
from app.schemas.workspace import (
    DashboardDetail,
    DashboardIn,
    DashboardOut,
    DashboardUpdate,
    WidgetOut,
    WidgetsSave,
)
from app.services.audit import audit

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_dashboard(db: Session, dash_id: uuid.UUID) -> Dashboard:
    d = db.get(Dashboard, dash_id)
    if d is None:
        raise AppError("Dashboard not found", "NOT_FOUND", 404)
    return d


def _can_view(d: Dashboard, user: User) -> bool:
    return d.is_shared or d.owner_id == user.id or user.role.value == "admin"


def _can_edit(d: Dashboard, user: User) -> bool:
    return d.owner_id == user.id or user.role.value == "admin"


def _dump(model, obj) -> dict:
    return model.model_validate(obj).model_dump(by_alias=True)


@router.get("")
def list_dashboards(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rows = db.scalars(
        select(Dashboard)
        .where(or_(Dashboard.is_shared.is_(True), Dashboard.owner_id == user.id))
        .order_by(Dashboard.updated_at.desc())
    ).all()
    return ok([_dump(DashboardOut, d) for d in rows])


@router.post("", status_code=201)
def create_dashboard(
    body: DashboardIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    d = Dashboard(
        owner_id=user.id, name=body.name.strip(),
        description=body.description, is_shared=body.is_shared,
    )
    db.add(d)
    db.flush()
    audit(db, user_id=user.id, action="dashboards.create",
          resource_type="dashboard", resource_id=str(d.id), ip=_client_ip(request))
    db.commit()
    db.refresh(d)
    return ok(_dump(DashboardOut, d))


@router.get("/{dashboard_id}")
def get_dashboard(
    dashboard_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    d = _get_dashboard(db, dashboard_id)
    if not _can_view(d, user):
        raise AppError("Dashboard not found", "NOT_FOUND", 404)
    data = _dump(DashboardDetail, d)
    data["widgets"] = [_dump(WidgetOut, w) for w in d.widgets]
    return ok(data)


@router.patch("/{dashboard_id}")
def update_dashboard(
    dashboard_id: uuid.UUID,
    body: DashboardUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    d = _get_dashboard(db, dashboard_id)
    if not _can_edit(d, user):
        raise AppError("Only the owner or an admin can edit this dashboard", "FORBIDDEN", 403)
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(d, f, v)
    audit(db, user_id=user.id, action="dashboards.update",
          resource_type="dashboard", resource_id=str(d.id), ip=_client_ip(request))
    db.commit()
    return ok(_dump(DashboardOut, d))


@router.delete("/{dashboard_id}")
def delete_dashboard(
    dashboard_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    d = _get_dashboard(db, dashboard_id)
    if not _can_edit(d, user):
        raise AppError("Only the owner or an admin can delete this dashboard", "FORBIDDEN", 403)
    db.delete(d)
    audit(db, user_id=user.id, action="dashboards.delete",
          resource_type="dashboard", resource_id=str(d.id), ip=_client_ip(request))
    db.commit()
    return ok(message="Dashboard deleted")


@router.put("/{dashboard_id}/widgets")
def save_widgets(
    dashboard_id: uuid.UUID,
    body: WidgetsSave,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    """Replace-all save of the dashboard's widget layout."""
    d = _get_dashboard(db, dashboard_id)
    if not _can_edit(d, user):
        raise AppError("Only the owner or an admin can edit this dashboard", "FORBIDDEN", 403)
    for w in list(d.widgets):
        db.delete(w)
    for i, w in enumerate(body.widgets):
        db.add(
            DashboardWidget(
                dashboard_id=d.id, type=w.type, title=w.title,
                config=w.config, position=w.position, sort_order=i,
            )
        )
    audit(db, user_id=user.id, action="dashboards.widgets.save",
          resource_type="dashboard", resource_id=str(d.id),
          meta={"count": len(body.widgets)}, ip=_client_ip(request))
    db.commit()
    db.refresh(d)
    return ok([_dump(WidgetOut, w) for w in d.widgets])


@router.post("/{dashboard_id}/duplicate", status_code=201)
def duplicate_dashboard(
    dashboard_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    d = _get_dashboard(db, dashboard_id)
    if not _can_view(d, user):
        raise AppError("Dashboard not found", "NOT_FOUND", 404)
    copy = Dashboard(
        owner_id=user.id,
        name=f"{d.name} (copy)"[:200],
        description=d.description,
        is_shared=False,
    )
    db.add(copy)
    db.flush()
    for w in d.widgets:
        db.add(
            DashboardWidget(
                dashboard_id=copy.id, type=w.type, title=w.title,
                config=w.config, position=w.position, sort_order=w.sort_order,
            )
        )
    audit(db, user_id=user.id, action="dashboards.duplicate",
          resource_type="dashboard", resource_id=str(copy.id), ip=_client_ip(request))
    db.commit()
    return ok(_dump(DashboardOut, copy))
