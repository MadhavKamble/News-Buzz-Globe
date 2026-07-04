"""SQLAlchemy table definitions shared by the ingestion loader and the API.

From Phase 7 onward, dbt owns the transformed/scored layer; this table is the
raw+scored landing table the pipeline writes to.
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

metadata = MetaData()

events = Table(
    "events",
    metadata,
    Column("global_event_id", BigInteger, primary_key=True, autoincrement=False),
    Column("event_date", DateTime(timezone=True), nullable=False),
    Column("date_added", DateTime(timezone=True), nullable=False, index=True),
    Column("actor1_name", Text),
    Column("actor2_name", Text),
    Column("event_code", Text, nullable=False),
    Column("event_root_code", Text, nullable=False, index=True),
    Column("quad_class", SmallInteger),
    Column("num_mentions", Integer),
    Column("num_sources", Integer),
    Column("num_articles", Integer),
    Column("avg_tone", Float),
    Column("action_geo_full_name", Text),
    Column("action_geo_country_code", Text),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    # GeoAlchemy2 auto-creates the GiST index (idx_events_geom) for this column.
    Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=False),
    Column("source_url", Text),
    Column("page_title", Text),
    Column("intensity", Float, nullable=False),
    Column(
        "ingested_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
