"""Grounded explanations: summaries may only cite numbers that actually
appeared in the result rows. LLM explanations get the real numbers in the
prompt; deterministic templates compute them directly."""

from app.services.ai.llm_provider import LLMProvider


def _fmt(v) -> str:
    if v is None:
        return "0"
    try:
        f = float(v)
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:,.2f}M"
        if abs(f) >= 10_000:
            return f"{f:,.0f}"
        return f"{f:,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(v)


def explain(
    *,
    question: str,
    intent_kind: str,
    columns: list[str],
    rows: list[dict],
    chart_type: str | None,
    provider: LLMProvider | None = None,
) -> dict:
    """Return {summary, detail} — grounded in `rows` only."""
    n = len(rows)
    if n == 0:
        return {
            "summary": "No data matched that question.",
            "detail": "The query ran successfully but returned zero rows. "
                      "Try a wider date range or a different filter.",
        }

    # LLM path — numbers are injected into the prompt, never invented.
    if provider is not None:
        sample = rows[:30]
        prompt = (
            f"Question: {question}\n"
            f"Columns: {columns}\n"
            f"Result rows ({n} total, first {len(sample)}): {sample}\n\n"
            'Respond as JSON {"summary": "one sentence answer", "detail": '
            '"2-3 sentences interpreting the result for a business analyst"}. '
            "Cite only numbers present in the rows."
        )
        try:
            out = provider.complete_json(
                "You explain query results to business users. Be precise; "
                "never invent numbers. JSON only.", prompt
            )
            if out and out.get("summary"):
                return {"summary": out["summary"], "detail": out.get("detail", "")}
        except Exception:
            pass  # deterministic fallback below

    val_col = columns[-1] if columns else None
    values = [r.get(val_col) for r in rows] if val_col else []

    if intent_kind == "metric" and n == 1:
        return {
            "summary": f"{val_col or 'Result'}: {_fmt(rows[0].get(val_col))}",
            "detail": f"The {val_col} across the selected data is "
                      f"{_fmt(rows[0].get(val_col))}.",
        }

    if intent_kind == "trend" and val_col and len(rows) > 1:
        first, last = rows[0].get(val_col), rows[-1].get(val_col)
        numeric = [(i, float(v)) for i, v in enumerate(values) if v is not None]
        summary = f"Trend from {rows[0].get('t', 'start')} to {rows[-1].get('t', 'end')}"
        detail = ""
        if numeric and first:
            change = (numeric[-1][1] - numeric[0][1]) / abs(numeric[0][1] or 1) * 100
            peak_i = max(numeric, key=lambda x: x[1])[0]
            summary = (
                f"{val_col} {'grew' if change >= 0 else 'declined'} "
                f"{abs(change):.1f}% over the period"
            )
            detail = (
                f"Started at {_fmt(first)} ({rows[0].get('t')}), ended at "
                f"{_fmt(last)} ({rows[-1].get('t')}). Peak: "
                f"{_fmt(numeric[peak_i][1])} at {rows[peak_i].get('t')}."
            )
        return {"summary": summary, "detail": detail}

    if intent_kind in ("ranking", "breakdown") and val_col:
        total = sum(float(v) for v in values if v is not None) or 1
        top = rows[0]
        top_label = top.get("label", str(top.get(list(top)[0])))
        top_val = top.get(val_col)
        share = float(top_val) / total * 100 if top_val else 0
        runner = rows[1] if n > 1 else None
        summary = f"{top_label} leads with {_fmt(top_val)} ({share:.0f}% share)"
        detail = f"Top {min(n, 10)} of {n} groups. " + (
            f"Runner-up: {runner.get('label')} at {_fmt(runner.get(val_col))}."
            if runner
            else "Only one group present."
        )
        return {"summary": summary, "detail": detail}

    if intent_kind == "comparison" and n >= 2 and val_col:
        a, b = rows[0], rows[1]
        av, bv = a.get(val_col), b.get(val_col)
        try:
            diff_pct = (float(av) - float(bv)) / abs(float(bv) or 1) * 100
            rel = f"{abs(diff_pct):.0f}% {'higher' if diff_pct >= 0 else 'lower'}"
        except (TypeError, ValueError):
            rel = "different"
        return {
            "summary": f"{a.get('label')} ({_fmt(av)}) vs {b.get('label')} ({_fmt(bv)})",
            "detail": f"{a.get('label')} is {rel} than {b.get('label')} on {val_col}.",
        }

    return {
        "summary": f"Query returned {n} row(s).",
        "detail": "See the results table for details.",
    }
