"""Real skill-demand forecasting — log-linear trend model over the curated
monthly demand series.

Demand/volume series are multiplicative (constant % growth), so we fit a linear
trend in log-space (OLS on log-demand) and exponentiate. This recovers the
underlying annualised growth rate faithfully and produces a natural exponential
forecast curve with a widening prediction band. It is a genuine, reproducible
statistical forecast in the same family BigQuery ML.FORECAST (ARIMA_PLUS) serves;
when BQML_DATASET is set, providers.py routes to BQML and this stays as the
offline default + parity reference. Deterministic: identical input → identical
output (SPEC R2/G4).
"""
from __future__ import annotations

import math
import statistics
from functools import lru_cache
from typing import Any, Dict

from app.engines import datasets as ds

Z = 1.28  # ~80% prediction interval


@lru_cache(maxsize=None)
def _fit(skill_id: str):
    """OLS fit of log(demand) on month index. Returns (intercept a, slope b,
    log-residual sigma, history tuple)."""
    y = ds.demand_series(skill_id)
    n = len(y)
    logs = [math.log(v) for v in y]
    xbar = (n - 1) / 2.0
    ybar = sum(logs) / n
    sxx = sum((t - xbar) ** 2 for t in range(n))
    sxy = sum((t - xbar) * (logs[t] - ybar) for t in range(n))
    b = sxy / sxx if sxx else 0.0
    a = ybar - b * xbar
    resid = [logs[t] - (a + b * t) for t in range(n)]
    sigma = statistics.pstdev(resid) if n > 1 else 0.0
    return a, b, sigma, y


@lru_cache(maxsize=None)
def skill_growth(skill_id: str) -> float:
    """Annualised demand growth implied by the fit (e.g. -0.18 == -18%/yr)."""
    _a, b, _sigma, _y = _fit(skill_id)
    return round(math.exp(12 * b) - 1.0, 4)


def forecast_demand(skill_id: str) -> Dict[str, Any]:
    """Full payload: 36 history points + 36 forecast points with a CI band."""
    a, b, sigma, y = _fit(skill_id)
    n = len(y)

    points = []
    for t in range(n):
        points.append({
            "month": ds.MONTH_LABELS[t],
            "value": round(y[t], 2),
            "upper": round(y[t], 2),
            "lower": round(y[t], 2),
            "is_forecast": False,
        })
    for h in range(1, ds.FORECAST_MONTHS + 1):
        t = n - 1 + h
        mean_log = a + b * t
        spread = Z * sigma * math.sqrt(h)
        points.append({
            "month": ds.MONTH_LABELS[t],
            "value": round(math.exp(mean_log), 2),
            "upper": round(math.exp(mean_log + spread), 2),
            "lower": round(math.exp(mean_log - spread), 2),
            "is_forecast": True,
        })

    growth = skill_growth(skill_id)
    direction = "up" if growth > 0.03 else "down" if growth < -0.03 else "flat"
    return {
        "skill": skill_id,
        "skill_label": ds.SKILL_NAME.get(skill_id, skill_id),
        "category": ds.SKILL_CATEGORY.get(skill_id, "rising"),
        "trend_direction": direction,
        "growth_rate_annual": growth,
        "current_index": round(y[-1], 2),
        "data_points": points,
        "data_source": (
            f"Log-linear trend forecast over a {n}-month {ds.MARKET} demand series "
            f"(BQML ML.FORECAST parity; reproducible)."
        ),
    }
