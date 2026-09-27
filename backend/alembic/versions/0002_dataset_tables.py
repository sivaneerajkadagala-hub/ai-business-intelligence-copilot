"""dataset tables: datasets, dataset_versions, dataset_columns, dataset_imports

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

dataset_status = postgresql.ENUM(
    "uploaded", "profiling", "importing", "ready", "failed", name="dataset_status", create_type=False
)
file_type = postgresql.ENUM("csv", "xlsx", name="file_type", create_type=False)
version_kind = postgresql.ENUM("original", "cleaned", name="version_kind", create_type=False)
import_status = postgresql.ENUM(
    "pending", "running", "success", "failed", name="import_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for e in (dataset_status, file_type, version_kind, import_status):
        e.create(bind)

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", dataset_status, nullable=False, server_default="uploaded"),
        sa.Column("original_filename", sa.String(300), nullable=False),
        sa.Column("file_type", file_type, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Numeric(5, 2)),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_datasets_owner_id", "datasets", ["owner_id"])

    op.create_table(
        "dataset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("dataset_versions.id", ondelete="SET NULL")),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("kind", version_kind, nullable=False),
        sa.Column("operations", postgresql.JSONB()),
        sa.Column("table_name", sa.String(63), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("dataset_id", "version_no", name="uq_dataset_versions_no"),
    )
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])

    op.create_table(
        "dataset_columns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("inferred_type", sa.String(20), nullable=False),
        sa.Column("null_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("distinct_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("min_value", sa.String(200)),
        sa.Column("max_value", sa.String(200)),
        sa.Column("mean", sa.Float()),
        sa.Column("median", sa.Float()),
        sa.Column("stddev", sa.Float()),
        sa.Column("outlier_count", sa.BigInteger()),
        sa.Column("top_values", postgresql.JSONB()),
        sa.UniqueConstraint("version_id", "normalized_name", name="uq_dataset_columns_name"),
    )
    op.create_index("ix_dataset_columns_dataset_id", "dataset_columns", ["dataset_id"])
    op.create_index("ix_dataset_columns_version_id", "dataset_columns", ["version_id"])

    op.create_table(
        "dataset_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("dataset_versions.id", ondelete="SET NULL")),
        sa.Column("imported_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", import_status, nullable=False, server_default="pending"),
        sa.Column("rows_imported", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rows_rejected", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_log", postgresql.JSONB()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dataset_imports_dataset_id", "dataset_imports", ["dataset_id"])


def downgrade() -> None:
    for table, indexes in {
        "dataset_imports": ["ix_dataset_imports_dataset_id"],
        "dataset_columns": ["ix_dataset_columns_version_id", "ix_dataset_columns_dataset_id"],
        "dataset_versions": ["ix_dataset_versions_dataset_id"],
        "datasets": ["ix_datasets_owner_id"],
    }.items():
        for ix in indexes:
            op.drop_index(ix, table_name=table)
        op.drop_table(table)
    bind = op.get_bind()
    for e in (import_status, version_kind, file_type, dataset_status):
        e.drop(bind)
