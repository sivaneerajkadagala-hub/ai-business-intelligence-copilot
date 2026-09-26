import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.user import CamelModel


class WidgetIn(CamelModel):
    type: str = Field(pattern="^(kpi|line|bar|pie|table|number)$")
    title: str = Field(min_length=1, max_length=200)
    config: dict = Field(default_factory=dict)
    position: dict


class WidgetOut(CamelModel):
    id: uuid.UUID
    type: str
    title: str
    config: dict
    position: dict
    sort_order: int


class DashboardIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    is_shared: bool = True


class DashboardUpdate(CamelModel):
    name: str | None = None
    description: str | None = None
    is_shared: bool | None = None


class DashboardOut(CamelModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    is_shared: bool
    created_at: datetime
    updated_at: datetime


class DashboardDetail(DashboardOut):
    widgets: list[WidgetOut]


class WidgetsSave(CamelModel):
    widgets: list[WidgetIn]


class SavedQueryIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    sql: str = Field(min_length=1)
    question: str | None = None
    dataset_id: uuid.UUID
    version_id: uuid.UUID | None = None
    is_shared: bool = False


class SavedQueryUpdate(CamelModel):
    name: str | None = None
    sql: str | None = None
    is_shared: bool | None = None


class SavedQueryOut(CamelModel):
    id: uuid.UUID
    name: str
    question: str | None
    sql: str
    dataset_id: uuid.UUID
    created_by: uuid.UUID | None
    is_shared: bool
    last_run_at: datetime | None
    created_at: datetime


class ReportIn(CamelModel):
    name: str | None = None
    dataset_id: uuid.UUID
    format: str = Field(pattern="^(pdf|csv)$")


class ReportOut(CamelModel):
    id: uuid.UUID
    name: str
    format: str
    status: str
    created_at: datetime
