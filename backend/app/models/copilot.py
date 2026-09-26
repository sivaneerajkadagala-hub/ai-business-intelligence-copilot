import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

jsonb = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class InsightType(str, enum.Enum):
    TREND = "trend"
    ANOMALY = "anomaly"
    COMPARISON = "comparison"
    RANKING = "ranking"
    FORECAST = "forecast"


class InsightSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(sa.String(200))
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("datasets.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )

    messages: Mapped[list["AIMessage"]] = relationship(
        back_populates="conversation", order_by="AIMessage.created_at",
        cascade="all, delete-orphan",
    )


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        sa.Enum(MessageRole, name="message_role", values_callable=lambda e: [m.value for m in e])
    )
    content: Mapped[str] = mapped_column(sa.Text)
    sql: Mapped[str | None] = mapped_column(sa.Text)
    result_snapshot: Mapped[dict | None] = mapped_column(jsonb)
    chart_spec: Mapped[dict | None] = mapped_column(jsonb)
    explanation: Mapped[str | None] = mapped_column(sa.Text)
    tokens_used: Mapped[int | None] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), index=True
    )

    conversation: Mapped[AIConversation] = relationship(back_populates="messages")


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[InsightType] = mapped_column(
        sa.Enum(InsightType, name="insight_type", values_callable=lambda e: [m.value for m in e]),
        index=True,
    )
    title: Mapped[str] = mapped_column(sa.String(300))
    body: Mapped[str] = mapped_column(sa.Text)
    severity: Mapped[InsightSeverity] = mapped_column(
        sa.Enum(InsightSeverity, name="insight_severity", values_callable=lambda e: [m.value for m in e]),
        default=InsightSeverity.INFO,
    )
    evidence: Mapped[dict | None] = mapped_column(jsonb)
    generated_by: Mapped[str] = mapped_column(sa.String(20), default="system")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
