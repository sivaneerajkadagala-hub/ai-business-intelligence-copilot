"""Physical data tables for imported dataset versions.

On PostgreSQL these live in the dedicated `data` schema (data.ds_<hex>) —
the `bi_reader` role has SELECT-only access there. On SQLite (tests/dev)
the schema is skipped and tables are plain `ds_<hex>`.
"""

import sqlalchemy as sa
from sqlalchemy import Engine, MetaData, Table

DATA_SCHEMA = "data"
TABLE_PREFIX = "ds_"

COLUMN_TYPE_MAP: dict[str, sa.types.TypeEngine] = {
    "string": sa.Text,
    "integer": sa.BigInteger,
    "float": sa.Float,
    "boolean": sa.Boolean,
    "date": sa.Date,
    "datetime": sa.DateTime,
}


def data_schema(engine: Engine) -> str | None:
    return DATA_SCHEMA if engine.dialect.name == "postgresql" else None


def qualified_name(table_name: str, engine: Engine) -> str:
    schema = data_schema(engine)
    return f"{schema}.{table_name}" if schema else table_name


def new_table_name() -> str:
    import uuid

    return f"{TABLE_PREFIX}{uuid.uuid4().hex[:12]}"


def build_table(engine: Engine, table_name: str, columns: list[tuple[str, str]]) -> Table:
    table = Table(
        table_name,
        MetaData(),
        *[
            sa.Column(name, COLUMN_TYPE_MAP.get(inferred, sa.Text))
            for name, inferred in columns
        ],
        schema=data_schema(engine),
    )
    table.create(engine)
    return table


def reflect_table(engine: Engine, table_name: str) -> Table:
    return Table(
        table_name,
        MetaData(),
        autoload_with=engine,
        schema=data_schema(engine),
    )


def drop_table(engine: Engine, table_name: str) -> None:
    Table(table_name, MetaData(), schema=data_schema(engine)).drop(
        engine, checkfirst=True
    )
