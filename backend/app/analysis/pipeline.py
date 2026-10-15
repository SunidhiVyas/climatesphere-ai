"""End-to-end analysis for one region/hazard: clean -> detect -> annual metrics -> trends -> honest insight text."""
from __future__ import annotations

import numpy as np

from .hazards import HAZARDS, detect
from .quality import clean_daily
from .trends import rolling_mean, trend_block

ROLL = 5
DEFINITIONS = {
    "heatwave": "{min_days}+ consecutive days with maximum temperature above the {pct:g}th percentile "
                "({scope}) of the region's daily Tmax.",
    "rainfall": "Days with precipitation above the {pct:g}th percentile of wet days (≥ 1 mm), "
                "events of {min_days}+ consecutive day(s).",
    "drought": "Dry spells: {min_days}+ consecutive days with less than 1 mm of precipitation "
               "(a simple drought proxy, not SPI/PDSI).",
}


def json_safe(o):
    """NaN/inf are not valid JSON -> null (recursively)."""
    if isinstance(o, float):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if isinstance(o, np.generic):
        return json_safe(o.item())
    return o


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(float(np.mean(xs)), 3) if xs else None


def build_insight(a: dict) -> dict:
    """Plain-language findings that never overstate: significance and caveats are always reported."""
    label = a["label"].lower()
    t = a["trend"]["hazard_days"]
    dc, mk, sen = t["decade_change"], t["mann_kendall"], t["sen"]
    unit = a["units"]["hazard_days"]
    caveats = [
        "Reanalysis data (ERA5) is gridded model output, not station measurements; areal averages smooth local extremes.",
        "Thresholds are computed from the same period that is analysed, so results describe change within the window.",
    ]
    if a["period"]["years_excluded"]:
        caveats.append(f"{len(a['period']['years_excluded'])} year(s) were excluded for <90% data coverage: "
                       f"{', '.join(map(str, a['period']['years_excluded']))}.")
    if not t["reliable"]:
        caveats.append(f"Only {t['n']} usable years - too short for a reliable trend (10+ recommended).")
    if mk["p"] is not None:
        caveats.append("Mann-Kendall assumes independent years; year-to-year persistence can make p-values optimistic.")

    if dc["first_mean"] is None or mk["p"] is None:
        return {"headline": f"Not enough valid years to assess a {label} trend.", "bullets": [], "caveats": caveats,
                "significant": False}

    fp, lp = dc["first_period"], dc["last_period"]
    base = f"{label.capitalize()} days averaged {dc['first_mean']:.1f} {unit} in {fp[0]}–{fp[1]} and {dc['last_mean']:.1f} in {lp[0]}–{lp[1]}"
    sig = mk["p"] < 0.05 and t["reliable"]
    if dc["pct"] is not None:
        chg = f"{'+' if dc['pct'] >= 0 else '−'}{abs(dc['pct']):.0f}%"
    else:
        chg = "change not expressed as % (near-zero baseline)"
    direction = "increased" if (mk["z"] or 0) > 0 else "decreased"
    if sig:
        head = (f"{label.capitalize()} days have {direction} significantly in {a['region']['name']}: "
                f"{dc['first_mean']:.1f} → {dc['last_mean']:.1f} {unit} ({chg}; Mann-Kendall p = {mk['p']:.3f}).")
    else:
        head = (f"No statistically significant {label} trend detected in {a['region']['name']} "
                f"(Mann-Kendall p = {mk['p']:.2f}); the {chg} difference between decades is within natural variability.")
    bullets = [f"{base} ({chg})."]
    if sen["slope_per_decade"] is not None:
        lo, hi = sen["ci95_per_decade"]
        bullets.append(f"Theil-Sen slope: {sen['slope_per_decade']:+.2f} {unit} per decade (95% CI {lo:+.2f} to {hi:+.2f}).")
    d = a["trend"]["duration"]["decade_change"]
    if d["first_mean"] is not None and d["last_mean"] is not None:
        bullets.append(f"Average event duration: {d['first_mean']:.1f} → {d['last_mean']:.1f} days.")
    i = a["trend"]["intensity"]["decade_change"] if a["units"]["intensity"] else None
    if i and i["first_mean"] is not None and i["last_mean"] is not None:
        bullets.append(f"Average intensity: {i['first_mean']:.1f} → {i['last_mean']:.1f} {a['units']['intensity']}.")
    return {"headline": head, "bullets": bullets, "caveats": caveats, "significant": bool(sig)}


