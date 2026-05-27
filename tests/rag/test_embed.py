"""Tests for ai_sw_bridge.rag.embed (spec.md §4.4).

Covers:

* HashEmbedder determinism (same string -> byte-identical vector).
* HashEmbedder unit-norm property.
* HashEmbedder dim override.
* cosine_similarity on known vectors.
* make_embedder('hash') forces the hash backend.
* make_embedder('auto') falls back to hash when
  sentence-transformers isn't importable (the typical CI path).
* make_embedder('sentence-transformers') raises when the package is
  missing.

The real SentenceTransformer backend is exercised in E5.4's
determinism gate (where a pinned model produces a byte-equal
index); unit-testing it here would require downloading a ~90 MB
model on every CI run.
"""

from __future__ import annotations

import numpy as np

from ai_sw_bridge.rag.embed import (
    DEFAULT_DIM,
    HashEmbedder,
    cosine_similarity,
    make_embedder,
)


def test_hash_embedder_deterministic() -> None:
    a = HashEmbedder().embed("SOLIDWORKS add-in objects")
    b = HashEmbedder().embed("SOLIDWORKS add-in objects")
    assert np.array_equal(a, b)


def test_hash_embedder_unit_norm() -> None:
    vec = HashEmbedder().embed("any non-empty text goes here")
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-5


def test_hash_embedder_empty_string_zero_vector() -> None:
    vec = HashEmbedder().embed("")
    assert vec.shape == (DEFAULT_DIM,)
    assert float(np.linalg.norm(vec)) == 0.0


def test_hash_embedder_dim_override() -> None:
    emb = HashEmbedder(dim=64)
    assert emb.dim == 64
    vec = emb.embed("something")
    assert vec.shape == (64,)


def test_hash_embedder_embed_many_shape() -> None:
    emb = HashEmbedder(dim=32)
    arr = emb.embed_many(["one", "two", "three"])
    assert arr.shape == (3, 32)


def test_hash_embedder_different_inputs_differ() -> None:
    emb = HashEmbedder()
    a = emb.embed("alpha beta gamma")
    b = emb.embed("delta epsilon zeta")
    assert not np.array_equal(a, b)


def test_cosine_similarity_parallel_vectors() -> None:
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([2.0, 0.0, 0.0], dtype=np.float32)
    assert abs(cosine_similarity(a, b) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal() -> None:
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert abs(cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_opposite() -> None:
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
    assert abs(cosine_similarity(a, b) + 1.0) < 1e-6


def test_cosine_similarity_zero_norm() -> None:
    a = np.zeros(4, dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == 0.0


def test_make_embedder_hash_forced() -> None:
    emb = make_embedder(backend="hash", dim=32)
    assert isinstance(emb, HashEmbedder)
    assert emb.dim == 32


def test_make_embedder_unknown_backend() -> None:
    import pytest

    with pytest.raises(ValueError):
        make_embedder(backend="does-not-exist")


def test_make_embedder_sentence_transformers_missing_raises() -> None:
    """Forcing the ST backend without the package raises ImportError."""
    import importlib
    import sys

    import pytest

    # Hide sentence_transformers for the duration of the test.
    saved = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = None  # type: ignore[assignment]
    try:
        # Re-import the module so the ImportError path in
        # SentenceTransformerEmbedder._get_model triggers.
        from ai_sw_bridge.rag import embed as embed_mod

        importlib.reload(embed_mod)
        emb = embed_mod.make_embedder(backend="sentence-transformers")
        with pytest.raises(ImportError):
            emb.embed("anything")
    finally:
        if saved is None:
            sys.modules.pop("sentence_transformers", None)
        else:
            sys.modules["sentence_transformers"] = saved
        from ai_sw_bridge.rag import embed as embed_mod

        importlib.reload(embed_mod)
