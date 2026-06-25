"""``ai-sw-memory`` — Design-Memory RAG CLI.

Semantic retrieval over the operator's OWN design history (the local
``sqlite-vec`` index built by :mod:`ai_sw_bridge.rag.design_memory`):

* ``ai-sw-memory build`` — (re)build the index by backfilling from existing
  history (``proposals/*.json`` + ``.checkpoints/*.sqlite``). Emits the
  ingestion report.
* ``ai-sw-memory search <query>`` — KNN over the index. Emits
  ``{hits: [{score, recipe: {...}}, ...]}``. Optional ``--kind`` /
  ``--recipe-kind`` metadata filters.
* ``ai-sw-memory stats`` — recipe count + by-kind breakdown + dim.

The index is a per-operator PRIVATE runtime artifact (gitignored) — embeddings
are computed on-device, so proprietary design history never leaves the machine.

Two-stream contract: stdout is JSON-only, stderr is human-readable.
Stability tier: **experimental**.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..rag.design_memory import DesignMemoryIndex, backfill_all
from ..rag.design_verbalizer import DesignRecipe
from ..rag.embed import DEFAULT_DIM, make_embedder
from .stability import add_subcommand_tier, add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet

_DEFAULT_INDEX = (
    Path(__file__).resolve().parent.parent
    / "rag"
    / "data"
    / "design_memory_index.sqlite"
)


def _emit_json(payload: Any) -> None:
    print(json.dumps(payload, sort_keys=False, indent=2))


def _emit_stderr(message: str) -> None:
    print(message, file=sys.stderr)


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


def _open_index(path: Path | str) -> DesignMemoryIndex:
    path = Path(path)
    if not path.exists():
        _emit_stderr(
            f"design-memory index not found: {path}. "
            "Run `ai-sw-memory build` to create it."
        )
        sys.exit(2)
    return DesignMemoryIndex.open(path)


def _resolve_backend(backend: str, idx: DesignMemoryIndex) -> str:
    """Match the index's embedding dim — a 256-dim index was built with the
    HashEmbedder; anything else came from a sentence-transformer model."""
    if backend == "auto" and idx.stats().get("dim") == DEFAULT_DIM:
        return "hash"
    return backend


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _cmd_build(args: argparse.Namespace) -> int:
    emb = make_embedder(backend=args.backend)
    idx = DesignMemoryIndex.create(Path(args.index), emb.dim)
    try:
        report = backfill_all(idx, emb, root=Path(args.root))
        report["ok"] = True
        report["index"] = str(args.index)
        report["embedder"] = type(emb).__name__
        report["dim"] = emb.dim
    finally:
        idx.close()
    _emit_json(report)
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    with _open_index(args.index) as idx:
        backend = _resolve_backend(args.backend, idx)
        emb = make_embedder(backend=backend)
        hits = idx.search(
            args.query,
            embedder=emb,
            k=args.k,
            kind=args.kind,
            recipe_kind=args.recipe_kind,
        )
    _emit_json(
        {
            "ok": True,
            "query": args.query,
            "hits": [
                {"score": round(score, 6), "recipe": _recipe_to_dict(r)}
                for r, score in hits
            ],
            "count": len(hits),
        }
    )
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    with _open_index(args.index) as idx:
        stats = idx.stats()
    _emit_json({"ok": True, **stats})
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-memory",
        description=(
            "Design-Memory RAG: semantic retrieval over the operator's own "
            "design history. build / search / stats. Two-stream contract: "
            "stdout is JSON-only; stderr carries human-readable notices. "
            "Embeddings are computed on-device (private)."
        ),
    )
    add_tier(parser, "experimental")
    parser.add_argument(
        "--index",
        default=str(_DEFAULT_INDEX),
        help="Path to the design-memory index (default: %(default)s).",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "hash", "sentence-transformers"),
        default="auto",
        help="Embedder backend (default: auto).",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser(
        "build", help="(Re)build the index by backfilling from history."
    )
    add_subcommand_tier(pb, "experimental")
    pb.add_argument(
        "--root",
        default=".",
        help="Repo root to backfill from (proposals/, .checkpoints/).",
    )
    pb.set_defaults(func=_cmd_build)

    ps = sub.add_parser("search", aliases=["query"], help="KNN over the index.")
    add_subcommand_tier(ps, "experimental")
    ps.add_argument("query", help="Free-form design-intent query.")
    ps.add_argument("-k", type=int, default=5, help="Top-k (default: 5).")
    ps.add_argument(
        "--kind",
        default=None,
        help="Filter by design type: feature_add/drawing/assembly/part_build.",
    )
    ps.add_argument(
        "--recipe-kind",
        dest="recipe_kind",
        default=None,
        help="Filter to recipes containing an operation (e.g. linear_pattern).",
    )
    ps.set_defaults(func=_cmd_search)

    pt = sub.add_parser("stats", help="Index recipe count + by-kind breakdown.")
    add_subcommand_tier(pt, "experimental")
    pt.set_defaults(func=_cmd_stats)

    return parser


@cli_stability("experimental")
def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    add_quiet_flag(parser)
    args = parser.parse_args(argv)
    apply_quiet(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
