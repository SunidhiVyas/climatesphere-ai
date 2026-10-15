"""Orchestrates: ingest (if needed) -> compute -> store in MongoDB -> READ from MongoDB and return."""
from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict
from dataclasses import dataclass

from ..analysis.pipeline import build_insight, run_analysis
from ..config import PIPELINE_VERSION
from ..db import get_db, utcnow
from ..regions import RegionSpec
from . import weather

_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
SOURCE = {"name": "Open-Meteo Historical Weather API (ERA5 / ERA5-Land reanalysis, Copernicus/ECMWF)",
          "url": "https://open-meteo.com/en/docs/historical-weather-api"}


@dataclass(frozen=True)
class Params:
    hazard: str = "heatwave"
    start: int = 1990
    end: int = 2020
    percentile: float = 95.0
    min_days: int = 3
    mode: str = "seasonal"


def _key(region: RegionSpec, p: Params) -> str:
    raw = json.dumps([region.key, p.hazard, p.start, p.end, p.percentile, p.min_days, p.mode, PIPELINE_VERSION])
    return hashlib.sha1(raw.encode()).hexdigest()


def get_analysis(region: RegionSpec, p: Params, *, include_all_events: bool = False) -> dict:
    db, key = get_db(), _key(region, p)
    doc = db.analyses.find_one({"_id": key})
    cache = "hit"
    if doc is None:
        with _locks[key]:                       # single-flight: concurrent identical requests compute once
            doc = db.analyses.find_one({"_id": key})
            if doc is None:
                cache = "miss"
                dates, arrays, ingest = weather.get_daily(region, p.start, p.end)
                result = run_analysis(region.to_dict(), dates, arrays, hazard=p.hazard, start=p.start, end=p.end,
                                      pct=p.percentile, min_days=p.min_days, mode=p.mode)
                result["source"] = SOURCE
                result["ingest"] = ingest
                db.analyses.replace_one({"_id": key}, {"_id": key, "rkey": region.key, "hazard": p.hazard,
                                                       "result": result, "computed_at": utcnow()}, upsert=True)
                doc = db.analyses.find_one({"_id": key})   # always serve what is stored in the database
    result = dict(doc["result"])
    result["region"] = {**result["region"], "name": region.name}   # display name is not part of the cache key
    result["insight"] = build_insight(result)                       # ...so text mentioning it is rebuilt
    result["meta"] = {"cache": cache, "computed_at": doc["computed_at"].isoformat() + "Z", "pipeline_version": PIPELINE_VERSION}
    if not include_all_events:
        result.pop("all_events", None)
    return result
