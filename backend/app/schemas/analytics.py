import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.user import CamelModel


class KpiFilter(CamelModel):
    column: str
    op: str = Field(pattern="^(eq|ne|gt|gte|lt|lte|contains)$")
    value: Any


class KpiFormula(CamelModel):
    aggregation: str = Field(pattern="^(sum|avg|count|count_distinct|min|max)$")
    column: str | None = None
    date_column: str | None = None
    filters: list[KpiFilter] | None = None


class KpiIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    dataset_id: uuid.UUID
    formula: KpiFormula
    target: float | None = None
    unit: str | None = Field(default=None, max_length=30)


class KpiUpdate(CamelModel):
    name: str | None = None
    description: str | None = None
    formula: KpiFormula | None = None
    target: float | None = None
    unit: str | None = None


class KpiOut(CamelModel):
    id: uuid.UUID
    name: str
    description: str | None
    dataset_id: uuid.UUID
    formula: dict
    target: float | None
    unit: str | None
    created_at: datetime
