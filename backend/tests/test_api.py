import pytest
from .conftest import CALLS


def test_health(client):
    j = client.get("/api/health").json()
    assert j["status"] == "ok" and "in-memory" in j["db"]["backend"]


def test_trends_flow_and_db_cache(client):
    q = "/api/trends?lat=40.4&lon=-3.7&name=Madrid&from=1995&to=2014"
    r1 = client.get(q)
    assert r1.status_code == 200, r1.text
    j = r1.json()
    assert j["meta"]["cache"] == "miss" and j["ingest"]["years_fetched"] == 20
    assert {"years", "series", "units", "source"} <= j.keys()                    # contract from the design
    assert {"frequency", "intensity", "duration"} <= j["series"].keys()
    n = len(CALLS)
    j2 = client.get(q).json()
    assert j2["meta"]["cache"] == "hit" and len(CALLS) == n                       # served from MongoDB, no upstream call
    # overlapping range only fetches the missing years
    j3 = client.get("/api/trends?lat=40.4&lon=-3.7&from=1990&to=2014").json()
    assert j3["ingest"]["years_fetched"] == 5 and j3["ingest"]["years_from_cache"] == 20


@pytest.mark.parametrize("qs", [
    "lat=95&lon=0&from=1990&to=2010", "lat=10&lon=0&from=1990&to=2090", "lat=10&lon=0&from=2000&to=2002",
    "lat=10&lon=0&from=1900&to=2010", "south=0&west=0&north=50&east=10&from=1990&to=2010", "south=5&west=0&north=1&east=10&from=1990&to=2010",
    "lat=10&lon=0&from=1990&to=2010&hazard=tornado", "lat=10&lon=0&from=1990&to=2010&percentile=10", "region=<script>alert(1)</script>&from=1990&to=2010",
    "from=1990&to=2010"])
def test_input_validation(client, qs):
    assert client.get("/api/trends?" + qs).status_code == 422


def test_region_name_and_lookup(client):
    j = client.get("/api/region?q=Madrid").json()
    assert j["region"] == "eu" and j["lat"] == 40.0
    t = client.get("/api/trends?region=Madrid&from=1995&to=2010")
    assert t.status_code == 200 and t.json()["region"]["name"] == "Testville"


def test_bbox_trend(client):
    r = client.get("/api/trends?south=35&west=-10&north=45&east=3&from=1995&to=2010&name=Iberia")
    assert r.status_code == 200 and r.json()["region"]["kind"] == "bbox"
    assert len([u for u in CALLS if "archive" in u]) >= 1


def test_summary_contract(client):
    j = client.get("/api/summary?lat=40&lon=-3&from=1995&to=2014").json()
    assert {"heatwaves", "extreme_rainfall", "drought", "cyclones"} <= j.keys() and j["cyclones"] is None
    assert {"value", "change_pct", "period"} <= j["heatwaves"].keys()


def test_other_hazards(client):
    for hz in ("rainfall", "drought"):
        r = client.get(f"/api/trends?lat=40&lon=-3&from=1995&to=2014&hazard={hz}")
        assert r.status_code == 200 and r.json()["hazard"] == hz


def test_exports(client):
    base = "lat=40&lon=-3&from=1995&to=2014&name=Madrid"
    csv = client.get(f"/api/export/csv?{base}")
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("year,") and len(csv.text.splitlines()) == 21
    assert "attachment" in csv.headers["content-disposition"]
    assert client.get(f"/api/export/csv?{base}&kind=events").text.startswith("start,end")
    pdf = client.get(f"/api/export/pdf?{base}")
    assert pdf.content[:5] == b"%PDF-"
    png = client.get(f"/api/plot.png?{base}")
    assert png.content[:4] == b"\x89PNG"


def test_extras(client):
    assert client.get("/api/aerosol?lat=40&lon=-3").json()["pm"]["value"] == 12.3
    lay = client.get("/api/layer?name=temp").json()
    assert lay["width"] * lay["height"] == len(lay["values"]) == 648 and all(0 <= v <= 1 for v in lay["values"])
    pr = client.get("/api/projections?lat=40&lon=-3&year=2040").json()
    assert pr["metrics"]["temp"]["value"] > 0 and "SSP5-8.5" in pr["metrics"]["temp"]["pathway"]
    ins = client.get("/api/insights?lat=40&lon=-3&year=2040").json()
    assert ins["text"] and "rule-based" in ins["model"]
    assert client.get("/api/impact").json()["indicators"][0]["value"] == 19.5
    assert client.get("/api/projections?lat=40&lon=-3&year=2100").status_code == 422


def test_newsletter_and_join(client):
    assert client.post("/api/newsletter", json={"email": "A@b.co"}).status_code == 201
    assert client.post("/api/newsletter", json={"email": "a@b.co"}).status_code == 201   # duplicate: same response
    assert client.post("/api/newsletter", json={"email": "nope"}).status_code == 422
    assert client.post("/api/community/join", json={"name": "Ana", "email": "ana@x.org"}).status_code == 201
    assert client.post("/api/community/join", json={"name": "<b>", "email": "ana@x.org"}).status_code == 422


def test_rate_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_DEFAULT_PER_MIN", "3")
    from app.main import limiter
    limiter.hits.clear()
    codes = [client.get("/api/presets").status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3] == 429


def test_security_headers_and_host_allowlist(client):
    assert client.get("/api/presets").headers["x-content-type-options"] == "nosniff"
    from app.sources import http
    import app.sources.http as h, importlib
    real = importlib.reload(h).fetch_json
    with pytest.raises(h.UpstreamError):
        real("https://evil.example.com/x")
    with pytest.raises(h.UpstreamError):
        real("http://archive-api.open-meteo.com/v1/archive")
