import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

jsonb = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class WidgetType(str, enum.Enum):
    KPI = "kpi"
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    TABLE = "table"
    NUMBER = "number"


class ReportFormat(str, enum.Enum):
    PDF = "pdf"
    CSV = "csv"


class ReportStatus(str, enum.Enum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(sa.String(20))
    title: Mapped[str] = mapped_column(sa.String(200))
    # config: {datasetId, dateColumn?, metricColumn?, dimension?, agg, bucket, kpiId?}
    config: Mapped[dict] = mapped_column(jsonb)
    # position: {x, y, w, h} on a 12-col grid
    position: Mapped[dict] = mapped_column(jsonb)
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0)

    dashboard: Mapped["Dashboard"] = relationship(back_populates="widgets")


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200))
    question: Mapped[str | None] = mapped_column(sa.Text)
    sql: Mapped[str] = mapped_column(sa.Text)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    is_shared: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200))
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    config: Mapped[dict] = mapped_column(jsonb)
    format: Mapped[ReportFormat] = mapped_column(
        sa.Enum(ReportFormat, name="report_format", values_callable=lambda e: [m.value for m in e])
    )
    status: Mapped[ReportStatus] = mapped_column(
        sa.Enum(ReportStatus, name="report_status", values_callable=lambda e: [m.value for m in e]),
        default=ReportStatus.GENERATING,
    )
    file_path: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
