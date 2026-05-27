"""Tests for tools/build_api_index.py (E5.4).

Covers the CLI entry point end-to-end:

* build -> writes an index file + prints JSON stats.
* --verify -> rebuild to tmp, byte-compare to committed copy.
* --verify fails when committed file doesn't exist.
* missing corpus -> exits 2 with a hint.
* determinism: two back-to-back builds produce byte-identical
  output at the same path.

Uses a tiny synthetic corpus (not the committed 149-topic one) so
the test runs in milliseconds.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = REPO_ROOT / "tools" / "build_api_index.py"
COMMITTED_INDEX = (
    REPO_ROOT / "src" / "ai_sw_bridge" / "rag" / "data" / "api_index.sqlite"
)


def _write_corpus(tmp_path: Path, topics: list[dict]) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps(
            {
                "source": str(tmp_path),
                "corpus": "sldworksapiprogguide",
                "topics_count": len(topics),
                "topics": topics,
            }
        ),
        encoding="utf-8",
    )
    return path


def _topic(title: str, text: str, category: str = "Overview") -> dict:
    return {
        "title": title,
        "text": text,
        "code_examples": [],
        "keywords": [],
        "category": category,
        "source": f"{category}/{title}.htm",
    }


def _run(*extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), *extra_args],
        capture_output=True,
        text=True,
    )


# -- build ------------------------------------------------------------------


def test_build_writes_index_and_prints_stats(tmp_path: Path) -> None:
    corpus = _write_corpus(
        tmp_path,
        [
            _topic("Alpha", "Some prose about the Alpha topic."),
            _topic("Beta", "Different prose about Beta."),
        ],
    )
    out = tmp_path / "idx.sqlite"
    result = _run("--corpus", str(corpus), "--output", str(out))
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["stats"]["topics"] == 2
    assert payload["stats"]["chunks"] >= 2
    assert out.exists()
    assert out.stat().st_size > 0


def test_build_fails_on_missing_corpus(tmp_path: Path) -> None:
    out = tmp_path / "idx.sqlite"
    result = _run("--corpus", str(tmp_path / "nope.json"), "--output", str(out))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert "error" in payload
    assert "chm_extract" in payload["hint"]
    assert not out.exists()


# -- determinism ------------------------------------------------------------


def test_two_builds_produce_byte_identical_output(tmp_path: Path) -> None:
    corpus = _write_corpus(
        tmp_path,
        [_topic(f"T{i}", f"Prose for topic {i}") for i in range(10)],
    )
    a = tmp_path / "a.sqlite"
    b = tmp_path / "b.sqlite"
    ra = _run("--corpus", str(corpus), "--output", str(a))
    rb = _run("--corpus", str(corpus), "--output", str(b))
    assert ra.returncode == rb.returncode == 0
    assert a.read_bytes() == b.read_bytes()


# -- verify -----------------------------------------------------------------


def test_verify_passes_when_committed_matches(tmp_path: Path) -> None:
    corpus = _write_corpus(
        tmp_path,
        [_topic("A", "prose A"), _topic("B", "prose B")],
    )
    committed = tmp_path / "committed.sqlite"
    r1 = _run("--corpus", str(corpus), "--output", str(committed))
    assert r1.returncode == 0

    r2 = _run("--corpus", str(corpus), "--output", str(committed), "--verify")
    assert r2.returncode == 0, r2.stdout
    payload = json.loads(r2.stdout)
    assert payload["ok"] is True
    assert payload["determinism_gate"] == "pass"


def test_verify_fails_when_no_committed_file(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path, [_topic("A", "p")])
    missing = tmp_path / "missing.sqlite"
    result = _run("--corpus", str(corpus), "--output", str(missing), "--verify")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "--verify" in payload["hint"]


def test_verify_fails_when_committed_differs(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path, [_topic("A", "p")])
    committed = tmp_path / "committed.sqlite"
    # Plant a "committed" file with arbitrary bytes so the rebuild
    # (which is deterministic) can't match it.
    committed.write_bytes(b"this is not a valid sqlite file")

    result = _run("--corpus", str(corpus), "--output", str(committed), "--verify")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["reason"].startswith("determinism gate failed")
    assert "committed_sha256" in payload
    assert "rebuilt_sha256" in payload


# -- committed index smoke --------------------------------------------------


def test_committed_index_loads_and_has_rows() -> None:
    """End-to-end smoke: the shipped index file loads + has content."""
    if not COMMITTED_INDEX.exists():
        import pytest

        pytest.skip("committed index not present (E5.4 not merged)")
    from ai_sw_bridge.rag import VectorIndex, make_embedder

    emb = make_embedder(backend="hash")
    with VectorIndex.open(COMMITTED_INDEX) as idx:
        stats = idx.stats()
        assert stats["chunks"] > 0
        assert stats["dim"] == emb.dim
        results = idx.search("macro feature edit", k=3, embedder=emb)
    assert len(results) > 0
    assert all(isinstance(r[0].name, str) for r in results)
