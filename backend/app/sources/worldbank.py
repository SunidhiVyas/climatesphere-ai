"""World Bank open-data adapter (global climate-action indicators, no key)."""
from __future__ import annotations

from . import http

BASE = "https://api.worldbank.org/v2/country/WLD/indicator/"

# key, indicator code, label, unit, reference year, definition, "good direction"
INDICATORS = [
    ("renewable", "EG.FEC.RNEW.ZS", "Renewable energy share", "% of final energy", 2000,
     "Renewable energy consumption as a share of total final energy consumption.", "up"),
    ("forest", "AG.LND.FRST.ZS", "Forest area", "% of land area", 1990,
     "Land under natural or planted trees at least 5 m tall.", "up"),
    ("co2pc", "EN.GHG.CO2.PC.CE.AR5", "CO₂ emissions per person", "t CO₂e / person", 2000,
     "Carbon-dioxide emissions (excl. LULUCF) per capita.", "down"),
]


def _first_value(j) -> tuple[float, int] | None:
    rows = j[1] if isinstance(j, list) and len(j) > 1 and j[1] else []
    for r in rows:
        if r.get("value") is not None:
            return float(r["value"]), int(r["date"])
    return None


def fetch_indicator(code: str, ref_year: int) -> dict:
    latest = _first_value(http.fetch_json(BASE + code, {"format": "json", "mrnev": 1}))
    ref = _first_value(http.fetch_json(BASE + code, {"format": "json", "date": ref_year}))
    return {"latest": latest, "ref": ref}
