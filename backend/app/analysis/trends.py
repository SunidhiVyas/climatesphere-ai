"""Trend statistics on annual series: OLS, Theil-Sen, Mann-Kendall, rolling mean, decadal comparison."""
from __future__ import annotations

import math

import numpy as np
from scipy import stats

MIN_RELIABLE_YEARS = 10


def _clean(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(y)
    return x[m], y[m]


def mann_kendall(y) -> dict:
    """Non-parametric Mann-Kendall test (tie-corrected, no autocorrelation correction)."""
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    n = len(y)
    if n < 4:
        return {"n": n, "tau": None, "z": None, "p": None, "trend": "insufficient data"}
    s = sum(np.sign(y[j] - y[i]) for i in range(n - 1) for j in range(i + 1, n))
    _, counts = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in counts)) / 18
    if var <= 0:
        return {"n": n, "tau": 0.0, "z": 0.0, "p": 1.0, "trend": "no trend"}
    z = 0.0 if s == 0 else (s - np.sign(s)) / math.sqrt(var)
    p = float(2 * stats.norm.sf(abs(z)))
    return {"n": n, "tau": round(float(s / (n * (n - 1) / 2)), 4), "z": round(float(z), 3), "p": round(p, 4),
            "trend": "no trend" if p >= 0.05 else ("increasing" if z > 0 else "decreasing")}


def ols(x, y) -> dict:
    x, y = _clean(x, y)
    if len(x) < 4 or np.ptp(x) == 0:
        return {"n": len(x), "slope_per_decade": None, "p": None, "r2": None, "ci95_per_decade": None}
    r = stats.linregress(x, y)
    tcrit = stats.t.ppf(0.975, len(x) - 2)
    return {"n": len(x), "slope_per_decade": round(float(r.slope) * 10, 4), "p": round(float(r.pvalue), 4),
            "r2": round(float(r.rvalue ** 2), 4),
            "ci95_per_decade": [round(float(r.slope - tcrit * r.stderr) * 10, 4), round(float(r.slope + tcrit * r.stderr) * 10, 4)],
            "_fit": (float(r.slope), float(r.intercept))}


def sen(x, y) -> dict:
    x, y = _clean(x, y)
    if len(x) < 4 or np.ptp(x) == 0:
        return {"slope_per_decade": None, "ci95_per_decade": None}
    sl, ic, lo, hi = stats.theilslopes(y, x, 0.95)
    return {"slope_per_decade": round(float(sl) * 10, 4), "ci95_per_decade": [round(float(lo) * 10, 4), round(float(hi) * 10, 4)]}


def rolling_mean(y, window: int = 5) -> list[float | None]:
    """Centred, NaN-aware rolling mean; needs >= half the window populated."""
    y = np.asarray(y, float)
    h, out = window // 2, []
    for i in range(len(y)):
        w = y[max(0, i - h): i + h + 1]
        w = w[np.isfinite(w)]
        out.append(round(float(w.mean()), 3) if len(w) >= (window + 1) // 2 else None)
    return out


def decade_change(years, y) -> dict:
    """Mean of the first vs last 10 years (halves when the period is shorter than 20 years)."""
    years, y = np.asarray(years), np.asarray(y, float)
    ok = np.isfinite(y)
    yy, vv = years[ok], y[ok]
    if len(yy) < 6:
        return {"first_mean": None, "last_mean": None, "pct": None}
    k = 10 if len(yy) >= 20 else len(yy) // 2
    first, last = vv[:k].mean(), vv[-k:].mean()
    pct = None if first < 0.05 else round(float((last - first) / first * 100), 1)  # undefined when baseline ~ 0
    return {"first_mean": round(float(first), 3), "last_mean": round(float(last), 3), "pct": pct,
            "first_period": [int(yy[0]), int(yy[k - 1])], "last_period": [int(yy[-k]), int(yy[-1])]}


def trend_block(years, y) -> tuple[dict, list[float | None]]:
    """Full statistics for one annual series + OLS fitted values for plotting."""
    o = ols(years, y)
    fit = o.pop("_fit", None)
    fitted = [None if fit is None else round(fit[0] * float(t) + fit[1], 3) for t in years]
    n = int(np.isfinite(np.asarray(y, float)).sum())
    return {"n": n, "reliable": n >= MIN_RELIABLE_YEARS, "mann_kendall": mann_kendall(y), "ols": o,
            "sen": sen(years, y), "decade_change": decade_change(years, y)}, fitted
