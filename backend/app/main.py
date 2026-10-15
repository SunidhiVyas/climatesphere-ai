
"""ClimateSphere API (FastAPI).

Endpoint contract:
  /api/region /api/summary /api/trends /api/layer /api/aerosol
  /api/projections /api/insights /api/impact
  POST /api/newsletter POST /api/community/join
  /api/export/{csv,pdf}, /api/plot.png, /api/presets, /api/health
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from . import db
from .config import MIN_YEAR, PIPELINE_VERSION, get_settings, last_complete_year
from .regions import MAX_BOX_SPAN_DEG, PRESETS, RegionSpec, continent_code
from .services import analysis_service as svc
from .services import export, extras
from .sources import http, open_meteo

log = logging.getLogger("climatesphere")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    log.info("DB backend: %s", db.backend_name())
    yield


app = FastAPI(
    title="ClimateSphere API",
    version=PIPELINE_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)


# -------------------------------------------------------------------
# Rate limiting and security headers
# -------------------------------------------------------------------

class SlidingWindow:
    def __init__(self) -> None:
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(
        self,
        ip: str,
        bucket: str,
        limit: int,
        window: float = 60.0,
    ) -> int:
        """Return zero if allowed; otherwise return seconds to wait."""
        now = time.monotonic()

        with self.lock:
            q = self.hits[(ip, bucket)]

            while q and now - q[0] > window:
                q.popleft()

            if len(q) >= limit:
                return int(window - (now - q[0])) + 1

            q.append(now)

            if len(self.hits) > 20000:
                self.hits.clear()

            return 0


limiter = SlidingWindow()

HEAVY = (
    "/api/trends",
    "/api/summary",
    "/api/export",
    "/api/plot",
    "/api/projections",
    "/api/insights",
    "/api/layer",
    "/api/aerosol",
    "/api/impact",
)


def client_ip(request: Request) -> str:
    settings = get_settings()

    if settings.trust_proxy:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()[:64]

    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    settings = get_settings()

    if path.startswith("/api") and request.method != "OPTIONS":
        if request.method == "POST":
            bucket = "post"
            limit = settings.rate_post

            try:
                content_length = int(
                    request.headers.get("content-length") or 0
                )
            except ValueError:
                content_length = 0

            if content_length > 10_000:
                return JSONResponse(
                    {"error": "Request body too large."},
                    status_code=413,
                )

        elif path.startswith(HEAVY):
            bucket = "heavy"
            limit = settings.rate_heavy

        else:
            bucket = "light"
            limit = settings.rate_default

        wait = limiter.check(
            client_ip(request),
            bucket,
            limit,
        )

        if wait:
            return JSONResponse(
                {"error": "Too many requests. Please slow down."},
                status_code=429,
                headers={"Retry-After": str(wait)},
            )

    response = await call_next(request)

    # Swagger UI loads its JavaScript and CSS from jsDelivr.
    # These rules permit those assets while restricting other sources.
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' https://cdn.jsdelivr.net "
                "'unsafe-inline'; "
                "style-src 'self' https://cdn.jsdelivr.net "
                "'unsafe-inline'; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "font-src 'self' https://cdn.jsdelivr.net data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'"
            ),
            "Cross-Origin-Resource-Policy": "cross-origin",
        }
    )

    return response


# -------------------------------------------------------------------
# Error handling
# -------------------------------------------------------------------

@app.exception_handler(http.UpstreamError)
async def upstream_handler(
    _: Request,
    exc: http.UpstreamError,
):
    headers = (
        {"Retry-After": str(exc.retry_after)}
        if exc.retry_after
        else None
    )

    status_code = (
        exc.status
        if exc.status in (429, 502, 503)
        else 502
    )

    return JSONResponse(
        {"error": f"Data provider problem: {exc.message}"},
        status_code=status_code,
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)

    return JSONResponse(
        {"error": "Internal server error."},
        status_code=500,
    )


# -------------------------------------------------------------------
# Input validation and region resolution
# -------------------------------------------------------------------

NAME_RE = re.compile(
    r"^[\w\s.,'’()\-]{2,80}$",
    re.UNICODE,
)

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)


def _clean_name(q: str) -> str:
    q = " ".join(q.split())

    if not NAME_RE.match(q):
        raise HTTPException(
            status_code=422,
            detail=(
                "Place name must be 2-80 characters "
                "(letters, spaces and . , ' ( ) - only)."
            ),
        )

    return q


def resolve_place(q: str) -> dict:
    q = _clean_name(q)
    key = "geo:" + q.lower()

    hit = db.cache_get(key)

    if hit is None:
        results = open_meteo.geocode(q, 5)

        hit = [
            {
                "name": item["name"],
                "lat": item["latitude"],
                "lon": item["longitude"],
                "country": item.get("country", ""),
                "admin1": item.get("admin1", ""),
                "timezone": item.get("timezone"),
                "population": item.get("population"),
            }
            for item in results
        ]

        db.cache_set(key, hit, 30 * 86400)

    if not hit:
        raise HTTPException(
            status_code=404,
            detail=f"No place found for '{q}'.",
        )

    return {"results": hit}


def region_dep(
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    north: float | None = Query(None, ge=-90, le=90),
    west: float | None = Query(None, ge=-180, le=180),
    east: float | None = Query(None, ge=-180, le=180),
    region: str | None = Query(None, max_length=80),
    name: str | None = Query(None, max_length=80),
) -> RegionSpec:
    label = _clean_name(name) if name else ""
    box = (south, west, north, east)

    if all(value is not None for value in box):
        if not (south < north and west < east):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Bounding box needs south < north and west < east. "
                    "Boxes crossing the antimeridian are not supported."
                ),
            )

        if (
            north - south > MAX_BOX_SPAN_DEG
            or east - west > MAX_BOX_SPAN_DEG
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Bounding box too large "
                    f"(max {MAX_BOX_SPAN_DEG:.0f} degrees per side)."
                ),
            )

        return RegionSpec.bbox(
            south, west, north, east, label
        )

    if any(value is not None for value in box):
        raise HTTPException(
            status_code=422,
            detail="Provide all of south, west, north, east for a box.",
        )

    if lat is not None and lon is not None:
        return RegionSpec.point(lat, lon, label)

    if region:
        top = resolve_place(region)["results"][0]

        return RegionSpec.point(
            top["lat"],
            top["lon"],
            label or top["name"],
        )

    raise HTTPException(
        status_code=422,
        detail=(
            "Provide a region: ?region=<place>, ?lat=&lon=, "
            "or ?south=&west=&north=&east=."
        ),
    )


def params_dep(
    hazard: Literal["heatwave", "rainfall", "drought"] = "heatwave",
    start: int = Query(1990, alias="from", ge=MIN_YEAR),
    end: int = Query(2020, alias="to"),
    percentile: float = Query(95.0, ge=80, le=99.9),
    min_days: int | None = Query(None, ge=1, le=30),
    mode: Literal["seasonal", "annual"] = "seasonal",
) -> svc.Params:
    last = last_complete_year()

    if end > last:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'to' must be {last} or earlier "
                "(the current year is incomplete)."
            ),
        )

    if end - start < 4:
        raise HTTPException(
            status_code=422,
            detail="Time range must span at least 5 years.",
        )

    from .analysis.hazards import HAZARDS

    return svc.Params(
        hazard,
        start,
        end,
        percentile,
        min_days or HAZARDS[hazard]["default_min_days"],
        mode,
    )


# -------------------------------------------------------------------
# API routes
# -------------------------------------------------------------------

@app.get("/api/health")
def health():
    database = db.get_db()

    return {
        "status": "ok",
        "version": PIPELINE_VERSION,
        "db": {
            "backend": db.backend_name(),
            "persistent": db.backend_name() == "mongodb",
        },
        "cache": {
            "analyses": database.analyses.count_documents({}),
            "weather_years": database.weather_years.count_documents({}),
        },
        "llm": (
            "configured"
            if get_settings().anthropic_api_key
            else "not configured"
        ),
        "last_complete_year": last_complete_year(),
    }


@app.get("/api/presets")
def presets():
    return {"presets": PRESETS}


@app.get("/api/region")
def region_lookup(
    q: str = Query(..., min_length=2, max_length=80),
):
    output = []

    for item in resolve_place(q)["results"]:
        output.append(
            {
                **item,
                "region": continent_code(
                    item.get("timezone"),
                    item["lat"],
                ),
                "label": ", ".join(
                    value
                    for value in (
                        item["name"],
                        item.get("admin1"),
                        item.get("country"),
                    )
                    if value
                ),
            }
        )

    top = output[0]

    return {**top, "results": output}


@app.get("/api/trends")
def trends(
    region: RegionSpec = Depends(region_dep),
    p: svc.Params = Depends(params_dep),
):
    return svc.get_analysis(region, p)


@app.get("/api/summary")
def summary(
    region: RegionSpec = Depends(region_dep),
    p: svc.Params = Depends(params_dep),
):
    names = {
        "heatwave": "heatwaves",
        "rainfall": "extreme_rainfall",
        "drought": "drought",
    }

    output: dict = {
        "region": region.to_dict(),
        "period": {"from": p.start, "to": p.end},
        "cyclones": None,
        "cyclones_note": (
            "Cyclone tracks are not derivable from daily weather data; "
            "not shown."
        ),
    }

    for hazard, key in names.items():
        analysis = svc.get_analysis(
            region,
            svc.Params(
                hazard,
                p.start,
                p.end,
                p.percentile,
                (
                    3
                    if hazard == "heatwave"
                    else 1 if hazard == "rainfall" else 15
                ),
                p.mode,
            ),
        )

        change = analysis["trend"]["frequency"]["decade_change"]

        output[key] = {
            "value": analysis["event_count"],
            "change_pct": change["pct"],
            "change_basis": "mean events/yr, last vs first 10 years",
            "period": f"{p.start}–{p.end}",
            "significant": analysis["insight"]["significant"],
            "mann_kendall_p": (
                analysis["trend"]["hazard_days"]["mann_kendall"]["p"]
            ),
            "unit": analysis["units"]["frequency"],
            "series": analysis["series"]["hazard_days"],
            "years": analysis["years"],
        }

    output["source"] = svc.SOURCE

    return output


@app.get("/api/layer")
def layer(
    name: Literal["temp", "rain", "wind", "cloud", "dry"] = "temp",
):
    return extras.layer(name)


@app.get("/api/aerosol")
def aerosol(region: RegionSpec = Depends(region_dep)):
    return extras.aerosol(
        region.lat,
        region.lon,
        region.name,
    )


@app.get("/api/projections")
def projections(
    region: RegionSpec = Depends(region_dep),
    year: int = Query(2050, ge=2021, le=2050),
    scenario: str | None = Query(None, max_length=12),
):
    return extras.projections(
        region.lat,
        region.lon,
        year,
        region.name,
    )


@app.get("/api/insights")
def insights(
    region: RegionSpec = Depends(region_dep),
    year: int = Query(2050, ge=2021, le=2050),
    scenario: str | None = Query(None, max_length=12),
    tab: str | None = Query(None, max_length=20),
):
    historical = svc.get_analysis(
        region,
        svc.Params(
            "heatwave",
            1990,
            min(2020, last_complete_year()),
            95.0,
            3,
            "seasonal",
        ),
    )

    facts: dict = {
        "region": region.name,
        "historical": {
            "headline": historical["insight"]["headline"],
            "bullets": historical["insight"]["bullets"],
            "caveats": historical["insight"]["caveats"],
        },
    }

    try:
        projection = extras.projections(
            region.lat,
            region.lon,
            year,
            region.name,
        )

        facts["projection"] = {
            key: projection[key]
            for key in ("region", "year", "metrics", "note")
        }

    except http.UpstreamError:
        log.warning("Projection data unavailable for insights.")

    return extras.insights(facts)


@app.get("/api/impact")
def impact():
    return extras.impact()


@app.get("/api/export/csv")
def export_csv(
    region: RegionSpec = Depends(region_dep),
    p: svc.Params = Depends(params_dep),
    kind: Literal["annual", "events"] = "annual",
):
    analysis = svc.get_analysis(
        region,
        p,
        include_all_events=True,
    )

    filename = export.safe_filename(
        analysis,
        "csv",
        kind,
    )

    return Response(
        export.to_csv(analysis, kind),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@app.get("/api/export/pdf")
def export_pdf(
    region: RegionSpec = Depends(region_dep),
    p: svc.Params = Depends(params_dep),
):
    analysis = svc.get_analysis(region, p)
    filename = export.safe_filename(analysis, "pdf")

    return Response(
        export.to_pdf(analysis),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@app.get("/api/plot.png")
def plot_png(
    region: RegionSpec = Depends(region_dep),
    p: svc.Params = Depends(params_dep),
):
    analysis = svc.get_analysis(region, p)

    return Response(
        export.to_png(analysis),
        media_type="image/png",
    )


# -------------------------------------------------------------------
# Newsletter and community endpoints
# -------------------------------------------------------------------

class Newsletter(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()

        if not EMAIL_RE.match(value):
            raise ValueError("Invalid e-mail address.")

        return value


class Join(Newsletter):
    name: str = Field(min_length=2, max_length=80)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _clean_name(value)


@app.post("/api/newsletter", status_code=201)
def newsletter(body: Newsletter):
    try:
        db.get_db().subscribers.insert_one(
            {
                "email": body.email,
                "created_at": db.utcnow(),
            }
        )
    except Exception:
        # Avoid exposing whether an email is already subscribed.
        log.debug("Newsletter entry already exists or could not be stored.")

    return {"ok": True}


@app.post("/api/community/join", status_code=201)
def community_join(body: Join):
    db.get_db().community.insert_one(
        {
            "name": body.name,
            "email": body.email,
            "created_at": db.utcnow(),
        }
    )

    return {"ok": True}
