"""Copilot orchestrator: question → intent → SQL (LLM or rules) →
validate → execute → chart + grounded explanation → persist."""

import time

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.analytics import QueryHistory, QuerySource, QueryStatus
from app.models.copilot import Insight, InsightSeverity, InsightType
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.services.ai import (
    anomalies,
    explainer,
    forecast,
    insights as insight_service,
    llm_provider,
    nl2sql,
    rule_engine,
    sql_validator,
)
from app.services.analytics import engine as aengine
from app.services.ai.intent import detect_intent, merge_followup
from app.services.ai.schema_context import build_schema_context
from app.services.audit import audit

ROW_CAP = 5000
SNAPSHOT_ROWS = 200


def _log_query(
    db: Session, *, user: User, dataset: Dataset, sql: str,
    status: QueryStatus, rows: int | None, duration_ms: int | None,
    error_code: str | None = None,
) -> None:
    db.add(
        QueryHistory(
            user_id=user.id,
            dataset_id=dataset.id,
            sql=sql[:10_000],
            status=status,
            row_count=rows,
            duration_ms=duration_ms,
            source=QuerySource.COPILOT,
            error_code=error_code,
        )
    )


def _execute(engine: Engine, sql: str) -> tuple[list[str], list[dict], int]:
    t0 = time.perf_counter()
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(sa.text("SET statement_timeout TO '10s'"))
        cursor = conn.exec_driver_sql(sql)
        columns = list(cursor.keys())
        raw = cursor.fetchmany(ROW_CAP + 1)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    rows = [dict(zip(columns, r)) for r in raw]
    return columns, rows, duration_ms


def answer_question(
    db: Session,
    engine: Engine,
    *,
    user: User,
    question: str,
    dataset: Dataset,
    version: DatasetVersion,
    ip: str | None,
    prior_question: str | None = None,
) -> dict:
    ctx = build_schema_context(engine, dataset, version)
    intent = detect_intent(question, ctx)
    if prior_question:
        prior = detect_intent(prior_question, ctx)
        intent = merge_followup(question, intent, prior)
    provider = llm_provider.get_provider()

    # Analytical intents bypass SQL generation — they're computed by
    # dedicated statistical services over the same validated aggregates.
    if intent.kind == "anomaly" and intent.date_col and intent.metric_col:
        return _answer_anomaly(db, engine, question, intent, dataset, version, user, ip)
    if intent.kind == "forecast" and intent.date_col and intent.metric_col:
        return _answer_forecast(db, engine, question, intent, dataset, version, user, ip)

    gen = None
    engine_used = "rules"
    if provider is not None:
        try:
            gen = nl2sql.generate(question, ctx, provider)
            if gen:
                engine_used = provider.name
        except Exception:
            gen = None  # provider failure → fall back to rules
    if gen is None:
        gen = rule_engine.generate(question, ctx, intent, engine)

    if gen is None:
        return {
            "content": (
                "I couldn't map that question to a query on this dataset. "
                f'Try things like: "Total {ctx["columns"][0]["name"]}", '
                '"monthly revenue trend", or "top 5 by category".'
            ),
            "sql": None,
            "result": None,
            "chart": None,
            "explanation": None,
            "engine": "none",
        }

    allowed_tables = {ctx["table"], ctx["tableName"]}
    allowed_columns = {c["name"] for c in ctx["columns"]}
    dialect = sql_validator.dialect_for(engine.dialect.name)

    try:
        safe_sql = sql_validator.validate(
            gen["sql"],
            allowed_tables=allowed_tables,
            allowed_columns=allowed_columns,
            dialect=dialect,
        )
    except sql_validator.SQLValidationError as e:
        _log_query(db, user=user, dataset=dataset, sql=gen["sql"],
                   status=QueryStatus.BLOCKED, rows=None, duration_ms=None,
                   error_code="SQL_BLOCKED")
        db.commit()
        return {
            "content": "I generated a candidate query but it failed the "
                       "safety validation, so it was not executed.",
            "sql": gen["sql"],
            "result": None,
            "chart": None,
            "explanation": str(e),
            "engine": engine_used,
        }

    try:
        columns, rows, duration_ms = _execute(engine, safe_sql)
    except Exception as e:
        _log_query(db, user=user, dataset=dataset, sql=safe_sql,
                   status=QueryStatus.FAILED, rows=None, duration_ms=None,
                   error_code="EXEC_FAILED")
        db.commit()
        raise AppError("The validated query failed to execute", "EXEC_FAILED", 500) from e

    _log_query(db, user=user, dataset=dataset, sql=safe_sql,
               status=QueryStatus.SUCCESS, rows=len(rows), duration_ms=duration_ms)

    # Serialize rows for JSON storage/response.
    clean_rows = [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}
        for r in rows[:SNAPSHOT_ROWS]
    ]
    result = {
        "columns": columns,
        "rows": clean_rows,
        "rowCount": len(rows),
        "meta": {
            "intent": intent.kind,
            "metric": intent.metric_col,
            "dim": intent.dim_col,
            "dateCol": intent.date_col,
            "bucket": intent.bucket,
            "agg": intent.agg,
        },
    }

    chart = gen.get("chart")
    if len(rows) <= 1 and columns:
        chart = {"type": "number"}
    if not rows:
        chart = None

    exp = explainer.explain(
        question=question, intent_kind=intent.kind, columns=columns,
        rows=clean_rows, chart_type=(chart or {}).get("type"), provider=provider,
    )

    # Persist typed insights for analytical intents.
    insight_map = {
        "trend": InsightType.TREND,
        "comparison": InsightType.COMPARISON,
        "ranking": InsightType.RANKING,
    }
    if intent.kind in insight_map and rows:
        db.add(
            Insight(
                dataset_id=dataset.id,
                type=insight_map[intent.kind],
                title=question[:300],
                body=f'{exp["summary"]} {exp["detail"]}'.strip(),
                severity=InsightSeverity.INFO,
                evidence={"rows": clean_rows[:10], "sql": safe_sql[:2000]},
                generated_by="system",
            )
        )

    audit(
        db, user_id=user.id, action="copilot.query",
        resource_type="dataset", resource_id=str(dataset.id),
        meta={"question": question[:200], "engine": engine_used,
              "rows": len(rows), "ms": duration_ms},
        ip=ip,
    )
    db.commit()

    return {
        "content": exp["summary"],
        "sql": safe_sql,
        "result": result,
        "chart": chart,
        "explanation": exp["detail"],
        "engine": engine_used,
        "intent": intent.kind,
    }


