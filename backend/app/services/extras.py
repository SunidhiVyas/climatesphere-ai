"""Secondary data products: global layers, air quality, projections, climate-action indicators, AI insights."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from ..config import get_settings
from ..db import cache_get, cache_set, utcnow
from ..sources import http, open_meteo, worldbank

# ---------------------------------------------------------------- global layers
GRID_W, GRID_H = 36, 18            # 10° cells
LAT = [85 - 10 * i for i in range(GRID_H)]
LON = [-175 + 10 * j for j in range(GRID_W)]
LAYERS = {   # name: (label, unit, physical min, physical max)
    "temp": ("Temperature", "°C", -40.0, 45.0),
    "rain": ("Precipitation", "mm", 0.0, 5.0),
    "wind": ("Wind speed", "km/h", 0.0, 70.0),
    "cloud": ("Cloud cover", "%", 0.0, 100.0),
    "dry": ("Dryness (1 − soil moisture)", "index", 0.0, 1.0),
}


def _grid_raw() -> dict:
    cached = cache_get("grid:v1")
    if cached:
        return cached
    pts = [(la, lo) for la in LAT for lo in LON]
    raw = {k: [] for k in LAYERS}
    for i in range(0, len(pts), 100):
        for loc in open_meteo.fetch_forecast_grid(pts[i:i + 100]):
            c = loc.get("current", {})
            sm = (loc.get("hourly", {}).get("soil_moisture_0_to_1cm") or [None])[0]
            raw["temp"].append(c.get("temperature_2m"))
            raw["rain"].append(c.get("precipitation"))
            raw["wind"].append(c.get("wind_speed_10m"))
            raw["cloud"].append(c.get("cloud_cover"))
            raw["dry"].append(None if sm is None else 1 - min(max(sm / 0.5, 0), 1))
    payload = {"raw": raw, "fetched_at": utcnow().isoformat() + "Z"}
    cache_set("grid:v1", payload, 6 * 3600)       # 648 locations -> refresh at most every 6 h
    return payload


def layer(name: str) -> dict:
    label, unit, lo, hi = LAYERS[name]
    g = _grid_raw()
    vals = [None if v is None else round(min(max((v - lo) / (hi - lo), 0), 1), 4) for v in g["raw"][name]]
    return {"live": True, "name": name, "label": label, "source": "Open-Meteo forecast API (current conditions)",
            "unit": unit, "min": lo, "max": hi, "width": GRID_W, "height": GRID_H, "values": vals,
            "lat_top": LAT[0], "lat_step": -10, "lon_left": LON[0], "lon_step": 10, "observed_at": g["fetched_at"]}


# ---------------------------------------------------------------- air quality
def aerosol(lat: float, lon: float, name: str) -> dict:
    key = f"aq:{lat:.1f}:{lon:.1f}"
    j = cache_get(key)
    if not j:
        j = open_meteo.fetch_air_quality(lat, lon)
        cache_set(key, j, 3600)
    cur, units = j.get("current", {}), j.get("current_units", {})

    def m(k):
        return {"value": cur.get(k), "unit": units.get(k, "")}
    return {"live": True, "region": name, "period": cur.get("time"), "source": "Open-Meteo Air Quality API (CAMS)",
            "pm": {**m("pm2_5"), "source": "CAMS", "period": cur.get("time"), "region": name},
            "pm10": m("pm10"), "dust": m("dust"), "aod": m("aerosol_optical_depth"),
            "who_guideline_pm25_24h": 15}


# ---------------------------------------------------------------- projections
def projections(lat: float, lon: float, year: int, name: str) -> dict:
    s = get_settings()
    key = f"proj:{lat:.1f}:{lon:.1f}:{s.climate_models}"
    data = cache_get(key)
    if not data:
        raw = open_meteo.fetch_climate(lat, lon, s.climate_models, "1991-01-01", "2050-12-31")
        data = {"times": raw["times"], "models": {m: {k: [None if np.isnan(x) else round(float(x), 2) for x in v]
                                                      for k, v in vs.items()} for m, vs in raw["models"].items()}}
        cache_set(key, data, 7 * 86400)
    t = np.array(data["times"], dtype="datetime64[D]")
    yrs = t.astype("datetime64[Y]").astype(int) + 1970
    base = (yrs >= 1991) & (yrs <= 2020)
    tgt = (yrs >= year - 5) & (yrs <= min(year + 4, 2050))
    ny_b, ny_t = len(set(yrs[base])), max(1, len(set(yrs[tgt])))
    res: dict[str, list] = {"temp": [], "heat": [], "rain": [], "drought": []}
    for model, v in data["models"].items():
        f = lambda k: np.array([np.nan if x is None else x for x in v.get(k, [])], float)  # noqa: E731
        tm, tx, pr = f("temperature_2m_mean"), f("temperature_2m_max"), f("precipitation_sum")
        if len(tm) != len(t):
            continue
        res["temp"].append(np.nanmean(tm[tgt]) - np.nanmean(tm[base]))
        p95 = np.nanpercentile(tx[base], 95)
        res["heat"].append(np.nansum(tx[tgt] > p95) / ny_t - np.nansum(tx[base] > p95) / ny_b)
        res["rain"].append((np.nansum(pr[tgt]) / ny_t) / max(np.nansum(pr[base]) / ny_b, 1e-6) * 100 - 100)
        res["drought"].append(np.nansum(pr[tgt] < 1) / ny_t - np.nansum(pr[base] < 1) / ny_b)
    if not res["temp"]:
        raise http.UpstreamError("Climate model data unavailable for this location.", 502)
    spec = {"temp": ("Warming", "°C", "{:+.1f}°C"), "heat": ("Extra hot days / yr", "days", "{:+.0f} days/yr"),
            "rain": ("Annual rainfall change", "%", "{:+.0f}%"), "drought": ("Extra dry days / yr", "days", "{:+.0f} days/yr")}
    metrics = {}
    for k, vals in res.items():
        med = float(np.median(vals))
        metrics[k] = {"label": spec[k][0], "value": round(med, 2), "unit": spec[k][1], "display": spec[k][2].format(med),
                      "range": [round(float(min(vals)), 2), round(float(max(vals)), 2)], "models": len(vals),
                      "baseline": "1991–2020", "year": year, "region": name,
                      "source": "Open-Meteo Climate API (CMIP6 HighResMIP)", "pathway": "SSP5-8.5 (high emissions)"}
    return {"live": True, "region": name, "year": year, "window": f"{max(year - 5, 2021)}–{min(year + 4, 2050)}",
            "metrics": metrics, "models": list(data["models"].keys()),
            "note": "Open-Meteo serves a single high-emission pathway (SSP5-8.5) up to 2050; lower scenarios and 2070/2100 are not available from this source."}


# ---------------------------------------------------------------- climate-action indicators
def impact() -> dict:
    c = cache_get("impact:v1")
    if c:
        return c
    items = []
    for key, code, label, unit, ref_year, definition, good in worldbank.INDICATORS:
        try:
            r = worldbank.fetch_indicator(code, ref_year)
        except http.UpstreamError:
            continue
        if not r["latest"]:
            continue
        v, y = r["latest"]
        ref = r["ref"]
        item = {"key": key, "label": label, "unit": unit, "value": round(v, 2), "year": y, "definition": definition,
                "good_direction": good, "source": f"World Bank WDI ({code})"}
        if ref:
            item["reference"] = {"value": round(ref[0], 2), "year": ref[1]}
            item["change_pct"] = round((v - ref[0]) / ref[0] * 100, 1) if ref[0] else None
        items.append(item)
    if not items:
        raise http.UpstreamError("World Bank data unavailable.", 502)
    out = {"live": True, "source": "World Bank World Development Indicators (world aggregate)", "indicators": items,
           "fetched_at": utcnow().isoformat() + "Z"}
    cache_set("impact:v1", out, 24 * 3600)
    return out


# ---------------------------------------------------------------- AI insights
SYSTEM = ("You are a careful climate-data explainer. Use ONLY the facts in the JSON provided. Never invent numbers, "
          "places or causes. State uncertainty and statistical significance plainly. 90-130 words, plain language, "
          "no headings or bullet points.")


def _rule_based(facts: dict) -> str:
    parts = [facts["historical"]["headline"]]
    p = facts.get("projection")
    if p:
        m = p["metrics"]
        parts.append(f"Climate models (CMIP6, SSP5-8.5) project about {m['temp']['display']} of warming in {p['region']} "
                     f"around {p['year']} compared with 1991–2020 (model range {m['temp']['range'][0]:+.1f} to "
                     f"{m['temp']['range'][1]:+.1f}°C) and roughly {m['heat']['display']} more days above today's 95th-percentile heat.")
    parts.append("These are model-based estimates under a high-emission pathway, not forecasts.")
    return " ".join(parts)


def insights(facts: dict) -> dict:
    s = get_settings()
    key = "ins:" + hashlib.sha1(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest() + (s.anthropic_model if s.anthropic_api_key else "rb")
    c = cache_get(key)
    if c:
        return c
    text, model = _rule_based(facts), "rule-based (set ANTHROPIC_API_KEY for LLM narration)"
    if s.anthropic_api_key:
        try:
            j = http.fetch_json("https://api.anthropic.com/v1/messages", method="POST", retries=1,
                                headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"},
                                json_body={"model": s.anthropic_model, "max_tokens": 400, "system": SYSTEM,
                                           "messages": [{"role": "user", "content": json.dumps(facts, default=str)}]})
            t = "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text").strip()
            if t:
                text, model = t, s.anthropic_model
        except http.UpstreamError:
            pass  # silently keep the rule-based text; never fail the request because the LLM is down
    out = {"text": text, "model": model, "source": "Computed from this app's own analysis", "generated": model != "rule-based (set ANTHROPIC_API_KEY for LLM narration)",
           "facts_used": {"historical": facts["historical"]["headline"], "projection": bool(facts.get("projection"))}}
    cache_set(key, out, 12 * 3600)
    return out
