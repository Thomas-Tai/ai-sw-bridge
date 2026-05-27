"""RAG evaluation harness (E5.6, audit_review.md §2.8).

Runs every query in ``tools/rag_eval_benchmark.json`` against the
committed index and reports precision@1, precision@5, and MRR.
The CI gate is ``precision@1 >= 0.80``; the script exits 0 on
pass, 1 on fail, 2 on missing inputs, 3 on unexpected errors.

CLI:
  python tools/rag_eval.py
  python tools/rag_eval.py --benchmark PATH --index PATH
  python tools/rag_eval.py --backend hash|sentence-transformers|auto

Two-stream contract: stdout is the JSON report, stderr carries the
progress ticker and final pass/fail verdict.

The benchmark JSON was calibrated (at generation time) so the
HashEmbedder baseline hits precision@1 = 1.000 on the committed
index. A regression in embed / index / chunk code drops the score;
a future swap to sentence-transformers should raise it toward 1.0
if the benchmark is re-calibrated for semantic queries.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ai_sw_bridge.rag.embed import make_embedder  # noqa: E402
from ai_sw_bridge.rag.index import VectorIndex  # noqa: E402

DEFAULT_BENCHMARK = _REPO_ROOT / "tools" / "rag_eval_benchmark.json"
DEFAULT_INDEX = (
    _REPO_ROOT / "src" / "ai_sw_bridge" / "rag" / "data" / "api_index.sqlite"
)


def _emit_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False))


def _emit_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def evaluate(
    *,
    benchmark_path: Path,
    index_path: Path,
    backend: str,
    k_max: int = 5,
) -> dict[str, Any]:
    """Run the benchmark. Returns the JSON-report payload."""
    if not benchmark_path.exists():
        raise FileNotFoundError(f"benchmark not found: {benchmark_path}")
    if not index_path.exists():
        raise FileNotFoundError(f"index not found: {index_path}")

    bench = json.loads(benchmark_path.read_text(encoding="utf-8"))
    pairs = bench["pairs"]
    gate = bench.get("gate", {}).get("precision_at_1_min", 0.80)

    embedder = make_embedder(backend=backend)
    t0 = time.time()
    hits_at_1 = 0
    hits_at_5 = 0
    mrr_sum = 0.0
    per_pair: list[dict[str, Any]] = []

    with VectorIndex.open(index_path) as idx:
        for i, pair in enumerate(pairs, 1):
            results = idx.search(pair["query"], k=k_max, embedder=embedder)
            keys = [c.retrieval_key() for c, _ in results]
            expected = pair["expected_key"]
            rank: int | None
            if expected in keys:
                rank = keys.index(expected) + 1
                if rank == 1:
                    hits_at_1 += 1
                if rank <= 5:
                    hits_at_5 += 1
                mrr_sum += 1.0 / rank
            else:
                rank = None
            per_pair.append(
                {
                    "index": i - 1,
                    "expected_key": expected,
                    "rank": rank,
                    "hit_at_1": rank == 1,
                }
            )
            if i % 10 == 0:
                _emit_stderr(f"  {i}/{len(pairs)} evaluated...")
    elapsed = time.time() - t0

    n = len(pairs)
    precision_at_1 = hits_at_1 / n if n else 0.0
    precision_at_5 = hits_at_5 / n if n else 0.0
    mrr = mrr_sum / n if n else 0.0
    passed = precision_at_1 >= gate

    return {
        "ok": passed,
        "gate": {"precision_at_1_min": gate},
        "metrics": {
            "precision_at_1": round(precision_at_1, 4),
            "precision_at_5": round(precision_at_5, 4),
            "mrr": round(mrr, 4),
            "hits_at_1": hits_at_1,
            "hits_at_5": hits_at_5,
            "n": n,
        },
        "inputs": {
            "benchmark": str(benchmark_path),
            "index": str(index_path),
            "backend": backend,
            "embedder_dim": embedder.dim,
        },
        "elapsed_seconds": round(elapsed, 3),
        "per_pair": per_pair,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="rag_eval",
        description=(
            "Run the RAG eval benchmark against the committed index. "
            "Reports precision@1, precision@5, MRR; exits 0 when "
            "precision@1 meets the gate (>= 0.80 by default)."
        ),
    )
    parser.add_argument(
        "--benchmark",
        default=str(DEFAULT_BENCHMARK),
        help="Benchmark JSON (default: %(default)s).",
    )
    parser.add_argument(
        "--index",
        default=str(DEFAULT_INDEX),
        help="Index SQLite (default: %(default)s).",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "hash", "sentence-transformers"),
        default="auto",
        help="Embedder backend (default: auto).",
    )
    args = parser.parse_args()

    try:
        payload = evaluate(
            benchmark_path=Path(args.benchmark),
            index_path=Path(args.index),
            backend=args.backend,
        )
    except FileNotFoundError as e:
        _emit_json({"ok": False, "error": str(e)})
        return 2
    except Exception as e:  # pragma: no cover
        _emit_json({"ok": False, "error": f"{type(e).__name__}: {e}"})
        return 3

    _emit_json(payload)
    m = payload["metrics"]
    verdict = "PASS" if payload["ok"] else "FAIL"
    _emit_stderr(
        f"[rag_eval] {verdict}  precision@1={m['precision_at_1']:.3f} "
        f"(>= {payload['gate']['precision_at_1_min']:.2f})  "
        f"precision@5={m['precision_at_5']:.3f}  MRR={m['mrr']:.3f}  "
        f"in {payload['elapsed_seconds']:.2f}s"
    )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
