"""Analytics query engine: safe, metadata-validated aggregations over
imported dataset-version tables. Column names are only ever resolved from
the dataset's own column metadata — never from raw user input."""

import uuid
from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.analytics import KPI
from app.models.dataset import DatasetColumn, DatasetVersion
from app.services.datasets import tables

AGGREGATIONS = {"sum", "avg", "count", "count_distinct", "min", "max"}
FILTER_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains"}
NUMERIC_TYPES = {"integer", "float"}
DATE_TYPES = {"date", "datetime"}
BUCKETS = {"day", "week", "month", "quarter", "year"}


def _column_meta(version: DatasetVersion, name: str) -> DatasetColumn:
    col = next((c for c in version.columns if c.normalized_name == name), None)
    if col is None:
        raise AppError(f"Unknown column '{name}'", "BAD_REQUEST", 400)
    return col


def _agg_expr(agg: str, column: sa.Column | None) -> sa.Column:
    if agg == "count":
        return func.count().label("value")
    assert column is not None
    fn = {
        "sum": func.sum,
        "avg": func.avg,
        "count_distinct": lambda c: func.count(sa.distinct(c)),
        "min": func.min,
        "max": func.max,
    }[agg]
    return fn(column).label("value")


def _date_bucket(engine: Engine, bucket: str, column: sa.Column) -> sa.SQLColumnExpression:
    if engine.dialect.name == "postgresql":
        return func.date_trunc(bucket, column).label("bucket")
    fmt = {
        "day": "%Y-%m-%d",
        "week": "%Y-W%W",
        "month": "%Y-%m",
        "year": "%Y",
    }
    if bucket == "quarter":
        # SQLite: build "2024-Q2" from year + computed quarter.
        q = (func.cast(func.strftime("%m", column), sa.Integer) + 2) / 3
        return (func.strftime("%Y", column) + "-Q" + func.cast(q, sa.Integer)).label("bucket")
    return func.strftime(fmt[bucket], column).label("bucket")


def _apply_date_range(stmt, column: sa.Column, frm: date | None, to: date | None):
    if frm:
        stmt = stmt.where(column >= frm)
    if to:
        stmt = stmt.where(column <= to)
    return stmt


def _apply_filters(stmt, table: sa.Table, version: DatasetVersion, filters: list | None):
    for f in filters or []:
        meta = _column_meta(version, str(f.get("column")))
        op = f.get("op")
        if op not in FILTER_OPS:
            raise AppError(f"Unsupported filter op '{op}'", "BAD_REQUEST", 400)
        col = table.c[meta.normalized_name]
        v = f.get("value")
        if op == "eq":
            stmt = stmt.where(col == v)
        elif op == "ne":
            stmt = stmt.where(col != v)
        elif op == "gt":
            stmt = stmt.where(col > v)
        elif op == "gte":
            stmt = stmt.where(col >= v)
        elif op == "lt":
            stmt = stmt.where(col < v)
        elif op == "lte":
            stmt = stmt.where(col <= v)
        elif op == "contains":
            stmt = stmt.where(col.ilike(f"%{v}%"))
    return stmt


def series(
    engine: Engine,
    version: DatasetVersion,
    *,
    date_column: str,
    metric_column: str | None,
    agg: str,
    bucket: str,
    frm: date | None,
    to: date | None,
) -> list[dict]:
    if agg not in AGGREGATIONS:
        raise AppError(f"Unsupported aggregation '{agg}'", "BAD_REQUEST", 400)
    if bucket not in BUCKETS:
        raise AppError(f"Unsupported bucket '{bucket}'", "BAD_REQUEST", 400)

    date_meta = _column_meta(version, date_column)
    if date_meta.inferred_type not in DATE_TYPES:
        raise AppError(f"Column '{date_column}' is not a date type", "BAD_REQUEST", 400)
    metric_meta = None
    if agg != "count":
        if not metric_column:
            raise AppError("metricColumn is required for this aggregation", "BAD_REQUEST", 400)
        metric_meta = _column_meta(version, metric_column)
        if metric_meta.inferred_type not in NUMERIC_TYPES:
            raise AppError(
                f"Column '{metric_column}' is not numeric", "BAD_REQUEST", 400
            )

    table = tables.reflect_table(engine, version.table_name)
    date_col = table.c[date_meta.normalized_name]
    metric_col = table.c[metric_meta.normalized_name] if metric_meta else None
    bucket_expr = _date_bucket(engine, bucket, date_col)

    stmt = select(bucket_expr, _agg_expr(agg, metric_col)).group_by(bucket_expr).order_by(bucket_expr)
    stmt = _apply_date_range(stmt, date_col, frm, to)

    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        {"t": str(r["bucket"]), "value": float(r["value"]) if r["value"] is not None else 0.0}
        for r in rows
    ]


