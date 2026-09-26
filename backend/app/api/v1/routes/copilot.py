import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.models.copilot import AIConversation, AIMessage, MessageRole
from app.models.dataset import Dataset, DatasetStatus, DatasetVersion
from app.models.user import User
from app.schemas.common import ok
from app.schemas.copilot import (
    ChatIn,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from app.services.ai import copilot
from app.services.audit import audit

router = APIRouter(prefix="/copilot", tags=["copilot"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_conversation(db: Session, conv_id: uuid.UUID, user: User) -> AIConversation:
    conv = db.get(AIConversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise AppError("Conversation not found", "NOT_FOUND", 404)
    return conv


def _dump(model, obj) -> dict:
    return model.model_validate(obj).model_dump(by_alias=True)


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rows = db.scalars(
        select(AIConversation)
        .where(AIConversation.user_id == user.id)
        .order_by(AIConversation.updated_at.desc())
        .limit(50)
    ).all()
    return ok([_dump(ConversationOut, c) for c in rows])


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    conv = _get_conversation(db, conversation_id, user)
    data = _dump(ConversationDetail, conv)
    data["messages"] = [_dump(MessageOut, m) for m in conv.messages]
    return ok(data)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    conv = _get_conversation(db, conversation_id, user)
    db.delete(conv)
    audit(db, user_id=user.id, action="copilot.conversation.delete",
          resource_type="conversation", resource_id=str(conversation_id),
          ip=_client_ip(request))
    db.commit()
    return ok(message="Conversation deleted")


@router.post("/chat")
def chat(
    body: ChatIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ds = db.get(Dataset, body.dataset_id)
    if ds is None or ds.deleted_at is not None:
        raise AppError("Dataset not found", "NOT_FOUND", 404)
    if ds.status != DatasetStatus.READY:
        raise AppError("Dataset is not ready for queries", "BAD_REQUEST", 400)
    version = db.get(DatasetVersion, ds.current_version_id) if ds.current_version_id else None
    if version is None:
        raise AppError("Dataset has no data version", "BAD_REQUEST", 400)

    if body.conversation_id:
        conv = _get_conversation(db, body.conversation_id, user)
    else:
        conv = AIConversation(
            user_id=user.id,
            title=body.question[:80],
            dataset_id=ds.id,
        )
        db.add(conv)
        db.flush()

    db.add(
        AIMessage(
            conversation_id=conv.id,
            role=MessageRole.USER,
            content=body.question,
        )
    )
    db.flush()

    answer = copilot.answer_question(
        db, engine,
        user=user, question=body.question, dataset=ds, version=version,
        ip=_client_ip(request),
    )

    msg = AIMessage(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=answer["content"],
        sql=answer.get("sql"),
        result_snapshot=answer.get("result"),
        chart_spec=answer.get("chart"),
        explanation=answer.get("explanation"),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return ok(
        {
            "conversationId": str(conv.id),
            "message": _dump(MessageOut, msg),
            "engine": answer.get("engine"),
        }
    )