def _answer_anomaly(db, engine, question, intent, dataset, version, user, ip):
    try:
        res = anomalies.detect(
            engine, version, date_column=intent.date_col,
            metric_column=intent.metric_col, bucket=intent.bucket,
        )
    except AppError as e:
        return {"content": e.message, "sql": None, "result": None,
                "chart": None, "explanation": None, "engine": "stats"}

    rows = res["anomalies"]
    if not rows:
        summary = f"No anomalies detected in {intent.metric_col}."
        detail = f"All {res['points']} points fall within normal range ({res['method']})."
    else:
        top = rows[0]
        summary = (
            f"Found {len(rows)} anomal{'ies' if len(rows) != 1 else 'y'} — biggest is a "
            f"{top['direction']} on {top['t']}: {top['value']:,.0f} "
            f"(expected ~{top['expected']:,.0f})."
        )
        detail = (
            f"{res['method']} analysis over {res['points']} {intent.bucket}ly points. "
            "Anomalies are deviations from the moving-average trend, not raw values."
        )

    result = {
        "columns": ["t", "value", "expected", "score", "direction", "severity"],
        "rows": rows[:SNAPSHOT_ROWS],
        "rowCount": len(rows),
        "series": res["series"],
    }
    if rows:
        db.add(Insight(
            dataset_id=dataset.id, type=InsightType.ANOMALY,
            title=f"{rows[0]['direction'].title()} in {intent.metric_col} on {rows[0]['t']}",
            body=f"{summary} {detail}", severity=InsightSeverity(rows[0]['severity']),
            evidence=rows[0], generated_by="system",
        ))
    audit(db, user_id=user.id, action="copilot.anomaly",
          resource_type="dataset", resource_id=str(dataset.id),
          meta={"found": len(rows)}, ip=ip)
    db.commit()
    return {
        "content": summary,
        "sql": None,
        "result": result,
        "chart": {"type": "anomaly", "x": "t", "y": "value"} if res["series"] else None,
        "explanation": detail,
        "engine": "stats",
        "intent": "anomaly",
    }


def _answer_forecast(db, engine, question, intent, dataset, version, user, ip):
    points = aengine.series(
        engine, version, date_column=intent.date_col,
        metric_column=intent.metric_col, agg="sum",
        bucket=intent.bucket, frm=None, to=None,
    )
    try:
        result = forecast.forecast(points, horizon=intent.horizon, bucket=intent.bucket)
    except ValueError as e:
        return {"content": str(e), "sql": None, "result": None,
                "chart": None, "explanation": None, "engine": "stats"}

    fp = result["points"]
    summary = (
        f"Next {intent.horizon} {intent.bucket}(s) projected {intent.metric_col}: "
        f"{fp[-1]['forecast']:,.0f} by {fp[-1]['t']} (method: {result['method']})."
    )
    detail = (
        f"Projected values range {fp[0]['forecast']:,.0f} → {fp[-1]['forecast']:,.0f} "
        f"with ~80% confidence intervals widening over the horizon. "
        "Forecasts are statistical projections, not guarantees."
    )

    result_snapshot = {
        "columns": ["t", "forecast", "lower", "upper"],
        "rows": fp,
        "rowCount": len(fp),
        "series": points[-40:],
    }
    db.add(Insight(
        dataset_id=dataset.id, type=InsightType.FORECAST,
        title=f"{intent.horizon}-{intent.bucket} {intent.metric_col} forecast",
        body=f"{summary} {detail}", severity=InsightSeverity.INFO,
        evidence={"forecast": fp, "method": result["method"]},
        generated_by="system",
    ))
    audit(db, user_id=user.id, action="copilot.forecast",
          resource_type="dataset", resource_id=str(dataset.id),
          meta={"horizon": intent.horizon, "method": result["method"]}, ip=ip)
    db.commit()
    return {
        "content": summary,
        "sql": None,
        "result": result_snapshot,
        "chart": {"type": "forecast", "x": "t", "y": "forecast"},
        "explanation": detail,
        "engine": "stats",
        "intent": "forecast",
    }
