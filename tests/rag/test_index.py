"""Tests for ai_sw_bridge.rag.index (spec.md §4.4).

Covers:

* VectorIndex.create / open / close lifecycle.
* build() is idempotent (re-running with same chunks yields the
  same row count, duplicate retrieval_keys skipped).
* add() returns the number of rows actually inserted.
* search() returns up to k results sorted by similarity desc.
* corpus_filter narrows to one corpus.
* stats() reports chunks + dim.
* FileNotFoundError on open() of missing path.

All tests use HashEmbedder (deterministic, zero-dep) so the index
test matrix doesn't depend on what's installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_sw_bridge.rag.corpus import ApiChunk
from ai_sw_bridge.rag.embed import HashEmbedder
from ai_sw_bridge.rag.index import VectorIndex


def _chunk(
    name: str,
    *,
    corpus: str = "sldworksapiprogguide",
    interface: str = "Overview",
    description: str = "prose goes here",
    chunk_index: int = 0,
) -> ApiChunk:
    return ApiChunk(
        chunk_type="topic",
        corpus=corpus,
        interface=interface,
        name=name,
        signature=None,
        description=description,
        example_code=None,
        chm_anchor=f"{interface}/{name}.htm",
        text_for_embedding=f"[{interface}]\n{name}\n{description}",
        chunk_index=chunk_index,
        keywords=(),
    )


@pytest.fixture
def emb() -> HashEmbedder:
    return HashEmbedder(dim=32)


@pytest.fixture
def idx_path(tmp_path: Path) -> Path:
    return tmp_path / "idx.sqlite"


# -- lifecycle --------------------------------------------------------------


def test_open_missing_raises(idx_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        VectorIndex.open(idx_path)


def test_create_then_open_roundtrip(idx_path: Path, emb: HashEmbedder) -> None:
    with VectorIndex.create(idx_path, emb.dim) as idx:
        idx.add([_chunk("Alpha")], emb)
    with VectorIndex.open(idx_path) as idx:
        assert idx.stats()["chunks"] == 1


# -- stats + build ----------------------------------------------------------


def test_stats_reports_dim_and_count(idx_path: Path, emb: HashEmbedder) -> None:
    with VectorIndex.create(idx_path, emb.dim) as idx:
        idx.build([_chunk("A"), _chunk("B")], emb)
        s = idx.stats()
    assert s["chunks"] == 2
    assert s["dim"] == emb.dim


def test_build_is_idempotent(idx_path: Path, emb: HashEmbedder) -> None:
    chunks = [_chunk("A"), _chunk("B")]
    with VectorIndex.create(idx_path, emb.dim) as idx:
        first = idx.build(chunks, emb)
        second = idx.build(chunks, emb)
    assert first == second == {"chunks": 2, "dim": emb.dim}


# -- add --------------------------------------------------------------------


def test_add_returns_rows_inserted(idx_path: Path, emb: HashEmbedder) -> None:
    with VectorIndex.create(idx_path, emb.dim) as idx:
        n = idx.add([_chunk("A"), _chunk("B")], emb)
    assert n == 2


def test_add_skips_duplicates_by_retrieval_key(
    idx_path: Path, emb: HashEmbedder
) -> None:
    a = _chunk("A")
    with VectorIndex.create(idx_path, emb.dim) as idx:
        assert idx.add([a], emb) == 1
        assert idx.add([a], emb) == 0  # same retrieval_key
        assert idx.stats()["chunks"] == 1


def test_add_empty_list_is_noop(idx_path: Path, emb: HashEmbedder) -> None:
    with VectorIndex.create(idx_path, emb.dim) as idx:
        assert idx.add([], emb) == 0
        assert idx.stats()["chunks"] == 0


# -- search -----------------------------------------------------------------


def test_search_returns_up_to_k_results(idx_path: Path, emb: HashEmbedder) -> None:
    chunks = [_chunk(f"T{i}", description=f"topic {i}") for i in range(10)]
    with VectorIndex.create(idx_path, emb.dim) as idx:
        idx.build(chunks, emb)
        results = idx.search("any query", k=3, embedder=emb)
    assert len(results) == 3


def test_search_sorted_by_similarity_descending(
    idx_path: Path, emb: HashEmbedder
) -> None:
    chunks = [_chunk(f"T{i}", description=f"topic {i}") for i in range(10)]
    with VectorIndex.create(idx_path, emb.dim) as idx:
        idx.build(chunks, emb)
        results = idx.search("any query", k=5, embedder=emb)
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)


def test_search_returns_full_chunk_payload(idx_path: Path, emb: HashEmbedder) -> None:
    chunks = [_chunk("Only", description="the only chunk")]
    with VectorIndex.create(idx_path, emb.dim) as idx:
        idx.build(chunks, emb)
        results = idx.search("whatever", k=1, embedder=emb)
    assert len(results) == 1
    chunk, _score = results[0]
    assert chunk.name == "Only"
    assert chunk.interface == "Overview"
    assert chunk.description == "the only chunk"


def test_search_corpus_filter(idx_path: Path, emb: HashEmbedder) -> None:
    chunks = [
        _chunk("Narrative", corpus="sldworksapiprogguide"),
        _chunk("Reference", corpus="sldworksapi", interface="IFeatureManager"),
    ]
    with VectorIndex.create(idx_path, emb.dim) as idx:
        idx.build(chunks, emb)
        results = idx.search(
            "anything",
            k=5,
            embedder=emb,
            corpus_filter="sldworksapi",
        )
    assert len(results) == 1
    assert results[0][0].name == "Reference"


def test_search_on_empty_index_returns_empty(idx_path: Path, emb: HashEmbedder) -> None:
    with VectorIndex.create(idx_path, emb.dim) as idx:
        assert idx.search("anything", k=5, embedder=emb) == []


# -- determinism ------------------------------------------------------------


def test_index_build_deterministic(tmp_path: Path, emb: HashEmbedder) -> None:
    """Two fresh builds over the same chunks yield byte-identical files."""
    chunks = [_chunk(f"T{i}", description=f"prose {i}") for i in range(5)]
    a_path = tmp_path / "a.sqlite"
    b_path = tmp_path / "b.sqlite"
    with VectorIndex.create(a_path, emb.dim) as idx:
        idx.build(chunks, emb)
    with VectorIndex.create(b_path, emb.dim) as idx:
        idx.build(chunks, emb)
    # WAL/journal sidecars can make the file differ byte-for-byte;
    # vacuum + close both so we compare the main DB only.
    for p in (a_path, b_path):
        import sqlite3

        conn = sqlite3.connect(str(p))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
        conn.close()
    assert a_path.read_bytes() == b_path.read_bytes()
