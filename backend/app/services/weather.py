"""Ingest + cache daily weather in MongoDB (one document per region-year; only missing years are fetched)."""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import date

import numpy as np

from ..db import get_db, utcnow
from ..regions import RegionSpec
from ..sources import open_meteo

CHUNK_YEARS = 12
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)   # single-flight per region
_upstream_slots = threading.BoundedSemaphore(4)                    # max concurrent heavy upstream fetches


def _days_in_year(y: int) -> int:
    return 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365


def _round(a: np.ndarray) -> list:
    return [None if np.isnan(v) else round(float(v), 1) for v in a]


def _split_years(fetched: dict) -> dict[int, dict]:
    d = np.array(fetched["times"], dtype="datetime64[D]")
    yrs = d.astype("datetime64[Y]").astype(int) + 1970
    out = {}
    for y in np.unique(yrs):
        m = yrs == y
        idx = (d[m] - np.datetime64(f"{y}-01-01")).astype(int)
        doc = {}
        for k in ("tmax", "tmin", "precip"):
            arr = np.full(_days_in_year(int(y)), np.nan)
            arr[idx] = fetched[k][m]
            doc[k] = _round(arr)
        out[int(y)] = doc
    return out


def _fetch_and_store(region: RegionSpec, years: list[int]) -> None:
    db = get_db()
    # contiguous groups, each limited to CHUNK_YEARS, so one failed call doesn't lose everything
    groups, cur = [], [years[0]]
    for y in years[1:]:
        if y == cur[-1] + 1 and len(cur) < CHUNK_YEARS:
            cur.append(y)
        else:
            groups.append(cur)
            cur = [y]
    groups.append(cur)
    for g in groups:
        with _upstream_slots:
            fetched = open_meteo.fetch_archive(region.sample_points(), date(g[0], 1, 1), date(g[-1], 12, 31))
        for y, doc in _split_years(fetched).items():
            if y in g:
                db.weather_years.replace_one(
                    {"_id": f"{region.key}:{y}"},
                    {"_id": f"{region.key}:{y}", "rkey": region.key, "year": y, **doc,
                     "source": "open-meteo/era5", "fetched_at": utcnow()},
                    upsert=True,
                )


def get_daily(region: RegionSpec, start: int, end: int) -> tuple[np.ndarray, dict, dict]:
    """Daily arrays for Jan 1 `start` .. Dec 31 `end`. Returns (dates, {'tmax','tmin','precip'}, meta)."""
    db = get_db()
    wanted = list(range(start, end + 1))

    def cached_years() -> set[int]:
        return {d["year"] for d in db.weather_years.find({"rkey": region.key, "year": {"$gte": start, "$lte": end}}, {"year": 1})}

    have = cached_years()
    missing = [y for y in wanted if y not in have]
    fetched_years = 0
    if missing:
        with _locks[region.key]:
            missing = [y for y in wanted if y not in cached_years()]  # someone else may have filled it
            if missing:
                _fetch_and_store(region, missing)
                fetched_years = len(missing)

    docs = {d["year"]: d for d in db.weather_years.find({"rkey": region.key, "year": {"$gte": start, "$lte": end}})}
    dates = np.arange(np.datetime64(f"{start}-01-01"), np.datetime64(f"{end + 1}-01-01"), dtype="datetime64[D]")
    out = {k: [] for k in ("tmax", "tmin", "precip")}
    for y in wanted:
        n = _days_in_year(y)
        for k in out:
            vals = docs[y][k] if y in docs else [None] * n
            vals = (vals + [None] * n)[:n]
            out[k].append(np.array([np.nan if v is None else v for v in vals], float))
    arrays = {k: np.concatenate(v) for k, v in out.items()}
    return dates, arrays, {"years_fetched": fetched_years, "years_from_cache": len(wanted) - fetched_years}
