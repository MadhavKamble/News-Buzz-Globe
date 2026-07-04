"""Event queries against the PostGIS events table."""

from datetime import datetime

from sqlalchemy import Engine, func, select

from backend.app.schemas import (
    BoundingBox,
    EventProperties,
    Feature,
    FeatureCollection,
    PointGeometry,
)
from common.models import events


def fetch_events(
    engine: Engine,
    bbox: BoundingBox | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    categories: list[str] | None = None,
    limit: int = 500,
) -> FeatureCollection:
    stmt = select(events)
    if bbox is not None:
        envelope = func.ST_MakeEnvelope(bbox.west, bbox.south, bbox.east, bbox.north, 4326)
        stmt = stmt.where(events.c.geom.op("&&")(envelope))
    if start is not None:
        stmt = stmt.where(events.c.date_added >= start)
    if end is not None:
        stmt = stmt.where(events.c.date_added <= end)
    if categories:
        stmt = stmt.where(events.c.event_root_code.in_(categories))
    stmt = stmt.order_by(events.c.intensity.desc()).limit(limit)

    features: list[Feature] = []
    with engine.connect() as conn:
        for row in conn.execute(stmt).mappings():
            features.append(
                Feature(
                    geometry=PointGeometry(coordinates=(row["lon"], row["lat"])),
                    properties=EventProperties(
                        id=row["global_event_id"],
                        title=row["page_title"],
                        intensity=row["intensity"],
                        num_articles=row["num_articles"],
                        num_sources=row["num_sources"],
                        num_mentions=row["num_mentions"],
                        avg_tone=row["avg_tone"],
                        event_code=row["event_code"],
                        event_root_code=row["event_root_code"],
                        quad_class=row["quad_class"],
                        date_added=row["date_added"],
                        location=row["action_geo_full_name"],
                        country_code=row["action_geo_country_code"],
                        source_url=row["source_url"],
                        actor1=row["actor1_name"],
                        actor2=row["actor2_name"],
                    ),
                )
            )
    return FeatureCollection(features=features)
