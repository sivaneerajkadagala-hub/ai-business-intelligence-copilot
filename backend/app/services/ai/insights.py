"""Automated business-insight generation over a dataset version."""

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.copilot import Insight, InsightSeverity, InsightType
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.services.ai import anomalies, forecast
from app.services.analytics import engine as aengine
from app.services.audit import audit


def _pick(version: DatasetVersion, types: set[str], preferred: list[str] = ()) -> str | None:
    cols = sorted(version.columns, key=lambda c: c.ordinal)
    for p in preferred:
        hit = next((c for c in cols if c.normalized_name == p and c.inferred_type in types), None)
        if hit:
            return hit.normalized_name
    hit = next((c for c in cols if c.inferred_type in types), None)
    return hit.normalized_name if hit else None


def generate(
    db: Session,
    engine: Engine,
    *,
    dataset: Dataset,
    version: DatasetVersion,
    user: User,
    ip: str | None,
) -> list[Insight]:
    """Recompute system insights for a dataset (idempotent refresh)."""
    db.execute(
        sa.delete(Insight).where(
            Insight.dataset_id == dataset.id, Insight.generated_by == "system"
        )
    )

    date_col = _pick(version, {"date", "datetime"}, ("date", "order_date", "signup_date"))
    metric_col = _pick(version, {"integer", "float"}, ("revenue", "amount", "profit", "quantity"))
    dim_col = next(
        (
            c.normalized_name
            for c in sorted(version.columns, key=lambda c: c.ordinal)
            if c.inferred_type == "string" and 1 < c.distinct_count <= 100
        ),
        None,
    )

    created: list[Insight] = []

    def add(**kw):
        ins = Insight(dataset_id=dataset.id, generated_by="system", **kw)
        db.add(ins)
        created.append(ins)

    # 1 — Trend
    if date_col and metric_col:
        pts = aengine.series(
            engine, version, date_column=date_col, metric_column=metric_col,
            agg="sum", bucket="month", frm=None, to=None,
        )
        if len(pts) >= 4:
            first, last = pts[0]["value"], pts[-1]["value"]
            if first:
                change = (last - first) / abs(first) * 100
                add(
                    type=InsightType.TREND,
                    title=f"{metric_col.replace('_', ' ').title()} trend",
                    body=(
                        f"{metric_col} {'grew' if change >= 0 else 'declined'} "
                        f"{abs(change):.1f}% from {pts[0]['t']} ({first:,.0f}) to "
                        f"{pts[-1]['t']} ({last:,.0f}), over {len(pts)} periods."
                    ),
                    severity=InsightSeverity.INFO,
                    evidence={"points": pts},
                )

    # 2 — Top contributor + laggard
    if dim_col and metric_col:
        items = aengine.breakdown(
            engine, version, dimension=dim_col, metric_column=metric_col,
            agg="sum", limit=50,
        )
        if len(items) >= 2:
            total = sum(i["value"] for i in items) or 1
            top, bottom = items[0], items[-1]
            add(
                type=InsightType.RANKING,
                title=f"Top {dim_col.replace('_', ' ')}",
                body=(
                    f"{top['label']} leads {dim_col} with {top['value']:,.0f} "
                    f"({top['value'] / total * 100:.0f}% of total {metric_col})."
                ),
                severity=InsightSeverity.INFO,
                evidence={"items": items[:10]},
            )
            if bottom["label"] != top["label"]:
                add(
                    type=InsightType.COMPARISON,
                    title=f"Lowest {dim_col.replace('_', ' ')}",
                    body=(
                        f"{bottom['label']} contributes the least: {bottom['value']:,.0f} "
                        f"({bottom['value'] / total * 100:.1f}%), vs {top['label']} "
                        f"at {top['value']:,.0f}."
                    ),
                    severity=InsightSeverity.INFO,
                    evidence={"item": bottom},
                )

    # 3 — Anomalies (daily granularity; warning severity)
    if date_col and metric_col:
        try:
            res = anomalies.detect(
                engine, version, date_column=date_col,
                metric_column=metric_col, bucket="day",
            )
            for a in res["anomalies"][:3]:
                add(
                    type=InsightType.ANOMALY,
                    title=f"{a['direction'].title()} in {metric_col.replace('_', ' ')} on {a['t']}",
                    body=(
                        f"{a['t']} recorded {a['value']:,.0f} "
                        f"(expected ~{a['expected']:,.0f}) — {abs(a['score']):.1f} "
                        f"{'σ' if a['method'] == 'zscore' else 'IQR'} "
                        f"{'above' if a['direction'] == 'spike' else 'below'} normal."
                    ),
                    severity=InsightSeverity(a["severity"]),
                    evidence=a,
                )
        except AppError:
            pass  # too few points — skip silently

    # 4 — Data quality
    if dataset.quality_score is not None and dataset.quality_score < 80:
        add(
            type=InsightType.ANOMALY,
            title="Data quality needs attention",
            body=(
                f"Quality score is {dataset.quality_score:.0f}/100 — missing or "
                "duplicate rows detected. Consider creating a cleaned version."
            ),
            severity=InsightSeverity.WARNING,
            evidence={"qualityScore": float(dataset.quality_score)},
        )

    audit(
        db, user_id=user.id, action="insights.generate",
        resource_type="dataset", resource_id=str(dataset.id),
        meta={"count": len(created)}, ip=ip,
    )
    db.commit()
    for ins in created:
        db.refresh(ins)
    return created
