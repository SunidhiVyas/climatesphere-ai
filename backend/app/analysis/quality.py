"""Cleaning of noisy daily weather: units, physical bounds, inconsistencies, spikes, short gaps, coverage."""
from __future__ import annotations

import warnings

import numpy as np

BOUNDS = {"tmax": (-80.0, 60.0), "tmin": (-90.0, 50.0), "precip": (0.0, 2000.0)}  # physical limits (°C, °C, mm/day)
MIN_YEAR_COVERAGE = 0.90   # years with less valid data than this are excluded from trends
MAX_INTERP_GAP = 2         # only bridge gaps of <= 2 days (linear interpolation); longer gaps stay missing


def find_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of consecutive True values."""
    m = np.concatenate(([False], np.asarray(mask, bool), [False])).astype(np.int8)
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def doy_index(dates: np.ndarray) -> np.ndarray:
    """Day-of-year on a 366-day calendar (Feb 29 = 60) so leap and non-leap years line up."""
    d = dates.astype("datetime64[D]")
    yr = d.astype("datetime64[Y]")
    doy = (d - yr.astype("datetime64[D]")).astype(int) + 1
    y = yr.astype(int) + 1970
    leap = ((y % 4 == 0) & (y % 100 != 0)) | (y % 400 == 0)
    return np.where(~leap & (doy >= 60), doy + 1, doy)


def year_of(dates: np.ndarray) -> np.ndarray:
    return dates.astype("datetime64[Y]").astype(int) + 1970


def _doy_matrix(values: np.ndarray, doy: np.ndarray, years: np.ndarray) -> np.ndarray:
    m = np.full((years.max() - years.min() + 1, 366), np.nan)
    m[years - years.min(), doy - 1] = values
    return m


def _spike_mask(values, doy, years, window=7, z=8.0, min_abs=20.0) -> np.ndarray:
    """Robust outlier test: far from the pooled +/-7-day climatology in MAD units AND by an absolute margin.
    Real extremes (a few sigma) survive; sensor/reanalysis artefacts (tens of degrees off) do not."""
    mat = _doy_matrix(values, doy, years)
    med, sig = np.full(366, np.nan), np.full(366, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for d in range(366):
            pool = mat[:, np.arange(d - window, d + window + 1) % 366].ravel()
            if np.isfinite(pool).sum() >= 10:
                med[d] = np.nanmedian(pool)
                sig[d] = 1.4826 * np.nanmedian(np.abs(pool - med[d]))
    dev = np.abs(values - med[doy - 1])
    with np.errstate(invalid="ignore"):
        return (dev > min_abs) & (dev > z * np.maximum(sig[doy - 1], 1.0))


def _interp_short_gaps(v: np.ndarray, max_gap: int) -> tuple[np.ndarray, int]:
    out, filled = v.copy(), 0
    for s, e in find_runs(np.isnan(v)):
        if e - s <= max_gap and s > 0 and e < len(v):
            out[s:e] = np.interp(np.arange(s, e), [s - 1, e], [v[s - 1], v[e]])
            filled += e - s
    return out, filled


def clean_daily(dates: np.ndarray, tmax: np.ndarray, tmin: np.ndarray, precip: np.ndarray) -> tuple[dict, dict]:
    """Returns ({'tmax','tmin','precip'} cleaned arrays, quality report)."""
    n = len(dates)
    doy, yrs = doy_index(dates), year_of(dates)
    t_max, t_min, pr = tmax.astype(float).copy(), tmin.astype(float).copy(), precip.astype(float).copy()
    rep = {"days_total": int(n),
           "missing_raw": {"tmax": int(np.isnan(t_max).sum()), "precip": int(np.isnan(pr).sum())}}

    # 1) physical bounds
    with np.errstate(invalid="ignore"):
        bad_tx = (t_max < BOUNDS["tmax"][0]) | (t_max > BOUNDS["tmax"][1])
        bad_tn = (t_min < BOUNDS["tmin"][0]) | (t_min > BOUNDS["tmin"][1])
        bad_pr = (pr < BOUNDS["precip"][0]) | (pr > BOUNDS["precip"][1])
    rep["out_of_range"] = int(bad_tx.sum() + bad_tn.sum() + bad_pr.sum())
    t_max[bad_tx], t_min[bad_tn], pr[bad_pr] = np.nan, np.nan, np.nan

    # 2) logical consistency: Tmin must not exceed Tmax (we cannot tell which one is wrong -> drop Tmax)
    with np.errstate(invalid="ignore"):
        incons = t_min > t_max + 0.5
    rep["inconsistent_tmax_tmin"] = int(incons.sum())
    t_max[incons] = np.nan

    # 3) spikes
    sp = _spike_mask(t_max, doy, yrs)
    rep["spikes_removed"] = int(np.nansum(sp))
    t_max[sp] = np.nan

    # 4) short gaps (temperature only: interpolating rain would invent rainfall)
    t_max, filled = _interp_short_gaps(t_max, MAX_INTERP_GAP)
    rep["interpolated_days"] = int(filled)
    rep["missing_after"] = {"tmax": int(np.isnan(t_max).sum()), "precip": int(np.isnan(pr).sum())}

    # 5) per-year coverage
    cov = {}
    for y in np.unique(yrs):
        m = yrs == y
        cov[int(y)] = {"tmax": float(np.isfinite(t_max[m]).mean()), "precip": float(np.isfinite(pr[m]).mean())}
    rep["coverage"] = cov
    rep["low_coverage_years"] = sorted(int(y) for y, c in cov.items() if min(c["tmax"], c["precip"]) < MIN_YEAR_COVERAGE)
    rep["completeness_pct"] = round(100 * float(np.isfinite(t_max).mean()), 2) if n else 0.0
    return {"tmax": t_max, "tmin": t_min, "precip": pr}, rep
