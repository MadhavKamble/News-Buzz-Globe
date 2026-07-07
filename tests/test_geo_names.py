from common.geo_names import detect_country_code


class TestDetectCountryCode:
    def test_detects_country_name(self):
        assert detect_country_code("whats the news today in india?") == "IN"

    def test_case_insensitive(self):
        assert detect_country_code("INDIA is voting today") == "IN"

    def test_no_match_returns_none(self):
        assert detect_country_code("tell me something interesting") is None

    def test_whole_word_avoids_substring_false_positive(self):
        # "Indiana" contains "india" as a substring but must not match it.
        assert detect_country_code("a story about Indiana") is None

    def test_matches_multi_word_country_name(self):
        assert detect_country_code("what's new in south sudan") == "OD"
