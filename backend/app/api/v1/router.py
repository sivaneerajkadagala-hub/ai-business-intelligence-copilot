from fastapi import APIRouter

from app.api.v1.routes import (
    analytics,
    auth,
    copilot,
    datasets,
    health,
    insights,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(datasets.router)
api_router.include_router(analytics.router)
api_router.include_router(copilot.router)
api_router.include_router(insights.router)
