"""Deterministic intent + entity extraction for the copilot.

Maps natural language to a structured intent referencing real column
names — the same extraction drives both the rule engine and (as context)
the LLM prompt."""

import re
from dataclasses import dataclass, field

STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "to", "by", "vs", "versus",
    "and", "or", "what", "which", "is", "are", "was", "were", "how", "many",
    "much", "show", "me", "get", "give", "list", "tell", "total", "each",
    "per", "all", "from", "this", "that", "over", "between", "average",
    "avg", "mean", "sum", "count", "top", "highest", "lowest", "best",
    "worst", "monthly", "weekly", "daily", "yearly", "trend", "trending",
    "sales", "data", "dataset", "number", "numbers", "value", "values",
    "compare", "comparison", "breakdown", "distribution", "across", "our",
    "my", "we", "do", "did", "does", "last", "past", "recent", "please",
}

AGG_WORDS = {
    "sum": ["total", "sum", "combined", "overall"],
    "avg": ["average", "avg", "mean", "typical"],
    "count": ["how many", "count", "number of", "rows"],
    "count_distinct": ["distinct", "unique"],
    "min": ["minimum", "lowest", "smallest", "min "],
    "max": ["maximum", "highest", "largest", "max ", "biggest"],
}

BUCKET_WORDS = {
    "day": ["daily", "per day", "each day", "by day", "day over day"],
    "week": ["weekly", "per week", "each week", "by week"],
    "month": ["monthly", "per month", "each month", "by month", "month over"],
    "quarter": ["quarterly", "per quarter", "each quarter", "by quarter"],
    "year": ["yearly", "annual", "per year", "each year", "by year", "annually"],
}


@dataclass
class Intent:
    kind: str  # metric | trend | breakdown | ranking | comparison | unsupported
    agg: str | None = None
    metric_col: str | None = None
    dim_col: str | None = None
    date_col: str | None = None
    bucket: str = "month"
    top_n: int = 10
    filters: list[dict] = field(default_factory=list)
    compare_values: list[str] = field(default_factory=list)
    period_days: int | None = None
    rationale: str = ""


def _words(question: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z0-9_]+", question.lower()) if w not in STOPWORDS]


def _singular(w: str) -> str:
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    return w.rstrip("s")


def _column_scores(question: str, ctx: dict) -> dict[str, int]:
    """Score each column by how strongly the question references it."""
    q = question.lower()
    scores: dict[str, int] = {}
    for col in ctx["columns"]:
        score = 0
        name = col["name"]
        disp = str(col.get("display") or name).lower()
        if re.search(rf"\b{re.escape(name)}\b", q):
            score += 3
        elif disp != name and re.search(rf"\b{re.escape(disp)}\b", q):
            score += 3
        # partial token match (e.g. "revenues" ~ "revenue", "categories" ~ "category")
        for w in _words(q):
            if len(w) >= 4 and _singular(w) in (name, _singular(disp)):
                score += 2
        if score:
            scores[name] = score
    return scores


def _detect_dim_filter(question: str, ctx: dict) -> list[dict]:
    """'revenue in the north' / 'for north region' → {column: region, value: North}."""
    q = question.lower()
    found: list[dict] = []
    for col in ctx["columns"]:
        for v in col["sampleValues"] or []:
            s = str(v).lower()
            if len(s) >= 3 and re.search(rf"\b{re.escape(s)}\b", q):
                found.append({"column": col["name"], "op": "eq", "value": str(v)})
    return found


def detect_intent(question: str, ctx: dict) -> Intent:
    q = question.lower().strip()
    scores = _column_scores(q, ctx)
    intent = Intent(kind="unsupported")

    date_cols = [c["name"] for c in ctx["columns"] if c["type"] in ("date", "datetime")]
    numeric_cols = {c["name"] for c in ctx["columns"] if c["type"] in ("integer", "float")}
    string_cols = [c["name"] for c in ctx["columns"] if c["type"] in ("string", "boolean")]

    intent.date_col = next(
        (c for c in date_cols if c in scores), date_cols[0] if date_cols else None
    )
    intent.metric_col = next((c for c in scores if c in numeric_cols), None)

    # Dimension = a referenced string column; fallback: first low-cardinality string col
    intent.dim_col = next((c for c in scores if c in string_cols), None)
    if intent.dim_col is None:
        cat = [c for c in ctx["columns"] if c["type"] == "string" and 1 < c["distinct"] <= 100]
        intent.dim_col = cat[0]["name"] if cat else None

    for agg, words in AGG_WORDS.items():
        if any(w in q for w in words):
            intent.agg = agg
            break
    for b, words in BUCKET_WORDS.items():
        if any(w in q for w in words):
            intent.bucket = b
            break

    m = re.search(r"\btop\s+(\d+)|(?:highest|best|worst)\s+(\d+)?", q)
    if m:
        intent.top_n = int(m.group(1) or m.group(2) or 10) if (m.group(1) or m.group(2)) else 5
        intent.top_n = min(intent.top_n, 50)

    pm = re.search(r"(?:last|past)\s+(\d+)\s+(day|days|week|weeks|month|months)", q)
    if pm:
        n, unit = int(pm.group(1)), pm.group(2)
        intent.period_days = n * {"d": 1, "w": 7, "m": 30}[unit[0]]

    intent.filters = _detect_dim_filter(q, ctx)
    intent.compare_values = [f["value"] for f in intent.filters]

    trend_signals = ["trend", "over time", "monthly", "weekly", "daily",
                     "yearly", "per month", "by month", "by week", "by day", "evolution"]
    ranking_signals = ["top ", "highest", "best", "worst", "largest", "biggest",
                       "leading", "most"]
    breakdown_signals = [" by ", "breakdown", "split by", "distribution", "across"]
    compare_signals = [" vs ", " versus ", "compare", "difference between"]

    if any(s in q for s in trend_signals) and intent.date_col and (intent.metric_col or intent.agg):
        intent.kind = "trend"
        intent.agg = intent.agg or "sum"
        intent.rationale = f"time series of {intent.agg} {intent.metric_col or 'rows'}"
    elif len(intent.compare_values) >= 2 and any(s in q for s in compare_signals):
        intent.kind = "comparison"
        intent.agg = intent.agg or "sum"
        intent.dim_col = next(
            (f["column"] for f in intent.filters), intent.dim_col
        )
        intent.rationale = f"comparing {intent.compare_values} on {intent.metric_col or 'rows'}"
    elif any(s in q for s in ranking_signals) and intent.dim_col:
        intent.kind = "ranking"
        intent.agg = intent.agg or "sum"
        intent.rationale = f"top {intent.top_n} {intent.dim_col} by {intent.metric_col or 'count'}"
    elif any(s in q for s in breakdown_signals) and intent.dim_col:
        intent.kind = "breakdown"
        intent.agg = intent.agg or "sum"
        intent.rationale = f"{intent.metric_col or 'rows'} by {intent.dim_col}"
    elif intent.agg in ("count", "count_distinct"):
        intent.kind = "metric"
        intent.rationale = "row count"
    elif intent.agg and intent.metric_col:
        intent.kind = "metric"
        intent.rationale = f"{intent.agg} of {intent.metric_col}"
    elif intent.metric_col:
        # A bare metric reference ("what is our revenue") → total
        intent.kind = "metric"
        intent.agg = "sum"
        intent.rationale = f"total {intent.metric_col}"

    if intent.agg and intent.agg != "count" and intent.agg != "count_distinct" and not intent.metric_col:
        if numeric_cols:
            intent.metric_col = sorted(numeric_cols)[0]
        else:
            intent.kind = "unsupported"

    return intent
