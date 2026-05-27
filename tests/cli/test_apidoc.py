"""Tests for ai_sw_bridge.cli.apidoc (E5.5, spec.md §4.6).

Covers all five subcommands end-to-end against a tiny tmp_path
index (built via VectorIndex.create + HashEmbedder) so the test
matrix doesn't depend on the committed 2 MB blob. A smoke test at
the end exercises the real committed index to catch drift between
the CLI and the shipped artifact.

Two-stream contract: every successful run emits JSON on stdout and
no JSON on stderr. Subprocess-invocation tests assert stdout
parses as JSON (and stderr doesn't).
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


REPO_ROOT = Path(__file__).resolve().parents[2]
APIDOC_MODULE = "ai_sw_bridge.cli.apidoc"


def _chunk(
    name: str,
    *,
    interface: str = "Overview",
    description: str = "prose goes here",
    example_code: str | None = None,
    chunk_index: int = 0,
) -> ApiChunk:
    return ApiChunk(
        chunk_type="topic",
        corpus="sldworksapiprogguide",
        interface=interface,
        name=name,
        signature=None,
        description=description,
        example_code=example_code,
        chm_anchor=f"{interface}/{name}.htm",
        text_for_embedding=f"[{interface}]\n{name}\n{description}",
        chunk_index=chunk_index,
        keywords=(),
    )


@pytest.fixture
def idx_path(tmp_path: Path) -> Path:
    """Build a tiny index and return its path.

    Uses the default HashEmbedder dim (256) so subprocess runs of the
    CLI -- which default to ``make_embedder('auto')`` producing
    256-dim vectors -- match the stored embeddings.
    """
    emb = HashEmbedder()  # default dim = 256
    chunks = [
        _chunk("Alpha", description="first topic about alpha concepts"),
        _chunk("Beta", description="second topic about beta concepts"),
        _chunk(
            "Gamma",
            interface="Misc",
            description="third topic",
            example_code="Dim x As Integer",
        ),
    ]
    path = tmp_path / "idx.sqlite"
    with VectorIndex.create(path, emb.dim) as idx:
        idx.build(chunks, emb)
    return path


def _run(
    *extra_args: str,
    index_path: Path | None = None,
) -> subprocess.CompletedProcess:
    argv = [sys.executable, "-m", APIDOC_MODULE]
    if index_path is not None:
        argv.extend(["--index", str(index_path)])
    argv.extend(extra_args)
    return subprocess.run(argv, capture_output=True, text=True)


# -- top-level --help -------------------------------------------------------


def test_help_lists_all_five_subcommands() -> None:
    result = _run("--help")
    assert result.returncode == 0
    # argparse emits the subcommand names in the usage banner.
    for sub in ("search", "detail", "members", "examples", "enum"):
        assert sub in result.stdout


def test_help_marks_experimental_tier() -> None:
    result = _run("--help")
    assert "[experimental]" in result.stdout


# -- search -----------------------------------------------------------------


def test_search_emits_json_hits(idx_path: Path) -> None:
    result = _run("search", "alpha", "-k", "2", index_path=idx_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["query"] == "alpha"
    assert 1 <= len(payload["hits"]) <= 2
    for hit in payload["hits"]:
        assert "score" in hit
        assert "chunk" in hit
        assert hit["chunk"]["retrieval_key"]


def test_search_k_default_returns_results(idx_path: Path) -> None:
    result = _run("search", "anything", index_path=idx_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert len(payload["hits"]) >= 1


def test_search_corpus_filter_narrows_results(idx_path: Path) -> None:
    result = _run(
        "--corpus",
        "sldworksapiprogguide",
        "search",
        "anything",
        index_path=idx_path,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    for hit in payload["hits"]:
        assert hit["chunk"]["corpus"] == "sldworksapiprogguide"


# -- detail -----------------------------------------------------------------


def test_detail_returns_full_chunk(idx_path: Path) -> None:
    key = "sldworksapiprogguide:Overview:Alpha:0"
    result = _run("detail", key, index_path=idx_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["chunk"]["name"] == "Alpha"
    assert payload["chunk"]["retrieval_key"] == key


def test_detail_missing_key_rc3(idx_path: Path) -> None:
    result = _run("detail", "sldworksapiprogguide:NoSuch:Topic:0", index_path=idx_path)
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["reason"] == "not_found"
    assert "no chunk" in result.stderr


# -- members ----------------------------------------------------------------


def test_members_lists_interfaces(idx_path: Path) -> None:
    result = _run("members", index_path=idx_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert set(payload["interfaces"]) == {"Overview", "Misc"}


def test_members_with_interface_lists_chunk_names(idx_path: Path) -> None:
    result = _run("members", "--interface", "Overview", index_path=idx_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    names = {m["name"] for m in payload["members"]}
    assert names == {"Alpha", "Beta"}


# -- examples ---------------------------------------------------------------


def test_examples_returns_chunks_with_code(idx_path: Path) -> None:
    result = _run("examples", "--limit", "5", index_path=idx_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["examples"][0]["name"] == "Gamma"
    assert "Dim x As Integer" in payload["examples"][0]["example_code"]


# -- enum -------------------------------------------------------------------


def test_enum_emits_corpus_missing_payload(idx_path: Path) -> None:
    result = _run("enum", "swEndConditions_e", index_path=idx_path)
    # rc=0 (subcommand ran fine); the "not implemented" state is in
    # the JSON payload, not the exit code.
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["reason"] == "enum_corpus_missing"
    assert payload["enum_name"] == "swEndConditions_e"
    assert "sldworksapi" in payload["hint"]
    assert "enum" in result.stderr


# -- error paths ------------------------------------------------------------


def test_missing_index_rc2(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.sqlite"
    result = _run("search", "anything", index_path=missing)
    assert result.returncode == 2
    assert "index not found" in result.stderr


# -- two-stream contract ----------------------------------------------------


def test_search_stdout_is_valid_json_no_json_on_stderr(idx_path: Path) -> None:
    result = _run("search", "alpha", index_path=idx_path)
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, dict)
    # stderr should carry zero parseable JSON objects. If any line
    # looks like a JSON object, the two-stream contract is violated.
    for line in result.stderr.splitlines():
        stripped = line.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            pytest.fail(f"JSON leaked onto stderr: {line!r}")


# -- committed index smoke --------------------------------------------------


def test_search_committed_index_smoke() -> None:
    """End-to-end: the CLI queries the committed 2 MB index."""
    committed = REPO_ROOT / "src" / "ai_sw_bridge" / "rag" / "data" / "api_index.sqlite"
    if not committed.exists():
        pytest.skip("committed index not present (E5.4 not merged)")
    result = _run("search", "early binding", "-k", "3")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["count"] >= 1
    assert any("Early" in h["chunk"]["name"] for h in payload["hits"])
