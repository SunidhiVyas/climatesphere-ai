"""Region model: a point (city) or a lat/lon bounding box."""
from __future__ import annotations

import math
from dataclasses import dataclass

MAX_BOX_SPAN_DEG = 30.0


def snap(x: float, step: float = 0.1) -> float:
    """Snap to the nominal grid resolution of the reanalysis so nearby clicks share one cache entry."""
    return round(round(x / step) * step, 4)


@dataclass(frozen=True)
class RegionSpec:
    kind: str                    # "point" | "bbox"
    lat: float                   # point or box centre
    lon: float
    name: str = ""
    south: float | None = None
    west: float | None = None
    north: float | None = None
    east: float | None = None

    @classmethod
    def point(cls, lat: float, lon: float, name: str = "") -> "RegionSpec":
        lat, lon = snap(lat), snap(lon)
        return cls("point", lat, lon, name or f"{lat:.1f}°, {lon:.1f}°")

    @classmethod
    def bbox(cls, south: float, west: float, north: float, east: float, name: str = "") -> "RegionSpec":
        s, w, n, e = snap(south), snap(west), snap(north), snap(east)
        return cls("bbox", (s + n) / 2, (w + e) / 2, name or f"Box {s:.1f},{w:.1f} → {n:.1f},{e:.1f}", s, w, n, e)

    @property
    def key(self) -> str:
        if self.kind == "point":
            return f"p:{self.lat:.1f}:{self.lon:.1f}"
        return f"b:{self.south:.1f}:{self.west:.1f}:{self.north:.1f}:{self.east:.1f}"

    def sample_points(self) -> list[tuple[float, float]]:
        """Points whose daily values are averaged to represent the region (max 9 -> bounded upstream cost)."""
        if self.kind == "point":
            return [(self.lat, self.lon)]
        dlat, dlon = self.north - self.south, self.east - self.west
        if max(dlat, dlon) < 1.0:
            return [(self.lat, self.lon)]
        fr = (1 / 6, 1 / 2, 5 / 6)  # centres of a 3x3 sub-grid
        return [(round(self.south + f * dlat, 2), round(self.west + g * dlon, 2)) for f in fr for g in fr]

    def to_dict(self) -> dict:
        d = {"name": self.name, "kind": self.kind, "lat": round(self.lat, 3), "lon": round(self.lon, 3)}
        if self.kind == "bbox":
            d["bbox"] = {"south": self.south, "west": self.west, "north": self.north, "east": self.east}
        return d


def continent_code(timezone: str | None, lat: float) -> str:
    """Coarse region code used by the globe UI: na|sa|eu|as|af|au."""
    tz = (timezone or "").split("/")[0]
    if tz == "America":
        return "sa" if lat < 12 else "na"
    return {"Europe": "eu", "Asia": "as", "Africa": "af", "Australia": "au", "Pacific": "au", "Indian": "as",
            "Atlantic": "eu", "Antarctica": "au", "Arctic": "eu"}.get(tz, "as")


# Hotspots shown on the globe / used as quick picks.
PRESETS = [
    {"name": "Delhi", "lat": 28.61, "lon": 77.21, "country": "India"},
    {"name": "Phoenix", "lat": 33.45, "lon": -112.07, "country": "USA"},
    {"name": "Paris", "lat": 48.86, "lon": 2.35, "country": "France"},
    {"name": "Cairo", "lat": 30.04, "lon": 31.24, "country": "Egypt"},
    {"name": "Sydney", "lat": -33.87, "lon": 151.21, "country": "Australia"},
    {"name": "São Paulo", "lat": -23.55, "lon": -46.63, "country": "Brazil"},
    {"name": "Beijing", "lat": 39.9, "lon": 116.4, "country": "China"},
    {"name": "Lagos", "lat": 6.52, "lon": 3.38, "country": "Nigeria"},
    {"name": "Toronto", "lat": 43.65, "lon": -79.38, "country": "Canada"},
    {"name": "Moscow", "lat": 55.76, "lon": 37.62, "country": "Russia"},
    {"name": "Dubai", "lat": 25.2, "lon": 55.27, "country": "UAE"},
    {"name": "Mexico City", "lat": 19.43, "lon": -99.13, "country": "Mexico"},
]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))
