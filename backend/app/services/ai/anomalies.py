"""Anomaly detection over metric-over-time series.

Primary: z-score on detrended residuals when seasonality is detectable,
or raw values otherwise. Fallback for short series: IQR fences."""

from datetime import date

import numpy as np
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.dataset import DatasetVersion
from app.services.analytics import engine as aengine


def detect(
    engine: Engine,
    version: DatasetVersion,
    *,
    date_column: str,
    metric_column: str,
    bucket: str = "day",
    frm: date | None = None,
    to: date | None = None,
    z_threshold: float = 2.5,
) -> dict:
    """Return {series, anomalies:[{t,value,score,severity,direction,method}]}."""
    points = aengine.series(
        engine, version, date_column=date_column, metric_column=metric_column,
        agg="sum", bucket=bucket, frm=frm, to=to,
    )
    if len(points) < 8:
        raise AppError(
            "Need at least 8 data points for anomaly detection",
            "BAD_REQUEST", 400,
        )

    t = [p["t"] for p in points]
    y = np.array([p["value"] for p in points], dtype=float)
    n = len(y)

    # Detrend with a centered moving average when the series is long enough —
    # anomalies should be spikes/dips, not the seasonal wave itself.
    window = min(7, n // 4 * 2 + 1)
    if window >= 5:
        kernel = np.ones(window) / window
        trend = np.convolve(y, kernel, mode="same")
        # Fix edge effects.
        trend[: window // 2] = trend[window // 2]
        trend[-(window // 2) :] = trend[-(window // 2)]
        resid = y - trend
        base = trend
    else:
        resid = y - np.median(y)
        base = np.full(n, np.median(y))

    anomalies: list[dict] = []
    std = resid.std()
    if std > 0 and n >= 12:
        z = resid / std
        method = "zscore"
        flags = np.abs(z) > z_threshold
        scores = z
    else:
        q1, q3 = np.percentile(resid, [25, 75])
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        flags = (resid < low) | (resid > high)
        method = "iqr"
        scores = resid / (iqr or 1)

    for i, flag in enumerate(flags):
        if flag:
            score = float(scores[i])
            anomalies.append(
                {
                    "t": t[i],
                    "value": float(y[i]),
                    "expected": float(base[i]),
                    "score": round(score, 2),
                    "direction": "spike" if resid[i] > 0 else "dip",
                    "severity": "critical" if abs(score) > (4 if method == "zscore" else 6) else "warning",
                    "method": method,
                }
            )

    return {
        "series": points,
        "anomalies": sorted(anomalies, key=lambda a: -abs(a["score"])),
        "method": method,
        "points": n,
    }
