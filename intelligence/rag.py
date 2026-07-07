"""Retrieval-augmented "chat with the news" over indexed story clusters.

Reuses the sentence-transformers model cached by intelligence.cluster.get_model()
(same embedding space as story clustering) and the Ollama endpoint already
configured for headline generation (intelligence.summarize). Chroma persists
to CHROMA_PATH on disk (bare-metal path, matching how this project's other
services run outside Docker).

Every public function degrades to a soft failure instead of raising: a down
Chroma store or Ollama server must never break job.py's pipeline cycle or the
/chat endpoint.
"""

import os

import requests

from common.logging_config import get_logger
from intelligence.cluster import DEFAULT_MODEL_NAME, get_model
from intelligence.summarize import OLLAMA_MODEL, OLLAMA_URL

logger = get_logger("intelligence.rag")

CHROMA_PATH = os.environ.get("CHROMA_PATH", "./data/chroma")
COLLECTION_NAME = "news_articles"


def _collection():
    """Lazy heavy import — chromadb (and its own deps) only loaded when needed."""
    import chromadb

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(COLLECTION_NAME)


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _document_text(article: dict) -> str:
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    return f"{title} {summary}".strip()


def index_articles(articles: list[dict]) -> None:
    """Embed and upsert articles into Chroma. Idempotent on each article's id.

    Each article is {id, title, summary, source_url, date_added}. Upsert (not
    insert) so re-indexing the same id — e.g. an ongoing story reappearing in
    a later pipeline run — updates the entry instead of duplicating it.
    """
    if not articles:
        return
    model = get_model(DEFAULT_MODEL_NAME)
    texts = [_document_text(a) for a in articles]
    embeddings = model.encode(
        texts, normalize_embeddings=True, show_progress_bar=False
    ).tolist()
    collection = _collection()
    collection.upsert(
        ids=[str(a["id"]) for a in articles],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {
                "title": a.get("title") or "",
                "summary": a.get("summary") or "",
                "source_url": a.get("source_url") or "",
                "date_added": _iso(a.get("date_added")),
            }
            for a in articles
        ],
    )


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Top-k articles most similar to `query`, with their metadata."""
    model = get_model(DEFAULT_MODEL_NAME)
    embedding = model.encode(
        [query], normalize_embeddings=True, show_progress_bar=False
    )[0].tolist()
    collection = _collection()
    result = collection.query(query_embeddings=[embedding], n_results=top_k)
    ids = (result.get("ids") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    return [{"id": doc_id, **meta} for doc_id, meta in zip(ids, metadatas, strict=True)]


def build_prompt(query: str, articles: list[dict]) -> str:
    lines = [f"- {a['title']}: {a['summary']}" if a.get("summary") else f"- {a['title']}"
             for a in articles]
    context = "\n".join(lines)
    return (
        "Answer the question using ONLY the news context below. "
        "If the context doesn't contain the answer, say you don't have enough information.\n\n"
        f"Context:\n{context}\n\nQuestion: {query}\nAnswer:"
    )


def answer(query: str, session: requests.Session | None = None) -> dict:
    """Retrieve grounding articles, then ask Ollama to answer from them.

    Returns {answer, sources} on success, or {answer: None, sources: [],
    error} if Chroma or Ollama is unavailable — never raises.
    """
    try:
        articles = retrieve(query)
    except Exception as exc:  # noqa: BLE001 - any retrieval failure degrades gracefully
        logger.warning("chroma unavailable for /chat", extra={"error": str(exc)[:200]})
        return {"answer": None, "sources": [], "error": str(exc)[:200]}

    sess = session or requests.Session()
    try:
        resp = sess.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": build_prompt(query, articles),
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=90,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
    except requests.RequestException as exc:
        logger.warning("ollama unavailable for /chat", extra={"error": str(exc)[:200]})
        return {"answer": None, "sources": [], "error": str(exc)[:200]}

    sources = [
        {
            "title": a.get("title"),
            "source_url": a.get("source_url") or None,
            "date_added": a.get("date_added"),
        }
        for a in articles
    ]
    return {"answer": text or None, "sources": sources}
