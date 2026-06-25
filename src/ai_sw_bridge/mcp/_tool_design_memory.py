"""Design-Memory MCP tool (§ Design-Memory RAG).

Exposes semantic retrieval over the operator's OWN design history — the local
``sqlite-vec`` index built by :mod:`ai_sw_bridge.rag.design_memory` (and the
``ai-sw-memory`` CLI). Lets the agent ground new geometry proposals in proven
past sequences before authoring.

Touches SQLite + a local embedder, NOT COM — so it does NOT use ``@com_tool``
(same exemption as the apidoc tools). The index is a per-operator private,
gitignored artifact; when absent the tool returns an actionable not-found dict
(the deterministic, CI-safe path the snapshot harness captures).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..rag.design_memory import DesignMemoryIndex
from ..rag.design_verbalizer import DesignRecipe
from ..rag.embed import DEFAULT_DIM, make_embedder

_DEFAULT_INDEX = (
    Path(__file__).resolve().parent.parent
    / "rag"
    / "data"
    / "design_memory_index.sqlite"
)


def _recipe_to_dict(r: DesignRecipe) -> dict[str, Any]:
    return {
        "retrieval_key": r.retrieval_key(),
        "source": r.source,
        "kind": r.kind,
        "doc": r.doc,
        "recipe_kinds": list(r.recipe_kinds),
        "state": r.state,
        "recipe_text": r.recipe_text,
    }


def register(mcp: Any) -> None:
    """Register the design-memory retrieval tool against *mcp*."""

    @mcp.tool()
    def sw_retrieve_design_memory(
        query: str,
        k: int = 5,
        kind: str | None = None,
        recipe_kind: str | None = None,
        backend: str = "auto",
    ) -> dict[str, Any]:
        """Find PAST designs semantically similar to *query* from the operator's
        own design history (local, on-device).

        Use this BEFORE proposing new SolidWorks geometry to ground the proposal
        in proven past strategies, feature combinations, or dimensional
        baselines. Each hit is a verbalized "design recipe" (a past feature-add
        batch, drawing, assembly, or part build).

        Args:
            query: Natural-language description of the design intent.
            k: Number of recipes to return (top-K).
            kind: Filter by design type — ``feature_add`` / ``drawing`` /
                ``assembly`` / ``part_build``.
            recipe_kind: Filter to recipes containing a specific operation,
                e.g. ``linear_pattern``, ``mate:concentric``, ``view:section``.
            backend: Embedder backend; ``auto`` matches the index's dimension.
        """
        if not _DEFAULT_INDEX.exists():
            return {
                "ok": False,
                "query": query,
                "error": f"design-memory index not found: {_DEFAULT_INDEX}",
                "hint": "Build it with `ai-sw-memory build` (backfills from "
                "proposals/ + .checkpoints/).",
                "hits": [],
                "count": 0,
            }
        with DesignMemoryIndex.open(_DEFAULT_INDEX) as idx:
            resolved = backend
            if resolved == "auto" and idx.stats().get("dim") == DEFAULT_DIM:
                resolved = "hash"
            emb = make_embedder(backend=resolved)
            hits = idx.search(
                query, embedder=emb, k=k, kind=kind, recipe_kind=recipe_kind
            )
        return {
            "ok": True,
            "query": query,
            "hits": [
                {"score": round(score, 6), "recipe": _recipe_to_dict(r)}
                for r, score in hits
            ],
            "count": len(hits),
        }
