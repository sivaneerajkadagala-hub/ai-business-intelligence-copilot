"""Builds the schema context exposed to SQL-generation engines.

Only this context is ever shown to the LLM or used by the rule engine —
it is derived from dataset metadata the user is authorized to see, so
unauthorized tables can never leak into a prompt or a query."""

import sqlalchemy as sa
from sqlalchemy import Engine

from app.models.dataset import Dataset, DatasetVersion
from app.services.datasets import tables


def build_schema_context(engine: Engine, dataset: Dataset, version: DatasetVersion) -> dict:
    columns = sorted(version.columns, key=lambda c: c.ordinal)
    return {
        "dataset": dataset.name,
        "table": tables.qualified_name(version.table_name, engine),
        "tableName": version.table_name,
        "rowCount": version.row_count,
        "columns": [
            {
                "name": c.normalized_name,
                "display": c.name,
                "type": c.inferred_type,
                "distinct": c.distinct_count,
                "sampleValues": [
                    t["value"] for t in (c.top_values or [])[:6] if t.get("value") is not None
                ],
            }
            for c in columns
        ],
    }


def describe_for_prompt(ctx: dict) -> str:
    lines = [f'TABLE "{ctx["table"]}" ({ctx["rowCount"]} rows) — dataset "{ctx["dataset"]}"']
    for c in ctx["columns"]:
        hint = f'  - "{c["name"]}" {c["type"]}'
        if c["sampleValues"]:
            vals = ", ".join(str(v) for v in c["sampleValues"][:5])
            hint += f" (e.g. {vals})"
        lines.append(hint)
    return "\n".join(lines)
