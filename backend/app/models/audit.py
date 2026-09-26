import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """Append-only audit trail. Rows are never updated or deleted."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(sa.String(100), index=True)
    resource_type: Mapped[str | None] = mapped_column(sa.String(50))
    resource_id: Mapped[str | None] = mapped_column(sa.String(64))
    meta: Mapped[dict | None] = mapped_column(
        "metadata",
        sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
    )
    ip: Mapped[str | None] = mapped_column(sa.String(45))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), index=True
    )
