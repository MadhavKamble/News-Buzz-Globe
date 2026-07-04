from datetime import UTC, datetime

import pytest

from ingestion import gdelt
from ingestion.gdelt import (
    EVENT_EXPORT_NUM_COLS,
    GKG_NUM_COLS,
    GdeltRowError,
    parse_event_row,
    parse_events_csv,
    parse_gkg_titles,
)


def make_row(overrides: dict[int, str] | None = None) -> str:
    """Build a valid 61-column GDELT event line, then apply overrides."""
    fields = [""] * EVENT_EXPORT_NUM_COLS
    fields[gdelt.COL_GLOBAL_EVENT_ID] = "1234567890"
    fields[gdelt.COL_SQLDATE] = "20260704"
    fields[gdelt.COL_ACTOR1_NAME] = "FRANCE"
    fields[gdelt.COL_ACTOR2_NAME] = "GERMANY"
    fields[gdelt.COL_EVENT_CODE] = "042"
    fields[gdelt.COL_EVENT_ROOT_CODE] = "04"
    fields[gdelt.COL_QUAD_CLASS] = "1"
    fields[gdelt.COL_NUM_MENTIONS] = "10"
    fields[gdelt.COL_NUM_SOURCES] = "3"
    fields[gdelt.COL_NUM_ARTICLES] = "8"
    fields[gdelt.COL_AVG_TONE] = "-2.5"
    fields[gdelt.COL_ACTION_GEO_FULL_NAME] = "Paris, France"
    fields[gdelt.COL_ACTION_GEO_COUNTRY] = "FR"
    fields[gdelt.COL_ACTION_GEO_LAT] = "48.8566"
    fields[gdelt.COL_ACTION_GEO_LON] = "2.3522"
    fields[gdelt.COL_DATE_ADDED] = "20260704120000"
    fields[gdelt.COL_SOURCE_URL] = "https://example.com/story"
    for index, value in (overrides or {}).items():
        fields[index] = value
    return "\t".join(fields)


class TestParseEventRow:
    def test_valid_row(self):
        event = parse_event_row(make_row())
        assert event.global_event_id == 1234567890
        assert event.event_date == datetime(2026, 7, 4, tzinfo=UTC)
        assert event.date_added == datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
        assert event.actor1_name == "FRANCE"
        assert event.event_code == "042"
        assert event.event_root_code == "04"
        assert event.quad_class == 1
        assert event.num_articles == 8
        assert event.avg_tone == -2.5
        assert event.lat == pytest.approx(48.8566)
        assert event.lon == pytest.approx(2.3522)
        assert event.source_url == "https://example.com/story"

    def test_missing_optional_fields_become_none(self):
        row = make_row(
            {
                gdelt.COL_ACTOR1_NAME: "",
                gdelt.COL_NUM_ARTICLES: "",
                gdelt.COL_AVG_TONE: "",
                gdelt.COL_ACTION_GEO_LAT: "",
                gdelt.COL_ACTION_GEO_LON: "",
                gdelt.COL_SOURCE_URL: "",
            }
        )
        event = parse_event_row(row)
        assert event.actor1_name is None
        assert event.num_articles is None
        assert event.avg_tone is None
        assert event.lat is None
        assert event.lon is None
        assert event.source_url is None

    def test_wrong_column_count_rejected(self):
        with pytest.raises(GdeltRowError) as excinfo:
            parse_event_row("only\tthree\tcolumns")
        assert excinfo.value.reason == "bad_column_count"

    def test_garbage_event_id_rejected(self):
        with pytest.raises(GdeltRowError) as excinfo:
            parse_event_row(make_row({gdelt.COL_GLOBAL_EVENT_ID: "not-a-number"}))
        assert excinfo.value.reason == "bad_event_id"

    def test_garbage_timestamp_rejected(self):
        with pytest.raises(GdeltRowError) as excinfo:
            parse_event_row(make_row({gdelt.COL_SQLDATE: "99999999"}))
        assert excinfo.value.reason == "bad_timestamp"

    def test_garbage_numeric_field_rejected(self):
        with pytest.raises(GdeltRowError) as excinfo:
            parse_event_row(make_row({gdelt.COL_ACTION_GEO_LAT: "12.3.4"}))
        assert excinfo.value.reason == "bad_numeric_field"

    def test_mojibake_in_text_fields_survives(self):
        event = parse_event_row(make_row({gdelt.COL_ACTOR1_NAME: "M�XICO"}))
        assert event.actor1_name == "M�XICO"


class TestParseEventsCsv:
    def test_mixed_good_and_bad_rows(self):
        text = "\n".join(
            [
                make_row(),
                "garbage line",
                make_row({gdelt.COL_GLOBAL_EVENT_ID: "999", gdelt.COL_SQLDATE: "bad"}),
                "",
            ]
        )
        events, drops = parse_events_csv(text)
        assert len(events) == 1
        assert drops == {"bad_column_count": 1, "bad_timestamp": 1}


class TestParseGkgTitles:
    def make_gkg_row(self, url: str, extras: str) -> str:
        fields = [""] * GKG_NUM_COLS
        fields[gdelt.GKG_COL_DOCUMENT_IDENTIFIER] = url
        fields[gdelt.GKG_COL_EXTRAS] = extras
        return "\t".join(fields)

    def test_extracts_page_title(self):
        text = self.make_gkg_row(
            "https://example.com/story",
            "<PAGE_LINKS>x</PAGE_LINKS><PAGE_TITLE>Big News Story</PAGE_TITLE>",
        )
        assert parse_gkg_titles(text) == {"https://example.com/story": "Big News Story"}

    def test_html_entities_unescaped(self):
        text = self.make_gkg_row(
            "https://example.com/s2",
            "<PAGE_TITLE>Recipe &#x2013; Mainline &amp; More</PAGE_TITLE>",
        )
        assert parse_gkg_titles(text) == {"https://example.com/s2": "Recipe – Mainline & More"}

    def test_rows_without_title_or_url_skipped(self):
        text = "\n".join(
            [
                self.make_gkg_row("https://a.com", "<OTHER>nope</OTHER>"),
                self.make_gkg_row("", "<PAGE_TITLE>orphan</PAGE_TITLE>"),
                "short\trow",
            ]
        )
        assert parse_gkg_titles(text) == {}
