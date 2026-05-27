"""Corpus loader (spec.md §4.3).

Loads extracted CHM JSON into a normalized :class:`ApiChunk` document
model. Two corpus types:

* ``sldworksapiprogguide`` — narrative topics. Each topic is one
  document; chunking (in :mod:`ai_sw_bridge.rag.chunk`) splits the
  prose into paragraph-based passages with overlap.
* ``sldworksapi`` — per-method / per-enum reference. Loaded from a
  batch-extracted JSON (one document per method or enum; chunking is
  identity).

The :class:`ApiChunk` dataclass carries a ``chunk_type`` tag so the
downstream embedder and index can route per-type (narrative chunks
tend to be longer; reference chunks are tight and self-describing).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ChunkType = Literal["method", "enum", "interface_summary", "example", "topic"]
CorpusType = Literal["sldworksapi", "sldworksapiprogguide"]

_DEFAULT_PROGGUIDE_CORPUS = (
    Path(__file__).resolve().parents[3]
    / "tools"
    / "rag_data"
    / "sldworksapiprogguide_corpus.json"
)


@dataclass(frozen=True)
class ApiChunk:
    """One retrieval unit.

    ``interface`` and ``name`` together form the stable retrieval key
    (``f"{corpus}:{interface}:{name}:{chunk_index}"``). For narrative
    topics, ``interface`` holds the topic category (e.g. ``Overview``)
    and ``name`` holds the topic title. For API reference chunks they
    hold the COM interface name and method / enum member name
    respectively.

    ``signature`` is the C# signature block for method chunks and
    ``None`` for everything else. ``example_code`` is the concatenated
    example snippet (may be multi-block for narrative topics).

    ``text_for_embedding`` is the string handed to the embedding model
    verbatim. Per spec.md §4.3 it's a structured concatenation of the
    chunk's identifying + descriptive fields so the retriever has
    both name-signal and content-signal in the same vector.
    """

    chunk_type: ChunkType
    corpus: CorpusType
    interface: str
    name: str
    signature: str | None
    description: str
    example_code: str | None
    chm_anchor: str
    text_for_embedding: str
    chunk_index: int = 0
    keywords: tuple[str, ...] = field(default_factory=tuple)

    def retrieval_key(self) -> str:
        return f"{self.corpus}:{self.interface}:{self.name}:{self.chunk_index}"


def _progguide_embedding_text(
    title: str, prose: str, code_examples: list[str], category: str | None
) -> str:
    """Structured concatenation for the embedding model.

    Order: category, title, prose, code. Category first so topics
    from the same chapter cluster (helps retrieval when the query
    names a chapter like "Getting Started"). Code last so it doesn't
    dominate short passages.
    """
    parts: list[str] = []
    if category:
        parts.append(f"[{category}]")
    parts.append(title)
    if prose:
        parts.append(prose)
    if code_examples:
        parts.append("\n\n".join(code_examples))
    return "\n".join(parts)


def load_progguide_corpus(
    path: Path | None = None,
) -> list[ApiChunk]:
    """Load the committed programmer's-guide corpus into ApiChunks.

    One chunk per topic (E5.3's embedder will further split long
    passages via :func:`ai_sw_bridge.rag.chunk.chunk_progguide_topic`).

    Args:
        path: Optional override. Defaults to
            ``tools/rag_data/sldworksapiprogguide_corpus.json``.

    Returns:
        List of ApiChunk instances sorted by (category, title) --
        the same order the extractor commits.

    Raises:
        FileNotFoundError: corpus file missing (run E5.1 first).
        json.JSONDecodeError: corpus file is malformed.
    """
    corpus_path = path if path is not None else _DEFAULT_PROGGUIDE_CORPUS
    with corpus_path.open("r", encoding="utf-8") as f:
        payload: dict[str, Any] = json.load(f)

    chunks: list[ApiChunk] = []
    for topic in payload.get("topics", []):
        title = topic.get("title") or ""
        if not title:
            continue
        category = topic.get("category") or ""
        prose = topic.get("text") or ""
        code_examples = topic.get("code_examples") or []
        keywords = tuple(topic.get("keywords") or ())
        anchor = topic.get("source") or ""

        chunks.append(
            ApiChunk(
                chunk_type="topic",
                corpus="sldworksapiprogguide",
                interface=category,
                name=title,
                signature=None,
                description=prose,
                example_code="\n\n".join(code_examples) if code_examples else None,
                chm_anchor=anchor,
                text_for_embedding=_progguide_embedding_text(
                    title, prose, code_examples, category
                ),
                chunk_index=0,
                keywords=keywords,
            )
        )
    return chunks


__all__ = ["ApiChunk", "ChunkType", "CorpusType", "load_progguide_corpus"]
