import numpy as np
from app.analysis import trends
from app.analysis.hazards import detect
from app.analysis.pipeline import run_analysis
from app.analysis.quality import clean_daily, find_runs
from .conftest import synth_daily


def _arrays(start, end):
    t, tx, tn, pr = synth_daily(start, end)
    f = lambda v: np.array([np.nan if x is None else x for x in v], float)
    return np.array(t, dtype="datetime64[D]"), f(tx), f(tn), f(pr)


def test_find_runs():
    assert find_runs(np.array([0, 1, 1, 0, 1, 1, 1], bool)) == [(1, 3), (4, 7)]


def test_quality_removes_spike_bridges_short_gap_keeps_long_gap():
    d, tx, tn, pr = _arrays("1999-01-01", "2003-12-31")
    clean, rep = clean_daily(d, tx, tn, pr)
    assert rep["out_of_range"] >= 1 and np.nanmax(clean["tmax"]) < 60           # 140°C removed
    assert rep["interpolated_days"] >= 1                                          # 1-day gap bridged
    i = int(np.flatnonzero(d == np.datetime64("2000-04-12"))[0])
    assert np.isnan(clean["tmax"][i])                                             # 5-day gap NOT bridged
    assert rep["coverage"][2000]["tmax"] > 0.98


def test_heatwave_detection_counts_and_min_length():
    d, tx, tn, pr = _arrays("1990-01-01", "2013-12-31")
    clean, rep = clean_daily(d, tx, tn, pr)
    ev, info, _ = detect("heatwave", d, clean, rep["coverage"], 95, 3, "seasonal")
    assert all(e["duration"] >= 3 for e in ev)
    per_year = {y: sum(1 for e in ev if e["year"] == y) for y in range(1990, 2014)}
    early = sum(per_year[y] for y in range(1990, 1996)); late = sum(per_year[y] for y in range(2008, 2014))
    assert late > early > 0                                                       # injected increase is found
    ev5, *_ = detect("heatwave", d, clean, rep["coverage"], 95, 8, "seasonal")
    assert len(ev5) < len(ev)


def test_pipeline_trend_is_increasing_and_significant():
    d, tx, tn, pr = _arrays("1990-01-01", "2019-12-31")
    a = run_analysis({"name": "T"}, d, {"tmax": tx, "tmin": tn, "precip": pr}, hazard="heatwave", start=1990, end=2019,
                     pct=95, min_days=3, mode="seasonal")
    t = a["trend"]["hazard_days"]
    assert t["mann_kendall"]["trend"] == "increasing" and t["mann_kendall"]["p"] < 0.05
    assert a["insight"]["significant"] and "increased" in a["insight"]["headline"]
    assert len(a["years"]) == 30 and len(a["series"]["frequency"]) == 30


def test_mann_kendall_known_values():
    mk = trends.mann_kendall(list(range(12)))
    assert mk["tau"] == 1.0 and mk["p"] < 0.001 and mk["trend"] == "increasing"
    assert trends.mann_kendall([5] * 12)["trend"] == "no trend"
    flat = trends.mann_kendall([1, 3, 2, 3, 1, 2, 3, 2, 1, 2, 3, 1])
    assert flat["p"] > 0.05


def test_decade_change_handles_zero_baseline():
    assert trends.decade_change(range(2000, 2020), [0] * 10 + [2] * 10)["pct"] is None
    assert trends.decade_change(range(2000, 2020), [1] * 10 + [2] * 10)["pct"] == 100.0
