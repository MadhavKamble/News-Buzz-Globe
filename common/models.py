"""SQLAlchemy table definitions.

Two layers since Phase 7:
- ``raw_events`` (raw_metadata): landing table owned and created by the
  Python ingestion pipeline. No geometry, no scores.
- ``events_scored`` (scored_metadata): transformed table owned and built by
  the dbt project (staging -> cleaned -> scored). Declared here only so the
  API can query it and tests can create an equivalent fixture table — the
  pipeline never creates it in production.
"""

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY

raw_metadata = MetaData()
scored_metadata = MetaData()
stories_metadata = MetaData()


def _core_columns() -> list[Column]:
    return [
        Column("global_event_id", BigInteger, primary_key=True, autoincrement=False),
        Column("event_date", DateTime(timezone=True), nullable=False),
        Column("date_added", DateTime(timezone=True), nullable=False, index=True),
        Column("actor1_name", Text),
        Column("actor2_name", Text),
        Column("event_code", Text, nullable=False),
        Column("event_root_code", Text, nullable=False),
        Column("quad_class", SmallInteger),
        Column("num_mentions", Integer),
        Column("num_sources", Integer),
        Column("num_articles", Integer),
        Column("avg_tone", Float),
        Column("action_geo_full_name", Text),
        Column("action_geo_country_code", Text),
        Column("lat", Float, nullable=False),
        Column("lon", Float, nullable=False),
        Column("source_url", Text),
        Column("page_title", Text),
        Column(
            "ingested_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    ]


raw_events = Table("raw_events", raw_metadata, *_core_columns())

events_scored = Table(
    "events_scored",
    scored_metadata,
    *_core_columns(),
    # GeoAlchemy2 auto-creates a GiST index for this column on create_all
    # (tests); in production dbt's post-hook builds the same index.
    Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=False),
    Column("intensity", Float, nullable=False),
    Column("scored_at", DateTime(timezone=True), server_default=func.now()),
)

# Phase 8: deduplicated stories — clusters of events about the same real-world
# story (embedding similarity), labeled by a locally hosted LLM summary.
story_clusters = Table(
    "story_clusters",
    stories_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_at", DateTime(timezone=True), nullable=False, index=True),
    Column("summary", Text, nullable=False),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    Column("member_count", Integer, nullable=False),
    Column("total_articles", Integer),
    Column("total_sources", Integer),
    Column("intensity", Float, nullable=False),
    Column("avg_tone", Float),
    Column("event_ids", ARRAY(BigInteger), nullable=False),
    Column("source_urls", ARRAY(Text)),
    # Phase 9: coverage trend vs. one hour earlier.
    Column("trend", Text, nullable=False, server_default="steady"),
    Column("articles_last_hour", Integer),
    Column("articles_prev_hour", Integer),
    Column("location", Text),
    Column("country_code", Text),
    Column("earliest", DateTime(timezone=True)),
    Column("latest", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
