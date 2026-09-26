"""Pandas-based dataset profiling: column normalization, type inference,
per-column statistics and a dataset quality score."""

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

INFERRED_TYPES = ("string", "integer", "float", "boolean", "date", "datetime")
DATETIME_HINT = re.compile(r"[-/:]")
TOP_VALUES_LIMIT = 10
IQR_OUTLIER_K = 1.5


def normalize_column_names(columns: list[str]) -> list[str]:
    """lowercase snake_case, unique, safe as SQL identifiers."""
    out: list[str] = []
    seen: dict[str, int] = {}
    for raw in columns:
        name = re.sub(r"[^0-9a-zA-Z]+", "_", str(raw).strip().lower()).strip("_")
        if not name or name[0].isdigit():
            name = f"c_{name}"
        base, n = name, seen.get(name, 1)
        while name in seen:
            n += 1
            name = f"{base}_{n}"
        seen[base] = n
        seen[name] = 1
        out.append(name)
    return out


def _infer_column(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    sample = series.dropna().astype(str)
    if sample.empty:
        return "string"

    # Boolean-like strings
    lowered = sample.str.lower().unique()
    if set(lowered) <= {"true", "false", "0", "1", "yes", "no"}:
        return "boolean"

    numeric = pd.to_numeric(sample, errors="coerce")
    if numeric.notna().mean() >= 0.9:
        frac = (numeric.dropna() % 1 != 0).mean()
        return "float" if frac > 0 else "integer"

    # Only try date parsing when values look date-ish.
    head = sample.head(100)
    if head.str.contains(DATETIME_HINT).mean() >= 0.8:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed", dayfirst=False)
        if parsed.notna().mean() >= 0.85:
            return "date" if (parsed.dt.hour == 0).all() and (parsed.dt.minute == 0).all() else "datetime"

    return "string"


def infer_types(df: pd.DataFrame) -> dict[str, str]:
    return {col: _infer_column(df[col]) for col in df.columns}


def coerce_types(df: pd.DataFrame, type_map: dict[str, str]) -> pd.DataFrame:
    df = df.copy()
    for col, t in type_map.items():
        s = df[col]
        try:
            if t in ("integer", "float"):
                df[col] = pd.to_numeric(s, errors="coerce")
            elif t == "boolean":
                df[col] = s.map(
                    lambda v: (
                        True if str(v).lower() in ("true", "1", "yes")
                        else False if str(v).lower() in ("false", "0", "no")
                        else (bool(v) if isinstance(v, (bool, np.bool_)) else None)
                    )
                )
            elif t == "date":
                df[col] = pd.to_datetime(s, errors="coerce", format="mixed").dt.date
            elif t == "datetime":
                df[col] = pd.to_datetime(s, errors="coerce", format="mixed")
            else:
                df[col] = s.where(s.isna(), s.astype(str))
        except Exception:
            df[col] = s.where(s.isna(), s.astype(str))
    return df


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str
    null_count: int
    distinct_count: int
    min_value: str | None = None
    max_value: str | None = None
    mean: float | None = None
    median: float | None = None
    stddev: float | None = None
    outlier_count: int | None = None
    top_values: list[dict] = field(default_factory=list)


def profile_dataframe(df: pd.DataFrame, type_map: dict[str, str]) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []
    for col in df.columns:
        s = df[col]
        t = type_map[col]
        p = ColumnProfile(
            name=col,
            inferred_type=t,
            null_count=int(s.isna().sum()),
            distinct_count=int(s.nunique(dropna=True)),
        )
        non_null = s.dropna()
        if not non_null.empty:
            p.min_value = str(non_null.min())
            p.max_value = str(non_null.max())
        if t in ("integer", "float") and not non_null.empty:
            numeric = pd.to_numeric(non_null, errors="coerce").dropna()
            if not numeric.empty:
                p.mean = float(numeric.mean())
                p.median = float(numeric.median())
                p.stddev = float(numeric.std()) if len(numeric) > 1 else 0.0
                q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
                iqr = q3 - q1
                low, high = q1 - IQR_OUTLIER_K * iqr, q3 + IQR_OUTLIER_K * iqr
                p.outlier_count = int(((numeric < low) | (numeric > high)).sum())
        if t in ("string", "boolean") or p.distinct_count <= 30:
            vc = s.value_counts(dropna=False).head(TOP_VALUES_LIMIT)
            p.top_values = [
                {"value": None if pd.isna(v) else str(v), "count": int(c)}
                for v, c in vc.items()
            ]
        profiles.append(p)
    return profiles


def quality_score(df: pd.DataFrame) -> float:
    """0–100 score: 100 minus weighted penalties for missing & duplicate data."""
    if df.empty:
        return 0.0
    missing_penalty = float(df.isna().mean().mean()) * 50
    dup_penalty = float(df.duplicated().mean()) * 40
    return round(max(0.0, 100.0 - missing_penalty - dup_penalty), 2)
