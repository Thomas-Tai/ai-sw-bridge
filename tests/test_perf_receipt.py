"""Model-B performance honesty gate: the code cannot silently outgrow its
last live-seat measurement.

The Perf Receipt (tools/perf_baselines/receipt.json) records p50/p95/p99 of
the end-to-end example build, stamped with the commit SHA it was measured at.
This seatless gate enforces:
  - Clause 1 (always): stale(receipt) <=> receipt.lag_acknowledged, where
    stale := the feature-build hot path (PERF_SURFACE) advanced since
    measured_at.
  - Clause 2 (only when NOT lag-acknowledged): the SLO/regression verdict,
    RE-DERIVED here from the receipt's raw p95/p99 vs the referenced baseline
    using thresholds IMPORTED from regression_check.py -- a committed boolean
    is never trusted.
Structural checks + Clause 1 apply always; Clause 2 + the corpus-size check
suspend under acknowledged lag (numbers admittedly stale). CI can't measure
perf (no seat); this makes the *documentation* of perf tamper-evident.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import regression_check as rc  # noqa: E402

RECEIPT_PATH = "tools/perf_baselines/receipt.json"

# The feature-build hot path: a change here can move build latency. Generated
# golden*.json outputs are deliberately excluded (they are results, not inputs).
PERF_SURFACE = (
    "src/ai_sw_bridge/spec",
    "src/ai_sw_bridge/features",
    "src/ai_sw_bridge/cli/build.py",
    ":(glob)examples/*/spec.json",
)

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True)


def _git_available() -> bool:
    if shutil.which("git") is None:
        return False
    return _git("rev-parse", "--git-dir").returncode == 0


def _load_receipt() -> dict:
    return json.loads((_ROOT / RECEIPT_PATH).read_text(encoding="utf-8"))


def _stale(measured_at: str) -> bool:
    """True if PERF_SURFACE advanced since measured_at (receipt is stale)."""
    out = _git("rev-list", f"{measured_at}..HEAD", "--", *PERF_SURFACE)
    return bool(out.stdout.strip())


pytestmark = pytest.mark.skipif(
    not _git_available(),
    reason="git history unavailable (shallow/no-git); CI runs with fetch-depth:0",
)


def test_receipt_exists_and_wellformed() -> None:
    r = _load_receipt()
    assert r.get("schema_version") == 1, "receipt schema_version must be 1"
    for key in (
        "measured_at",
        "baseline",
        "p50",
        "p95",
        "p99",
        "n_specs",
        "host_meta",
        "lag_acknowledged",
    ):
        assert key in r, f"receipt missing required field: {key}"
    assert isinstance(r["measured_at"], str) and _SHA_RE.match(
        r["measured_at"]
    ), "measured_at must be a git SHA"
    for pk in ("p50", "p95", "p99"):
        assert isinstance(r[pk], (int, float)), f"{pk} must be numeric"
    assert isinstance(r["lag_acknowledged"], bool)
    if r["lag_acknowledged"]:
        assert r.get(
            "lag_reason"
        ), "lag_acknowledged=true requires a non-empty lag_reason"


def test_measured_at_reachable() -> None:
    r = _load_receipt()
    assert (
        _git("cat-file", "-e", r["measured_at"]).returncode == 0
    ), f"measured_at {r['measured_at']} is not in git history (rebase/forged?)"


def test_baseline_reference_resolves() -> None:
    r = _load_receipt()
    bp = _ROOT / r["baseline"]
    assert bp.is_file(), f"receipt baseline {r['baseline']} missing on disk"
    b = json.loads(bp.read_text(encoding="utf-8"))
    for pk in ("p95", "p99"):
        assert isinstance(b.get(pk), (int, float)), f"baseline missing numeric {pk}"


def test_freshness_biconditional() -> None:
    r = _load_receipt()
    stale = _stale(r["measured_at"])
    ack = bool(r["lag_acknowledged"])
    assert stale == ack, (
        f"perf receipt: stale={stale} but lag_acknowledged={ack} — a stale "
        f"measurement must set lag_acknowledged (+reason); a fresh one must not."
    )


def test_green_when_current() -> None:
    r = _load_receipt()
    if r["lag_acknowledged"]:
        pytest.skip("lag acknowledged — Clause 2 suspended (numbers admittedly stale)")
    p95 = r["p95"]
    p99 = r["p99"]
    assert p95 < rc.SLO_01_P95_MAX_S, f"SLO-01: p95 {p95}s >= {rc.SLO_01_P95_MAX_S}s"
    assert p99 < rc.SLO_02_P99_MAX_S, f"SLO-02: p99 {p99}s >= {rc.SLO_02_P99_MAX_S}s"
    b = json.loads((_ROOT / r["baseline"]).read_text(encoding="utf-8"))
    assert p95 <= b["p95"] * (
        1 + rc.BASELINE_P95_REGRESSION_PCT
    ), f"p95 regression: {p95}s vs baseline {b['p95']}s"
    assert p99 <= b["p99"] * (
        1 + rc.BASELINE_P99_REGRESSION_PCT
    ), f"p99 regression: {p99}s vs baseline {b['p99']}s"


def test_n_specs_matches_corpus() -> None:
    r = _load_receipt()
    if r["lag_acknowledged"]:
        pytest.skip("lag acknowledged — corpus-size check suspended (corpus may grow)")
    on_disk = len(list((_ROOT / "examples").glob("*/spec.json")))
    assert (
        r["n_specs"] == on_disk
    ), f"receipt n_specs {r['n_specs']} != corpus size {on_disk}"
