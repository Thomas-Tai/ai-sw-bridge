"""API-doc MCP tools (W5.4, §6.3).

Five tools exposing the committed RAG index (``ai-sw-apidoc``):

* ``sw_apidoc_search`` — KNN search over the index.
* ``sw_apidoc_detail`` — fetch one chunk by retrieval key.
* ``sw_apidoc_members`` — list interfaces, or chunk names under one.
* ``sw_apidoc_examples`` — list chunks carrying ``example_code``.
* ``sw_apidoc_enum`` — enum lookup (emits ``corpus_missing`` until the
  sldworksapi batch corpus lands).

These tools touch SQLite, not COM — they do NOT use ``@com_tool``.
The contract test exempts them from the decorator audit.

Design: ``docs/mcp_server_design.md`` §6.3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..rag.corpus import ApiChunk
from ..rag.embed import DEFAULT_DIM, make_embedder
from ..rag.index import VectorIndex


_DEFAULT_INDEX = (
    Path(__file__).resolve().parent.parent / "rag" / "data" / "api_index.sqlite"
)


def _chunk_to_dict(c: ApiChunk) -> dict[str, Any]:
    return {
        "retrieval_key": c.retrieval_key(),
        "corpus": c.corpus,
        "chunk_type": c.chunk_type,
        "interface": c.interface,
        "name": c.name,
        "signature": c.signature,
        "description": c.description,
        "example_code": c.example_code,
        "chm_anchor": c.chm_anchor,
        "keywords": list(c.keywords),
    }


def register(mcp: Any) -> None:
    """Register every §6.3 apidoc tool against *mcp*."""

    @mcp.tool()
    def sw_apidoc_search(
        query: str,
        k: int = 5,
        corpus: str | None = None,
        backend: str = "auto",
    ) -> dict[str, Any]:
        """KNN search over the committed RAG index."""
        if not _DEFAULT_INDEX.exists():
            return {
                "ok": False,
                "error": f"index not found: {_DEFAULT_INDEX}",
                "hint": "Run `python tools/build_api_index.py` to build it.",
            }
        with VectorIndex.open(_DEFAULT_INDEX) as idx:
            resolved = backend
            if resolved == "auto":
                idx_dim = idx.stats().get("dim")
                if idx_dim == DEFAULT_DIM:
                    resolved = "hash"
            emb = make_embedder(backend=resolved)
            hits = idx.search(query, embedder=emb, k=k, corpus_filter=corpus)
        return {
            "ok": True,
            "query": query,
            "hits": [
                {"score": round(score, 6), "chunk": _chunk_to_dict(chunk)}
                for chunk, score in hits
            ],
            "count": len(hits),
        }

    @mcp.tool()
    def sw_apidoc_detail(retrieval_key: str) -> dict[str, Any]:
        """Fetch one chunk by its retrieval key."""
        if not _DEFAULT_INDEX.exists():
            return {
                "ok": False,
                "error": f"index not found: {_DEFAULT_INDEX}",
            }
        with VectorIndex.open(_DEFAULT_INDEX) as idx:
            chunk = idx.get_chunk(retrieval_key)
        if chunk is None:
            return {
                "ok": False,
                "reason": "not_found",
                "key": retrieval_key,
            }
        return {"ok": True, "chunk": _chunk_to_dict(chunk)}

    @mcp.tool()
    def sw_apidoc_members(
        interface: str | None = None,
        corpus: str | None = None,
    ) -> dict[str, Any]:
        """List interfaces (or chunk names under one interface)."""
        if not _DEFAULT_INDEX.exists():
            return {
                "ok": False,
                "error": f"index not found: {_DEFAULT_INDEX}",
            }
        with VectorIndex.open(_DEFAULT_INDEX) as idx:
            if interface is None:
                names = idx.list_interfaces(corpus_filter=corpus)
                return {"ok": True, "interfaces": names, "count": len(names)}
            rows = idx._conn.execute(
                "SELECT name, retrieval_key FROM chunks "
                "WHERE interface = ? AND (? IS NULL OR corpus = ?) "
                "ORDER BY name",
                (interface, corpus, corpus),
            ).fetchall()
        members = [
            {"name": r["name"], "retrieval_key": r["retrieval_key"]} for r in rows
        ]
        return {
            "ok": True,
            "interface": interface,
            "members": members,
            "count": len(members),
        }

    @mcp.tool()
    def sw_apidoc_examples(
        limit: int = 10,
        corpus: str | None = None,
    ) -> dict[str, Any]:
        """List chunks carrying example_code blocks."""
        if not _DEFAULT_INDEX.exists():
            return {
                "ok": False,
                "error": f"index not found: {_DEFAULT_INDEX}",
            }
        with VectorIndex.open(_DEFAULT_INDEX) as idx:
            chunks = idx.find_with_code(limit=limit, corpus_filter=corpus)
        return {
            "ok": True,
            "examples": [_chunk_to_dict(c) for c in chunks],
            "count": len(chunks),
        }

    @mcp.tool()
    def sw_apidoc_enum(enum_name: str) -> dict[str, Any]:
        """Look up an enum by name.

        The committed index carries the programmer's guide only; enum
        lookup requires the sldworksapi batch corpus (E5.1 follow-up).
        Returns ``ok=False`` with ``reason="enum_corpus_missing"``
        until that corpus lands.
        """
        return {
            "ok": False,
            "reason": "enum_corpus_missing",
            "enum_name": enum_name,
            "hint": (
                "Batch-extract sldworksapi.chm and rebuild the index "
                "(`python tools/chm_extract.py batch <spec> <out>` then "
                "`python tools/build_api_index.py`) to enable enum lookup."
            ),
        }
