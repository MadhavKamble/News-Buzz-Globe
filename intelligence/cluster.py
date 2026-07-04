"""Embedding-based story clustering.

Grouping near-duplicate GDELT events about the same real-world story is a
similarity problem, not a generative one: we embed page titles locally with
sentence-transformers and merge pairs above a cosine-similarity threshold
using union-find (transitive closure). No LLM involved here by design.
"""

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


def embed_titles(titles: list[str], model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """Encode titles into L2-normalized embeddings (lazy heavy import)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    return model.encode(
        titles, normalize_embeddings=True, show_progress_bar=False, batch_size=64
    )
