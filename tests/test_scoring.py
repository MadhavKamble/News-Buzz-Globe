from datetime import UTC, datetime, timedelta

import pytest

from ingestion.config import IntensityConfig
from ingestion.scoring import intensity_score, normalize_count, recency_decay

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
CFG = IntensityConfig(
    w_articles=0.4,
    w_sources=0.3,
    w_recency=0.3,
    articles_cap=100,
    sources_cap=25,
    half_life_hours=6,
)


class TestNormalizeCount:
    def test_zero_and_none_and_negative_are_zero(self):
        assert normalize_count(0, 100) == 0.0
        assert normalize_count(None, 100) == 0.0
        assert normalize_count(-5, 100) == 0.0

    def test_cap_saturates_at_one(self):
        assert normalize_count(100, 100) == 1.0
        assert normalize_count(10_000, 100) == 1.0

    def test_monotonic_below_cap(self):
        values = [normalize_count(v, 100) for v in (1, 5, 20, 50, 99)]
        assert values == sorted(values)
        assert all(0.0 < v < 1.0 for v in values)

    def test_invalid_cap_raises(self):
        with pytest.raises(ValueError):
            normalize_count(5, 0)


class TestRecencyDecay:
    def test_fresh_event_is_one(self):
        assert recency_decay(NOW, NOW, 6) == 1.0

    def test_future_event_clamps_to_one(self):
        assert recency_decay(NOW + timedelta(hours=2), NOW, 6) == 1.0

    def test_half_life(self):
        assert recency_decay(NOW - timedelta(hours=6), NOW, 6) == pytest.approx(0.5)
        assert recency_decay(NOW - timedelta(hours=12), NOW, 6) == pytest.approx(0.25)

    def test_naive_datetimes_treated_as_utc(self):
        naive = NOW.replace(tzinfo=None) - timedelta(hours=6)
        assert recency_decay(naive, NOW, 6) == pytest.approx(0.5)

    def test_invalid_half_life_raises(self):
        with pytest.raises(ValueError):
            recency_decay(NOW, NOW, 0)


class TestIntensityScore:
    def test_max_score_is_sum_of_weights(self):
        score = intensity_score(1000, 1000, NOW, NOW, CFG)
        assert score == pytest.approx(1.0)

    def test_dead_old_event_scores_near_zero(self):
        score = intensity_score(0, 0, NOW - timedelta(days=30), NOW, CFG)
        assert score < 0.001

    def test_recency_only_event(self):
        # No articles/sources info: only the recency term contributes.
        score = intensity_score(None, None, NOW, NOW, CFG)
        assert score == pytest.approx(CFG.w_recency)

    def test_bounded_zero_to_one(self):
        for articles, sources, age_h in [(1, 1, 0), (50, 10, 3), (10_000, 500, 100)]:
            score = intensity_score(
                articles, sources, NOW - timedelta(hours=age_h), NOW, CFG
            )
            assert 0.0 <= score <= 1.0
