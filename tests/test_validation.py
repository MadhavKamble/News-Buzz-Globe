from datetime import UTC, datetime

from ingestion.gdelt import RawEvent
from ingestion.validate import validate_events


def make_event(**overrides) -> RawEvent:
    defaults = dict(
        global_event_id=1,
        event_date=datetime(2026, 7, 4, tzinfo=UTC),
        date_added=datetime(2026, 7, 4, 12, 0, tzinfo=UTC),
        actor1_name="FRANCE",
        actor2_name=None,
        event_code="042",
        event_root_code="04",
        quad_class=1,
        num_mentions=10,
        num_sources=3,
        num_articles=8,
        avg_tone=-2.5,
        action_geo_full_name="Paris, France",
        action_geo_country_code="FR",
        lat=48.8566,
        lon=2.3522,
        source_url="https://example.com/story",
    )
    defaults.update(overrides)
    return RawEvent(**defaults)


class TestCoordinateValidation:
    def test_null_coordinates_dropped(self):
        result = validate_events([make_event(lat=None), make_event(lon=None)])
        assert result.valid == []
        assert result.drop_counts == {"invalid_coordinates": 2}

    def test_out_of_bounds_dropped(self):
        result = validate_events(
            [make_event(lat=95.0), make_event(lon=-181.0), make_event(lat=-91.0)]
        )
        assert result.valid == []
        assert result.drop_counts == {"invalid_coordinates": 3}

    def test_null_island_dropped(self):
        result = validate_events([make_event(lat=0.0, lon=0.0)])
        assert result.valid == []
        assert result.drop_counts == {"invalid_coordinates": 1}

    def test_valid_coordinates_kept(self):
        result = validate_events([make_event()])
        assert len(result.valid) == 1
        assert result.drop_counts == {}


class TestCountValidation:
    def test_negative_counts_dropped(self):
        result = validate_events([make_event(num_articles=-1)])
        assert result.valid == []
        assert result.drop_counts == {"negative_counts": 1}

    def test_none_counts_allowed(self):
        result = validate_events(
            [make_event(num_mentions=None, num_sources=None, num_articles=None)]
        )
        assert len(result.valid) == 1


class TestEventCodeValidation:
    def test_missing_event_code_dropped(self):
        result = validate_events([make_event(event_code="")])
        assert result.valid == []
        assert result.drop_counts == {"missing_event_code": 1}


class TestDeduplication:
    def test_duplicate_ids_collapsed_last_wins(self):
        first = make_event(global_event_id=42, num_articles=5)
        second = make_event(global_event_id=42, num_articles=99)
        result = validate_events([first, second])
        assert len(result.valid) == 1
        assert result.valid[0].num_articles == 99
        assert result.drop_counts == {"duplicate_event_id_in_batch": 1}

    def test_distinct_ids_all_kept(self):
        result = validate_events(
            [make_event(global_event_id=i) for i in (1, 2, 3)]
        )
        assert len(result.valid) == 3
