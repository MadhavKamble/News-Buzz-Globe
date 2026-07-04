import numpy as np
import pytest

from intelligence.cluster import cluster_embeddings


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


class TestClusterEmbeddings:
    def test_empty(self):
        assert cluster_embeddings(np.zeros((0, 4))) == []

    def test_identical_vectors_merge(self):
        emb = np.stack([unit([1, 0, 0]), unit([1, 0, 0]), unit([0, 1, 0])])
        clusters = cluster_embeddings(emb, threshold=0.9)
        assert sorted(map(sorted, clusters)) == [[0, 1], [2]]

    def test_transitive_merge(self):
        # a~b and b~c but a!~c: all three must still merge (union-find).
        a = unit([1, 0, 0])
        b = unit([1, 0.55, 0])
        c = unit([1, 1.2, 0])
        emb = np.stack([a, b, c])
        sims = emb @ emb.T
        assert sims[0, 1] > 0.85 and sims[1, 2] > 0.85 and sims[0, 2] < 0.85
        clusters = cluster_embeddings(emb, threshold=0.85)
        assert sorted(map(sorted, clusters)) == [[0, 1, 2]]

    def test_below_threshold_stays_separate(self):
        emb = np.stack([unit([1, 0, 0]), unit([0, 1, 0]), unit([0, 0, 1])])
        clusters = cluster_embeddings(emb, threshold=0.5)
        assert len(clusters) == 3

    def test_largest_cluster_first(self):
        emb = np.stack([unit([0, 1, 0])] + [unit([1, 0, 0])] * 3)
        clusters = cluster_embeddings(emb, threshold=0.9)
        assert len(clusters[0]) == 3

    def test_every_index_assigned_once(self):
        rng = np.random.default_rng(42)
        emb = rng.normal(size=(50, 8))
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)
        clusters = cluster_embeddings(emb, threshold=0.7)
        flat = sorted(i for c in clusters for i in c)
        assert flat == list(range(50))

    @pytest.mark.parametrize("bad", [0.0, 1.0, -0.2, 1.5])
    def test_invalid_threshold_rejected(self, bad):
        with pytest.raises(ValueError):
            cluster_embeddings(np.eye(3), threshold=bad)
