import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.common import ok

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
def list_audit_logs(
    action: str | None = None,
    user_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    stmt = select(AuditLog, User.email).outerjoin(
        User, User.id == AuditLog.user_id
    )
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)

    total = db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0
    rows = db.execute(
        stmt.order_by(AuditLog.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()

    return ok(
        {
            "items": [
                {
                    "id": str(log.id),
                    "userId": str(log.user_id) if log.user_id else None,
                    "actor": email,
                    "action": log.action,
                    "resourceType": log.resource_type,
                    "resourceId": log.resource_id,
                    "meta": log.meta,
                    "ip": log.ip,
                    "createdAt": log.created_at.isoformat() if log.created_at else None,
                }
                for log, email in rows
            ],
            "total": total,
            "page": page,
            "pages": max(1, -(-total // page_size)),
        }
    )
