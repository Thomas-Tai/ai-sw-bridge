"""Build the committed RAG index (E5.4, execution_plan_90d.md #3.4).

Pipeline:

    sldworksapiprogguide_corpus.json (E5.1)
        -> load_progguide_corpus()         # ApiChunk list
        -> chunk_progguide_topic() * N      # windowed sub-chunks
        -> HashEmbedder (deterministic)     # 256-dim float32
        -> VectorIndex.create()             # sqlite-vec KNN index

Default output path (committed to the repo):

    src/ai_sw_bridge/rag/data/api_index.sqlite

The CI determinism gate (documented in release_engineering.md; the
workflow addition is tracked separately) runs this script on every
PR that touches ``rag/`` and asserts the rebuilt file is byte-equal
to the committed copy. That assertion is what keeps the embedding
+ index path reproducible across hosts.

CLI
---
  python tools/build_api_index.py               # build -> default path
  python tools/build_api_index.py --verify      # rebuild + compare
  python tools/build_api_index.py --output PATH # custom path
  python tools/build_api_index.py --backend hash | sentence-transformers | auto

Exit codes:
  0 = success
  1 = verify failed (rebuilt file differs from committed copy)
  2 = input corpus missing
  3 = unexpected error
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Allow ``python tools/build_api_index.py`` from any cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ai_sw_bridge.rag.chunk import chunk_progguide_topic  # noqa: E402
from ai_sw_bridge.rag.corpus import load_progguide_corpus  # noqa: E402
from ai_sw_bridge.rag.embed import make_embedder  # noqa: E402
from ai_sw_bridge.rag.index import VectorIndex  # noqa: E402

DEFAULT_CORPUS = _REPO_ROOT / "tools" / "rag_data" / "sldworksapiprogguide_corpus.json"
DEFAULT_OUTPUT = (
    _REPO_ROOT / "src" / "ai_sw_bridge" / "rag" / "data" / "api_index.sqlite"
)

DEFAULT_CHUNK_TOKENS = 200
DEFAULT_OVERLAP_TOKENS = 40


def _vacuum(path: Path) -> None:
    """Checkpoint WAL + VACUUM so the resulting file is standalone.

    sqlite-vec and SQLite itself leave journal sidecars (``-wal``,
    ``-shm``) and internal free pages around after a build. Both
    make byte-equal comparisons flaky. Running ``PRAGMA
    wal_checkpoint(TRUNCATE)`` followed by ``VACUUM`` collapses the
    WAL into the main file and reclaims free pages so two fresh
    builds over identical input produce byte-identical output.
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    finally:
        conn.close()


def build_index(
    *,
    corpus_path: Path,
    output_path: Path,
    backend: str = "auto",
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> dict[str, Any]:
    """Run the pipeline end-to-end. Returns a small stats dict."""
    if not corpus_path.exists():
        raise FileNotFoundError(f"corpus not found: {corpus_path}")

    topics = load_progguide_corpus(corpus_path)
    chunks: list = []
    for topic in topics:
        chunks.extend(
            chunk_progguide_topic(
                topic,
                chunk_tokens=chunk_tokens,
                overlap_tokens=overlap_tokens,
            )
        )

    embedder = make_embedder(backend=backend)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with VectorIndex.create(output_path, embedder.dim) as idx:
        idx.build(chunks, embedder)

    _vacuum(output_path)

    return {
        "topics": len(topics),
        "chunks": len(chunks),
        "dim": embedder.dim,
        "backend": backend,
        "output": str(output_path),
        "bytes": output_path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="build_api_index",
        description=(
            "Build the committed RAG index from the programmer's-guide "
            "corpus. Deterministic: same corpus + same embedder backend "
            "=> byte-identical SQLite output (after VACUUM)."
        ),
    )
    parser.add_argument(
        "--corpus",
        default=str(DEFAULT_CORPUS),
        help="Path to the sldworksapiprogguide corpus JSON (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output index path (default: %(default)s).",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "hash", "sentence-transformers"),
        default="auto",
        help="Embedder backend (default: auto).",
    )
    parser.add_argument(
        "--chunk-tokens",
        type=int,
        default=DEFAULT_CHUNK_TOKENS,
        help="Chunker target tokens per window (default: %(default)s).",
    )
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=DEFAULT_OVERLAP_TOKENS,
        help="Chunker overlap tokens (default: %(default)s).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Rebuild to a tmp file and assert byte-equal to the "
            "committed copy at --output. Used by the CI determinism "
            "gate. Exit 1 on mismatch."
        ),
    )
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    output_path = Path(args.output)

    if not corpus_path.exists():
        print(
            json.dumps(
                {
                    "error": f"corpus not found: {corpus_path}",
                    "hint": (
                        "Run `python tools/chm_extract.py progguide "
                        "tools/rag_data/sldworksapiprogguide_corpus.json` "
                        "first."
                    ),
                },
                indent=2,
            )
        )
        return 2

    try:
        if args.verify:
            if not output_path.exists():
                print(
                    json.dumps(
                        {
                            "error": (
                                f"--verify but no committed file at {output_path}"
                            ),
                            "hint": (
                                "Run without --verify first to produce the baseline."
                            ),
                        },
                        indent=2,
                    )
                )
                return 1
            committed_bytes = output_path.read_bytes()
            tmp_path = output_path.with_suffix(".sqlite.rebuild")
            stats = build_index(
                corpus_path=corpus_path,
                output_path=tmp_path,
                backend=args.backend,
                chunk_tokens=args.chunk_tokens,
                overlap_tokens=args.overlap_tokens,
            )
            rebuilt_bytes = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)
            if committed_bytes != rebuilt_bytes:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "reason": "determinism gate failed: rebuilt index "
                            "differs byte-for-byte from committed copy",
                            "committed_bytes": len(committed_bytes),
                            "rebuilt_bytes": len(rebuilt_bytes),
                            "committed_sha256": _sha256(committed_bytes),
                            "rebuilt_sha256": _sha256(rebuilt_bytes),
                            "stats": stats,
                        },
                        indent=2,
                    )
                )
                return 1
            print(
                json.dumps(
                    {"ok": True, "determinism_gate": "pass", "stats": stats},
                    indent=2,
                )
            )
            return 0

        stats = build_index(
            corpus_path=corpus_path,
            output_path=output_path,
            backend=args.backend,
            chunk_tokens=args.chunk_tokens,
            overlap_tokens=args.overlap_tokens,
        )
        print(json.dumps({"ok": True, "stats": stats}, indent=2))
        return 0
    except Exception as e:  # pragma: no cover - top-level error path
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2))
        return 3


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
