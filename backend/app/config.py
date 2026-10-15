"""Runtime configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

# Bump when detection / trend logic changes so cached analyses are recomputed.
PIPELINE_VERSION = "1.0.0"

# Earliest year served by the Open-Meteo historical (ERA5) archive that we allow.
MIN_YEAR = 1950


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    mongo_uri: str
    mongo_db: str
    allow_mock_db: bool          # dev convenience: fall back to in-memory DB if MongoDB is unreachable
    cors_origins: list[str]
    trust_proxy: bool            # honour X-Forwarded-For (only enable behind a trusted reverse proxy)
    rate_default: int            # requests / minute / IP for cheap endpoints
    rate_heavy: int              # requests / minute / IP for endpoints that may hit upstream APIs
    rate_post: int               # requests / minute / IP for POST endpoints
    upstream_per_minute: int     # outbound calls / minute to third-party APIs (global, all users)
    weather_ttl_days: int        # how long cached raw weather years stay valid
    analysis_ttl_days: int       # how long computed analyses stay valid
    anthropic_api_key: str
    anthropic_model: str
    climate_models: str          # Open-Meteo Climate API (CMIP6) models used for projections


def get_settings() -> Settings:
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        mongo_uri=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        mongo_db=os.getenv("MONGO_DB", "climatesphere"),
        allow_mock_db=_bool("ALLOW_MOCK_DB", True),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        trust_proxy=_bool("TRUST_PROXY", False),
        rate_default=_int("RATE_DEFAULT_PER_MIN", 120),
        rate_heavy=_int("RATE_HEAVY_PER_MIN", 30),
        rate_post=_int("RATE_POST_PER_MIN", 10),
        upstream_per_minute=_int("UPSTREAM_PER_MIN", 300),
        weather_ttl_days=_int("WEATHER_TTL_DAYS", 90),
        analysis_ttl_days=_int("ANALYSIS_TTL_DAYS", 14),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5").strip(),
        climate_models=os.getenv("CLIMATE_MODELS", "EC_Earth3P_HR,MRI_AGCM3_2_S,MPI_ESM1_2_XR").strip(),
    )


def last_complete_year() -> int:
    """Most recent calendar year with a full 12 months of data (partial years would bias trends)."""
    return date.today().year - 1
