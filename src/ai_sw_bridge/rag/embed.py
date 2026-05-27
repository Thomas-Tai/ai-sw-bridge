"""Embedding backends for the RAG lane (spec.md §4.4).

Two backends behind a single :class:`Embedder` protocol:

* :class:`HashEmbedder` — deterministic, zero-dep embedder used as
  the default in CI and tests. Produces stable vectors across
  processes / hosts / Python versions so the index build is
  byte-reproducible (spec.md §4.4 risk register: *embedding
  determinism*). Vectors are sparse-ish 256-dim float32 arrays
  derived from word-level hashes; retrieval quality is poor but
  sufficient to exercise the index + eval harness end-to-end.
* :class:`SentenceTransformerEmbedder` — production backend. Loads
  a pinned sentence-transformers model (default
  ``all-MiniLM-L6-v2``; 384-dim float32). The model is downloaded
  once and cached under ``~/.cache/torch/sentence_transformers/``;
  E5.4 mirrors it into the repo for offline use. Lazy import so
  ``sentence-transformers`` is NOT a hard dep of ``ai_sw_bridge``.

The embedder is constructed via :func:`make_embedder` which picks
the SentenceTransformer backend when the package is importable,
else falls back to HashEmbedder. Tests pin the backend explicitly
so the test matrix doesn't depend on what's installed in the dev
venv.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np

DEFAULT_DIM = 256
DEFAULT_ST_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder(Protocol):
    """Embedding backend. Implementations must be deterministic for a
    given input string (same string -> same vector, byte-identical)."""

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> np.ndarray: ...

    def embed_many(self, texts: Sequence[str]) -> np.ndarray: ...


# ---------------------------------------------------------------------------
# Hash-based embedder (default / CI / tests)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HashEmbedder:
    """Deterministic, zero-dep embedder.

    Each word hashes (SHA-256) to 8 bucket indices + 8 signed weights.
    The vector is the sum of signed one-hot-ish bucket activations,
    L2-normalized at the end. This is essentially "feature hashing"
    (Weinberger et al. 2009) scaled to a 256-dim unit vector.

    Quality: poor compared to a real transformer -- the eval harness
    (E5.6) reports lower precision@1 on the benchmark. But it is
    *stable* (same string -> same bytes, forever) and *fast* (no
    model load, no network). Sufficient for:

    * exercising the index build (E5.4) end-to-end;
    * exercising the cli/apidoc.py surface (E5.5);
    * CI smoke tests that must not require a GPU or a download.

    To upgrade to a real model, install sentence-transformers and
    use :class:`SentenceTransformerEmbedder` (or let
    :func:`make_embedder` pick it up automatically).
    """

    dim: int = DEFAULT_DIM

    def embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for word in text.lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            # 8 buckets, 8 signs. Each bucket: 2 bytes -> index % dim.
            # Each sign: 1 byte -> +1 if high bit clear else -1.
            for i in range(8):
                bucket_bytes = digest[2 * i : 2 * i + 2]
                sign_byte = digest[16 + i : 17 + i]
                bucket = struct.unpack(">H", bucket_bytes)[0] % self.dim
                sign = 1.0 if sign_byte[0] < 128 else -1.0
                vec[bucket] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def embed_many(self, texts: Sequence[str]) -> np.ndarray:
        return np.stack([self.embed(t) for t in texts])


# ---------------------------------------------------------------------------
# sentence-transformers embedder (production)
# ---------------------------------------------------------------------------


@dataclass
class SentenceTransformerEmbedder:
    """Production embedder backed by ``sentence-transformers``.

    The model is loaded lazily on first :meth:`embed` call so
    constructing the embedder is cheap. Set ``model_name`` to pin a
    specific version (default ``all-MiniLM-L6-v2``; 384-dim).

    Determinism: sentence-transformers emits float32 vectors that
    are stable across runs on the same CPU/GPU, but NOT necessarily
    byte-identical across different PyTorch builds. E5.4 pins both
    the model version AND the pytorch build to keep CI rebuilds
    byte-equal.
    """

    model_name: str = DEFAULT_ST_MODEL
    _model: object | None = None

    @property
    def dim(self) -> int:
        return self._get_model().get_sentence_embedding_dimension()

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:  # pragma: no cover
                raise ImportError(
                    "sentence-transformers is not installed; install with "
                    "`pip install sentence-transformers` or fall back to "
                    "HashEmbedder via make_embedder(backend='hash')."
                ) from e
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, text: str) -> np.ndarray:
        vec = self._get_model().encode(
            [text], convert_to_numpy=True, show_progress_bar=False
        )[0]
        return vec.astype(np.float32, copy=False)

    def embed_many(self, texts: Sequence[str]) -> np.ndarray:
        vecs = self._get_model().encode(
            list(texts), convert_to_numpy=True, show_progress_bar=False
        )
        return vecs.astype(np.float32, copy=False)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_embedder(
    backend: str = "auto",
    *,
    model_name: str = DEFAULT_ST_MODEL,
    dim: int = DEFAULT_DIM,
) -> Embedder:
    """Construct an embedder.

    Args:
        backend: ``"auto"`` (default) picks SentenceTransformer when
            importable, else HashEmbedder. ``"hash"`` forces the
            hash backend. ``"sentence-transformers"`` forces the
            transformer backend (raises ImportError on first
            :meth:`embed` call if the package is missing).
        model_name: Passed through to SentenceTransformerEmbedder.
        dim: Passed through to HashEmbedder.
    """
    if backend == "hash":
        return HashEmbedder(dim=dim)
    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder(model_name=model_name)
    if backend == "auto":
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            return HashEmbedder(dim=dim)
        return SentenceTransformerEmbedder(model_name=model_name)
    raise ValueError(
        f"unknown backend {backend!r}; expected one of "
        "'auto', 'hash', 'sentence-transformers'"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two unit-ish vectors.

    Defensive: handles zero-norm inputs by returning 0.0 instead of
    NaN. Used by the retriever (index.py) and eval harness (E5.6).
    """
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


__all__ = [
    "DEFAULT_DIM",
    "DEFAULT_ST_MODEL",
    "Embedder",
    "HashEmbedder",
    "SentenceTransformerEmbedder",
    "cosine_similarity",
    "make_embedder",
]
