"""Tests for tools/rag_eval.py (E5.6, audit_review.md §2.8).

Covers the eval harness CLI + the underlying evaluate() helper:

* evaluate() returns precision@1 / precision@5 / MRR metrics and
  honors the precision@1 gate from the benchmark JSON.
* CLI exits 0 on gate pass, 1 on fail, 2 on missing inputs.
* CLI prints JSON to stdout (two-stream contract) and the
  pass/fail verdict to stderr.
* Per-pair payload carries rank + hit_at_1 for every query.

Uses a tiny synthetic benchmark + index so the test runs in
milliseconds and doesn't depend on the committed 2 MB index.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ai_sw_bridge.rag.corpus import ApiChunk
from ai_sw_bridge.rag.embed import HashEmbedder
from ai_sw_bridge.rag.index import VectorIndex


REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_SCRIPT = REPO_ROOT / "tools" / "rag_eval.py"


def _chunk(
    name: str,
    *,
    description: str,
    chunk_index: int = 0,
) -> ApiChunk:
    return ApiChunk(
        chunk_type="topic",
        corpus="sldworksapiprogguide",
        interface="Overview",
        name=name,
        signature=None,
        description=description,
        example_code=None,
        chm_anchor=f"Overview/{name}.htm",
        text_for_embedding=f"[Overview]\n{name}\n{description}",
        chunk_index=chunk_index,
        keywords=(),
    )


def _build_index(path: Path, chunks: list[ApiChunk]) -> HashEmbedder:
    emb = HashEmbedder()
    with VectorIndex.create(path, emb.dim) as idx:
        idx.build(chunks, emb)
    return emb


def _write_benchmark(
    path: Path,
    pairs: list[dict],
    *,
    gate: float = 0.80,
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "corpus": "sldworksapiprogguide",
                "pairs_count": len(pairs),
                "gate": {"precision_at_1_min": gate},
                "pairs": pairs,
            }
        ),
        encoding="utf-8",
    )


def _run(
    benchmark_path: Path,
    index_path: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(EVAL_SCRIPT),
            "--benchmark",
            str(benchmark_path),
            "--index",
            str(index_path),
            "--backend",
            "hash",
            *extra_args,
        ],
        capture_output=True,
        text=True,
    )


# -- evaluate() helper ------------------------------------------------------


def test_evaluate_reports_metrics(tmp_path: Path) -> None:
    # Three chunks with distinctive descriptions. The query reuses
    # the source chunk's text so the hash embedder ranks it first.
    chunks = [
        _chunk("Alpha", description="alpha electroencephalogram neurofeedback"),
        _chunk("Beta", description="beta magnetohydrodynamic plasma"),
        _chunk("Gamma", description="gamma crystallography diffraction"),
    ]
    idx_path = tmp_path / "idx.sqlite"
    _build_index(idx_path, chunks)

    bench_path = tmp_path / "bench.json"
    _write_benchmark(
        bench_path,
        [
            {
                "query": "alpha electroencephalogram neurofeedback",
                "expected_key": "sldworksapiprogguide:Overview:Alpha:0",
            },
            {
                "query": "beta magnetohydrodynamic plasma",
                "expected_key": "sldworksapiprogguide:Overview:Beta:0",
            },
            {
                "query": "gamma crystallography diffraction",
                "expected_key": "sldworksapiprogguide:Overview:Gamma:0",
            },
        ],
    )

    # Import evaluate() lazily (tools/ isn't a package).
    import importlib.util

    spec = importlib.util.spec_from_file_location("rag_eval", EVAL_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    report = mod.evaluate(
        benchmark_path=bench_path, index_path=idx_path, backend="hash"
    )
    assert report["ok"] is True
    assert report["metrics"]["precision_at_1"] == 1.0
    assert report["metrics"]["precision_at_5"] == 1.0
    assert report["metrics"]["mrr"] == 1.0
    assert report["metrics"]["n"] == 3
    assert len(report["per_pair"]) == 3
    assert all(p["hit_at_1"] for p in report["per_pair"])


def test_evaluate_gate_fails_when_precision_low(tmp_path: Path) -> None:
    # Three chunks; one query points at a chunk whose description
    # doesn't match the query text -> rank != 1 -> precision@1 = 2/3.
    chunks = [
        _chunk("Alpha", description="alpha electroencephalogram neurofeedback"),
        _chunk("Beta", description="beta magnetohydrodynamic plasma"),
        _chunk("Gamma", description="gamma crystallography diffraction"),
    ]
    idx_path = tmp_path / "idx.sqlite"
    _build_index(idx_path, chunks)

    bench_path = tmp_path / "bench.json"
    _write_benchmark(
        bench_path,
        [
            {
                "query": "alpha electroencephalogram neurofeedback",
                "expected_key": "sldworksapiprogguide:Overview:Alpha:0",
            },
            {
                "query": "beta magnetohydrodynamic plasma",
                "expected_key": "sldworksapiprogguide:Overview:Beta:0",
            },
            {
                # This query is unrelated to Gamma; the expected chunk
                # won't be at rank 1.
                "query": "rhinoceros hippopotamus crocodile",
                "expected_key": "sldworksapiprogguide:Overview:Gamma:0",
            },
        ],
    )

    import importlib.util

    spec = importlib.util.spec_from_file_location("rag_eval", EVAL_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    report = mod.evaluate(
        benchmark_path=bench_path, index_path=idx_path, backend="hash"
    )
    # precision@1 = 2/3 ~ 0.667, gate is 0.80 -> fail.
    assert report["ok"] is False
    assert report["metrics"]["precision_at_1"] == pytest.approx(2 / 3, abs=1e-3)


# -- CLI --------------------------------------------------------------------


def test_cli_rc0_on_pass(tmp_path: Path) -> None:
    chunks = [
        _chunk("Alpha", description="alpha electroencephalogram neurofeedback"),
    ]
    idx_path = tmp_path / "idx.sqlite"
    _build_index(idx_path, chunks)
    bench_path = tmp_path / "bench.json"
    _write_benchmark(
        bench_path,
        [
            {
                "query": "alpha electroencephalogram neurofeedback",
                "expected_key": "sldworksapiprogguide:Overview:Alpha:0",
            }
        ],
    )
    result = _run(bench_path, idx_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "PASS" in result.stderr


def test_cli_rc1_on_gate_fail(tmp_path: Path) -> None:
    chunks = [
        _chunk("Alpha", description="alpha electroencephalogram neurofeedback"),
        _chunk("Beta", description="beta magnetohydrodynamic plasma"),
    ]
    idx_path = tmp_path / "idx.sqlite"
    _build_index(idx_path, chunks)
    bench_path = tmp_path / "bench.json"
    # One pair is wrong -> precision@1 = 0.5, gate is 0.80 -> rc=1.
    _write_benchmark(
        bench_path,
        [
            {
                "query": "alpha electroencephalogram neurofeedback",
                "expected_key": "sldworksapiprogguide:Overview:Alpha:0",
            },
            {
                "query": "rhinoceros hippopotamus",
                "expected_key": "sldworksapiprogguide:Overview:Beta:0",
            },
        ],
    )
    result = _run(bench_path, idx_path)
    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "FAIL" in result.stderr


def test_cli_rc2_on_missing_index(tmp_path: Path) -> None:
    bench_path = tmp_path / "bench.json"
    _write_benchmark(bench_path, [])
    missing = tmp_path / "nope.sqlite"
    result = _run(bench_path, missing)
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert "index not found" in payload["error"]


def test_cli_rc2_on_missing_benchmark(tmp_path: Path) -> None:
    chunks = [_chunk("Alpha", description="alpha something")]
    idx_path = tmp_path / "idx.sqlite"
    _build_index(idx_path, chunks)
    missing_bench = tmp_path / "nope.json"
    result = _run(missing_bench, idx_path)
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert "benchmark not found" in payload["error"]


def test_cli_two_stream_contract(tmp_path: Path) -> None:
    """stdout is JSON, stderr carries no JSON."""
    chunks = [
        _chunk("Alpha", description="alpha electroencephalogram neurofeedback"),
    ]
    idx_path = tmp_path / "idx.sqlite"
    _build_index(idx_path, chunks)
    bench_path = tmp_path / "bench.json"
    _write_benchmark(
        bench_path,
        [
            {
                "query": "alpha electroencephalogram neurofeedback",
                "expected_key": "sldworksapiprogguide:Overview:Alpha:0",
            }
        ],
    )
    result = _run(bench_path, idx_path)
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, dict)
    for line in result.stderr.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed_line = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        # json.loads happily parses numbers + strings; only fail on
        # objects/arrays which would indicate a structured leak.
        if isinstance(parsed_line, (dict, list)):
            pytest.fail(f"JSON leaked onto stderr: {line!r}")


# -- committed benchmark + index smoke --------------------------------------


def test_committed_benchmark_passes_gate() -> None:
    """End-to-end: the shipped benchmark + index pass the 0.80 gate."""
    committed_idx = (
        REPO_ROOT / "src" / "ai_sw_bridge" / "rag" / "data" / "api_index.sqlite"
    )
    committed_bench = REPO_ROOT / "tools" / "rag_eval_benchmark.json"
    if not committed_idx.exists() or not committed_bench.exists():
        pytest.skip("committed index/benchmark not present (E5.4/E5.6 not merged)")
    result = subprocess.run(
        [
            sys.executable,
            str(EVAL_SCRIPT),
            "--benchmark",
            str(committed_bench),
            "--index",
            str(committed_idx),
            "--backend",
            "hash",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["metrics"]["precision_at_1"] >= 0.80
