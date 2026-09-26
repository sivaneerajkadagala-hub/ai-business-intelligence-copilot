"""Deterministic NL → SQL engine ("demo mode").

Builds queries with SQLAlchemy Core and compiles them against the live
engine dialect — so generated SQL is dialect-correct on both Postgres and
SQLite, with literals bound safely by the compiler."""

from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy import Engine, func, select

from app.services.analytics.engine import _agg_expr, _date_bucket
from app.services.ai.intent import Intent
from app.services.datasets import tables


def _bare_table(engine: Engine, ctx: dict) -> sa.Table:
    return sa.Table(
        ctx["tableName"],
        sa.MetaData(),
        *[sa.Column(c["name"]) for c in ctx["columns"]],
        schema=tables.data_schema(engine),
    )


def _compile(engine: Engine, stmt) -> str:
    compiled = stmt.compile(
        engine, compile_kwargs={"literal_binds": True}
    )
    return str(compiled)


def _period_filter(table: sa.Table, date_col: str | None, days: int | None) -> sa.ColumnElement | None:
    if date_col and days:
        return table.c[date_col] >= (date.today() - timedelta(days=days))
    return None


def generate(question: str, ctx: dict, intent: Intent, engine: Engine) -> dict | None:
    """Return {sql, intentKind, rationale, chart} or None when no pattern fits."""
    table = _bare_table(engine, ctx)
    metric = intent.metric_col
    agg = intent.agg or "sum"
    metric_col = table.c[metric] if metric else None

    def agg_expr() -> sa.Column:
        return _agg_expr(agg, metric_col)

    where_extra = _period_filter(table, intent.date_col, intent.period_days)
    dim_filters = [
        table.c[f["column"]] == f["value"]
        for f in intent.filters
        if intent.kind != "comparison" and f["column"] in table.c
    ]

    stmt = None
    chart: dict | None = None

    if intent.kind == "trend" and intent.date_col:
        bucket = _date_bucket(engine, intent.bucket, table.c[intent.date_col])
        stmt = (
            select(bucket.label("t"), agg_expr().label("value"))
            .group_by(bucket)
            .order_by(bucket)
            .limit(500)
        )
        chart = {"type": "line", "x": "t", "y": "value"}

    elif intent.kind == "comparison" and intent.dim_col and len(intent.compare_values) >= 2:
        stmt = (
            select(table.c[intent.dim_col].label("label"), agg_expr().label("value"))
            .where(table.c[intent.dim_col].in_(intent.compare_values))
            .group_by(table.c[intent.dim_col])
            .order_by(sa.text("value DESC"))
            .limit(50)
        )
        chart = {"type": "bar", "x": "label", "y": "value"}

    elif intent.kind in ("ranking", "breakdown") and intent.dim_col:
        stmt = (
            select(table.c[intent.dim_col].label("label"), agg_expr().label("value"))
            .group_by(table.c[intent.dim_col])
            .order_by(sa.text("value DESC"))
            .limit(intent.top_n if intent.kind == "ranking" else 25)
        )
        chart = {"type": "bar", "x": "label", "y": "value"}

    elif intent.kind == "metric":
        stmt = select(agg_expr().label("value")).select_from(table)
        chart = {"type": "number"}

    if stmt is None:
        return None

    if where_extra is not None:
        stmt = stmt.where(where_extra)
    for cond in dim_filters:
        stmt = stmt.where(cond)

    return {
        "sql": _compile(engine, stmt),
        "intentKind": intent.kind,
        "rationale": intent.rationale,
        "chart": chart,
    }
