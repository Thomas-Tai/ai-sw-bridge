"""RAG (Retrieval-Augmented Generation) lane for the SOLIDWORKS API.

Gated by ``flags.rag_apidoc`` (default OFF). Two corpora feed the lane:

* **sldworksapiprogguide** — narrative topics from the programmer's
  guide CHM. Loaded from
  ``tools/rag_data/sldworksapiprogguide_corpus.json`` (committed by
  E5.1). Chunked as paragraph-based passages with table-boundary
  preservation (spec.md §4.3 extension for narrative content).
* **sldworksapi** — per-method / per-enum reference. Batch-extracted
  from sldworksapi.chm via ``tools/chm_extract.py batch``. Chunked
  as one chunk per method or enum (spec.md §4.3).

Submodules:

* :mod:`ai_sw_bridge.rag.corpus` — load extracted CHM JSON into a
  normalized :class:`ApiChunk` document model.
* :mod:`ai_sw_bridge.rag.chunk` — chunking strategies per corpus
  type.
* :mod:`ai_sw_bridge.rag.embed` (E5.3) — sentence-transformer
  embeddings.
* :mod:`ai_sw_bridge.rag.index` (E5.3) — sqlite-vec backed
  similarity search.
"""

from __future__ import annotations

from .corpus import ApiChunk, load_progguide_corpus
from .chunk import chunk_progguide_topic

__all__ = [
    "ApiChunk",
    "chunk_progguide_topic",
    "load_progguide_corpus",
]
