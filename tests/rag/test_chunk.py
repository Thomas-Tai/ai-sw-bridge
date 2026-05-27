"""Tests for ai_sw_bridge.rag.chunk (spec.md §4.3).

Covers the paragraph-based chunker for narrative topics:

* Short topic (prose fits in one window) -> single chunk, index 0.
* Long topic -> multiple chunks with sequential chunk_index values.
* Stability: two runs over the same input produce byte-identical
  text_for_embedding outputs.
* Overlap: adjacent chunks share trailing paragraphs (the last N
  tokens of chunk[i] reappear at the start of chunk[i+1]).
* Empty-prose topic passes through unchanged.
* ValueError on overlap >= chunk_tokens.
* Single giant paragraph (> chunk_tokens) emits as one chunk
  (graceful degradation; caller can post-split if needed).
"""

from __future__ import annotations

from ai_sw_bridge.rag.chunk import (
    _approx_tokens,
    chunk_progguide_topic,
)
from ai_sw_bridge.rag.corpus import ApiChunk


def _topic(
    prose: str,
    *,
    title: str = "Topic Title",
    category: str = "Overview",
) -> ApiChunk:
    return ApiChunk(
        chunk_type="topic",
        corpus="sldworksapiprogguide",
        interface=category,
        name=title,
        signature=None,
        description=prose,
        example_code=None,
        chm_anchor="Overview/Topic.htm",
        text_for_embedding=f"[{category}]\n{title}\n{prose}",
        keywords=("k1",),
    )


# -- short topics -----------------------------------------------------------


def test_short_topic_single_chunk() -> None:
    prose = "Short prose that fits in one window."
    chunks = chunk_progguide_topic(_topic(prose), chunk_tokens=200, overlap_tokens=40)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].description == prose


def test_empty_prose_single_chunk() -> None:
    chunks = chunk_progguide_topic(_topic(""), chunk_tokens=200, overlap_tokens=40)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


# -- long topics ------------------------------------------------------------


def test_long_topic_splits_into_multiple_chunks() -> None:
    # 30 paragraphs of ~30 words each = 900 words. At chunk_tokens=50
    # each window holds 1-2 paragraphs -> many chunks.
    paras = [f"Para {i}: " + "word " * 29 for i in range(30)]
    prose = "\n\n".join(paras)
    chunks = chunk_progguide_topic(_topic(prose), chunk_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    # chunk_index is sequential from 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Every sub-chunk inherits the parent's name/category/corpus
    for c in chunks:
        assert c.name == "Topic Title"
        assert c.interface == "Overview"
        assert c.corpus == "sldworksapiprogguide"


def test_long_topic_preserves_all_paragraphs() -> None:
    """Every input paragraph appears in at least one output chunk."""
    paras = [f"Para-{i}-unique-marker" for i in range(20)]
    prose = "\n\n".join(paras)
    chunks = chunk_progguide_topic(_topic(prose), chunk_tokens=3, overlap_tokens=1)

    all_paras = []
    for c in chunks:
        all_paras.extend(c.description.split("\n\n"))
    for p in paras:
        assert p in all_paras, f"{p} missing from all chunks"


def test_adjacent_chunks_share_overlap() -> None:
    """Adjacent chunks share at least one paragraph at the boundary."""
    paras = [f"Para-{i}" for i in range(20)]
    prose = "\n\n".join(paras)
    chunks = chunk_progguide_topic(_topic(prose), chunk_tokens=3, overlap_tokens=1)

    assert len(chunks) >= 2
    for i in range(len(chunks) - 1):
        a_paras = chunks[i].description.split("\n\n")
        b_paras = chunks[i + 1].description.split("\n\n")
        # At least one paragraph must appear in both.
        shared = set(a_paras) & set(b_paras)
        assert shared, (
            f"chunks {i} and {i+1} share no boundary paragraphs: "
            f"a={a_paras} b={b_paras}"
        )


# -- stability --------------------------------------------------------------


def test_chunker_deterministic_across_runs() -> None:
    paras = [f"Para {i}: " + "word " * 29 for i in range(25)]
    prose = "\n\n".join(paras)
    chunk = _topic(prose)

    a = chunk_progguide_topic(chunk, chunk_tokens=50, overlap_tokens=10)
    b = chunk_progguide_topic(chunk, chunk_tokens=50, overlap_tokens=10)

    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x.text_for_embedding == y.text_for_embedding
        assert x.description == y.description
        assert x.chunk_index == y.chunk_index


def test_chunker_preserves_keywords_and_anchor() -> None:
    paras = ["para " * 30 for _ in range(10)]  # ~30 words each
    prose = "\n\n".join(paras)
    parent = ApiChunk(
        chunk_type="topic",
        corpus="sldworksapiprogguide",
        interface="Overview",
        name="T",
        signature=None,
        description=prose,
        example_code="Dim x As Integer",
        chm_anchor="Overview/T.htm",
        text_for_embedding="t",
        keywords=("Bodies", "Faces"),
    )
    chunks = chunk_progguide_topic(parent, chunk_tokens=50, overlap_tokens=10)
    assert len(chunks) > 1
    for c in chunks:
        assert c.keywords == ("Bodies", "Faces")
        assert c.chm_anchor == "Overview/T.htm"
        assert c.example_code == "Dim x As Integer"


# -- validation -------------------------------------------------------------


def test_overlap_must_be_less_than_chunk_tokens() -> None:
    import pytest

    with pytest.raises(ValueError):
        chunk_progguide_topic(_topic("anything"), chunk_tokens=10, overlap_tokens=10)
    with pytest.raises(ValueError):
        chunk_progguide_topic(_topic("anything"), chunk_tokens=10, overlap_tokens=20)


# -- single giant paragraph -------------------------------------------------


def test_single_giant_paragraph_emits_one_chunk() -> None:
    """Graceful degradation: no paragraph breaks -> no split."""
    giant = "word " * 500  # ~500 words, way over 50-token window
    chunks = chunk_progguide_topic(_topic(giant), chunk_tokens=50, overlap_tokens=10)
    # One chunk (the giant paragraph as-is).
    assert len(chunks) == 1
    assert chunks[0].description == giant


def test_approx_tokens_is_word_count() -> None:
    assert _approx_tokens("one two three") == 3
    assert _approx_tokens("") == 0
    assert _approx_tokens("   spaced   out   ") == 2