def run_analysis(region: dict, dates: np.ndarray, raw: dict, *, hazard: str, start: int, end: int,
                 pct: float, min_days: int, mode: str) -> dict:
    cfg = HAZARDS[hazard]
    arrays, quality = clean_daily(dates, raw["tmax"], raw["tmin"], raw["precip"])
    events, thr_info, ok_years = detect(hazard, dates, arrays, quality["coverage"], pct, min_days, mode)

    years = list(range(start, end + 1))
    excluded = [y for y in years if y not in ok_years]
    freq, hdays, dur, inten, peak = [], [], [], [], []
    for y in years:
        if y not in ok_years:
            for lst in (freq, hdays, dur, inten, peak):
                lst.append(None)
            continue
        ev = [e for e in events if e["year"] == y]
        freq.append(len(ev))
        hdays.append(sum(e["duration"] for e in ev))
        dur.append(_mean([e["duration"] for e in ev]))
        inten.append(_mean([e["intensity"] for e in ev]) if cfg["units"]["intensity"] else None)
        peak.append(max((e["peak"] for e in ev), default=None))

    trend, fit = {}, {}
    for name, series in (("frequency", freq), ("hazard_days", hdays), ("duration", dur), ("intensity", inten)):
        arr = [np.nan if v is None else v for v in series]
        trend[name], fit[name] = trend_block(years, arr)

    decades = []
    for d0 in range((start // 10) * 10, end + 1, 10):
        ys = [y for y in years if d0 <= y < d0 + 10 and y in ok_years]
        if len(ys) >= 5:
            decades.append({"label": f"{d0}s", "years": len(ys),
                            "events_per_year": _mean([freq[years.index(y)] for y in ys]),
                            "hazard_days_per_year": _mean([hdays[years.index(y)] for y in ys])})

    season = [0] * 12
    for e in events:
        season[int(e["start"][5:7]) - 1] += 1

    scope = "calendar-day, ±7-day window" if mode == "seasonal" else "all days pooled"
    result = {
        "hazard": hazard, "label": cfg["label"], "region": region,
        "period": {"from": start, "to": end, "years_analyzed": len(years) - len(excluded), "years_excluded": excluded},
        "definition": {"text": DEFINITIONS[hazard].format(min_days=min_days, pct=pct, scope=scope),
                       "baseline": f"{start}–{end}", **thr_info},
        "years": years,
        "series": {"frequency": freq, "hazard_days": hdays, "duration": dur, "intensity": inten, "peak": peak},
        "units": cfg["units"],
        "rolling": {"window": ROLL, "frequency": rolling_mean([np.nan if v is None else v for v in freq], ROLL),
                    "hazard_days": rolling_mean([np.nan if v is None else v for v in hdays], ROLL)},
        "fit": {"frequency": fit["frequency"], "hazard_days": fit["hazard_days"]},
        "trend": trend, "decades": decades, "seasonality": season,
        "event_count": len(events),
        "events": sorted(events, key=lambda e: (e["duration"], e.get("intensity") or 0), reverse=True)[:30],
        "all_events": events[:2000],
        "data_quality": {k: v for k, v in quality.items() if k != "coverage"}
                        | {"coverage_pct_by_year": {str(y): round(100 * c["tmax"], 1) for y, c in quality["coverage"].items()}},
    }
    result["insight"] = build_insight(result)
    return json_safe(result)