def breakdown(
    engine: Engine,
    version: DatasetVersion,
    *,
    dimension: str,
    metric_column: str | None,
    agg: str,
    limit: int,
    frm: date | None = None,
    to: date | None = None,
    date_column: str | None = None,
) -> list[dict]:
    if agg not in AGGREGATIONS:
        raise AppError(f"Unsupported aggregation '{agg}'", "BAD_REQUEST", 400)
    dim_meta = _column_meta(version, dimension)
    metric_meta = None
    if agg != "count":
        if not metric_column:
            raise AppError("metricColumn is required for this aggregation", "BAD_REQUEST", 400)
        metric_meta = _column_meta(version, metric_column)
        if metric_meta.inferred_type not in NUMERIC_TYPES:
            raise AppError(f"Column '{metric_column}' is not numeric", "BAD_REQUEST", 400)

    table = tables.reflect_table(engine, version.table_name)
    dim_col = table.c[dim_meta.normalized_name]
    metric_col = table.c[metric_meta.normalized_name] if metric_meta else None
    value_expr = _agg_expr(agg, metric_col)

    stmt = (
        select(dim_col.label("label"), value_expr)
        .group_by(dim_col)
        .order_by(value_expr.desc())
        .limit(min(limit, 100))
    )
    if date_column:
        dmeta = _column_meta(version, date_column)
        stmt = _apply_date_range(stmt, table.c[dmeta.normalized_name], frm, to)

    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        {"label": str(r["label"]) if r["label"] is not None else "(empty)",
         "value": float(r["value"]) if r["value"] is not None else 0.0}
        for r in rows
    ]


def evaluate_kpi(
    db: Session,
    engine: Engine,
    kpi: KPI,
    *,
    frm: date | None,
    to: date | None,
) -> dict:
    formula = kpi.formula or {}
    agg = formula.get("aggregation")
    column = formula.get("column")
    date_column = formula.get("dateColumn")
    filters = formula.get("filters") or []

    if agg not in AGGREGATIONS:
        raise AppError(f"Unsupported aggregation '{agg}'", "BAD_REQUEST", 400)
    if agg != "count" and not column:
        raise AppError("KPI formula requires a column", "BAD_REQUEST", 400)

    version = db.get(DatasetVersion, _latest_version_id(db, kpi.dataset_id))
    if version is None:
        raise AppError("KPI dataset has no data version", "BAD_REQUEST", 400)

    table = tables.reflect_table(engine, version.table_name)
    metric_meta = _column_meta(version, column) if agg != "count" else None
    metric_col = table.c[metric_meta.normalized_name] if metric_meta else None
    value_expr = _agg_expr(agg, metric_col)

    stmt = select(value_expr)
    if date_column:
        dmeta = _column_meta(version, date_column)
        stmt = _apply_date_range(stmt, table.c[dmeta.normalized_name], frm, to)
    stmt = _apply_filters(stmt, table, version, filters)

    def run(s):
        with engine.connect() as conn:
            v = conn.execute(s).scalar()
        return float(v) if v is not None else 0.0

    value = run(stmt)

    # Period-over-period delta: same window shifted back by its own length.
    delta_pct = None
    if frm and to and date_column:
        span = (to - frm).days or 1
        prev_to = frm - timedelta(days=1)
        prev_frm = prev_to - timedelta(days=span - 1)
        dmeta = _column_meta(version, date_column)
        prev_stmt = select(value_expr)
        prev_stmt = _apply_date_range(prev_stmt, table.c[dmeta.normalized_name], prev_frm, prev_to)
        prev_stmt = _apply_filters(prev_stmt, table, version, filters)
        prev = run(prev_stmt)
        if prev:
            delta_pct = round((value - prev) / abs(prev) * 100, 1)

    progress = None
    if kpi.target:
        progress = round(value / kpi.target * 100, 1)

    return {
        "value": value,
        "deltaPct": delta_pct,
        "target": kpi.target,
        "progressPct": progress,
        "unit": kpi.unit,
    }


def _latest_version_id(db: Session, dataset_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(DatasetVersion.id)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.version_no.desc())
        .limit(1)
    )
