"""Ingestion configuration. Everything is overridable via environment variables."""

import os
from dataclasses import dataclass, field

GDELT_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://nbg:nbg_dev_password@localhost:5432/newsbuzz",
    )


@dataclass(frozen=True)
class IntensityConfig:
    """Weights and shape parameters for the buzz-intensity formula.

    intensity = w_articles * norm(NumArticles)
              + w_sources  * norm(NumSources)
              + w_recency  * recency_decay(event_time)

    norm() is a saturating log: log1p(x) / log1p(cap), clipped to [0, 1].
    A fixed cap (rather than per-batch min-max) keeps scores comparable
    across ingestion runs and across time-slider positions.
    recency_decay is exponential with a configurable half-life.
    """

    w_articles: float = field(
        default_factory=lambda: float(os.environ.get("INTENSITY_W_ARTICLES", "0.4"))
    )
    w_sources: float = field(
        default_factory=lambda: float(os.environ.get("INTENSITY_W_SOURCES", "0.3"))
    )
    w_recency: float = field(
        default_factory=lambda: float(os.environ.get("INTENSITY_W_RECENCY", "0.3"))
    )
    articles_cap: int = field(
        default_factory=lambda: int(os.environ.get("INTENSITY_ARTICLES_CAP", "100"))
    )
    sources_cap: int = field(
        default_factory=lambda: int(os.environ.get("INTENSITY_SOURCES_CAP", "25"))
    )
    half_life_hours: float = field(
        default_factory=lambda: float(os.environ.get("INTENSITY_HALF_LIFE_HOURS", "6"))
    )
