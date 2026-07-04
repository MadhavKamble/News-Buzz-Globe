"""Pydantic models: query-parameter validation and GeoJSON response types."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class BoundingBox(BaseModel):
    """west,south,east,north in EPSG:4326 degrees."""

    west: float
    south: float
    east: float
    north: float

    @field_validator("west", "east")
    @classmethod
    def _lon_range(cls, v: float) -> float:
        if not -180.0 <= v <= 180.0:
            raise ValueError("longitude must be in [-180, 180]")
        return v

    @field_validator("south", "north")
    @classmethod
    def _lat_range(cls, v: float) -> float:
        if not -90.0 <= v <= 90.0:
            raise ValueError("latitude must be in [-90, 90]")
        return v

    @classmethod
    def from_query(cls, raw: str) -> "BoundingBox":
        parts = raw.split(",")
        if len(parts) != 4:
            raise ValueError("bbox must be 'west,south,east,north'")
        west, south, east, north = (float(p) for p in parts)
        box = cls(west=west, south=south, east=east, north=north)
        if box.south > box.north:
            raise ValueError("bbox south must be <= north")
        return box


class EventProperties(BaseModel):
    id: int
    title: str | None
    intensity: float
    num_articles: int | None
    num_sources: int | None
    num_mentions: int | None
    avg_tone: float | None
    event_code: str
    event_root_code: str
    quad_class: int | None
    date_added: datetime
    location: str | None
    country_code: str | None
    source_url: str | None
    actor1: str | None
    actor2: str | None


class StoryProperties(BaseModel):
    id: int
    summary: str
    member_count: int
    total_articles: int | None
    total_sources: int | None
    intensity: float
    avg_tone: float | None
    trend: Literal["rising", "falling", "steady"] = "steady"
    articles_last_hour: int | None = None
    articles_prev_hour: int | None = None
    location: str | None
    country_code: str | None
    source_urls: list[str]
    event_ids: list[int]
    earliest: datetime | None
    latest: datetime | None
    run_at: datetime


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # (lon, lat)


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: EventProperties


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]


class StoryFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: StoryProperties


class StoryCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[StoryFeature]
