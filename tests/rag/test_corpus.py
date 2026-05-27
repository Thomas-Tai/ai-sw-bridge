"""Tests for ai_sw_bridge.rag.corpus (spec.md §4.3).

Covers:

* Schema shape of the loaded chunks (every topic produces a chunk;
  ``chunk_type='topic'``; ``interface`` holds the category).
* ``text_for_embedding`` order: category first, title next, prose
  next, code last.
* Empty-prose / empty-code handling.
* The committed corpus file loads (end-to-end smoke).
* FileNotFoundError when the corpus file is missing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.rag.corpus import (
    ApiChunk,
    _progguide_embedding_text,
    load_progguide_corpus,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_CORPUS = REPO_ROOT / "tools" / "rag_data" / "sldworksapiprogguide_corpus.json"


def _write_corpus(tmp_path: Path, topics: list[dict]) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps(
            {
                "source": str(tmp_path),
                "corpus": "sldworksapiprogguide",
                "topics_count": len(topics),
                "topics": topics,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _topic(
    title: str = "Topic Title",
    text: str = "Some narrative prose about an API concept.",
    code_examples: list[str] | None = None,
    keywords: list[str] | None = None,
    category: str = "Overview",
    source: str = "Overview/Topic.htm",
) -> dict:
    return {
        "title": title,
        "text": text,
        "code_examples": code_examples or [],
        "keywords": keywords or [],
        "category": category,
        "source": source,
    }


# -- embedding-text order ---------------------------------------------------


def test_embedding_text_orders_category_title_prose_code() -> None:
    text = _progguide_embedding_text(
        title="The Title",
        prose="Prose paragraph.",
        code_examples=["Dim x As Integer"],
        category="Overview",
    )
    lines = text.split("\n")
    assert lines[0] == "[Overview]"
    assert lines[1] == "The Title"
    assert "Prose paragraph." in text
    assert text.endswith("Dim x As Integer")


def test_embedding_text_omits_empty_category() -> None:
    text = _progguide_embedding_text(
        title="Title", prose="p", code_examples=[], category=None
    )
    assert not text.startswith("[")
    assert text.split("\n")[0] == "Title"


# -- corpus loader ----------------------------------------------------------


def test_load_progguide_corpus_one_topic_per_entry(tmp_path: Path) -> None:
    path = _write_corpus(
        tmp_path,
        [_topic(title="A"), _topic(title="B", category="Misc")],
    )
    chunks = load_progguide_corpus(path)

    assert len(chunks) == 2
    assert all(c.chunk_type == "topic" for c in chunks)
    assert all(c.corpus == "sldworksapiprogguide" for c in chunks)
    titles = {c.name for c in chunks}
    assert titles == {"A", "B"}
    cats = {c.name: c.interface for c in chunks}
    assert cats["A"] == "Overview"
    assert cats["B"] == "Misc"


def test_load_progguide_corpus_skips_untitled(tmp_path: Path) -> None:
    path = _write_corpus(tmp_path, [_topic(title=""), _topic(title="X")])
    chunks = load_progguide_corpus(path)
    assert len(chunks) == 1
    assert chunks[0].name == "X"


def test_load_progguide_corpus_empty_code_becomes_none(tmp_path: Path) -> None:
    path = _write_corpus(tmp_path, [_topic(code_examples=[])])
    chunks = load_progguide_corpus(path)
    assert chunks[0].example_code is None


def test_load_progguide_corpus_joins_multiple_code_blocks(
    tmp_path: Path,
) -> None:
    path = _write_corpus(
        tmp_path,
        [_topic(code_examples=["line one", "line two"])],
    )
    chunks = load_progguide_corpus(path)
    assert chunks[0].example_code == "line one\n\nline two"


def test_load_progguide_corpus_keywords_tuple(tmp_path: Path) -> None:
    path = _write_corpus(tmp_path, [_topic(keywords=["Bodies", "Faces"])])
    chunks = load_progguide_corpus(path)
    assert chunks[0].keywords == ("Bodies", "Faces")
    assert isinstance(chunks[0].keywords, tuple)


def test_load_progguide_corpus_retrieval_key_unique(tmp_path: Path) -> None:
    path = _write_corpus(
        tmp_path,
        [
            _topic(title="A", category="Overview"),
            _topic(title="A", category="Misc"),
            _topic(title="B", category="Overview"),
        ],
    )
    chunks = load_progguide_corpus(path)
    keys = [c.retrieval_key() for c in chunks]
    assert len(set(keys)) == len(keys)


def test_load_progguide_corpus_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_progguide_corpus(tmp_path / "does-not-exist.json")


def test_load_progguide_corpus_committed_file_smoke() -> None:
    """End-to-end: the committed corpus loads without error."""
    if not COMMITTED_CORPUS.exists():
        pytest.skip("committed corpus not present (E5.1 not merged)")
    chunks = load_progguide_corpus(COMMITTED_CORPUS)
    assert len(chunks) > 0
    # Every chunk has the mandatory fields populated.
    for c in chunks:
        assert c.chunk_type == "topic"
        assert c.corpus == "sldworksapiprogguide"
        assert c.name
        assert c.text_for_embedding


def test_apichunk_frozen() -> None:
    """ApiChunk is frozen per spec.md §4.3 (immutable document model)."""
    c = ApiChunk(
        chunk_type="topic",
        corpus="sldworksapiprogguide",
        interface="Overview",
        name="T",
        signature=None,
        description="p",
        example_code=None,
        chm_anchor="a.htm",
        text_for_embedding="t",
    )
    with pytest.raises(AttributeError):
        c.name = "other"  # type: ignore[misc]
