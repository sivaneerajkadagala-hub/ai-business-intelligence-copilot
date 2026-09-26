from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine
from app.schemas.common import ok

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    db_status = "up"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"

    settings = get_settings()
    return ok(
        {
            "status": "ok",
            "version": "0.1.0",
            "database": db_status,
            "demoMode": settings.is_demo_mode,
        }
    )
