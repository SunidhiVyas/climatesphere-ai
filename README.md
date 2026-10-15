# ClimateSphere AI — Climate Hazard Trend Analyzer

A full-stack web app that analyses historical weather for a chosen region, detects climate hazards
(**heatwaves** by default, plus heavy rainfall and dry spells) and reports whether the trend is
**statistically real** — with the underlying numbers, method and caveats always shown.

The project was built from a static design brief and aims to show *honest* results: it never invents
values, it states uncertainty plainly, and it degrades gracefully when a data source is unavailable.

---

## Table of contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Database configuration](#database-configuration)
- [API usage](#api-usage)
- [Climate data sources](#climate-data-sources)
- [Methodology](#methodology)
- [Data handling & quality](#data-handling--quality)
- [Assumptions](#assumptions)
- [Limitations](#limitations)
- [Testing](#testing)
- [Deployment](#deployment)
- [Security & performance](#security--performance)
- [Verification status](#verification-status)
- [AI tools used](#ai-tools-used)
- [Data sources & licences](#data-sources--licences)
- [What I would improve with more time](#what-i-would-improve-with-more-time)

---

## Overview

ClimateSphere AI answers a simple question for any place on Earth: *"Is the climate here getting worse,
and is that change real or just noise?"* You pick a region and a period; the backend fetches daily
weather (ERA5 reanalysis via Open-Meteo), cleans it, detects hazardous events with a transparent
percentile rule, and tests the trend with **Mann–Kendall** and **Theil–Sen** statistics. Results are
cached in **MongoDB** and streamed to a React interface with charts, an interactive 3D globe, a
comparison view, CMIP6 projections and downloadable CSV/PDF reports.

- **Frontend:** React 18 (Vite), Chart.js, Leaflet, Three.js, d3-geo
- **Backend:** Python 3.12, FastAPI, NumPy / SciPy, matplotlib + ReportLab
- **Database:** MongoDB (NoSQL) via PyMongo — local, Docker or MongoDB Atlas
- **Data:** Open-Meteo (ERA5 archive, geocoding, CMIP6 climate, CAMS air quality, forecast grid), World Bank

`design-reference/index.html` is the original static design this app was built from.

---

## Features

**Pages**

| Page | What it does |
|---|---|
| **Home** | Hero with an interactive 3D globe, live pipeline-status panel, mission and "how it works" sections. |
| **Dashboard** | Pick region / hazard / period / detection settings and get an insight headline, KPIs, hazard-days-per-year chart, events-per-year, intensity or decadal charts, seasonality, largest-events table, data-quality report and export links. |
| **Explore** | Rotate the globe, switch live data layers (temperature, precipitation, wind, cloud, dryness), click any point or hotspot to see that region's hazard summary and current air quality. |
| **Trends** | Compare up to 5 regions with the same definition; multi-line chart plus a statistics table with the significance verdict. |
| **AI Lab** | CMIP6 (SSP5-8.5) projections to 2050 and a plain-language explanation grounded strictly in the computed numbers. |
| **Reports** | Report builder (CSV / events CSV / PDF + server-rendered PNG plot), World Bank global indicators and data-source citations. |

**Backend capabilities**

- Historical ERA5 daily weather ingest with per-year caching in MongoDB.
- Heatwave / heavy-rain / dry-spell detection with configurable percentile and minimum run length.
- Trend statistics: 5-year rolling mean, OLS with 95 % CI, Theil–Sen slope, tie-corrected Mann–Kendall, first-vs-last-decade comparison.
- Data-quality pipeline (range checks, spike removal, short-gap interpolation, coverage reporting).
- Global live layer grid, air quality, CMIP6 projections, World Bank indicators and AI insights.
- CSV/PDF/PNG exports; newsletter and community join endpoints.
- Per-IP rate limiting, host allow-list, security headers and an outbound quota limiter.

---

## Architecture

```
React (HashRouter)  ──/api──►  FastAPI  ──► services ──► MongoDB
 Dashboard/Explore/            │  rate limit, validation,    weather_years  (raw daily data, 1 doc / region-year)
 Trends/AI Lab/Reports         │  security headers           analyses       (computed results, 1 doc / query)
                               │                             api_cache      (geocode, layers, projections…)
                               │                             subscribers / community
                               └─► sources/http.py ─► Open-Meteo · World Bank · (Anthropic, optional)
                                   allow-list, timeouts, retries, outbound rate limit
```

**Request flow for `/api/trends`:** validate input → look up `analyses` in MongoDB → on a miss, take a
per-query lock (single-flight), fetch only the *missing years* from Open-Meteo into `weather_years`,
clean the data, detect events, compute trends, store the result in `analyses` → **read it back from
MongoDB** and return JSON (+ `meta.cache: hit|miss`). Overlapping requests (e.g. 1990–2020 then
1995–2024) reuse cached years.

---

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 5, React Router 6 (HashRouter), Chart.js 4 + react-chartjs-2, Leaflet + react-leaflet, Three.js, d3-geo, topojson-client + world-atlas |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic v2, httpx, NumPy, SciPy |
| Database | MongoDB (PyMongo); mongomock as an in-memory dev fallback |
| Exports | matplotlib (PNG plot), ReportLab (PDF), built-in CSV |
| Data | Open-Meteo (ERA5 archive, geocoding, CMIP6 Climate, CAMS Air Quality, Forecast), World Bank Open Data |
| Optional AI | Anthropic Claude API for narrative insights (rule-based fallback when no key) |
| Tests | pytest (backend), Vitest + Testing Library (frontend) |
| Deploy | Docker / Docker Compose, Render (`render.yaml`), any static host (Vercel/Netlify) |

---

## Project structure

```
climatesphere/
├─ backend/
│  ├─ app/
│  │  ├─ main.py              # FastAPI app: routes, validation, rate limiting, error handling
│  │  ├─ config.py            # env-driven Settings (frozen dataclass)
│  │  ├─ db.py                # MongoDB connection, indexes/TTLs, generic cache helpers
│  │  ├─ regions.py           # RegionSpec (point / bbox / place), presets, continent mapping
│  │  ├─ analysis/            # hazards, quality, trends, pipeline (pure functions)
│  │  ├─ services/            # analysis_service (orchestration), weather (ingest), export, extras
│  │  └─ sources/             # http gateway, open_meteo, worldbank adapters
│  ├─ tests/                  # pytest suite (synthetic upstream responses, in-memory DB)
│  ├─ requirements.txt
│  └─ Dockerfile
├─ frontend/
│  ├─ src/
│  │  ├─ App.jsx, main.jsx, state.jsx, api.js, styles.css
│  │  ├─ components/          # Globe, charts, Header, Footer, RegionPicker, Reveal, ui
│  │  ├─ pages/               # Home, Dashboard, Explore, Trends, AILab, Reports
│  │  └─ test/                # Vitest page tests + fixtures
│  ├─ index.html, vite.config.js, package.json
├─ design-reference/index.html   # original static design / API contract
├─ docker-compose.yml            # API + MongoDB
├─ render.yaml                   # Render blueprint for the API
├─ .env.example                  # placeholders only (safe to commit)
└─ README.md
```

---

## Getting started

### Prerequisites

- Python 3.12+
- Node.js 18+
- (Optional) MongoDB 6/7 locally, via Docker, or a MongoDB Atlas cluster

### 1) Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env            # optional; defaults work for local dev
uvicorn app.main:app --reload --port 8000
```

API: http://localhost:8000 · interactive docs: http://localhost:8000/api/docs

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 (Vite proxies `/api` to `:8000`).

### 3) Everything in Docker

```bash
docker compose up --build          # API on :8000 + MongoDB on :27017
```

MongoDB: run one locally (`docker compose up mongo`) or use a free Atlas cluster via `MONGO_URI`.
If MongoDB is unreachable and `ALLOW_MOCK_DB=1` (default for dev), the API falls back to an
**in-memory** database so the app still runs — nothing is persisted, and `/api/health` plus the footer
say so. Set `ALLOW_MOCK_DB=0` in production.

---

## Environment variables

Copy `.env.example` and edit locally. **Never commit real values.**

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB / Atlas connection string (secret in production). |
| `MONGO_DB` | `climatesphere` | Database name. |
| `ALLOW_MOCK_DB` | `1` | If `1`, fall back to in-memory mongomock when MongoDB is unreachable (dev only). |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed front-end origins. |
| `TRUST_PROXY` | `0` | Honour `X-Forwarded-For` (enable behind a trusted proxy). |
| `RATE_DEFAULT_PER_MIN` | `120` | Per-IP rate limit for cheap endpoints. |
| `RATE_HEAVY_PER_MIN` | `30` | Per-IP rate limit for endpoints that may hit upstream APIs. |
| `RATE_POST_PER_MIN` | `10` | Per-IP rate limit for POST endpoints. |
| `UPSTREAM_PER_MIN` | `300` | Global outbound-call cap to third-party APIs. |
| `WEATHER_TTL_DAYS` | `90` | TTL for cached raw weather years. |
| `ANALYSIS_TTL_DAYS` | `14` | TTL for cached computed analyses. |
| `ANTHROPIC_API_KEY` | *(empty)* | Optional; enables LLM narration (rule-based text otherwise). |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model used for narration. |
| `CLIMATE_MODELS` | `EC_Earth3P_HR,MRI_AGCM3_2_S,MPI_ESM1_2_XR` | CMIP6 models used for projections. |
| `MONGO_TIMEOUT_MS` | `3000` | Server-selection timeout (used for the mock-DB fallback). |
| `VITE_API_BASE` | *(empty)* | Frontend: backend base URL in production (e.g. `https://your-api.onrender.com`). |

---

## Database configuration

The app uses **MongoDB** as a NoSQL store for both raw ingested data and computed results.

**Collections**

| Collection | Contents | Index / TTL |
|---|---|---|
| `weather_years` | Raw daily Tmax/Tmin/precip, one doc per region-year | `(rkey, year)`; TTL on `fetched_at` = `WEATHER_TTL_DAYS` |
| `analyses` | Computed analysis results, one doc per query | TTL on `computed_at` = `ANALYSIS_TTL_DAYS` |
| `api_cache` | Generic cache (geocoding, layers, projections, indicators…) | TTL on `expires_at` |
| `subscribers` | Newsletter e-mails | unique index on `email` |
| `community` | Community-join requests | — |

**Local / Docker:** `MONGO_URI=mongodb://localhost:27017` (or `mongodb://mongo:27017` inside Compose).

**MongoDB Atlas (recommended for deployment):**

1. Create a free **M0** cluster.
2. Add a database user and allow your host's IP (Render/Cloud Run egress, or `0.0.0.0/0` for a demo).
3. Copy the connection string and set it **as an environment variable / secret** on the host:
   `MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority`
4. Set `ALLOW_MOCK_DB=0` in production so the app fails loudly instead of silently using in-memory storage.

> ⚠️ The Atlas connection string contains credentials. Keep it only in the host's secret store or a
> local, untracked `.env` file. It is excluded by `.gitignore` and must never be committed.

---

## API usage

All endpoints are `GET` unless noted. Region can be given as `?lat=&lon=`, a box
`?south=&west=&north=&east=` (max 30° per side), or `?region=<place name>`.

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Status: DB backend, cache counts, LLM config, last complete year. |
| `GET /api/presets` | Hotspot cities. |
| `GET /api/region?q=` | Place search (geocoding, cached 30 d). |
| `GET /api/trends` | Full analysis: series for charts, trend stats, events, insight, data quality. |
| `GET /api/summary` | Heatwave / heavy-rain / dry-spell headline numbers (+ `cyclones: null`). |
| `GET /api/layer?name=` | Live global layer grid (`temp`/`rain`/`wind`/`cloud`/`dry`). |
| `GET /api/aerosol` | Current air quality (PM2.5, PM10, dust, AOD). |
| `GET /api/projections?year=` | CMIP6 projections (2021–2050) vs 1991–2020 baseline. |
| `GET /api/insights?year=` | Narrative insight (LLM if configured, else rule-based). |
| `GET /api/impact` | World Bank global indicators. |
| `GET /api/export/csv` `GET /api/export/pdf` `GET /api/plot.png` | CSV (annual/events), PDF report, server-rendered plot. |
| `POST /api/newsletter` `POST /api/community/join` | Validated sign-ups stored in MongoDB. |

**Analysis parameters:** `hazard` (`heatwave`/`rainfall`/`drought`), `from`, `to`, `percentile`
(80–99.9), `min_days`, `mode` (`seasonal`/`annual`).

**Examples**

```bash
# Full heatwave analysis for Madrid, 1995–2014
curl "http://localhost:8000/api/trends?lat=40.4&lon=-3.7&name=Madrid&from=1995&to=2014"

# Console summary for a bounding box
curl "http://localhost:8000/api/summary?south=35&west=-10&north=45&east=3&name=Iberia&from=1995&to=2014"

# Live temperature layer for the globe
curl "http://localhost:8000/api/layer?name=temp"
```

The `region / summary / trends / layer / aerosol / projections / insights` response shapes follow the
contract documented in the comments of `design-reference/index.html`.

---

## Climate data sources

| Source | Used for | Notes |
|---|---|---|
| Open-Meteo **Historical Weather API** | Daily Tmax/Tmin/precipitation | ERA5 / ERA5-Land reanalysis (Copernicus/ECMWF), 1950–present, ~0.1–0.25° grid. |
| Open-Meteo **Geocoding API** | Place search | Cached 30 days. |
| Open-Meteo **Climate API** | CMIP6 projections to 2050 | Single high-emission pathway (SSP5-8.5). |
| Open-Meteo **Air Quality API** | PM2.5, PM10, dust, AOD | CAMS composition forecasts. |
| Open-Meteo **Forecast API** | Live global layer grid | Current conditions sampled on a 10° grid, cached 6 h. |
| World Bank **WDI** | Global climate-action indicators | Renewable share, forest area, CO₂ per person. |
| Anthropic **Claude** *(optional)* | Narrative insights | Constrained to computed numbers; rule-based fallback when unset. |

---

## Methodology

**Hazard detection**

- **Heatwave (default):** ≥ 3 consecutive days with daily Tmax above the **95th percentile for that
  calendar day** (percentile pooled over a ±7-day window across all years — the WMO/ETCCDI-style
  approach, so summer thresholds are not diluted by winter). `mode=annual` uses a single threshold for
  all days (the simple reading of the brief).
- **Heavy rainfall:** days above the 95th percentile of wet days (≥ 1 mm).
- **Dry spells:** ≥ 15 consecutive days < 1 mm — a **drought proxy**, not SPI/PDSI; in arid climates it
  is the norm.

**Per-year metrics:** event count, hazard days, mean duration, mean intensity (°C above threshold / mm),
peak value.

**Trend statistics**

- 5-year rolling mean, OLS with 95 % CI, **Theil–Sen** slope, **Mann–Kendall** test (tie-corrected),
  first-vs-last-decade comparison.
- A trend is called *significant* only if Mann–Kendall p < 0.05 **and** ≥ 10 usable years.
- The "+X %" headline is always shown with its p-value and an explicit "not significant" wording when
  applicable.

---

## Data handling & quality

Real-world weather data is noisy, so every series passes a quality pipeline:

- Units are requested in °C/mm **and** verified from the response (°F/K/inch converted).
- Physical-range checks; `Tmin > Tmax` rows dropped.
- Robust spike detection (MAD z-score **and** ≥ 20 °C deviation, so real extremes survive).
- Gaps ≤ 2 days linearly interpolated (temperature only); longer gaps stay missing and **break** event
  runs.
- Years with < 90 % coverage excluded and reported.
- Everything counted and surfaced in the `data_quality` block of `/api/trends`.

---

## Assumptions

- ERA5 reanalysis (via Open-Meteo, ~0.1–0.25° grid) stands in for station data. Coordinates are snapped
  to 0.1°.
- A box is represented by the **mean of up to 9 sample points**, which smooths local extremes (areal
  Tmax is lower than a point's).
- Thresholds use the *analysed period itself* as baseline (no fixed 1961–1990 / 1991–2020 reference),
  so results describe change **within** the window.
- Only complete calendar years are used (`to` ≤ last year); boxes crossing the antimeridian are not
  supported.
- Open-Meteo's Climate API offers one high-emission pathway (SSP5-8.5) to **2050** only — the UI says so
  rather than faking SSP scenarios or 2100.
- Tropical cyclones cannot be derived from daily weather data, so they are omitted (`cyclones: null`)
  instead of invented.

---

## Limitations

- **Reanalysis, not observations:** ERA5 is model-based; results are only as good as that product.
- **Window-relative baseline:** without a fixed reference period, absolute warming statements are
  limited; the app deliberately avoids them.
- **Areal smoothing:** box analyses understate localized extremes.
- **Autocorrelation:** the trend tests are not prewhitened, so p-values can be optimistic.
- **Drought proxy only:** dry-spell counts are not SPI/SPEI.
- **Single emissions pathway** for projections (SSP5-8.5) and **2050 horizon** only.
- **Free-tier upstream limits:** heavy first-time ingests can be slow (10–40 s per new region) and are
  rate-limited; a cold global layer build may briefly hit provider limits and retry.
- **Demo persistence:** with `ALLOW_MOCK_DB=1` and no MongoDB, nothing is persisted.

---

## Testing

```bash
# Backend (27 tests) - synthetic upstream responses + in-memory DB, no network
cd backend
pytest

# Frontend (9 page tests) - renders pages against real backend JSON, heavy widgets stubbed
cd frontend
npm test
```

Backend tests cover analysis logic (hazard detection, trend tests, quality pipeline), the API contract,
caching behaviour, input validation, rate limiting, security headers, exports and the host allow-list.
Frontend tests render each page against fixture JSON with WebGL/canvas/Leaflet stubbed.

---

## Deployment

**Database:** MongoDB Atlas M0 → copy the connection string.

**API — Render** (`render.yaml` blueprint) or **Cloud Run** using `backend/Dockerfile`. Set:

```text
MONGO_URI       = mongodb+srv://...        (secret)
ALLOW_MOCK_DB   = 0
TRUST_PROXY     = 1
CORS_ORIGINS    = https://<your-frontend-url>
ANTHROPIC_API_KEY = (optional)
```

**Frontend — Vercel / Netlify:** root `frontend`, build `npm run build`, output `dist`, env
`VITE_API_BASE=<API URL>`. The app uses `HashRouter`, so no rewrite rules are needed.

**Docker (self-host everything):** `docker compose up --build`.

---

## Security & performance

- Input validation on every parameter (ranges, enums, bbox sanity/size, place-name whitelist regex).
- Per-IP sliding-window rate limits (default / heavy / POST buckets, `429 + Retry-After`).
- Outbound calls only to an HTTPS host **allow-list** with timeouts, retries/backoff, a response-size
  cap and a global outbound rate limiter (stays inside free-tier quotas).
- Single-flight locks + bounded upstream concurrency; MongoDB TTL caches (weather 90 d, analyses 14 d,
  layers 6 h).
- CORS allow-list, security headers, body-size limit; CSV formula-injection guard.
- No user text is ever placed into an upstream URL path; duplicate newsletter sign-ups return the same
  response (no e-mail enumeration).
- **Secrets are environment-only.** `.gitignore` excludes `.env*` (except `.env.example`), keys,
  certificates and credential files.

---

## Verification status

Please read before judging the numbers:

- Backend logic, API, caching, validation, rate limiting and exports are covered by automated tests that
  use **synthetic upstream responses**.
- The Open-Meteo / World Bank / Anthropic integrations were written from their public documentation but
  were **not exercised against the live services** in the environment this was generated in (no outbound
  access). The first real run may need small adjustments (e.g. the CMIP6 model names in
  `CLIMATE_MODELS`, World Bank indicator codes in `sources/worldbank.py`).
- The UI is covered by render tests against real backend JSON (WebGL/canvas/Leaflet stubbed); it was
  **not inspected visually in a browser** during generation.
- PyMongo code was tested against `mongomock`, not a real MongoDB server (TTL indexes are only enforced
  by real MongoDB).

---

## AI tools used

I used AI assistants as productivity tools during this project, and I reviewed, ran and adapted
everything they produced:

- **ChatGPT** — used for **UI/UX design**. I supplied my own ideas and requirements and used its
  suggestions for layout, styling and interaction patterns, which I then refined into the React
  interface.
- **Claude (Anthropic)** — used to **generate the initial implementation code** (backend, frontend,
  tests and documentation). I reviewed, corrected and extended the generated code.
- **opencode** — used as a **coding/debugging agent** to investigate and fix runtime errors (for example,
  an upstream rate-limit failure that broke the Explore page's live data layer).

The running app can optionally call Claude at runtime to narrate insights (`ANTHROPIC_API_KEY`); the
text is constrained to the computed numbers, and a deterministic rule-based narrative is used when no
key is set.

---

## Data sources & licences

Open-Meteo (CC BY 4.0; free for non-commercial use — see their terms) · Copernicus ERA5 / CAMS ·
World Bank Open Data (CC BY 4.0) · Natural Earth via `world-atlas` (public domain) ·
map tiles © OpenStreetMap contributors, © CARTO.

---

## What I would improve with more time

Fixed reference baseline (1991–2020) and per-user baseline choice · prewhitening / block-bootstrap for
autocorrelated series · SPI/SPEI-based drought · station-data validation (NOAA GHCN) · background
pre-warming of popular regions and a job queue for long ingests · Redis for rate limits across multiple
instances · Leaflet-draw for box editing · e2e tests (Playwright) · i18n and accessibility audit ·
exact unit/integration tests against a MongoDB container in CI.
