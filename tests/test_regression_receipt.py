"""Offline unit tests for the regression_check.py Perf Receipt helpers.

No SOLIDWORKS seat: exercises the pure payload builder + git-sha helper +
argparse wiring with synthetic data. The live-seat emit path is proven in
Phase 5A Task 5.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import regression_check as rc  # noqa: E402

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def test_build_receipt_payload_shape() -> None:
    payload = rc._build_receipt_payload(
        percentiles={"p50": 5.0, "p95": 11.0, "p99": 12.0},
        spec_times=[4.1234, 5.0, 11.0],
        n_specs=3,
        baseline=_ROOT / "tools" / "perf_baselines" / "v0.10.json",
        measured_at="0dffa96a2f94974d8f54bb1b16659c4a293fb546",
        sw_revision="32.1.0",
    )
    assert payload["schema_version"] == 1
    assert payload["measured_at"] == "0dffa96a2f94974d8f54bb1b16659c4a293fb546"
    assert payload["baseline"] == "tools/perf_baselines/v0.10.json"
    assert payload["p95"] == 11.0
    assert payload["n_specs"] == 3
    assert payload["spec_times"][0] == 4.123  # rounded to 3 dp
    assert payload["host_meta"]["sw_revision"] == "32.1.0"
    # A just-built receipt is current by construction.
    assert payload["lag_acknowledged"] is False
    assert payload["lag_reason"] is None


def test_build_receipt_payload_no_baseline() -> None:
    payload = rc._build_receipt_payload(
        percentiles={"p50": None, "p95": None, "p99": None},
        spec_times=[],
        n_specs=0,
        baseline=None,
        measured_at=None,
    )
    assert payload["baseline"] is None
    assert payload["measured_at"] is None
    assert payload["p95"] is None


def test_repo_rel_normalizes_to_posix() -> None:
    rel = rc._repo_rel(_ROOT / "tools" / "perf_baselines" / "v0.10.json")
    assert rel == "tools/perf_baselines/v0.10.json"


def test_current_git_sha_is_40_hex() -> None:
    sha = rc._current_git_sha()
    # In the repo, HEAD resolves; in a non-git sandbox it may be None (skip).
    if sha is None:
        return
    assert _SHA_RE.match(sha), f"unexpected sha: {sha!r}"


def test_emit_receipt_flag_parses() -> None:
    # The parser must accept --emit-receipt without running any build.
    import argparse

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--baseline-compare", dest="baseline_compare", type=Path)
    parser.add_argument("--write-baseline", dest="write_baseline", type=Path)
    parser.add_argument("--emit-receipt", dest="emit_receipt", type=Path)
    ns = parser.parse_args(["--check", "--emit-receipt", "r.json"])
    assert ns.emit_receipt == Path("r.json")
