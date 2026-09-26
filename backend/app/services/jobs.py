"""Tiny in-process job runner for async ingestion.

A ThreadPoolExecutor keeps uploads non-blocking without an external
broker — sufficient for this app's scale; swap for Celery/RQ + Redis if
multi-replica deployments need shared queues."""

import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.models.dataset import Dataset, DatasetImport
from app.models.user import User
from app.services.datasets import ingest

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingest")


def submit_import(dataset_id: uuid.UUID, user_id: uuid.UUID, ip: str | None) -> None:
    _executor.submit(_run_import, dataset_id, user_id, ip)


def _run_import(dataset_id: uuid.UUID, user_id: uuid.UUID, ip: str | None) -> None:
    db = SessionLocal()
    try:
        dataset = db.get(Dataset, dataset_id)
        user = db.get(User, user_id)
        import_record = db.scalar(
            select(DatasetImport)
            .where(DatasetImport.dataset_id == dataset_id)
            .order_by(DatasetImport.started_at.desc())
            .limit(1)
        )
        if dataset is None or user is None or import_record is None:
            return
        ingest.process_import(
            db, engine, dataset=dataset, import_record=import_record,
            user=user, ip=ip,
        )
    finally:
        db.close()
