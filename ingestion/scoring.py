"""Buzz-intensity scoring.

Pure functions so they are trivially unit-testable and reusable by the
backend (which re-applies recency decay at query time). Canonical scoring
moves into dbt in Phase 7; this module remains the reference implementation
and the source of the query-time recency term.
"""

import math
from datetime import UTC, datetime

from ingestion.config import IntensityConfig


def normalize_count(value: float | int | None, cap: int) -> float:
    """Saturating log normalization: log1p(value) / log1p(cap), clipped to [0, 1].

    Article/source counts are heavy-tailed; log1p tames the tail and the fixed
    cap keeps scores comparable across ingestion batches.
    """
    if value is None or value <= 0:
        return 0.0
    if cap <= 0:
        raise ValueError("cap must be positive")
    return min(1.0, math.log1p(float(value)) / math.log1p(float(cap)))


def recency_decay(
    event_time: datetime, reference_time: datetime, half_life_hours: float
) -> float:
    """Exponential decay of freshness: 1.0 at reference_time, 0.5 one half-life earlier.

    Events timestamped in the future of the reference time clamp to 1.0.
    """
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=UTC)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)
    age_hours = (reference_time - event_time).total_seconds() / 3600.0
    if age_hours <= 0:
        return 1.0
    return math.exp(-math.log(2) * age_hours / half_life_hours)


def intensity_score(
    num_articles: int | None,
    num_sources: int | None,
    event_time: datetime,
    reference_time: datetime | None = None,
    config: IntensityConfig | None = None,
) -> float:
    """Combined buzz intensity in [0, 1] (given weights summing to 1)."""
    cfg = config or IntensityConfig()
    ref = reference_time or datetime.now(UTC)
    return (
        cfg.w_articles * normalize_count(num_articles, cfg.articles_cap)
        + cfg.w_sources * normalize_count(num_sources, cfg.sources_cap)
        + cfg.w_recency * recency_decay(event_time, ref, cfg.half_life_hours)
    )
