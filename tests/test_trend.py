from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from intelligence.job import compute_trend

RUN_AT = datetime(2026, 7, 4, 18, 0, tzinfo=UTC)


@dataclass
class Member:
    num_articles: int | None
    date_added: datetime


def m(articles, minutes_ago):
    return Member(articles, RUN_AT - timedelta(minutes=minutes_ago))


class TestComputeTrend:
    def test_rising(self):
        members = [m(30, 10), m(20, 30), m(10, 90)]
        trend, last, prev = compute_trend(members, RUN_AT)
        assert (trend, last, prev) == ("rising", 50, 10)

    def test_falling(self):
        members = [m(5, 10), m(40, 70), m(30, 110)]
        trend, last, prev = compute_trend(members, RUN_AT)
        assert (trend, last, prev) == ("falling", 5, 70)

    def test_steady(self):
        members = [m(10, 10), m(10, 90)]
        trend, last, prev = compute_trend(members, RUN_AT)
        assert (trend, last, prev) == ("steady", 10, 10)

    def test_new_story_with_no_prior_coverage_is_rising(self):
        members = [m(15, 5)]
        trend, last, prev = compute_trend(members, RUN_AT)
        assert (trend, last, prev) == ("rising", 15, 0)

    def test_old_story_with_no_recent_coverage_is_falling(self):
        members = [m(15, 100)]
        trend, _, _ = compute_trend(members, RUN_AT)
        assert trend == "falling"

    def test_none_article_counts_treated_as_zero(self):
        members = [Member(None, RUN_AT - timedelta(minutes=10)), m(10, 10)]
        trend, last, _ = compute_trend(members, RUN_AT)
        assert last == 10
        assert trend == "rising"

    def test_older_than_two_hours_ignored(self):
        members = [m(10, 10), m(500, 200)]
        _, last, prev = compute_trend(members, RUN_AT)
        assert (last, prev) == (10, 0)
