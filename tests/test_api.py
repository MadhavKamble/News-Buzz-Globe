"""API tests via FastAPI TestClient against a dedicated PostGIS test database.

Requires a reachable Postgres (local docker-compose or the CI service
container); the suite creates/tears down its own `newsbuzz_test` database.
"""

import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.main import app, engine_dep
from common.models import scored_metadata as metadata

ADMIN_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://nbg:nbg_dev_password@localhost:5432/newsbuzz",
)
TEST_DB = "newsbuzz_test"

T0 = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 4, 18, 0, tzinfo=UTC)

FIXTURES = [
    # (id, lat, lon, root_code, date_added, intensity, title)
    (1, 48.8566, 2.3522, "04", T0, 0.9, "Paris summit"),
    (2, 35.6762, 139.6503, "14", T0, 0.5, "Tokyo protest"),
    (3, -33.8688, 151.2093, "04", T1, 0.7, "Sydney talks"),
]


def _fixture_row(event_id, lat, lon, root_code, date_added, intensity, title):
    return {
        "global_event_id": event_id,
        "event_date": date_added,
        "date_added": date_added,
        "actor1_name": "ACTOR1",
        "actor2_name": None,
        "event_code": root_code + "2",
        "event_root_code": root_code,
        "quad_class": 1,
        "num_mentions": 10,
        "num_sources": 3,
        "num_articles": 8,
        "avg_tone": -1.5,
        "action_geo_full_name": title,
        "action_geo_country_code": "XX",
        "lat": lat,
        "lon": lon,
        "geom": f"SRID=4326;POINT({lon} {lat})",
        "source_url": f"https://example.com/{event_id}",
        "page_title": title,
        "intensity": intensity,
    }


@pytest.fixture(scope="module")
def test_engine():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Postgres not reachable for API tests: {exc}")
    test_url = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"
    engine = create_engine(test_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    metadata.create_all(engine)
    from common.models import events_scored as events

    with engine.begin() as conn:
        conn.execute(events.insert(), [_fixture_row(*f) for f in FIXTURES])
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture()
def client(test_engine):
    app.dependency_overrides[engine_dep] = lambda: test_engine
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealth:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}


class TestEvents:
    def test_returns_valid_geojson(self, client):
        body = client.get("/events").json()
        assert body["type"] == "FeatureCollection"
        assert len(body["features"]) == 3
        feature = body["features"][0]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert len(feature["geometry"]["coordinates"]) == 2
        assert {"id", "title", "intensity", "event_root_code"} <= set(
            feature["properties"]
        )

    def test_ordered_by_intensity_desc(self, client):
        ids = [
            f["properties"]["id"] for f in client.get("/events").json()["features"]
        ]
        assert ids == [1, 3, 2]

    def test_bbox_filter(self, client):
        # Europe-only box: keeps Paris, drops Tokyo and Sydney.
        body = client.get("/events", params={"bbox": "-10,35,30,60"}).json()
        assert [f["properties"]["id"] for f in body["features"]] == [1]

    def test_time_window_filter(self, client):
        body = client.get(
            "/events",
            params={"start": "2026-07-04T15:00:00Z", "end": "2026-07-04T23:00:00Z"},
        ).json()
        assert [f["properties"]["id"] for f in body["features"]] == [3]

    def test_category_filter(self, client):
        body = client.get("/events", params={"category": ["14"]}).json()
        assert [f["properties"]["id"] for f in body["features"]] == [2]

    def test_multiple_categories(self, client):
        body = client.get("/events", params={"category": ["04", "14"]}).json()
        assert len(body["features"]) == 3

    def test_limit(self, client):
        body = client.get("/events", params={"limit": 1}).json()
        assert [f["properties"]["id"] for f in body["features"]] == [1]

    def test_combined_filters(self, client):
        body = client.get(
            "/events",
            params={"bbox": "-180,-90,180,90", "category": ["04"], "limit": 10},
        ).json()
        assert [f["properties"]["id"] for f in body["features"]] == [1, 3]


class TestThemes:
    def test_themes_endpoint(self, client):
        body = client.get("/themes").json()
        assert "diplomacy" in body and "conflict" in body
        all_codes = sorted(c for t in body.values() for c in t["codes"])
        assert all_codes == [f"{i:02d}" for i in range(1, 21)]

    def test_theme_filter(self, client):
        # 'protest' = root code 14 -> Tokyo fixture only.
        body = client.get("/events", params={"theme": ["protest"]}).json()
        assert [f["properties"]["id"] for f in body["features"]] == [2]

    def test_theme_merges_with_category(self, client):
        body = client.get(
            "/events", params={"theme": ["protest"], "category": ["04"]}
        ).json()
        assert len(body["features"]) == 3

    def test_unknown_theme_rejected(self, client):
        assert client.get("/events", params={"theme": ["sports"]}).status_code == 422


class TestReferenceTimeIntensity:
    def test_at_recomputes_recency(self, client):
        # Both '04' events have identical counts; at T1 the Sydney event
        # (date_added=T1) is fresher than Paris (T0) regardless of the higher
        # stored intensity fixture value for Paris.
        body = client.get(
            "/events",
            params={"category": ["04"], "at": "2026-07-04T18:00:00Z"},
        ).json()
        ids = [f["properties"]["id"] for f in body["features"]]
        assert ids == [3, 1]
        intensities = [f["properties"]["intensity"] for f in body["features"]]
        assert intensities[0] > intensities[1]
        assert all(0.0 <= i <= 1.0 for i in intensities)

    def test_without_at_uses_stored_intensity(self, client):
        body = client.get("/events", params={"category": ["04"]}).json()
        assert [f["properties"]["id"] for f in body["features"]] == [1, 3]

    def test_at_with_time_window(self, client):
        body = client.get(
            "/events",
            params={
                "start": "2026-07-04T00:00:00Z",
                "end": "2026-07-04T13:00:00Z",
                "at": "2026-07-04T13:00:00Z",
            },
        ).json()
        # Only the two T0 events fall in the window.
        assert len(body["features"]) == 2

    def test_bad_at_rejected(self, client):
        assert client.get("/events", params={"at": "not-a-date"}).status_code == 422


class TestValidation:
    @pytest.mark.parametrize(
        "bbox",
        ["1,2,3", "a,b,c,d", "-200,35,30,60", "-10,70,30,60", "-10,-95,30,60"],
    )
    def test_bad_bbox_rejected(self, client, bbox):
        assert client.get("/events", params={"bbox": bbox}).status_code == 422

    @pytest.mark.parametrize("code", ["0", "21", "99", "xx", "004"])
    def test_bad_category_rejected(self, client, code):
        assert client.get("/events", params={"category": [code]}).status_code == 422

    def test_bad_limit_rejected(self, client):
        assert client.get("/events", params={"limit": 0}).status_code == 422
        assert client.get("/events", params={"limit": 99999}).status_code == 422

    def test_start_after_end_rejected(self, client):
        resp = client.get(
            "/events",
            params={"start": "2026-07-05T00:00:00Z", "end": "2026-07-04T00:00:00Z"},
        )
        assert resp.status_code == 422

    def test_bad_datetime_rejected(self, client):
        assert client.get("/events", params={"start": "not-a-date"}).status_code == 422
