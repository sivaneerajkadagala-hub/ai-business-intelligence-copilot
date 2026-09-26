"""dashboard_widgets, saved_queries, reports

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

report_format = postgresql.ENUM("pdf", "csv", name="report_format")
report_status = postgresql.ENUM("generating", "ready", "failed", name="report_status")


def upgrade() -> None:
    bind = op.get_bind()
    report_format.create(bind)
    report_status.create(bind)

    op.create_table(
        "dashboard_widgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("position", postgresql.JSONB(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_dashboard_widgets_dashboard_id", "dashboard_widgets", ["dashboard_id"]
    )

    op.create_table(
        "saved_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("question", sa.Text()),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_saved_queries_dataset_id", "saved_queries", ["dataset_id"])

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("format", report_format, nullable=False),
        sa.Column("status", report_status, nullable=False, server_default="generating"),
        sa.Column("file_path", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_reports_owner_id", "reports", ["owner_id"])


def downgrade() -> None:
    for ix, table in [
        ("ix_reports_owner_id", "reports"),
        ("ix_saved_queries_dataset_id", "saved_queries"),
        ("ix_dashboard_widgets_dashboard_id", "dashboard_widgets"),
    ]:
        op.drop_index(ix, table_name=table)
    for table in ("reports", "saved_queries", "dashboard_widgets"):
        op.drop_table(table)
    bind = op.get_bind()
    report_status.drop(bind)
    report_format.drop(bind)
