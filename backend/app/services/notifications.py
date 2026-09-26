"""In-app notifications — emitted by ingest, reports, insights."""

import uuid

from sqlalchemy.orm import Session

from app.models.notification import Notification


def notify(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> None:
    if user_id is None:
        return
    db.add(
        Notification(
            user_id=user_id, type=type, title=title[:200],
            body=body, link=link,
        )
    )
