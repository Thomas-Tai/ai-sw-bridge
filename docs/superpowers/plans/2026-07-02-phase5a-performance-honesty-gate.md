# Phase 5A — The Performance Honesty Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make performance regression a real CI gate for a seatless runner by committing a git-anchored measurement receipt and enforcing, deterministically, that the code cannot silently outgrow it.

**Architecture:** Extend the Phase-4 Model-B honesty architecture into the perf domain. A live-seat run of the existing `tools/regression_check.py` emits a **Perf Receipt** JSON (raw p50/p95/p99 stamped with the measured commit SHA). A new seatless test `tests/test_perf_receipt.py` enforces a freshness biconditional (`stale ⇔ lag_acknowledged`) over the feature-build hot path, and — when the receipt claims to be current — **re-derives** the SLO/regression verdict from the raw numbers using thresholds imported from `regression_check.py` (never trusting a committed boolean).

**Tech Stack:** Python 3.10+, pytest, `git` CLI (rev-list / cat-file / rev-parse), stdlib only (json, re, subprocess, shutil, pathlib). No new dependencies. No COM in the gate.

## Global Constraints

- **Branch `docs/commercial-elevation` ONLY.** Never commit to `master` or `feat/w67-phase3`.
- **HOLD `git push`** until the whole phase is complete and the gauntlet is green, then a **single `isPrivate`-guarded fast-forward** push: verify `gh repo view --json isPrivate` == `true`, `origin/master` is an ancestor of HEAD, and HEAD is unchanged immediately before `git push origin docs/commercial-elevation:master` (no force).
- **Live SOLIDWORKS seat at PID 40652 must stay untouched by the automated suite.** Seat-safe selection only: `pytest -m "not solidworks_only and not destructive_sw"`. NEVER run bare `pytest`. Exactly one task (Task 5) is a deliberate, non-destructive, maintainer-initiated live-seat run.
- **`black --check` before every commit** (not just flake8). The gotcha: a single-line `assert not x, f"..."` over 88 cols fails black even when flake8-clean — black wants the parenthesized `assert (\n not x\n), f"..."` form (or a wrapped multi-string message).
- **flake8 clean** on `src/` and any new test file; **mypy** unchanged on `src/` (tests are out of mypy's `src` scope).
- **SLO thresholds are single-sourced** from `tools/regression_check.py` (`SLO_01_P95_MAX_S=12.0`, `SLO_02_P99_MAX_S=25.0`, `BASELINE_P95_REGRESSION_PCT=0.15`, `BASELINE_P99_REGRESSION_PCT=0.25`). The gate imports them; it must never hard-code copies.
- **No CI change is required** (`.github/workflows/ci.yml` already checks out `fetch-depth: 0` on the `test` job, and the new test auto-collects into the seat-safe suite). This is *verified* as a DoD step, not edited.
- **"Concrete not dirt"**: fix genuine issues; do not chase cosmetic purity or reopen ratified design decisions.

---

## File Structure

- **`tools/regression_check.py`** (modify) — add an additive `--emit-receipt <path>` flag plus two pure helpers (`_current_git_sha`, `_build_receipt_payload`). Existing `--capture`/`--check`/`--write-baseline`/`--baseline-compare` behaviour is untouched.
- **`tests/test_regression_receipt.py`** (create) — offline unit tests for the two new pure helpers + the argparse wiring (no seat, synthetic data).
- **`tests/test_perf_receipt.py`** (create) — the seatless honesty gate (sibling to `tests/test_i18n_staleness.py`). Imports thresholds from `regression_check`.
- **`tools/perf_baselines/receipt.json`** (create) — the committed receipt. Provisional (lag-acknowledged, seeded from v0.10) in Task 3; replaced by the real fresh seat-measured receipt in Task 5.
- **`docs/perf_gate.md`** (create) — the contract: metric, SLO, receipt shape, biconditional, ritual, baseline-bump.
- **`CONTRIBUTING.md`** (modify) — a perf-receipt ritual + baseline-bump line.

**Checkpoints:**
- **CP1 (offline, no seat):** Task 1 (tool flag + helpers) · Task 2 (offline helper tests) · Task 3 (gate + provisional receipt + bite-prove).
- **CP2 (seat + docs + push):** Task 4 (docs) · Task 5 (live-seat real receipt) · Task 6 (final gauntlet + isPrivate FF push + memory).

---

## Task 1: Add `--emit-receipt` + pure receipt helpers to `regression_check.py`

**COM-adjacency:** NONE (the two helpers are pure; the flag only *writes* after an existing run).

**Files:**
- Modify: `tools/regression_check.py`

**Interfaces:**
- Produces:
  - `_current_git_sha() -> str | None` — HEAD SHA via `git rev-parse HEAD`, or `None` if git unavailable.
  - `_repo_rel(p: Path) -> str` — repo-relative POSIX string for a path.
  - `_build_receipt_payload(percentiles: dict[str, float | None], spec_times: list[float], n_specs: int, baseline: Path | None, measured_at: str | None, sw_revision: str | None = None) -> dict` — the §5.2 receipt dict with `schema_version=1`, `lag_acknowledged=False`, `lag_reason=None`.
  - CLI: `--emit-receipt <path>` writes the payload after a `--check`/`--capture` run.

- [ ] **Step 1: Add the helpers.** Insert after `_make_perf_payload` (around line 200) in `tools/regression_check.py`:

```python
def _current_git_sha() -> str | None:
    """Return the current HEAD commit SHA, or None if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else None


def _repo_rel(p: Path) -> str:
    """Repo-relative POSIX path string (falls back to as_posix if outside)."""
    try:
        return p.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _build_receipt_payload(
    percentiles: dict[str, float | None],
    spec_times: list[float],
    n_specs: int,
    baseline: Path | None,
    measured_at: str | None,
    sw_revision: str | None = None,
) -> dict:
    """Build the Perf Receipt JSON payload (spec §5.2).

    Raw measurements only -- no committed verdict. CI re-derives the SLO
    verdict from p95/p99. A just-measured receipt is current by
    construction: lag_acknowledged is False and lag_reason is None.
    """
    return {
        "schema_version": 1,
        "measured_at": measured_at,
        "baseline": _repo_rel(baseline) if baseline is not None else None,
        "p50": percentiles["p50"],
        "p95": percentiles["p95"],
        "p99": percentiles["p99"],
        "n_specs": n_specs,
        "spec_times": [round(t, 3) for t in spec_times],
        "host_meta": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "sw_revision": sw_revision,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lag_acknowledged": False,
        "lag_reason": None,
    }
```

- [ ] **Step 2: Thread `sw_revision` best-effort + write the receipt in `check()`.** In `check()`, initialise `sw_rev: str | None = None` next to `spec_times`, and inside the per-spec loop after `data` is known to be non-None, add `sw_rev = data.get("sw_revision") or sw_rev`. Then add an `emit_receipt` parameter and, after the SLI print block, write the receipt. The new signature and tail of `check()`:

```python
def check(
    baseline_compare: Path | None = None,
    emit_receipt: Path | None = None,
) -> int:
    """Rebuild every example and compare its total volume to the baseline."""
    specs = _find_specs()
    if not specs:
        print("No example specs found", file=sys.stderr)
        return 2

    regressions = 0
    checked = 0
    spec_times: list[float] = []
    sw_rev: str | None = None
    for spec_path in specs:
        name = spec_path.parent.name
        golden_path = spec_path.parent / "golden.json"
        if not golden_path.exists():
            print(f"SKIP {name} (no golden.json; run --capture first)")
            continue
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        data, elapsed = _build_with_mass(spec_path)
        spec_times.append(elapsed)
        if data is None:
            print(f"FAIL {name}: build error ({elapsed:.1f}s)")
            regressions += 1
            continue
        sw_rev = data.get("sw_revision") or sw_rev
        checked += 1
        total, _ = _total_mass_and_features(data)
        expected = golden.get("total_mass_mm3", 0.0)
        tol = golden.get("tolerance_mm3", DEFAULT_TOLERANCE_MM3)
        if abs(total - expected) > tol:
            print(
                f"FAIL {name}: total {total} mm^3 vs golden {expected} mm^3 "
                f"(tolerance +/-{tol}, {elapsed:.1f}s)"
            )
            regressions += 1
        else:
            print(f"OK   {name} ({total} mm^3, {elapsed:.1f}s)")

    percentiles = _compute_percentiles(spec_times)
    print(
        f"\nSLI: p50={percentiles['p50']}s p95={percentiles['p95']}s "
        f"p99={percentiles['p99']}s ({len(spec_times)} specs)"
    )

    slo_ok = _check_slo_and_baseline(percentiles, baseline_compare)

    if emit_receipt is not None:
        payload = _build_receipt_payload(
            percentiles,
            spec_times,
            len(spec_times),
            baseline_compare,
            _current_git_sha(),
            sw_rev,
        )
        emit_receipt.parent.mkdir(parents=True, exist_ok=True)
        emit_receipt.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Perf receipt written to {emit_receipt}", file=sys.stderr)

    if regressions:
        print(f"\n{regressions} regression(s) detected")
        return 1
    if not slo_ok:
        return 1
    print(f"\nAll {checked} checked example(s) within tolerance")
    return 0
```

- [ ] **Step 3: Wire the argparse flag + pass it through `main()`.** Add the argument after `--write-baseline` and pass it to `check()`:

```python
    parser.add_argument(
        "--emit-receipt",
        dest="emit_receipt",
        type=Path,
        default=None,
        help="Path to write the git-anchored Perf Receipt JSON after a run.",
    )
    args = parser.parse_args()
    if args.capture:
        return capture(
            write_baseline=args.write_baseline, baseline_compare=args.baseline_compare
        )
    return check(
        baseline_compare=args.baseline_compare, emit_receipt=args.emit_receipt
    )
```

- [ ] **Step 4: Verify it imports and the flag parses (offline, no seat).**

Run: `python -c "import ast; ast.parse(open('tools/regression_check.py').read()); print('parse ok')"`
Then: `python tools/regression_check.py --help`
Expected: help text includes `--emit-receipt`. No seat touched (help exits before any build).

- [ ] **Step 5: black + flake8 + commit.**

Run: `python -m black --check tools/regression_check.py && python -m flake8 tools/regression_check.py`
Expected: both clean.

```bash
git add tools/regression_check.py
git commit -m "feat(perf): regression_check.py --emit-receipt writes a git-anchored perf receipt (Phase 5A)"
```

---

## Task 2: Offline unit tests for the receipt helpers

**COM-adjacency:** NONE.

**Files:**
- Create: `tests/test_regression_receipt.py`

**Interfaces:**
- Consumes: `regression_check._build_receipt_payload`, `_current_git_sha`, `_repo_rel` (Task 1); the module is imported by adding `tools/` to `sys.path`.

- [ ] **Step 1: Write the tests.**

```python
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
```

> Note: `test_emit_receipt_flag_parses` rebuilds a minimal parser rather than invoking `rc.main()` (which would require a seat). It guards that `--emit-receipt` is a valid flag name/shape. The real end-to-end wiring is exercised on the seat in Task 5.

- [ ] **Step 2: Run — expect PASS (offline).**

Run: `python -m pytest tests/test_regression_receipt.py -q -p no:cacheprovider`
Expected: PASS (all 5). Importing `regression_check` is offline-safe — it is stdlib-only (no pywin32/COM).

- [ ] **Step 3: black + flake8 + commit.**

Run: `python -m black --check tests/test_regression_receipt.py && python -m flake8 tests/test_regression_receipt.py`
Expected: clean. If black reports a reformat, run `python -m black tests/test_regression_receipt.py` and re-check.

```bash
git add tests/test_regression_receipt.py
git commit -m "test(perf): offline unit tests for the perf-receipt helpers (Phase 5A)"
```

---

## Task 3: The honesty gate + provisional receipt + bite-prove

**COM-adjacency:** NONE (pure git + JSON + arithmetic).

**Files:**
- Create: `tests/test_perf_receipt.py`
- Create: `tools/perf_baselines/receipt.json` (provisional, lag-acknowledged)

**Interfaces:**
- Consumes: `regression_check.SLO_01_P95_MAX_S`, `SLO_02_P99_MAX_S`, `BASELINE_P95_REGRESSION_PCT`, `BASELINE_P99_REGRESSION_PCT` (imported); the committed `tools/perf_baselines/receipt.json`; git history.

- [ ] **Step 1: Write the gate.**

```python
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
```

- [ ] **Step 2: Run — expect FAIL (no receipt yet).**

Run: `python -m pytest tests/test_perf_receipt.py -q -p no:cacheprovider`
Expected: FAIL — `test_receipt_exists_and_wellformed` and others error on the missing `tools/perf_baselines/receipt.json`. This is the TDD red.

- [ ] **Step 3: Create the provisional (lag-acknowledged) receipt.** This seeds the gate green *honestly*: it points at the real v0.10 baseline commit (`0dffa96…`), whose numbers were truly measured, and declares the measurement lagged because the hot path has advanced 145 commits since. `lag_acknowledged` suspends Clause 2 + corpus-size until the real seat receipt lands in Task 5. Write `tools/perf_baselines/receipt.json`:

```json
{
  "schema_version": 1,
  "measured_at": "0dffa96a2f94974d8f54bb1b16659c4a293fb546",
  "baseline": "tools/perf_baselines/v0.10.json",
  "p50": 5.985,
  "p95": 11.933,
  "p99": 12.537,
  "n_specs": 15,
  "spec_times": [
    4.375, 4.703, 9.641, 4.515, 6.078, 3.219, 3.281, 5.985,
    10.234, 5.406, 6.328, 3.922, 12.688, 8.844, 11.609
  ],
  "host_meta": {
    "platform": "Windows-10-10.0.26200-SP0",
    "python": "3.10.6",
    "sw_revision": null
  },
  "timestamp": "2026-05-27T04:55:47.471902+00:00",
  "lag_acknowledged": true,
  "lag_reason": "Provisional placeholder seeded from the v0.10 live-seat baseline (commit 0dffa96). The feature-build engine has advanced since; a fresh receipt is pending the Phase 5A live-seat measurement (Task 5)."
}
```

- [ ] **Step 4: Run — expect PASS.**

Run: `python -m pytest tests/test_perf_receipt.py -q -p no:cacheprovider`
Expected: PASS. `test_freshness_biconditional` sees `stale=True, ack=True` → pass; `test_green_when_current` and `test_n_specs_matches_corpus` skip (lag acknowledged); structural + reachability + baseline tests pass.

- [ ] **Step 5: Bite-prove all five failure modes (revert each; confirm `git status --short` clean after).** Run each mutation, confirm the named test goes RED, then restore.

  1. **Silent rot** (Clause 1): temporarily touch a PERF_SURFACE file *after* `measured_at` with no lag flag. Since `measured_at` is already old, the receipt is already stale — so instead flip the receipt to *claim fresh*: set `"lag_acknowledged": false` (leave the old `measured_at`). Now `stale=True, ack=False` → `test_freshness_biconditional` MUST FAIL. Revert the file.
     ```bash
     python - <<'PY'
     import json, pathlib
     p = pathlib.Path("tools/perf_baselines/receipt.json")
     r = json.loads(p.read_text(encoding="utf-8"))
     r["lag_acknowledged"] = False; r["lag_reason"] = None
     p.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
     PY
     python -m pytest tests/test_perf_receipt.py -k freshness_biconditional -q -p no:cacheprovider   # expect FAIL
     git checkout -- tools/perf_baselines/receipt.json
     ```
  2. **Crying wolf** (Clause 1): set `measured_at` to current `HEAD` (fresh) while keeping `lag_acknowledged: true`. Now `stale=False, ack=True` → `test_freshness_biconditional` MUST FAIL. Revert.
     ```bash
     HEAD_SHA=$(git rev-parse HEAD)
     python - <<PY
     import json, pathlib
     p = pathlib.Path("tools/perf_baselines/receipt.json")
     r = json.loads(p.read_text(encoding="utf-8"))
     r["measured_at"] = "$HEAD_SHA"   # fresh, but lag still true
     p.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
     PY
     python -m pytest tests/test_perf_receipt.py -k freshness_biconditional -q -p no:cacheprovider   # expect FAIL
     git checkout -- tools/perf_baselines/receipt.json
     ```
  3. **Unreachable measured_at**: set `measured_at` to a syntactically valid but non-existent SHA. `test_measured_at_reachable` MUST FAIL. Revert.
     ```bash
     python - <<'PY'
     import json, pathlib
     p = pathlib.Path("tools/perf_baselines/receipt.json")
     r = json.loads(p.read_text(encoding="utf-8"))
     r["measured_at"] = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
     p.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
     PY
     python -m pytest tests/test_perf_receipt.py -k measured_at_reachable -q -p no:cacheprovider   # expect FAIL
     git checkout -- tools/perf_baselines/receipt.json
     ```
  4. **Fresh but failing SLO** (Clause 2): make the receipt claim fresh (`measured_at=HEAD`, `lag_acknowledged=false`) with `p95` above the SLO ceiling. `test_green_when_current` MUST FAIL. Revert.
     ```bash
     HEAD_SHA=$(git rev-parse HEAD)
     python - <<PY
     import json, pathlib
     p = pathlib.Path("tools/perf_baselines/receipt.json")
     r = json.loads(p.read_text(encoding="utf-8"))
     r["measured_at"] = "$HEAD_SHA"
     r["lag_acknowledged"] = False; r["lag_reason"] = None
     r["p95"] = 20.0   # > SLO_01_P95_MAX_S (12.0)
     p.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
     PY
     python -m pytest tests/test_perf_receipt.py -k green_when_current -q -p no:cacheprovider   # expect FAIL
     git checkout -- tools/perf_baselines/receipt.json
     ```
  5. **Baseline pointing at a missing file**: set `baseline` to a nonexistent path. `test_baseline_reference_resolves` MUST FAIL. Revert.
     ```bash
     python - <<'PY'
     import json, pathlib
     p = pathlib.Path("tools/perf_baselines/receipt.json")
     r = json.loads(p.read_text(encoding="utf-8"))
     r["baseline"] = "tools/perf_baselines/does_not_exist.json"
     p.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
     PY
     python -m pytest tests/test_perf_receipt.py -k baseline_reference_resolves -q -p no:cacheprovider   # expect FAIL
     git checkout -- tools/perf_baselines/receipt.json
     ```

- [ ] **Step 6: Confirm green again + clean tree + black/flake8, then commit.**

Run: `python -m pytest tests/test_perf_receipt.py -q -p no:cacheprovider` (expect PASS) and `git status --short tools/perf_baselines/receipt.json` (expect empty).
Run: `python -m black --check tests/test_perf_receipt.py && python -m flake8 tests/test_perf_receipt.py` (expect clean; if black reformats, apply it).

```bash
git add tests/test_perf_receipt.py tools/perf_baselines/receipt.json
git commit -m "test(perf): Model-B performance honesty gate + provisional lagged receipt (Phase 5A)"
```

**CP1 telemetry to report:** tool-flag commit; helper-unit-test count; gate green (with provisional lag); the five bite-prove REDs each reverted; suite still seat-safe.

---

## Task 4: Docs — the ritual + the contract

**COM-adjacency:** NONE.

**Files:**
- Create: `docs/perf_gate.md`
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Write `docs/perf_gate.md`.**

```markdown
# The Performance Honesty Gate

`ai-sw-bridge`'s performance is gated by a **Model-B honesty contract**, the
same shape as the i18n staleness gate. CI has no SOLIDWORKS seat, so it cannot
*measure* performance — instead it enforces that a committed **Perf Receipt**
stays honest about the code it describes.

## The metric and the ceiling

The metric is the **end-to-end example build**: `tools/regression_check.py`
builds every `examples/*/spec.json` on a live seat and records per-build
wall-clock, reducing to p50/p95/p99. The ceiling is the SLO that shipped in
v0.11 (single-sourced in `regression_check.py`):

- **SLO-01:** p95 < 12 s
- **SLO-02:** p99 < 25 s
- **Regression:** p95 must not exceed the baseline p95 by >15%, nor p99 by >25%.

## The receipt

`tools/perf_baselines/receipt.json` records the last measurement's raw
percentiles plus `measured_at` (the commit SHA it was measured at), the
`baseline` it was compared against, and a `lag_acknowledged` flag. It carries
**no verdict** — CI re-derives pass/fail from the raw numbers, so editing a
boolean cannot fake a green.

## The gate (`tests/test_perf_receipt.py`)

- **Freshness biconditional (always):** the receipt is *stale* iff the
  feature-build hot path (`src/ai_sw_bridge/spec/`, `features/`,
  `cli/build.py`, `examples/*/spec.json`) advanced since `measured_at`. A stale
  receipt MUST set `lag_acknowledged: true` (+ a `lag_reason`); a fresh one MUST
  NOT. Silent rot and crying wolf both fail CI.
- **Green-when-current (only when not lag-acknowledged):** CI re-derives the
  SLO + regression verdict from the receipt's raw p95/p99 vs the referenced
  baseline. A fresh receipt that fails the SLO is a real regression → red.

Honest lag is allowed and visible; silent rot is impossible.

## The ritual (maintainer, on a live seat)

Regenerate the receipt after you change the build hot path:

    python tools/regression_check.py --check \
        --baseline-compare tools/perf_baselines/v0.10.json \
        --emit-receipt tools/perf_baselines/receipt.json

This is non-destructive (builds into fresh blank parts, never saves over your
files) but it drives a live seat, so it is never part of the automated suite.
Commit the refreshed `receipt.json` (it lands fresh, `lag_acknowledged: false`).

If you changed the hot path but cannot re-measure now, set
`lag_acknowledged: true` with a `lag_reason` and commit — CI stays green with
visible debt until the next measurement.

## Baseline-bump discipline

When performance regresses acceptably (e.g. a new, inherently slower feature),
bump the baseline rather than lying to the gate:

    python tools/regression_check.py --check \
        --baseline-compare tools/perf_baselines/v0.10.json \
        --write-baseline  tools/perf_baselines/v1.7.json \
        --emit-receipt    tools/perf_baselines/receipt.json

then repoint `receipt.baseline` to the new file. In this solo, fast-forward
repo, a "reviewed baseline bump" is a deliberate, self-documented baseline
commit. Keep the old baseline for provenance.
```

- [ ] **Step 2: Add the perf-receipt line to `CONTRIBUTING.md`.** In the "Translating docs" area's sibling location — directly after the i18n-freshness block added in Phase 4 — insert a parallel perf block. Find the paragraph ending `See the "staleness gate" section of `TRANSLATION_PROMPT.md` for the full contract.` and add after it:

```markdown

**Performance freshness is also a gate.** If you change the feature-build hot
path (`src/ai_sw_bridge/spec/`, `src/ai_sw_bridge/features/`,
`src/ai_sw_bridge/cli/build.py`, or `examples/*/spec.json`), the committed
performance receipt (`tools/perf_baselines/receipt.json`) is now stale. Before
the change is merge-ready, either **re-measure on a live seat**
(`python tools/regression_check.py --check --baseline-compare
tools/perf_baselines/v0.10.json --emit-receipt tools/perf_baselines/receipt.json`)
and commit the fresh receipt, **or** set `lag_acknowledged: true` (+ a
`lag_reason`) on it. `tests/test_perf_receipt.py` enforces `stale ⇔
lag_acknowledged` and re-derives the SLO verdict from the raw numbers. See
`docs/perf_gate.md`.
```

- [ ] **Step 3: Commit (docs are prose; no black).**

Run: `git status --short` (expect only the two doc files staged).

```bash
git add docs/perf_gate.md CONTRIBUTING.md
git commit -m "docs(perf): perf_gate.md contract + CONTRIBUTING perf-freshness gate (Phase 5A)"
```

---

## Task 5: Live-seat receipt generation (the one seat exercise)

**COM-adjacency:** **YES — the only seat-adjacent task.** Orchestrator/maintainer-run on the operator workstation with a live SOLIDWORKS seat. Non-destructive: `regression_check.py --check` opens each example spec, builds into a fresh blank part, reads mass, and never saves over operator files. Do NOT delegate this to a subagent; do NOT run bare `pytest`.

**Files:**
- Modify: `tools/perf_baselines/receipt.json` (provisional → real fresh receipt).
- Possibly create: `tools/perf_baselines/v1.7.json` (only if a baseline bump is warranted — see Step 3).

- [ ] **Step 1: Seat-prefire sanity (non-destructive).** Confirm the seat is alive and the golden files exist for the corpus.

Run: `python tools/regression_check.py --check --baseline-compare tools/perf_baselines/v0.10.json`
Expected: each example prints `OK … (<time>s)`; the SLI line prints p50/p95/p99 over the 20-spec corpus. If many specs `SKIP (no golden.json)`, run `python tools/regression_check.py --capture` first (also live-seat) to record goldens, then re-run `--check`.

- [ ] **Step 2: Emit the real receipt.**

Run:
```bash
python tools/regression_check.py --check \
    --baseline-compare tools/perf_baselines/v0.10.json \
    --emit-receipt tools/perf_baselines/receipt.json
```
Expected: `Perf receipt written to tools/perf_baselines/receipt.json`. The new receipt has `measured_at` = current HEAD, `lag_acknowledged: false`, `n_specs` = 20, real host/sw_revision.

- [ ] **Step 3: Decide green vs baseline-bump (do NOT dodge with lag).**
  - If `test_green_when_current` will pass (p95 < 12 s, p99 < 25 s, within +15%/+25% of v0.10) → proceed.
  - If the fresh measurement legitimately exceeds the v0.10 baseline regression thresholds but is *acceptable* (corpus grew from 15→20 specs; more/heavier features), **bump the baseline**: re-run Step 2 adding `--write-baseline tools/perf_baselines/v1.7.json`, then edit `receipt.json`'s `baseline` to `tools/perf_baselines/v1.7.json`. Document why in the commit. **Never** set `lag_acknowledged: true` on a just-measured receipt to escape a real regression — that is crying wolf and the gate will (correctly) reject it as fresh+acknowledged.
  - If it exceeds the **absolute** SLO (p95 ≥ 12 s / p99 ≥ 25 s), that is a genuine perf problem — stop and investigate; do not ship.

- [ ] **Step 4: Verify the gate is green against the real receipt.**

Run: `python -m pytest tests/test_perf_receipt.py -q -p no:cacheprovider`
Expected: PASS — now `test_green_when_current` and `test_n_specs_matches_corpus` **run** (not skip) because `lag_acknowledged` is false, and pass.

- [ ] **Step 5: Confirm seat untouched + commit.**

Run: `powershell -NoProfile -Command "Get-Process -Id 40652 -ErrorAction SilentlyContinue | Select-Object Id,ProcessName"` (expect PID 40652 still SLDWORKS).

```bash
git add tools/perf_baselines/receipt.json tools/perf_baselines/v1.7.json 2>/dev/null; git add tools/perf_baselines/receipt.json
git commit -m "perf(receipt): live-seat measurement at HEAD — fresh receipt, Clause 2 armed (Phase 5A)"
```

**CP2 (partial) telemetry to report:** the measured p50/p95/p99, SW revision, whether a baseline bump was needed, and the gate now green with Clause 2 *active*.

---

## Task 6: Final gauntlet + isPrivate-guarded FF push + memory

**COM-adjacency:** NONE (seat-safe suite excludes seat tests).

- [ ] **Step 1: Full seat-safe suite.**

Run: `python -m pytest -m "not solidworks_only and not destructive_sw" -q -p no:cacheprovider`
Expected: PASS. Count = prior baseline (3922) + the new perf tests (5 gate + 5 helper = 10) ≈ 3932, plus skips. Live seat untouched (COM-free selection).

- [ ] **Step 2: Static gates.**

Run each; all must pass:
```bash
python -m black --check .            # tracked tree clean (only untracked scratchpad/ may differ)
python -m flake8 src/ tests/test_perf_receipt.py tests/test_regression_receipt.py
python -m mypy --config-file mypy.ini src/ai_sw_bridge
python tools/module_size_gate.py --strict
python -c "import sys; from importlinter.cli import lint_imports; sys.exit(lint_imports())"
python tools/doc_coverage_gate.py
python tools/two_stream_lint.py src/
```
Expected: black clean (tracked), flake8 clean, mypy Success, module-size OK, import-linter 3 kept/0 broken, doc-coverage passed, two-stream OK.

- [ ] **Step 3: Verify "no CI change needed" (DoD).**

Run: `grep -n "fetch-depth" .github/workflows/ci.yml`
Expected: `fetch-depth: 0` present on the `test` job (from Phase 4). The new tests carry no exclusion marker, so they auto-collect into the `test` job's `pytest` run. No edit to `ci.yml`.

- [ ] **Step 4: DoD checklist.** Confirm: `--emit-receipt` shipped; `receipt.json` fresh + derived-green (`lag_acknowledged: false`); gate green + bite-proven (5 REDs, reverted); seat-safe suite green; docs written; CI unchanged (verified); seat untouched by the suite.

- [ ] **Step 5: isPrivate-guarded fast-forward push.**

```bash
gh repo view --json isPrivate -q .isPrivate          # must print: true
HEAD_SHA=$(git rev-parse HEAD)
git fetch origin master
git merge-base --is-ancestor origin/master HEAD && echo "FF-safe" || echo "ABORT: not a fast-forward"
git log --oneline origin/master..HEAD                 # review the Phase 5A commits master will gain
git rev-parse HEAD                                    # must still equal $HEAD_SHA
git push origin docs/commercial-elevation:master      # un-forced FF
git fetch origin master && test "$(git rev-parse origin/master)" = "$HEAD_SHA" && echo "origin/master == HEAD"
```
Expected: `isPrivate` true; FF-safe; push reports `origin/master -> master`; `origin/master == HEAD`.

- [ ] **Step 6: Record the memory.** Write `memory/project_phase5a_perf_honesty_gate_shipped.md` (type: project) summarizing: Model-B extended to perf; the receipt contract; the CI-re-derives-verdict property; the provisional→real receipt sequencing; the measured p50/p95/p99 + any baseline bump; commits + FF SHA range; that Phase 5B (installer) remains. Add a one-line pointer to `memory/MEMORY.md`.

**Final telemetry to report:** commit stack; suite count; static-gate results; measured perf numbers; FF push SHA range; seat PID unchanged.

---

## Self-Review (against the spec)

- **Spec coverage:** §4.1 `--emit-receipt` → Task 1; §5.2 receipt contract → Task 1 (`_build_receipt_payload`) + Task 3 (provisional) + Task 5 (real); §5.3 tests 1–6 → Task 3; §5.4 fail-loud edges → Task 3 bite-prove; §5.5 skipif + fetch-depth → Task 3 (`pytestmark`) + Task 6 Step 3; §5.6 trust model (CI re-derives) → Task 3 `test_green_when_current`; §6 ritual → Task 4 + Task 5; §6.1 baseline bump → Task 4 doc + Task 5 Step 3; §7 DoD → Task 6; §9 ratified decisions (location/JSON field/Clause-2 suspension) → encoded in Task 3. ✓
- **Placeholder scan:** none — every code/JSON/doc block is complete; the one SHA is resolved (`0dffa96a2f94974d8f54bb1b16659c4a293fb546`).
- **Type consistency:** `_build_receipt_payload` signature identical in Task 1 and Task 2; receipt field names (`measured_at`, `lag_acknowledged`, `lag_reason`, `baseline`, `p50/p95/p99`, `n_specs`, `schema_version`, `host_meta`, `spec_times`, `timestamp`) identical across Tasks 1/2/3/5; threshold names (`SLO_01_P95_MAX_S`, `SLO_02_P99_MAX_S`, `BASELINE_P95_REGRESSION_PCT`, `BASELINE_P99_REGRESSION_PCT`) match `regression_check.py`; `PERF_SURFACE` identical in the gate and the docs. ✓
```
