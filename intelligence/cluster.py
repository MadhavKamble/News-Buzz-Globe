"""Embedding-based story clustering.

Grouping near-duplicate GDELT events about the same real-world story is a
similarity problem, not a generative one: we embed page titles locally with
sentence-transformers and merge pairs above a cosine-similarity threshold
using union-find (transitive closure). No LLM involved here by design.
"""

from functools import lru_cache

import numpy as np


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def cluster_embeddings(embeddings: np.ndarray, threshold: float = 0.6) -> list[list[int]]:
    """Group row indices whose cosine similarity exceeds `threshold`.

    Expects L2-normalized embeddings (sentence-transformers
    `normalize_embeddings=True`), so cosine similarity is a dot product.
    Merging is transitive: if A~B and B~C, then {A, B, C} is one cluster.
    Returns clusters sorted largest-first; every index appears exactly once.
    """
    n = len(embeddings)
    if n == 0:
        return []
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be in (0, 1)")
    sims = embeddings @ embeddings.T
    uf = UnionFind(n)
    for i, j in zip(*np.where(np.triu(sims, k=1) >= threshold), strict=True):
        uf.union(int(i), int(j))
    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(uf.find(idx), []).append(idx)
    return sorted(groups.values(), key=len, reverse=True)


DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_model(model_name: str = DEFAULT_MODEL_NAME):
    """Load the sentence-transformers model once per process (lazy heavy import).

    Shared by embed_titles() and intelligence.rag, which both need the same
    embedding space — loading it twice per pipeline cycle would double the
    (CPU-bound) model load time for no benefit. Every caller must pass the
    same argument shape (all callers use DEFAULT_MODEL_NAME explicitly) since
    lru_cache keys on the literal call, not the resolved default — get_model()
    and get_model(DEFAULT_MODEL_NAME) would otherwise cache as two entries.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_titles(titles: list[str], model_name: str = DEFAULT_MODEL_NAME) -> np.ndarray:
    """Encode titles into L2-normalized embeddings, via the shared cached model."""
    model = get_model(model_name)
    return model.encode(
        titles, normalize_embeddings=True, show_progress_bar=False, batch_size=64
    )
