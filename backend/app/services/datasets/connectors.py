"""External database connectors — transient, credential-free.

The connection URL is used once (list tables or read rows) and never
persisted. Only postgresql:// and sqlite:/// schemes are allowed; queries
are sqlglot-validated SELECTs with an enforced row cap."""

import pandas as pd
import sqlalchemy as sa
import sqlglot
from sqlglot import exp
from sqlalchemy import create_engine

from app.core.errors import AppError
from app.services.ai.sql_validator import FORBIDDEN_EXPRESSIONS, SQLValidationError

ALLOWED_SCHEMES = {"postgresql", "sqlite"}
SOURCE_ROW_CAP = 100_000


def _make_engine(url: str):
    scheme = url.split("://", 1)[0].lower()
    base_scheme = scheme.split("+", 1)[0]  # sqlite+pysqlite → sqlite
    if base_scheme not in ALLOWED_SCHEMES:
        raise AppError(
            f"Unsupported source scheme '{scheme}'. Allowed: postgresql, sqlite",
            "BAD_REQUEST", 400,
        )
    try:
        eng = create_engine(
            url,
            connect_args={"connect_timeout": 5}
            if base_scheme != "sqlite" else {},
            pool_pre_ping=True,
        )
    except Exception as e:
        raise AppError("Could not create a connection engine", "BAD_REQUEST", 400) from e
    return eng


def _sanitized_host(url: str) -> str:
    """host:port without credentials — safe to store as provenance."""
    try:
        rest = url.split("://", 1)[1]
        host = rest.split("@")[-1].split("/")[0]
        return host
    except Exception:
        return "unknown"


def list_tables(url: str) -> dict:
    eng = _make_engine(url)
    try:
        insp = sa.inspect(eng)
        schemas = insp.get_schema_names()
        tables: list[dict] = []
        for schema in schemas:
            if schema in ("information_schema", "pg_catalog", "pg_toast", "sqlite_sequence"):
                continue
            for t in insp.get_table_names(schema=schema):
                tables.append({"schema": schema, "table": t})
        return {"tables": tables[:500], "host": _sanitized_host(url)}
    except sa.exc.SQLAlchemyError as e:
        raise AppError("Could not connect to the data source", "CONN_FAILED", 400) from e
    finally:
        eng.dispose()


def validate_source_query(sql: str) -> str:
    """Allowlist-free variant for external sources: single SELECT, no
    forbidden constructs, enforced row cap."""
    try:
        parsed = [s for s in sqlglot.parse(sql) if s is not None]
    except Exception as e:
        raise AppError(f"Unparseable query: {e}", "BAD_REQUEST", 400) from e
    if len(parsed) != 1:
        raise AppError("Exactly one statement is allowed", "BAD_REQUEST", 400)
    stmt = parsed[0]
    if not isinstance(stmt, exp.Select):
        raise AppError("Only SELECT queries are allowed on data sources", "BAD_REQUEST", 400)
    for node in stmt.walk():
        if isinstance(node, FORBIDDEN_EXPRESSIONS):
            raise AppError("Query contains a forbidden statement type", "BAD_REQUEST", 400)
    if stmt.args.get("limit") is None:
        stmt = stmt.limit(SOURCE_ROW_CAP)
    return stmt.sql()


def read_source(url: str, *, table: str | None, query: str | None) -> tuple[pd.DataFrame, dict]:
    """Read a capped DataFrame + provenance dict."""
    eng = _make_engine(url)
    try:
        if table and not query:
            insp = sa.inspect(eng)
            valid = {t for s in insp.get_schema_names() for t in insp.get_table_names(schema=s)}
            if table not in valid:
                raise AppError(f"Table '{table}' not found in the source", "NOT_FOUND", 404)
            sql = f'SELECT * FROM "{table}" LIMIT {SOURCE_ROW_CAP}'
            table_name = table
        else:
            sql = validate_source_query(query or "")
            table_name = query or "query"

        df = pd.read_sql(sa.text(sql), eng)
        prov = {
            "scheme": url.split("://", 1)[0],
            "host": _sanitized_host(url),
            "table": table_name[:200],
        }
        return df, prov
    except sa.exc.SQLAlchemyError as e:
        raise AppError(f"Source read failed: {str(e)[:200]}", "CONN_FAILED", 400) from e
    finally:
        eng.dispose()
