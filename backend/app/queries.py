"""Event queries against the PostGIS events table."""

from datetime import datetime

from sqlalchemy import Float, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.sql import literal

from backend.app.schemas import (
    BoundingBox,
    EventProperties,
    Feature,
    FeatureCollection,
    PointGeometry,
    StoryCollection,
    StoryFeature,
    StoryProperties,
)
from common.models import events_scored as events
from common.models import story_clusters
from ingestion.config import IntensityConfig  # single source of formula params


def _effective_intensity(at: datetime):
    """Intensity recomputed with recency decay relative to `at` (SQL-side).

    Mirrors ingestion.scoring.intensity_score so scrubbing the time slider
    makes hotspots grow/fade instead of showing as-of-ingestion scores.
    """
    cfg = IntensityConfig()
    norm_articles = func.least(
        1.0,
        func.ln(1.0 + func.greatest(func.coalesce(events.c.num_articles, 0), 0))
        / func.ln(literal(1.0 + cfg.articles_cap, Float)),
    )
    norm_sources = func.least(
        1.0,
        func.ln(1.0 + func.greatest(func.coalesce(events.c.num_sources, 0), 0))
        / func.ln(literal(1.0 + cfg.sources_cap, Float)),
    )
    age_hours = func.greatest(
        0.0,
        func.extract("epoch", literal(at) - events.c.date_added) / 3600.0,
    )
    decay = func.exp(-0.6931471805599453 * age_hours / cfg.half_life_hours)
    return (
        cfg.w_articles * norm_articles
        + cfg.w_sources * norm_sources
        + cfg.w_recency * decay
    )


def fetch_events(
    engine: Engine,
    bbox: BoundingBox | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    categories: list[str] | None = None,
    limit: int = 500,
    at: datetime | None = None,
) -> FeatureCollection:
    intensity_col = (
        _effective_intensity(at).label("effective_intensity")
        if at is not None
        else events.c.intensity.label("effective_intensity")
    )
    stmt = select(events, intensity_col)
    if bbox is not None:
        envelope = func.ST_MakeEnvelope(bbox.west, bbox.south, bbox.east, bbox.north, 4326)
        stmt = stmt.where(events.c.geom.op("&&")(envelope))
    if start is not None:
        stmt = stmt.where(events.c.date_added >= start)
    if end is not None:
        stmt = stmt.where(events.c.date_added <= end)
    if categories:
        stmt = stmt.where(events.c.event_root_code.in_(categories))
    stmt = stmt.order_by(intensity_col.desc()).limit(limit)

    features: list[Feature] = []
    with engine.connect() as conn:
        for row in conn.execute(stmt).mappings():
            features.append(
                Feature(
                    geometry=PointGeometry(coordinates=(row["lon"], row["lat"])),
                    properties=EventProperties(
                        id=row["global_event_id"],
                        title=row["page_title"],
                        intensity=row["effective_intensity"],
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


def fetch_stories(engine: Engine, limit: int = 500) -> StoryCollection:
    """Latest clustering run's story hotspots, highest intensity first."""
    latest_run = select(func.max(story_clusters.c.run_at)).scalar_subquery()
    stmt = (
        select(story_clusters)
        .where(story_clusters.c.run_at == latest_run)
        .order_by(story_clusters.c.intensity.desc())
        .limit(limit)
    )
    features: list[StoryFeature] = []
    with engine.connect() as conn:
        for row in conn.execute(stmt).mappings():
            features.append(
                StoryFeature(
                    geometry=PointGeometry(coordinates=(row["lon"], row["lat"])),
                    properties=StoryProperties(
                        id=row["id"],
                        summary=row["summary"],
                        member_count=row["member_count"],
                        total_articles=row["total_articles"],
                        total_sources=row["total_sources"],
                        intensity=min(1.0, row["intensity"]),
                        avg_tone=row["avg_tone"],
                        trend=row["trend"],
                        articles_last_hour=row["articles_last_hour"],
                        articles_prev_hour=row["articles_prev_hour"],
                        location=row["location"],
                        country_code=row["country_code"],
                        source_urls=row["source_urls"] or [],
                        event_ids=row["event_ids"] or [],
                        earliest=row["earliest"],
                        latest=row["latest"],
                        run_at=row["run_at"],
                    ),
                )
            )
    return StoryCollection(features=features)
