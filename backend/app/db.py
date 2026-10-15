"""MongoDB access (NoSQL store for cached weather, computed analyses and generic API cache).

Collections
  weather_years  one doc per (region key, year): daily tmax/tmin/precip arrays      (TTL: fetched_at)
  analyses       one doc per (region, hazard, period, params, pipeline version)      (TTL: computed_at)
  api_cache      generic key/value cache for geocoding, layers, projections, ...     (TTL: expires_at)
  subscribers    newsletter e-mails (unique index)
  community      community-join requests
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, MongoClient

from .config import get_settings

log = logging.getLogger("climatesphere.db")

_db = None
_backend = "uninitialised"


def utcnow() -> datetime:
    """Naive UTC datetime (what MongoDB stores/returns by default)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def init_db():
    """Connect to MongoDB; optionally fall back to an in-memory mongomock DB for local dev."""
    global _db, _backend
    s = get_settings()
    try:
        client = MongoClient(s.mongo_uri, serverSelectionTimeoutMS=int(os.getenv('MONGO_TIMEOUT_MS', '3000')))
        client.admin.command("ping")
        _db, _backend = client[s.mongo_db], "mongodb"
    except Exception as exc:  # noqa: BLE001
        if not s.allow_mock_db:
            raise
        import mongomock

        log.warning("MongoDB unreachable (%s). Using IN-MEMORY mongomock - data is NOT persisted.", exc.__class__.__name__)
        _db, _backend = mongomock.MongoClient()[s.mongo_db], "in-memory (mongomock)"
    _ensure_indexes(s)
    return _db


def _ensure_indexes(s) -> None:
    db = _db
    db.weather_years.create_index([("rkey", ASCENDING), ("year", ASCENDING)])
    db.weather_years.create_index("fetched_at", expireAfterSeconds=s.weather_ttl_days * 86400)
    db.analyses.create_index("computed_at", expireAfterSeconds=s.analysis_ttl_days * 86400)
    db.api_cache.create_index("expires_at", expireAfterSeconds=0)
    db.subscribers.create_index("email", unique=True)


def get_db():
    return _db if _db is not None else init_db()


def backend_name() -> str:
    return _backend


# ---- generic cache helpers -------------------------------------------------
def cache_get(key: str) -> Any | None:
    doc = get_db().api_cache.find_one({"_id": key})
    if doc and doc.get("expires_at") and doc["expires_at"] > utcnow():  # TTL monitor runs only every ~60 s
        return doc["payload"]
    return None


def cache_set(key: str, payload: Any, ttl_seconds: int) -> None:
    get_db().api_cache.replace_one(
        {"_id": key},
        {"_id": key, "payload": payload, "expires_at": utcnow() + timedelta(seconds=ttl_seconds)},
        upsert=True,
    )
