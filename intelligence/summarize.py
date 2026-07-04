"""Cluster summarization via self-hosted Ollama.

This is the one genuinely generative job in the project: turning a cluster of
raw page titles into a single readable headline. Runs against the local
Ollama server (same machine/VM — free, no rate limits). If Ollama is
unreachable the caller falls back to the best member title, so the pipeline
never blocks on the LLM.
"""

import os

import requests

from common.logging_config import get_logger

logger = get_logger("intelligence.summarize")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")
MAX_TITLES_IN_PROMPT = 8


def build_prompt(titles: list[str]) -> str:
    unique = list(dict.fromkeys(t.strip() for t in titles if t and t.strip()))
    lines = "\n".join(f"- {t}" for t in unique[:MAX_TITLES_IN_PROMPT])
    return (
        "The following news headlines all describe the same story. "
        "Write ONE combined headline of at most 15 words. "
        "Reply with only the headline, no quotes, no preamble.\n\n" + lines
    )


def clean_summary(text: str) -> str:
    lines = text.strip().strip('"').strip("'").splitlines()
    if not lines:
        return ""
    return lines[0].strip().rstrip(".")


def summarize_titles(
    titles: list[str],
    session: requests.Session | None = None,
    timeout: int = 90,
) -> str | None:
    """One-line summary for a cluster, or None if Ollama is unavailable."""
    sess = session or requests.Session()
    try:
        resp = sess.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": build_prompt(titles),
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 60},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        summary = clean_summary(resp.json().get("response", ""))
        return summary or None
    except requests.RequestException as exc:
        logger.warning("ollama unavailable, falling back to member title",
                       extra={"error": str(exc)[:200]})
        return None
