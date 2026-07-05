"""Partitioning + retention/rollup tests against a dedicated PostGIS database."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from ingestion.load import ensure_schema, upsert_events
from ingestion.maintenance import run_once as maintenance_run
from ingestion.partitions import ensure_raw_events, list_partitions

ADMIN_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://nbg:nbg_dev_password@localhost:5432/newsbuzz",
)
TEST_DB = "newsbuzz_test_part"

NOW = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
OLD = NOW - timedelta(days=120)  # well past the 90-day window
RECENT = NOW - timedelta(days=3)


def make_row(event_id, date_added, lat=48.85, lon=2.35, root="04", articles=10):
    return {
        "global_event_id": event_id,
        "event_date": date_added,
        "date_added": date_added,
        "actor1_name": "A",
        "actor2_name": None,
        "event_code": root + "2",
        "event_root_code": root,
        "quad_class": 1,
        "num_mentions": articles,
        "num_sources": 3,
        "num_articles": articles,
        "avg_tone": -2.0,
        "action_geo_full_name": "Somewhere",
        "action_geo_country_code": "XX",
        "lat": lat,
        "lon": lon,
        "source_url": None,
        "page_title": None,
    }


@pytest.fixture(scope="module")
def engine():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Postgres not reachable: {exc}")
    url = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"
    eng = create_engine(url)
    ensure_schema(eng)
    upsert_events(
        eng,
        [
            make_row(1, OLD, lat=10.0, lon=20.0, root="14", articles=5),
            make_row(2, OLD + timedelta(hours=2), lat=10.5, lon=20.5, root="14", articles=7),
            make_row(3, OLD + timedelta(hours=3), lat=10.4, lon=20.2, root="18", articles=4),
            make_row(4, RECENT, articles=12),
            make_row(5, RECENT + timedelta(hours=1), articles=9),
        ],
    )
    yield eng
    eng.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    admin.dispose()


class TestPartitioning:
    def test_monthly_partitions_created(self, engine):
        names = [p["name"] for p in list_partitions(engine)]
        assert f"raw_events_y{OLD.year}m{OLD.month:02d}" in names
        assert f"raw_events_y{RECENT.year}m{RECENT.month:02d}" in names

    def test_last_7_days_query_prunes_old_partitions(self, engine):
        """The pruning guarantee: a recent-window query must not touch old months."""
        old_part = f"raw_events_y{OLD.year}m{OLD.month:02d}"
        recent_part = f"raw_events_y{RECENT.year}m{RECENT.month:02d}"
        with engine.connect() as conn:
            plan = "\n".join(
                r[0]
                for r in conn.execute(
                    text(
                        "EXPLAIN SELECT * FROM raw_events "
                        "WHERE date_added >= :cutoff"
                    ),
                    {"cutoff": NOW - timedelta(days=7)},
                )
            )
        assert recent_part in plan
        assert old_part not in plan

    def test_ensure_raw_events_idempotent(self, engine):
        ensure_raw_events(engine)  # second call must be a no-op
        assert len(list_partitions(engine)) >= 2

    def test_upsert_conflict_updates_counts(self, engine):
        upsert_events(engine, [make_row(4, RECENT, articles=99)])
        with engine.connect() as conn:
            articles = conn.execute(
                text("SELECT num_articles FROM raw_events WHERE global_event_id = 4")
            ).scalar()
        assert articles == 99


class TestRetentionRollup:
    def test_old_partition_rolled_up_then_dropped(self, engine):
        metrics = maintenance_run(engine.url.render_as_string(hide_password=False), as_of=NOW)
        old_part = f"raw_events_y{OLD.year}m{OLD.month:02d}"
        assert old_part in metrics["partitions_dropped"]
        names = [p["name"] for p in list_partitions(engine)]
        assert old_part not in names

        with engine.connect() as conn:
            rollups = conn.execute(
                text(
                    "SELECT day, cell_lat, cell_lon, event_root_code, event_count, "
                    "total_articles FROM events_rollup_daily ORDER BY event_root_code"
                )
            ).fetchall()
        # Events 1+2 share day/2-degree-cell/root '14' (lat 10.x -> cell 5,
        # lon 20.x -> cell 10); event 3 is root '18' in the same cell.
        assert len(rollups) == 2
        merged = rollups[0]
        assert merged.event_root_code == "14"
        assert merged.event_count == 2
        assert merged.total_articles == 12
        assert (merged.cell_lat, merged.cell_lon) == (5, 10)
        assert rollups[1].event_root_code == "18"
        assert rollups[1].event_count == 1

    def test_recent_raw_rows_untouched(self, engine):
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM raw_events")
            ).scalar()
        assert count == 2  # events 4 and 5 remain as raw rows

    def test_rerun_is_idempotent(self, engine):
        metrics = maintenance_run(engine.url.render_as_string(hide_password=False), as_of=NOW)
        assert metrics["partitions_dropped"] == []
        assert metrics["rollup_rows_written"] == 0
