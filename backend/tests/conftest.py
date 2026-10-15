"""Test fixtures: synthetic-but-realistic upstream responses, in-memory DB. No network is used."""
import os

os.environ.update(MONGO_TIMEOUT_MS="200", ALLOW_MOCK_DB="1", MONGO_URI="mongodb://127.0.0.1:1", RATE_HEAVY_PER_MIN="1000", RATE_DEFAULT_PER_MIN="1000",
                  RATE_POST_PER_MIN="1000")

import math
from datetime import date, timedelta

import pytest

CALLS = []


def synth_daily(start: str, end: str, lat: float = 40.0):
    """Seasonal Tmax + noise; heatwaves (4 days, +9°C) whose count grows over time; a few gaps and a bogus spike."""
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    times, tmax, tmin, pr = [], [], [], []
    d = d0
    i = 0
    while d <= d1:
        doy = d.timetuple().tm_yday
        noise = 6 * math.sin(i * 12.9898) * math.cos(i * 4.1414)
        base = 18 + 12 * math.sin(2 * math.pi * (doy - 110) / 365.25) + noise
        n_hw = 1 + (d.year - 1990) // 12                   # 1,2,3 heatwaves per year (increasing)
        for k in range(n_hw):
            s = 100 + int(abs(math.sin(d.year * 12.9 + k * 78.2)) * 200)   # pseudo-random summer start day
            if s <= doy < s + 4:
                base += 14
        v = base
        if d.year == 2000 and 100 <= doy <= 104:           # gap of 5 days (too long to bridge)
            v = None
        if d.year == 2001 and doy == 50:                   # 1-day gap (bridged)
            v = None
        if d.year == 2002 and doy == 20:                   # absurd spike -> must be removed
            v = 140.0
        times.append(d.isoformat())
        tmax.append(None if v is None else round(v, 1))
        tmin.append(None if v is None else round(min(v - 8, v), 1))
        x = math.sin(i * 7.77) * math.cos(i * 1.3)
        pr.append(round((x - 0.35) * 40, 1) if x > 0.35 else 0.0)
        d += timedelta(days=1)
        i += 1
    return times, tmax, tmin, pr


def fake_fetch(url, params=None, **kw):
    CALLS.append(url)
    if "archive-api" in url:
        lats = str(params["latitude"]).split(",")
        times, tx, tn, pr = synth_daily(params["start_date"], params["end_date"])
        locs = [{"daily_units": {"temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_sum": "mm"},
                 "daily": {"time": times, "temperature_2m_max": tx, "temperature_2m_min": tn, "precipitation_sum": pr}} for _ in lats]
        return locs if len(locs) > 1 else locs[0]
    if "geocoding" in url:
        return {"results": [{"name": "Testville", "latitude": 40.0, "longitude": -3.7, "country": "Spain", "admin1": "Madrid", "timezone": "Europe/Madrid"}]}
    if "air-quality" in url:
        return {"current": {"time": "2026-10-15T10:00", "pm2_5": 12.3, "pm10": 20.1, "dust": 3.0, "aerosol_optical_depth": 0.2},
                "current_units": {"pm2_5": "μg/m³", "pm10": "μg/m³", "dust": "μg/m³", "aerosol_optical_depth": ""}}
    if "api.open-meteo.com/v1/forecast" in url:
        n = len(str(params["latitude"]).split(","))
        return [{"current": {"temperature_2m": 15, "precipitation": 0.2, "cloud_cover": 50, "wind_speed_10m": 10},
                 "hourly": {"soil_moisture_0_to_1cm": [0.25]}} for _ in range(n)]
    if "climate-api" in url:
        times, tx, _, pr = synth_daily("1991-01-01", "2050-12-31")
        out = {"time": times}
        for m in params["models"].split(","):
            out[f"temperature_2m_mean_{m}"] = [None if v is None else v - 5 + (int(t[:4]) - 1991) * 0.04 for v, t in zip(tx, times)]
            out[f"temperature_2m_max_{m}"] = [None if v is None else v + (int(t[:4]) - 1991) * 0.04 for v, t in zip(tx, times)]
            out[f"precipitation_sum_{m}"] = pr
        return {"daily": out}
    if "worldbank" in url:
        return [{"page": 1}, [{"value": 19.5, "date": "2021"}]]
    raise AssertionError("unexpected url " + url)


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from app import db
    from app.sources import http
    monkeypatch.setattr(http, "fetch_json", fake_fetch)
    CALLS.clear()
    db._db = None
    with TestClient(__import__("app.main", fromlist=["app"]).app) as c:
        yield c
