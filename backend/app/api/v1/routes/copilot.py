import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.deps import get_current_user, require_analyst
from app.core.errors import AppError
from app.models.analytics import Dashboard
from app.models.copilot import AIConversation, AIMessage, MessageRole
from app.models.dataset import Dataset, DatasetStatus, DatasetVersion
from app.models.user import User
from app.models.workspace import DashboardWidget
from app.schemas.common import ok
from app.schemas.copilot import (
    ChatIn,
    ConversationDetail,
    ConversationOut,
    MessageOut,
    PinIn,
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

    # Multi-turn context: the previous user question in this conversation
    # lets follow-ups like "and by category" inherit the metric/dataset scope.
    prior_q = db.scalar(
        select(AIMessage.content)
        .where(
            AIMessage.conversation_id == conv.id,
            AIMessage.role == MessageRole.USER,
        )
        .order_by(AIMessage.created_at.desc())
        .limit(1)
    )

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
        ip=_client_ip(request), prior_question=prior_q,
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


@router.post("/messages/{message_id}/pin", status_code=201)
def pin_message_to_dashboard(
    message_id: uuid.UUID,
    body: PinIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_analyst),
) -> dict:
    """Turn a copilot answer's chart into a dashboard widget."""
    msg = db.get(AIMessage, message_id)
    if msg is None:
        raise AppError("Message not found", "NOT_FOUND", 404)
    conv = db.get(AIConversation, msg.conversation_id)
    if conv is None or conv.user_id != user.id:
        raise AppError("Message not found", "NOT_FOUND", 404)
    dash = db.get(Dashboard, body.dashboard_id)
    if dash is None or (dash.owner_id != user.id and user.role.value != "admin"):
        raise AppError("Dashboard not found or not editable", "NOT_FOUND", 404)

    snap = msg.result_snapshot or {}
    meta = snap.get("meta") or {}
    intent = meta.get("intent")
    if not intent or intent not in ("trend", "ranking", "breakdown", "comparison"):
        raise AppError(
            "This answer can't be pinned — only trend/breakdown charts are supported",
            "BAD_REQUEST", 400,
        )

    ds_id = conv.dataset_id
    if intent == "trend":
        wtype, config = "line", {
            "datasetId": str(ds_id), "dateColumn": meta.get("dateCol"),
            "metricColumn": meta.get("metric"), "agg": meta.get("agg") or "sum",
            "bucket": meta.get("bucket") or "month",
        }
    else:
        wtype, config = "bar", {
            "datasetId": str(ds_id), "dimension": meta.get("dim"),
            "metricColumn": meta.get("metric"), "agg": meta.get("agg") or "sum",
        }
    needed = ["metricColumn", "dateColumn"] if wtype == "line" else ["metricColumn", "dimension"]
    if any(not config.get(k) for k in needed):
        raise AppError("Not enough metadata to rebuild this chart as a widget", "BAD_REQUEST", 400)

    y_max = max((w.position.get("y", 0) + w.position.get("h", 4) for w in dash.widgets), default=0)
    widget = DashboardWidget(
        dashboard_id=dash.id, type=wtype,
        title=(msg.content or "Copilot answer")[:200],
        config=config, position={"x": 0, "y": y_max, "w": 6, "h": 4},
        sort_order=len(dash.widgets),
    )
    db.add(widget)
    audit(db, user_id=user.id, action="dashboards.widget.pin",
          resource_type="dashboard", resource_id=str(dash.id),
          meta={"messageId": str(message_id)}, ip=_client_ip(request))
    db.commit()
    return ok({"dashboardId": str(dash.id), "dashboardName": dash.name})
