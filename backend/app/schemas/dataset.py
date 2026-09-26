import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.user import CamelModel


class DatasetOut(CamelModel):
    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    status: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    row_count: int
    column_count: int
    quality_score: float | None
    is_shared: bool
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class VersionOut(CamelModel):
    id: uuid.UUID
    version_no: int
    kind: str
    operations: list | None
    table_name: str
    row_count: int
    column_count: int
    created_at: datetime


class ColumnOut(CamelModel):
    name: str
    normalized_name: str
    ordinal: int
    inferred_type: str
    null_count: int
    distinct_count: int
    min_value: str | None
    max_value: str | None
    mean: float | None
    median: float | None
    stddev: float | None
    outlier_count: int | None
    top_values: list[dict] | None


class CleanOperation(CamelModel):
    op: str
    columns: list[str] | None = None
    column: str | None = None
    strategy: str | None = None
    value: Any | None = None
    to: str | None = None
    new_name: str | None = Field(default=None, alias="newName")
    method: str | None = None
    threshold: float | None = None


class CleanIn(CamelModel):
    version_id: uuid.UUID | None = None
    operations: list[CleanOperation] = Field(min_length=1)


class ImportOut(CamelModel):
    id: uuid.UUID
    status: str
    rows_imported: int
    rows_rejected: int
    error_log: list | None
    started_at: datetime | None
    finished_at: datetime | None
