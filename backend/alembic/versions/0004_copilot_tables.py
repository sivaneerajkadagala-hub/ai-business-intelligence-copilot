"""copilot tables: ai_conversations, ai_messages, insights

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

message_role = postgresql.ENUM("user", "assistant", "system", name="message_role")
insight_type = postgresql.ENUM(
    "trend", "anomaly", "comparison", "ranking", "forecast", name="insight_type"
)
insight_severity = postgresql.ENUM("info", "warning", "critical", name="insight_severity")


def upgrade() -> None:
    bind = op.get_bind()
    for e in (message_role, insight_type, insight_severity):
        e.create(bind)

    op.create_table(
        "ai_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_conversations_user_id", "ai_conversations", ["user_id"])

    op.create_table(
        "ai_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sql", sa.Text()),
        sa.Column("result_snapshot", postgresql.JSONB()),
        sa.Column("chart_spec", postgresql.JSONB()),
        sa.Column("explanation", sa.Text()),
        sa.Column("tokens_used", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_messages_conversation_id", "ai_messages", ["conversation_id"])
    op.create_index("ix_ai_messages_created_at", "ai_messages", ["created_at"])

    op.create_table(
        "insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", insight_type, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", insight_severity, nullable=False,
                  server_default="info"),
        sa.Column("evidence", postgresql.JSONB()),
        sa.Column("generated_by", sa.String(20), nullable=False,
                  server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_insights_dataset_id", "insights", ["dataset_id"])
    op.create_index("ix_insights_type", "insights", ["type"])


def downgrade() -> None:
    for ix, table in [
        ("ix_insights_type", "insights"),
        ("ix_insights_dataset_id", "insights"),
        ("ix_ai_messages_created_at", "ai_messages"),
        ("ix_ai_messages_conversation_id", "ai_messages"),
        ("ix_ai_conversations_user_id", "ai_conversations"),
    ]:
        op.drop_index(ix, table_name=table)
    for table in ("insights", "ai_messages", "ai_conversations"):
        op.drop_table(table)
    bind = op.get_bind()
    for e in (insight_severity, insight_type, message_role):
        e.drop(bind)
