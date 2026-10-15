"""Hazard definitions and event detection.

heatwave  >= min_days consecutive days with Tmax above the P-th percentile of that calendar day
          (seasonal mode: +/-7-day window pooled over all years; annual mode: one threshold for all days)
rainfall  days with precipitation above the P-th percentile of wet days (>= 1 mm)   [ETCCDI R95p-style]
drought   dry spells: >= min_days consecutive days with < 1 mm   (a proxy - not SPI/PDSI)
"""
from __future__ import annotations

import warnings

import numpy as np

from .quality import doy_index, find_runs, year_of

WET_MM = 1.0

HAZARDS = {
    "heatwave": {"label": "Heatwave", "default_min_days": 3, "var": "tmax",
                 "units": {"frequency": "events/yr", "hazard_days": "heatwave days/yr", "intensity": "°C above threshold", "duration": "days"}},
    "rainfall": {"label": "Heavy rainfall", "default_min_days": 1, "var": "precip",
                 "units": {"frequency": "events/yr", "hazard_days": "heavy-rain days/yr", "intensity": "mm/day", "duration": "days"}},
    "drought": {"label": "Dry spell (drought proxy)", "default_min_days": 15, "var": "precip",
                "units": {"frequency": "spells/yr", "hazard_days": "dry-spell days/yr", "intensity": None, "duration": "days"}},
}


def seasonal_threshold(values, doy, years, pct, window: int = 7) -> np.ndarray:
    """Per-calendar-day percentile; returns an array aligned with `values`."""
    mat = np.full((years.max() - years.min() + 1, 366), np.nan)
    mat[years - years.min(), doy - 1] = values
    thr = np.full(366, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for d in range(366):
            pool = mat[:, np.arange(d - window, d + window + 1) % 366].ravel()
            pool = pool[np.isfinite(pool)]
            if len(pool) >= 30:
                thr[d] = np.percentile(pool, pct)
    # Feb 29 has few samples; fall back to neighbours if undefined
    for d in np.flatnonzero(np.isnan(thr)):
        thr[d] = np.nanmean(thr[[(d - 1) % 366, (d + 1) % 366]])
    return thr[doy - 1]


def detect(hazard: str, dates, arrays: dict, coverage: dict, pct: float, min_days: int, mode: str):
    """Returns (events, threshold_info). Events are dicts sorted by start date."""
    cfg = HAZARDS[hazard]
    var = cfg["var"]
    yrs, doy = year_of(dates), doy_index(dates)
    ok_years = {y for y, c in coverage.items() if c[var] >= 0.90}
    ok = np.isin(yrs, list(ok_years))
    v = np.where(ok, arrays[var], np.nan)

    info: dict = {"percentile": pct, "min_days": min_days, "mode": mode}
    if hazard == "heatwave":
        if mode == "seasonal":
            thr = seasonal_threshold(v, doy, yrs, pct)
        else:
            thr = np.full(len(v), np.nanpercentile(v, pct))
        mask = v > thr
        info.update(unit="°C", min=round(float(np.nanmin(thr)), 1), max=round(float(np.nanmax(thr)), 1),
                    mean=round(float(np.nanmean(thr)), 1))
    elif hazard == "rainfall":
        wet = v[np.isfinite(v) & (v >= WET_MM)]
        t = float(np.percentile(wet, pct)) if len(wet) >= 30 else float("nan")
        thr = np.full(len(v), t)
        mask = v > t
        info.update(unit="mm/day", mean=round(t, 1), min=round(t, 1), max=round(t, 1), wet_day_mm=WET_MM)
    else:  # drought / dry spell
        thr = np.full(len(v), WET_MM)
        mask = np.isfinite(v) & (v < WET_MM)
        info.update(unit="mm/day", mean=WET_MM, min=WET_MM, max=WET_MM, wet_day_mm=WET_MM)

    events = []
    for s, e in find_runs(mask):
        if e - s < min_days:
            continue
        seg = v[s:e]
        ev = {"start": str(dates[s])[:10], "end": str(dates[e - 1])[:10], "duration": int(e - s), "year": int(yrs[s])}
        if hazard == "heatwave":
            exc = seg - thr[s:e]
            ev.update(peak=round(float(seg.max()), 1), intensity=round(float(exc.mean()), 2))
        elif hazard == "rainfall":
            ev.update(peak=round(float(seg.max()), 1), intensity=round(float(seg.mean()), 1), total_mm=round(float(seg.sum()), 1))
        else:
            ev.update(peak=float(e - s), intensity=None)
        events.append(ev)
    return events, info, ok_years
