import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DatasetStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROFILING = "profiling"
    IMPORTING = "importing"
    READY = "ready"
    FAILED = "failed"


class FileType(str, enum.Enum):
    CSV = "csv"
    XLSX = "xlsx"
    SOURCE = "source"


class VersionKind(str, enum.Enum):
    ORIGINAL = "original"
    CLEANED = "cleaned"


class ImportStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


jsonb = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[DatasetStatus] = mapped_column(
        sa.Enum(DatasetStatus, name="dataset_status", values_callable=lambda e: [m.value for m in e]),
        default=DatasetStatus.UPLOADED,
    )
    original_filename: Mapped[str] = mapped_column(sa.String(300))
    file_type: Mapped[FileType] = mapped_column(
        sa.Enum(FileType, name="file_type", values_callable=lambda e: [m.value for m in e])
    )
    file_size_bytes: Mapped[int] = mapped_column(sa.BigInteger)
    storage_path: Mapped[str] = mapped_column(sa.String(500))
    row_count: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    column_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    quality_score: Mapped[float | None] = mapped_column(sa.Numeric(5, 2))
    is_shared: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    versions: Mapped[list["DatasetVersion"]] = relationship(
        back_populates="dataset", order_by="DatasetVersion.version_no"
    )


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (sa.UniqueConstraint("dataset_id", "version_no"),)

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("dataset_versions.id", ondelete="SET NULL")
    )
    version_no: Mapped[int] = mapped_column(sa.Integer)
    kind: Mapped[VersionKind] = mapped_column(
        sa.Enum(VersionKind, name="version_kind", values_callable=lambda e: [m.value for m in e])
    )
    operations: Mapped[list | None] = mapped_column(jsonb)
    table_name: Mapped[str] = mapped_column(sa.String(63))
    row_count: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    column_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    columns: Mapped[list["DatasetColumn"]] = relationship(back_populates="version")


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"
    __table_args__ = (sa.UniqueConstraint("version_id", "normalized_name"),)

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200))
    normalized_name: Mapped[str] = mapped_column(sa.String(200))
    ordinal: Mapped[int] = mapped_column(sa.Integer)
    inferred_type: Mapped[str] = mapped_column(sa.String(20))
    null_count: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    distinct_count: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    min_value: Mapped[str | None] = mapped_column(sa.String(200))
    max_value: Mapped[str | None] = mapped_column(sa.String(200))
    mean: Mapped[float | None] = mapped_column(sa.Float)
    median: Mapped[float | None] = mapped_column(sa.Float)
    stddev: Mapped[float | None] = mapped_column(sa.Float)
    outlier_count: Mapped[int | None] = mapped_column(sa.BigInteger)
    top_values: Mapped[list | None] = mapped_column(jsonb)

    version: Mapped[DatasetVersion] = relationship(back_populates="columns")


class DatasetImport(Base):
    __tablename__ = "dataset_imports"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("dataset_versions.id", ondelete="SET NULL")
    )
    imported_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ImportStatus] = mapped_column(
        sa.Enum(ImportStatus, name="import_status", values_callable=lambda e: [m.value for m in e]),
        default=ImportStatus.PENDING,
    )
    rows_imported: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    rows_rejected: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    error_log: Mapped[list | None] = mapped_column(jsonb)
    # Provenance for non-file imports: {"scheme": "postgresql", "host": "...", "table": "..."}
    source: Mapped[dict | None] = mapped_column(jsonb)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
