"""Load validated events into the raw landing table (Postgres).

Upsert on GLOBALEVENTID handles duplicates across export windows: GDELT
re-emits an event when its mention/article counts grow, so on conflict we
take the fresher counts. Scoring/geometry happen downstream in dbt
(staging -> cleaned -> scored) since Phase 7.
"""

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from common.models import raw_events, raw_metadata
from ingestion.gdelt import RawEvent
from ingestion.partitions import ensure_partition_for, ensure_raw_events


def ensure_schema(engine: Engine) -> None:
    # Partitioned raw_events first (create or migrate), then the rest
    # (ingestion_runs); create_all skips the already-existing raw_events.
    ensure_raw_events(engine)
    ensure_partition_for(engine, datetime.now(UTC))
    raw_metadata.create_all(engine)


def event_to_row(event: RawEvent) -> dict:
    return {
        "global_event_id": event.global_event_id,
        "event_date": event.event_date,
        "date_added": event.date_added,
        "actor1_name": event.actor1_name,
        "actor2_name": event.actor2_name,
        "event_code": event.event_code,
        "event_root_code": event.event_root_code,
        "quad_class": event.quad_class,
        "num_mentions": event.num_mentions,
        "num_sources": event.num_sources,
        "num_articles": event.num_articles,
        "avg_tone": event.avg_tone,
        "action_geo_full_name": event.action_geo_full_name,
        "action_geo_country_code": event.action_geo_country_code,
        "lat": event.lat,
        "lon": event.lon,
        "source_url": event.source_url,
        "page_title": event.page_title,
    }


def upsert_events(engine: Engine, rows: list[dict], chunk_size: int = 1000) -> int:
    """Insert rows, updating volatile fields on conflict. Returns row count.

    Conflict target is the composite PK (global_event_id, date_added): the
    partition key must be part of any unique constraint. A GDELT re-emission
    with a fresher date_added lands as a new row; the dbt cleaned layer
    dedupes to the latest per event id.
    """
    if not rows:
        return 0
    for month in {str(r["date_added"])[:7] for r in rows}:
        ensure_partition_for(engine, datetime.fromisoformat(month + "-01T00:00:00+00:00"))
    update_cols = [
        "num_mentions",
        "num_sources",
        "num_articles",
        "avg_tone",
        "page_title",
    ]
    written = 0
    with engine.begin() as conn:
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            stmt = pg_insert(raw_events).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["global_event_id", "date_added"],
                set_={col: stmt.excluded[col] for col in update_cols},
            )
            conn.execute(stmt)
            written += len(chunk)
    return written
