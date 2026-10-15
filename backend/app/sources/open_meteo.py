"""Open-Meteo adapters (free, no API key): archive (ERA5), geocoding, forecast grid, air quality, climate (CMIP6)."""
from __future__ import annotations

import re
import warnings
from datetime import date

import numpy as np

from . import http

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
CLIMATE = "https://climate-api.open-meteo.com/v1/climate"


def _list(j):
    """Open-Meteo returns a dict for one location and a list of dicts for several."""
    return j if isinstance(j, list) else [j]


def _arr(values, unit: str | None, kind: str) -> np.ndarray:
    a = np.array([np.nan if v is None else v for v in values], dtype=float)
    u = (unit or "").lower()
    if kind == "temp":
        if "f" in u and "°" in unit:       # °F
            a = (a - 32) * 5 / 9
        elif u in {"k", "kelvin"}:
            a = a - 273.15
    elif kind == "precip" and "inch" in u:
        a = a * 25.4
    return a


def _lat_lon_params(points):
    return {"latitude": ",".join(f"{p[0]:.2f}" for p in points), "longitude": ",".join(f"{p[1]:.2f}" for p in points)}


def geocode(q: str, count: int = 5) -> list[dict]:
    j = http.fetch_json(GEOCODE, {"name": q, "count": count, "language": "en", "format": "json"})
    return j.get("results") or []


def fetch_archive(points: list[tuple[float, float]], start: date, end: date) -> dict:
    """Daily Tmax/Tmin/precip for [start, end]; several points are averaged into one areal series."""
    j = http.fetch_json(
        ARCHIVE,
        {**_lat_lon_params(points), "start_date": start.isoformat(), "end_date": end.isoformat(),
         "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "timezone": "GMT",
         "temperature_unit": "celsius", "precipitation_unit": "mm"},
    )
    locs = _list(j)
    times = locs[0]["daily"]["time"]
    stacks = {"tmax": [], "tmin": [], "precip": []}
    for loc in locs:
        d, u = loc["daily"], loc.get("daily_units", {})
        stacks["tmax"].append(_arr(d["temperature_2m_max"], u.get("temperature_2m_max"), "temp"))
        stacks["tmin"].append(_arr(d["temperature_2m_min"], u.get("temperature_2m_min"), "temp"))
        stacks["precip"].append(_arr(d["precipitation_sum"], u.get("precipitation_sum"), "precip"))
    out = {"times": times}
    for k, rows in stacks.items():
        m = np.vstack(rows)
        valid = (~np.isnan(m)).sum(axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN columns are handled just below
            mean = np.nanmean(m, axis=0)
        mean[valid < max(1, int(np.ceil(len(rows) / 2)))] = np.nan  # need >= half of the points
        out[k] = mean
    return out


def fetch_forecast_grid(points: list[tuple[float, float]]) -> list[dict]:
    j = http.fetch_json(
        FORECAST,
        {**_lat_lon_params(points),
         "current": "temperature_2m,precipitation,cloud_cover,wind_speed_10m",
         "hourly": "soil_moisture_0_to_1cm", "forecast_hours": 1, "timezone": "GMT"},
    )
    return _list(j)


def fetch_air_quality(lat: float, lon: float) -> dict:
    return http.fetch_json(AIR, {"latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}",
                                 "current": "pm10,pm2_5,dust,aerosol_optical_depth", "timezone": "GMT"})


_KEY = re.compile(r"^(temperature_2m_mean|temperature_2m_max|precipitation_sum)(?:_(.+))?$")


def fetch_climate(lat: float, lon: float, models: str, start: str, end: str) -> dict[str, dict[str, np.ndarray]]:
    """CMIP6 daily projections. Returns {model: {var: array}} plus a "times" entry."""
    j = http.fetch_json(CLIMATE, {"latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}", "start_date": start,
                                  "end_date": end, "models": models,
                                  "daily": "temperature_2m_mean,temperature_2m_max,precipitation_sum"})
    d = j["daily"]
    out: dict = {"times": d["time"], "models": {}}
    for k, v in d.items():
        m = _KEY.match(k)
        if m:
            model = m.group(2) or models.split(",")[0]
            out["models"].setdefault(model, {})[m.group(1)] = np.array([np.nan if x is None else x for x in v], float)
    return out
