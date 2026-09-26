import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

jsonb = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class QuerySource(str, enum.Enum):
    COPILOT = "copilot"
    MANUAL = "manual"
    WIDGET = "widget"


class QueryStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


class KPI(Base):
    __tablename__ = "kpis"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str | None] = mapped_column(sa.Text)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    # formula: {aggregation, column, dateColumn?, filters?: [{column, op, value}]}
    formula: Mapped[dict] = mapped_column(jsonb)
    target: Mapped[float | None] = mapped_column(sa.Float)
    unit: Mapped[str | None] = mapped_column(sa.String(30))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class Dashboard(Base):
    """Dashboard shell — widgets arrive in Phase 7."""

    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str | None] = mapped_column(sa.Text)
    is_shared: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class QueryHistory(Base):
    __tablename__ = "query_history"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("datasets.id", ondelete="SET NULL")
    )
    sql: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[QueryStatus] = mapped_column(
        sa.Enum(QueryStatus, name="query_status", values_callable=lambda e: [m.value for m in e]),
    )
    row_count: Mapped[int | None] = mapped_column(sa.Integer)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    source: Mapped[QuerySource] = mapped_column(
        sa.Enum(QuerySource, name="query_source", values_callable=lambda e: [m.value for m in e]),
        default=QuerySource.MANUAL,
    )
    error_code: Mapped[str | None] = mapped_column(sa.String(50))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), index=True
    )
