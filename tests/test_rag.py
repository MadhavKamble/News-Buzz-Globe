"""Unit tests for intelligence/rag.py.

Follows this repo's existing convention (see test_summarize.py, test_cache.py)
of injecting fakes for heavy/external dependencies rather than hitting a real
sentence-transformers model or a real Ollama server.
"""

import hashlib

import numpy as np
import pytest

from intelligence import rag

VOCAB_DIM = 64


def _bow_vector(text: str) -> np.ndarray:
    """Deterministic bag-of-words embedding stand-in: identical/near-identical
    text yields high cosine similarity, which is all these tests need."""
    vec = np.zeros(VOCAB_DIM)
    for word in text.lower().split():
        idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % VOCAB_DIM
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


class FakeModel:
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        return np.stack([_bow_vector(t) for t in texts])


class FakeCollection:
    """In-memory stand-in for a Chroma collection (upsert + cosine query)."""

    def __init__(self):
        self.ids = []
        self.embeddings = []
        self.metadatas = []

    def upsert(self, ids, embeddings, documents, metadatas):
        for i, doc_id in enumerate(ids):
            if doc_id in self.ids:
                idx = self.ids.index(doc_id)
                self.embeddings[idx] = embeddings[i]
                self.metadatas[idx] = metadatas[i]
            else:
                self.ids.append(doc_id)
                self.embeddings.append(embeddings[i])
                self.metadatas.append(metadatas[i])

    def query(self, query_embeddings, n_results, where=None):
        q = np.array(query_embeddings[0])
        candidates = range(len(self.ids))
        if where:
            key, value = next(iter(where.items()))
            candidates = [i for i in candidates if self.metadatas[i].get(key) == value]
        scored = sorted(
            candidates, key=lambda i: float(np.dot(q, np.array(self.embeddings[i]))), reverse=True
        )[:n_results]
        return {
            "ids": [[self.ids[i] for i in scored]],
            "metadatas": [[self.metadatas[i] for i in scored]],
        }


@pytest.fixture
def fake_collection(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(rag, "get_model", lambda *a, **kw: FakeModel())
    monkeypatch.setattr(rag, "_collection", lambda: collection)
    return collection


ARTICLES = [
    {"id": 1, "title": "Mumbai floods worsen", "summary": "Red alert issued",
     "source_url": "https://a.example/1", "country_code": "IN",
     "date_added": "2026-07-04T12:00:00+00:00"},
    {"id": 2, "title": "EU summit reaches trade deal", "summary": "Leaders agree on tariffs",
     "source_url": "https://a.example/2", "country_code": "BE",
     "date_added": "2026-07-04T12:00:00+00:00"},
    {"id": 3, "title": "Tokyo stock market rallies", "summary": "Nikkei hits record high",
     "source_url": "https://a.example/3", "country_code": "JA",
     "date_added": "2026-07-04T12:00:00+00:00"},
    {"id": 4, "title": "Wildfire spreads near Athens", "summary": "Evacuations ordered",
     "source_url": "https://a.example/4", "country_code": "GR",
     "date_added": "2026-07-04T12:00:00+00:00"},
    {"id": 5, "title": "Cricket World Cup final set", "summary": "India to face Australia",
     "source_url": "https://a.example/5", "country_code": "IN",
     "date_added": "2026-07-04T12:00:00+00:00"},
]


class FakeOllamaResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self.text}


class FakeOllamaSession:
    def __init__(self, text="Mumbai is experiencing severe flooding.", exc=None):
        self.text = text
        self.exc = exc

    def post(self, *args, **kwargs):
        if self.exc:
            raise self.exc
        return FakeOllamaResponse(self.text)


class TestIndexAndRetrieve:
    def test_index_and_retrieve(self, fake_collection):
        rag.index_articles(ARTICLES)
        results = rag.retrieve("Mumbai floods worsen Red alert issued", top_k=3)
        assert any(r["title"] == "Mumbai floods worsen" for r in results)


class TestAnswer:
    def test_answer_returns_sources(self, fake_collection):
        rag.index_articles(ARTICLES)
        result = rag.answer("What is happening in Mumbai?", session=FakeOllamaSession())
        assert result["answer"] == "Mumbai is experiencing severe flooding."
        assert len(result["sources"]) > 0
        assert "error" not in result


class TestCountryFilter:
    def test_retrieve_scopes_to_country(self, fake_collection):
        rag.index_articles(ARTICLES)
        results = rag.retrieve("India cricket news", top_k=10, country_code="IN")
        assert results
        assert all(r["country_code"] == "IN" for r in results)

    def test_answer_detects_country_and_scopes_retrieval(self, fake_collection):
        rag.index_articles(ARTICLES)
        result = rag.answer("What is happening in India?", session=FakeOllamaSession())
        assert all(s["title"] in ("Mumbai floods worsen", "Cricket World Cup final set")
                    for s in result["sources"])

    def test_falls_back_to_unscoped_when_country_has_no_matches(self, fake_collection):
        rag.index_articles(ARTICLES)
        # Zimbabwe is a real detectable country name but no fixture article
        # is tagged for it — the scoped search comes up empty, so answer()
        # should fall back to an unscoped search rather than returning no
        # sources at all.
        result = rag.answer("What is happening in Zimbabwe?", session=FakeOllamaSession())
        assert len(result["sources"]) > 0


class TestGracefulDegradation:
    def test_chroma_unavailable_returns_error(self, monkeypatch):
        def _boom():
            raise RuntimeError("invalid chroma path")

        monkeypatch.setattr(rag, "get_model", lambda *a, **kw: FakeModel())
        monkeypatch.setattr(rag, "_collection", _boom)
        result = rag.answer("anything", session=FakeOllamaSession())
        assert result == {"answer": None, "sources": [], "error": "invalid chroma path"}

    def test_ollama_unavailable_returns_error(self, fake_collection):
        import requests

        rag.index_articles(ARTICLES)
        result = rag.answer(
            "What is happening in Mumbai?",
            session=FakeOllamaSession(exc=requests.ConnectionError("refused")),
        )
        assert result["answer"] is None
        assert result["sources"] == []
        assert "error" in result
