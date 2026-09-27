"""analytics tables: kpis, dashboards, query_history

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

query_status = postgresql.ENUM("success", "failed", "blocked", name="query_status", create_type=False)
query_source = postgresql.ENUM("copilot", "manual", "widget", name="query_source", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    query_status.create(bind)
    query_source.create(bind)

    op.create_table(
        "kpis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("formula", postgresql.JSONB(), nullable=False),
        sa.Column("target", sa.Float()),
        sa.Column("unit", sa.String(30)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_kpis_dataset_id", "kpis", ["dataset_id"])

    op.create_table(
        "dashboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dashboards_owner_id", "dashboards", ["owner_id"])

    op.create_table(
        "query_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="SET NULL")),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("status", query_status, nullable=False),
        sa.Column("row_count", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("source", query_source, nullable=False, server_default="manual"),
        sa.Column("error_code", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_query_history_user_id", "query_history", ["user_id"])
    op.create_index("ix_query_history_created_at", "query_history", ["created_at"])


def downgrade() -> None:
    for ix, table in [
        ("ix_query_history_created_at", "query_history"),
        ("ix_query_history_user_id", "query_history"),
        ("ix_dashboards_owner_id", "dashboards"),
        ("ix_kpis_dataset_id", "kpis"),
    ]:
        op.drop_index(ix, table_name=table)
    for table in ("query_history", "dashboards", "kpis"):
        op.drop_table(table)
    bind = op.get_bind()
    query_source.drop(bind)
    query_status.drop(bind)
