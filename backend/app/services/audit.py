import uuid

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def audit(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    meta: dict | None = None,
    ip: str | None = None,
) -> None:
    """Append an audit-log row. Caller commits."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            meta=meta,
            ip=ip,
        )
    )
