"""``ai-sw-apidoc`` — RAG query CLI (spec.md §4.6).

Five subcommands:

* ``ai-sw-apidoc search <query>`` — KNN over the committed index.
  Emits ``{hits: [{score, chunk: {...}}, ...]}``.
* ``ai-sw-apidoc detail <retrieval_key>`` — fetch one chunk by key.
* ``ai-sw-apidoc members [--interface X]`` — list distinct
  interface (or topic category) names. When ``--interface`` is
  given, returns the list of chunk names under that interface.
* ``ai-sw-apidoc examples`` — list chunks that carry an
  ``example_code`` block.
* ``ai-sw-apidoc enum <name>`` — enum lookup. Today the committed
  index only contains the programmer's-guide corpus (no enum
  data), so this subcommand emits ``{"ok": false, "reason":
  "enum lookup requires the sldworksapi batch corpus (E5.1
  follow-up); the committed index carries the programmer's guide
  only"}`` with rc=0 and a stderr notice. The contract is in
  place for when the API-reference corpus lands.

Two-stream contract: stdout is JSON-only, stderr is human-readable
(errors, warnings, "0 rows" notices).

Stability tier: **experimental** — the subcommand set may grow as
the corpus expands. Marked with ``@cli_stability("experimental")``
(Task 1.9 decorator from v0.11).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..rag.corpus import ApiChunk
from ..rag.embed import make_embedder
from ..rag.index import VectorIndex
from .stability import add_subcommand_tier, add_tier, cli_stability


_DEFAULT_INDEX = (
    Path(__file__).resolve().parent.parent / "rag" / "data" / "api_index.sqlite"
)


def _emit_json(payload: Any) -> None:
    """Emit one JSON object to stdout (two-stream contract)."""
    print(json.dumps(payload, sort_keys=False, indent=2))


def _emit_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _open_index(path: Path | str) -> VectorIndex:
    path = Path(path)
    if not path.exists():
        _emit_stderr(
            f"index not found: {path}. Run `python tools/build_api_index.py` "
            "to build it."
        )
        sys.exit(2)
    return VectorIndex.open(path)


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


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _cmd_search(args: argparse.Namespace) -> int:
    with _open_index(args.index) as idx:
        emb = make_embedder(backend=args.backend)
        hits = idx.search(
            args.query,
            embedder=emb,
            k=args.k,
            corpus_filter=args.corpus,
        )
    _emit_json(
        {
            "ok": True,
            "query": args.query,
            "hits": [
                {"score": round(score, 6), "chunk": _chunk_to_dict(chunk)}
                for chunk, score in hits
            ],
            "count": len(hits),
        }
    )
    return 0


def _cmd_detail(args: argparse.Namespace) -> int:
    with _open_index(args.index) as idx:
        chunk = idx.get_chunk(args.retrieval_key)
    if chunk is None:
        _emit_stderr(f"no chunk for key {args.retrieval_key!r}")
        _emit_json({"ok": False, "reason": "not_found", "key": args.retrieval_key})
        return 3
    _emit_json({"ok": True, "chunk": _chunk_to_dict(chunk)})
    return 0


def _cmd_members(args: argparse.Namespace) -> int:
    with _open_index(args.index) as idx:
        if args.interface is None:
            names = idx.list_interfaces(corpus_filter=args.corpus)
            _emit_json({"ok": True, "interfaces": names, "count": len(names)})
            return 0
        # Sub-filter: list chunk names under a given interface.
        rows = idx._conn.execute(
            "SELECT name, retrieval_key FROM chunks "
            "WHERE interface = ? AND (? IS NULL OR corpus = ?) "
            "ORDER BY name",
            (args.interface, args.corpus, args.corpus),
        ).fetchall()
    names = [{"name": r["name"], "retrieval_key": r["retrieval_key"]} for r in rows]
    _emit_json(
        {
            "ok": True,
            "interface": args.interface,
            "members": names,
            "count": len(names),
        }
    )
    return 0


def _cmd_examples(args: argparse.Namespace) -> int:
    with _open_index(args.index) as idx:
        chunks = idx.find_with_code(limit=args.limit, corpus_filter=args.corpus)
    _emit_json(
        {
            "ok": True,
            "examples": [_chunk_to_dict(c) for c in chunks],
            "count": len(chunks),
        }
    )
    return 0


def _cmd_enum(args: argparse.Namespace) -> int:
    # The committed index (E5.4) carries the programmer's guide only.
    # Enum data comes from the sldworksapi.chm batch extract, which
    # is not yet in the index. The subcommand contract is in place
    # so the CLI surface doesn't change when that corpus lands.
    _emit_stderr(
        f"enum {args.enum_name!r}: the committed index carries the "
        "programmer's guide only; enum lookup needs the sldworksapi "
        "batch corpus (E5.1 follow-up)."
    )
    _emit_json(
        {
            "ok": False,
            "reason": "enum_corpus_missing",
            "enum_name": args.enum_name,
            "hint": (
                "Batch-extract sldworksapi.chm and rebuild the index "
                "(`python tools/chm_extract.py batch <spec> <out>` then "
                "`python tools/build_api_index.py`) to enable enum lookup."
            ),
        }
    )
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-apidoc",
        description=(
            "Query the committed RAG index (spec.md §4.6). Five "
            "subcommands cover KNN search, single-chunk detail, "
            "interface / member enumeration, example listing, and "
            "enum lookup. Two-stream contract: stdout is JSON-only; "
            "stderr carries human-readable notices."
        ),
    )
    add_tier(parser, "experimental")
    parser.add_argument(
        "--index",
        default=str(_DEFAULT_INDEX),
        help="Path to the committed RAG index (default: %(default)s).",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "hash", "sentence-transformers"),
        default="auto",
        help="Embedder backend (default: auto).",
    )
    parser.add_argument(
        "--corpus",
        default=None,
        help="Restrict to one corpus (e.g. sldworksapiprogguide).",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("search", help="KNN search over the index.")
    add_subcommand_tier(ps, "experimental")
    ps.add_argument("query", help="Free-form query string.")
    ps.add_argument("-k", type=int, default=5, help="Top-k (default: 5).")
    ps.set_defaults(func=_cmd_search)

    pd = sub.add_parser("detail", help="Fetch one chunk by retrieval key.")
    add_subcommand_tier(pd, "experimental")
    pd.add_argument("retrieval_key", help="Chunk retrieval key.")
    pd.set_defaults(func=_cmd_detail)

    pm = sub.add_parser(
        "members",
        help="List interfaces (or chunk names under one interface).",
    )
    add_subcommand_tier(pm, "experimental")
    pm.add_argument(
        "--interface",
        default=None,
        help="Restrict to one interface; list its members.",
    )
    pm.set_defaults(func=_cmd_members)

    pe = sub.add_parser("examples", help="List chunks carrying example_code.")
    add_subcommand_tier(pe, "experimental")
    pe.add_argument("--limit", type=int, default=10, help="Cap (default: 10).")
    pe.set_defaults(func=_cmd_examples)

    pn = sub.add_parser("enum", help="Look up an enum by name.")
    add_subcommand_tier(pn, "experimental")
    pn.add_argument("enum_name", help="Enum name (e.g. swEndConditions_e).")
    pn.set_defaults(func=_cmd_enum)

    return parser


@cli_stability("experimental")
def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
