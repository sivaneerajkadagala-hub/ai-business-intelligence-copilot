import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.user import CamelModel


class ConversationOut(CamelModel):
    id: uuid.UUID
    title: str
    dataset_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MessageOut(CamelModel):
    id: uuid.UUID
    role: str
    content: str
    sql: str | None
    result_snapshot: dict | None
    chart_spec: dict | None
    explanation: str | None
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ChatIn(CamelModel):
    question: str = Field(min_length=2, max_length=1000)
    dataset_id: uuid.UUID
    conversation_id: uuid.UUID | None = None


class ChatOut(CamelModel):
    conversation_id: uuid.UUID
    message: MessageOut
    engine: str | None = None
