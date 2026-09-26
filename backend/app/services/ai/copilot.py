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
from app.services.ai import explainer, llm_provider, nl2sql, rule_engine, sql_validator
from app.services.ai.intent import detect_intent
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
) -> dict:
    ctx = build_schema_context(engine, dataset, version)
    intent = detect_intent(question, ctx)
    provider = llm_provider.get_provider()

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
    result = {"columns": columns, "rows": clean_rows, "rowCount": len(rows)}

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
