import requests

from intelligence.summarize import build_prompt, clean_summary, summarize_titles


class TestBuildPrompt:
    def test_dedupes_and_caps_titles(self):
        titles = ["Same story"] * 3 + [f"Story {i}" for i in range(20)]
        prompt = build_prompt(titles)
        assert prompt.count("- ") == 8  # MAX_TITLES_IN_PROMPT
        assert prompt.count("Same story") == 1
        assert "at most 15 words" in prompt

    def test_skips_blank_titles(self):
        prompt = build_prompt(["", "  ", "Real headline"])
        assert prompt.count("- ") == 1


class TestCleanSummary:
    def test_strips_quotes_and_trailing_period(self):
        assert clean_summary('"Mumbai floods worsen."') == "Mumbai floods worsen"

    def test_keeps_first_line_only(self):
        assert clean_summary("Headline here\nExtra commentary") == "Headline here"


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc

    def post(self, *args, **kwargs):
        if self.exc:
            raise self.exc
        return self.response


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class TestSummarizeTitles:
    def test_returns_cleaned_summary(self):
        sess = FakeSession(FakeResponse({"response": ' "Big flood hits city." \n'}))
        assert summarize_titles(["a", "b"], session=sess) == "Big flood hits city"

    def test_none_when_ollama_down(self):
        sess = FakeSession(exc=requests.ConnectionError("refused"))
        assert summarize_titles(["a", "b"], session=sess) is None

    def test_none_on_empty_response(self):
        sess = FakeSession(FakeResponse({"response": "   "}))
        assert summarize_titles(["a"], session=sess) is None
