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

    def query(self, query_embeddings, n_results):
        q = np.array(query_embeddings[0])
        sims = [float(np.dot(q, np.array(e))) for e in self.embeddings]
        order = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:n_results]
        return {
            "ids": [[self.ids[i] for i in order]],
            "metadatas": [[self.metadatas[i] for i in order]],
        }


@pytest.fixture
def fake_collection(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(rag, "get_model", lambda *a, **kw: FakeModel())
    monkeypatch.setattr(rag, "_collection", lambda: collection)
    return collection


ARTICLES = [
    {"id": 1, "title": "Mumbai floods worsen", "summary": "Red alert issued",
     "source_url": "https://a.example/1", "date_added": "2026-07-04T12:00:00+00:00"},
    {"id": 2, "title": "EU summit reaches trade deal", "summary": "Leaders agree on tariffs",
     "source_url": "https://a.example/2", "date_added": "2026-07-04T12:00:00+00:00"},
    {"id": 3, "title": "Tokyo stock market rallies", "summary": "Nikkei hits record high",
     "source_url": "https://a.example/3", "date_added": "2026-07-04T12:00:00+00:00"},
    {"id": 4, "title": "Wildfire spreads near Athens", "summary": "Evacuations ordered",
     "source_url": "https://a.example/4", "date_added": "2026-07-04T12:00:00+00:00"},
    {"id": 5, "title": "Cricket World Cup final set", "summary": "India to face Australia",
     "source_url": "https://a.example/5", "date_added": "2026-07-04T12:00:00+00:00"},
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
