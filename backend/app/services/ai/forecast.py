"""Forecasting: additive Holt-Winters → Holt's linear trend →
seasonal-naive fallback, selected automatically by series length.
Small grid search picks smoothing params by SSE. Pure numpy — no
statsmodels dependency."""

import math
from datetime import date, timedelta

import numpy as np
from dateutil.relativedelta import relativedelta

BUCKET_SEASON = {"day": 7, "week": 4, "month": 12, "quarter": 4, "year": 1}
BUCKET_STEP = {
    "day": relativedelta(days=1),
    "week": relativedelta(weeks=1),
    "month": relativedelta(months=1),
    "quarter": relativedelta(months=3),
    "year": relativedelta(years=1),
}


def _hw_sse(y: np.ndarray, season: int, a: float, b: float, g: float) -> tuple[float, tuple]:
    """Holt-Winters additive; returns (sse, (level, trend, seasonal))."""
    n = len(y)
    level = y[:season].mean()
    trend = (y[season:2 * season].mean() - level) / season if n >= 2 * season else 0.0
    seas = y[:season] - level
    sse = 0.0
    for i in range(n):
        f = level + trend + seas[i % season]
        sse += (y[i] - f) ** 2
        prev_level = level
        level = a * (y[i] - seas[i % season]) + (1 - a) * (level + trend)
        trend = b * (level - prev_level) + (1 - b) * trend
        seas[i % season] = g * (y[i] - level) + (1 - g) * seas[i % season]
    return sse, (level, trend, seas.copy())


def _holt_sse(y: np.ndarray, a: float, b: float) -> tuple[float, tuple]:
    level, trend = y[0], y[1] - y[0]
    sse = 0.0
    for i in range(1, len(y)):
        f = level + trend
        sse += (y[i] - f) ** 2
        prev = level
        level = a * y[i] + (1 - a) * f
        trend = b * (level - prev) + (1 - b) * trend
    return sse, (level, trend)


def forecast(
    points: list[dict], *, horizon: int, bucket: str
) -> dict:
    """points: [{t, value}] chronological. Returns method + forecast rows
    with confidence intervals."""
    if len(points) < 3:
        raise ValueError("Need at least 3 points to forecast")

    y = np.array([p["value"] for p in points], dtype=float)
    n = len(y)
    season = BUCKET_SEASON.get(bucket, 1)
    resid_std = 0.0

    if season > 1 and n >= 2 * season:
        best = min(
            (
                _hw_sse(y, season, a, b, g)
                for a in (0.2, 0.4, 0.6)
                for b in (0.05, 0.1)
                for g in (0.05, 0.15)
            ),
            key=lambda x: x[0],
        )
        _, (level, trend, seas) = best
        method = "holt_winters"
        fc = [
            float(level + (h + 1) * trend + seas[(n + h) % season])
            for h in range(horizon)
        ]
        fitted_sse = best[0]
        resid_std = math.sqrt(fitted_sse / max(n - 3, 1))
    elif n >= 4:
        best = min(
            (_holt_sse(y, a, b) for a in (0.2, 0.4, 0.6, 0.8) for b in (0.02, 0.05, 0.1)),
            key=lambda x: x[0],
        )
        _, (level, trend) = best
        method = "holt_linear"
        fc = [float(level + (h + 1) * trend) for h in range(horizon)]
        resid_std = math.sqrt(best[0] / max(n - 2, 1))
    else:
        method = "naive"
        fc = [float(y[-1])] * horizon
        resid_std = float(y.std()) or abs(float(y[-1])) * 0.1 or 1.0

    # Next-period labels from the last series label.
    last_t = _parse_period(points[-1]["t"], bucket)
    step = BUCKET_STEP.get(bucket, relativedelta(months=1))
    labels = [
        _fmt_period(last_t + step * (h + 1), bucket) for h in range(horizon)
    ]

    z = 1.28  # ~80% interval
    rows = []
    for h in range(horizon):
        margin = z * resid_std * math.sqrt(h + 1)
        rows.append(
            {
                "t": labels[h],
                "forecast": round(fc[h], 2),
                "lower": round(fc[h] - margin, 2),
                "upper": round(fc[h] + margin, 2),
            }
        )
    return {"method": method, "points": rows, "residStd": round(resid_std, 2)}


def _parse_period(t: str, bucket: str) -> date:
    """Parse bucket labels back to dates."""
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return date.fromisoformat(t) if fmt == "%Y-%m-%d" else _from_fmt(t, fmt)
        except ValueError:
            continue
    # Week/quarter labels like "2024-W05" / "2024-Q2" — approximate.
    if "-W" in t:
        y, w = t.split("-W")
        return date.fromisocalendar(int(y), int(w), 1)
    if "-Q" in t:
        y, q = t.split("-Q")
        return date(int(y), (int(q) - 1) * 3 + 1, 1)
    return date.today()


def _from_fmt(t: str, fmt: str) -> date:
    from datetime import datetime

    return datetime.strptime(t, fmt).date()


def _fmt_period(d: date, bucket: str) -> str:
    if bucket == "day":
        return d.isoformat()
    if bucket == "week":
        return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
    if bucket == "quarter":
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    if bucket == "year":
        return str(d.year)
    return d.strftime("%Y-%m")
