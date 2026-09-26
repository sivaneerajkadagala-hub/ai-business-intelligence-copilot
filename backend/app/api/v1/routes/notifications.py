import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.security import utcnow
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import ok

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _dump(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "readAt": n.read_at.isoformat() if n.read_at else None,
        "createdAt": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("")
def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return ok([_dump(n) for n in db.scalars(stmt).all()])


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    count = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ) or 0
    return ok({"count": count})


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise AppError("Notification not found", "NOT_FOUND", 404)
    n.read_at = utcnow()
    db.commit()
    return ok(message="Marked read")


@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    db.execute(
        sa.update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    return ok(message="All marked read")
