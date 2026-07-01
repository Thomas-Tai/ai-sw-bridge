# Phase 0 — Foundation & Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pour the load-bearing concrete — the CI invariants and frozen contracts that every later phase stands on — so the degraded state becomes un-mergeable, without touching the COM engine.

**Architecture:** Additive guardrails only. New gate scripts under `tools/`, new tests under `tests/`, small edits to `.github/workflows/ci.yml`, `mypy.ini`, and docs. No `src/` behavior changes. Every gate follows the existing precedent (`tools/doc_coverage_gate.py`, `tools/two_stream_lint.py` — plain-Python scripts run as CI steps; `tests/test_readme_counts.py` — derive-from-code assertions).

**Tech Stack:** Python 3.10+, pytest, black 25.12.0, flake8, mypy 2.1.0, import-linter, GitHub Actions (`windows-2025`, matrix 3.10/3.12/3.14).

**Spec:** `docs/superpowers/specs/2026-07-01-commercial-google-standard-elevation-design.md` §7.

## Global Constraints

- **No `src/` behavior change.** Phase 0 adds guardrails and docs only; the COM engine is untouched.
- **Two-stream contract:** gate scripts print human text to **stderr** on failure, machine output to **stdout**; never both (enforced by `tools/two_stream_lint.py`).
- **black==25.12.0, `target-version=["py310"]`** — every new `.py` must pass `black --check .`.
- **flake8 to zero** on `src/`; new `tools/` and `tests/` files must not introduce F/E4xx/E7xx violations.
- **New modules ≤ 800 hand-written LOC** (the budget this phase installs).
- **Absolute imports in new modules** (no `from .x import y`) — Appendix A.1 of the spec.
- **Commit style:** short imperative, conventional-commit prefix (`feat:`/`test:`/`docs:`/`ci:`/`chore:`); **no co-author trailers**.
- **Baseline:** branch off `origin/master` @ `ee8ada4` (v1.7.0). The current line — NOT local `master` (stale).

---

## Task Group A — Module-size budget gate

**Rationale:** No CI check caps module size today; `builder.py` is 3,335 LOC and 10 `src/` modules exceed 800. Install a ratchet that (a) blocks any *new* module over 800 LOC and (b) freezes today's offenders at their current size (shrink-only), in **warn mode** for Phase 0.

### Task A1: The `module_size_gate.py` tool + its test

**Files:**
- Create: `tools/module_size_gate.py`
- Create: `tools/module_size_baseline.json`
- Create: `tests/test_module_size_gate.py`

**Interfaces:**
- Produces: `tools/module_size_gate.py` with `count_loc(path: Path) -> int`, `scan(root: Path) -> dict[str, int]`, `load_baseline() -> dict[str, int]`, `check(scan_result, baseline, *, ceiling=800, warn=True) -> list[str]` (returns violation messages; empty = pass), and `main(argv=None) -> int`. CLI flags: `--update-baseline` (rewrite the JSON), `--strict` (blocking instead of warn).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_module_size_gate.py
"""Guardrail-for-the-guardrail: the module-size gate's own logic."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "module_size_gate", _ROOT / "tools" / "module_size_gate.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_new_module_over_ceiling_is_a_violation() -> None:
    scan = {"src/ai_sw_bridge/brand_new_huge.py": 900}
    baseline: dict[str, int] = {}
    violations = gate.check(scan, baseline, ceiling=800)
    assert any("brand_new_huge.py" in v for v in violations)


def test_grandfathered_file_may_not_grow() -> None:
    scan = {"src/ai_sw_bridge/spec/builder.py": 3400}
    baseline = {"src/ai_sw_bridge/spec/builder.py": 3335}
    violations = gate.check(scan, baseline, ceiling=800)
    assert any("builder.py" in v and "grew" in v for v in violations)


def test_grandfathered_file_shrinking_is_ok() -> None:
    scan = {"src/ai_sw_bridge/spec/builder.py": 3000}
    baseline = {"src/ai_sw_bridge/spec/builder.py": 3335}
    assert gate.check(scan, baseline, ceiling=800) == []


def test_new_small_module_is_ok() -> None:
    scan = {"src/ai_sw_bridge/tiny.py": 120}
    assert gate.check(scan, {}, ceiling=800) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_module_size_gate.py -v`
Expected: FAIL — `tools/module_size_gate.py` does not exist (import error).

- [ ] **Step 3: Write the tool**

```python
# tools/module_size_gate.py
#!/usr/bin/env python3
"""Module-size budget gate.

New hand-written ``src/`` modules must stay <= CEILING (800) lines. Modules
already over budget are grandfathered in ``module_size_baseline.json`` and may
only SHRINK (a ratchet). Generated files (header ``DO NOT HAND-EDIT``) are
exempt.

Warn mode (default): prints violations, exits 0. --strict: exits 1 on any
violation. --update-baseline: rewrites the baseline from the current tree.

Run from repo root: python tools/module_size_gate.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
BASELINE_PATH = REPO_ROOT / "tools" / "module_size_baseline.json"
CEILING = 800
_GENERATED_MARKER = "DO NOT HAND-EDIT"


def count_loc(path: Path) -> int:
    """Physical line count of a file (matches ``wc -l`` semantics closely)."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def _is_generated(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return False
    return _GENERATED_MARKER in head


def scan(root: Path = SRC) -> dict[str, int]:
    """Map repo-relative path -> LOC for every non-generated ``*.py`` under root."""
    result: dict[str, int] = {}
    for py in sorted(root.rglob("*.py")):
        if "__pycache__" in py.parts or _is_generated(py):
            continue
        result[py.relative_to(REPO_ROOT).as_posix()] = count_loc(py)
    return result


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def check(
    scan_result: dict[str, int],
    baseline: dict[str, int],
    *,
    ceiling: int = CEILING,
) -> list[str]:
    """Return a list of violation strings (empty == pass)."""
    violations: list[str] = []
    for path, loc in sorted(scan_result.items()):
        base = baseline.get(path)
        if base is None:
            if loc > ceiling:
                violations.append(
                    f"{path}: NEW module is {loc} LOC (> {ceiling} ceiling). "
                    f"Split it, or add an explicit waiver via --update-baseline "
                    f"with a rationale in the PR."
                )
        elif loc > base:
            violations.append(
                f"{path}: grew {base} -> {loc} LOC. Grandfathered modules are "
                f"shrink-only; move new code into a focused module."
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Module-size budget gate")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    current = scan()
    if args.update_baseline:
        over = {p: n for p, n in current.items() if n > CEILING}
        BASELINE_PATH.write_text(
            json.dumps(over, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"baseline updated: {len(over)} grandfathered modules", file=sys.stderr)
        return 0

    violations = check(current, load_baseline())
    if not violations:
        print("module-size gate: OK", file=sys.stderr)
        return 0
    print("module-size gate violations:", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_module_size_gate.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Generate the baseline and format**

Run:
```bash
python tools/module_size_gate.py --update-baseline
python tools/module_size_gate.py   # should print "module-size gate: OK"
black tools/module_size_gate.py tests/test_module_size_gate.py
flake8 tools/module_size_gate.py tests/test_module_size_gate.py
```
Expected: the baseline lists ~10 modules (`spec/builder.py` 3335, `sw_types.py` excluded as generated, etc.); the second run prints `OK`; black/flake8 clean. Verify `sw_types.py` is NOT in the baseline (it carries the generated marker).

- [ ] **Step 6: Commit**

```bash
git add tools/module_size_gate.py tools/module_size_baseline.json tests/test_module_size_gate.py
git commit -m "feat(ci): module-size budget gate (warn mode) with shrink-only baseline"
```

### Task A2: Wire the gate into CI (warn mode)

**Files:**
- Modify: `.github/workflows/ci.yml` (after the "Two-stream contract lint" step, ~line 71)

- [ ] **Step 1: Add the CI step**

Insert after the `Two-stream contract lint` step:
```yaml
      - name: Module-size budget gate (warn)
        # Warn-only in Phase 0: prints modules that grew past their baseline or
        # new modules over the 800-LOC ceiling, but does not fail the build.
        # Promoted to --strict in Phase 3 once builder.py is decomposed.
        run: python tools/module_size_gate.py
```

- [ ] **Step 2: Verify locally the command exits 0**

Run: `python tools/module_size_gate.py; echo "exit=$?"`
Expected: `module-size gate: OK` and `exit=0`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run module-size budget gate in warn mode"
```

---

## Task Group B — Coverage ratchet + per-package floors

**Rationale:** CI uses a fixed `--cov-fail-under=60` (measured 64% at v1.5.0) with no per-package floor. Replace with a ratchet (never-decrease, with tolerance) and higher floors on the correctness-critical packages `spec/`, `features/`, `errors/`.

### Task B1: The coverage-gate tool + baseline + test

**Files:**
- Create: `tools/coverage_gate.py`
- Create: `tools/coverage_baseline.json`
- Create: `tests/test_coverage_gate.py`

**Interfaces:**
- Consumes: a `coverage.json` (produced by `coverage json`) with `.totals.percent_covered` and `.files[path].summary.percent_covered`.
- Produces: `evaluate(cov_json: dict, baseline: dict, *, tolerance=1.0, package_floors: dict[str,float]) -> list[str]` (violations; empty == pass); `main(argv=None) -> int` with `--update-baseline`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coverage_gate.py
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "coverage_gate", _ROOT / "tools" / "coverage_gate.py"
)
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

_FLOORS = {"src/ai_sw_bridge/spec/": 85.0}


def _cov(total: float, files: dict[str, float]) -> dict:
    return {
        "totals": {"percent_covered": total},
        "files": {p: {"summary": {"percent_covered": v}} for p, v in files.items()},
    }


def test_total_drop_beyond_tolerance_fails() -> None:
    cov = _cov(60.0, {})
    baseline = {"__total__": 64.0}
    violations = cg.evaluate(cov, baseline, tolerance=1.0, package_floors={})
    assert any("total coverage" in v for v in violations)


def test_total_within_tolerance_ok() -> None:
    cov = _cov(63.2, {})
    baseline = {"__total__": 64.0}
    assert cg.evaluate(cov, baseline, tolerance=1.0, package_floors={}) == []


def test_package_below_floor_fails() -> None:
    cov = _cov(64.0, {"src/ai_sw_bridge/spec/builder.py": 80.0})
    violations = cg.evaluate(cov, {"__total__": 64.0}, package_floors=_FLOORS)
    assert any("spec/" in v and "floor" in v for v in violations)


def test_package_meets_floor_ok() -> None:
    cov = _cov(64.0, {"src/ai_sw_bridge/spec/builder.py": 90.0})
    assert cg.evaluate(cov, {"__total__": 64.0}, package_floors=_FLOORS) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coverage_gate.py -v`
Expected: FAIL — `tools/coverage_gate.py` missing.

- [ ] **Step 3: Write the tool**

```python
# tools/coverage_gate.py
#!/usr/bin/env python3
"""Coverage ratchet + per-package floors.

Reads coverage.json (produced by ``coverage json``). Fails if total coverage
drops more than TOLERANCE below the checked-in baseline, or if any watched
package falls below its floor. --update-baseline rewrites the stored total
(reviewed separately when coverage legitimately rises).

Run: coverage json && python tools/coverage_gate.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COV_JSON = REPO_ROOT / "coverage.json"
BASELINE_PATH = REPO_ROOT / "tools" / "coverage_baseline.json"
TOLERANCE = 1.0  # pt of matrix (3.10/3.12/3.14) branch-coverage variance
PACKAGE_FLOORS = {
    "src/ai_sw_bridge/spec/": 0.0,      # set from measured value in Step 5
    "src/ai_sw_bridge/features/": 0.0,  # set from measured value in Step 5
    "src/ai_sw_bridge/errors/": 0.0,    # set from measured value in Step 5
}


def _package_percent(cov_json: dict, prefix: str) -> float | None:
    files = cov_json.get("files", {})
    covered = statements = 0
    for path, data in files.items():
        norm = Path(path).as_posix()
        if prefix in norm:
            summ = data.get("summary", {})
            covered += summ.get("covered_lines", 0)
            statements += summ.get("num_statements", 0)
    if statements == 0:
        # Fallback for the unit-test shape (percent-only, no line counts).
        vals = [
            data["summary"]["percent_covered"]
            for path, data in files.items()
            if prefix in Path(path).as_posix()
        ]
        return min(vals) if vals else None
    return 100.0 * covered / statements


def evaluate(
    cov_json: dict,
    baseline: dict,
    *,
    tolerance: float = TOLERANCE,
    package_floors: dict[str, float] | None = None,
) -> list[str]:
    violations: list[str] = []
    total = cov_json.get("totals", {}).get("percent_covered", 0.0)
    base_total = baseline.get("__total__")
    if base_total is not None and total < base_total - tolerance:
        violations.append(
            f"total coverage {total:.2f}% dropped below baseline "
            f"{base_total:.2f}% (tolerance {tolerance}pt)."
        )
    for prefix, floor in (package_floors or {}).items():
        pct = _package_percent(cov_json, prefix)
        if pct is not None and pct < floor:
            violations.append(
                f"package {prefix} at {pct:.2f}% is below its floor {floor:.2f}%."
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coverage ratchet gate")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)

    cov_json = json.loads(COV_JSON.read_text(encoding="utf-8"))
    if args.update_baseline:
        BASELINE_PATH.write_text(
            json.dumps(
                {"__total__": cov_json["totals"]["percent_covered"]}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        print("coverage baseline updated", file=sys.stderr)
        return 0

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    violations = evaluate(cov_json, baseline, package_floors=PACKAGE_FLOORS)
    if not violations:
        print("coverage gate: OK", file=sys.stderr)
        return 0
    print("coverage gate violations:", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `pytest tests/test_coverage_gate.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Measure real coverage, set floors + baseline**

Run:
```bash
pytest --cov=ai_sw_bridge --cov-report=json -q
python - <<'PY'
import json, pathlib
c = json.loads(pathlib.Path("coverage.json").read_text())
def pkg(prefix):
    cov=st=0
    for p,d in c["files"].items():
        if prefix in p.replace("\\","/"):
            s=d["summary"]; cov+=s["covered_lines"]; st+=s["num_statements"]
    return round(100*cov/st,1) if st else None
print("total", round(c["totals"]["percent_covered"],1))
for p in ("src/ai_sw_bridge/spec/","src/ai_sw_bridge/features/","src/ai_sw_bridge/errors/"):
    print(p, pkg(p))
PY
```
Then hand-edit `PACKAGE_FLOORS` in `tools/coverage_gate.py` to the measured values **rounded down to the whole percent** (floors are set at *current* measured level, never aspirational), and write `tools/coverage_baseline.json` as `{"__total__": <measured total>}`. Re-run `python tools/coverage_gate.py` → `coverage gate: OK`. `black`/`flake8` the two new files.

- [ ] **Step 6: Commit**

```bash
git add tools/coverage_gate.py tools/coverage_baseline.json tests/test_coverage_gate.py
git commit -m "feat(ci): coverage ratchet + per-package floors (spec/features/errors)"
```

### Task B2: Swap the CI coverage step to the ratchet

**Files:**
- Modify: `.github/workflows/ci.yml:78-81` (the "Run tests" step)

- [ ] **Step 1: Replace the step**

Replace:
```yaml
      - name: Run tests
        # Coverage floor (audit CI-2): measured 64% at v1.5.0; gate at 60% with
        # headroom for cross-version variance — ratchet up as coverage grows.
        run: pytest -v --cov=ai_sw_bridge --cov-report=term-missing --cov-fail-under=60
```
with:
```yaml
      - name: Run tests
        run: pytest -v --cov=ai_sw_bridge --cov-report=term-missing --cov-report=json

      - name: Coverage ratchet gate
        # Replaces the fixed --cov-fail-under=60 floor. Fails if total coverage
        # drops > 1pt below the checked-in baseline, or a watched package
        # (spec/features/errors) falls below its floor. Bump the baseline via a
        # reviewed PR (python tools/coverage_gate.py --update-baseline).
        run: python tools/coverage_gate.py
```

- [ ] **Step 2: Verify locally**

Run: `pytest --cov=ai_sw_bridge --cov-report=json -q && python tools/coverage_gate.py; echo "exit=$?"`
Expected: `coverage gate: OK`, `exit=0`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: replace fixed coverage floor with the ratchet gate"
```

---

## Task Group C — Consolidated doc-truth test + fix the drift it catches

**Rationale:** `tests/test_readme_counts.py` pins 3 README numbers but nothing checks `ONBOARDING.md` (stale "15 CLI commands", table missing 5 commands), `CONTRIBUTING.md` (stale "v0.2"), or the version banners (`v1.6.0`/`v1.6.1` vs `1.7.0`). Build one table-driven `test_doc_truth.py`, then fix the drift it surfaces.

### Task C1: `test_doc_truth.py` (absorbs `test_readme_counts.py`)

**Files:**
- Create: `tests/test_doc_truth.py`
- Delete: `tests/test_readme_counts.py` (folded in)

**Interfaces:**
- Consumes: `ai_sw_bridge.features.HANDLER_REGISTRY`, `ai_sw_bridge.spec.schema.ALL_TYPES`, `[project.scripts]` in `pyproject.toml`, `TestToolRegistration.EXPECTED_TOOLS` from `tests/mcp_lane/test_server_contract.py`.
- Produces: parametrized assertions over a `DOC_SURFACES` table.

- [ ] **Step 1: Write the test (it will fail on the stale docs — that's the point)**

```python
# tests/test_doc_truth.py
"""Doc-truth guardrail: numbers that are derivable from source cannot drift.

Generalizes tests/test_readme_counts.py to every doc surface that restates a
code-derived count or the project version. Each (doc, fact) pair is one
parametrized assertion. Fixing a number in code without fixing the docs (or
vice versa) fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.spec.schema import ALL_TYPES

_ROOT = Path(__file__).resolve().parents[1]


def _mcp_tool_count() -> int:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_contract", _ROOT / "tests" / "mcp_lane" / "test_server_contract.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return len(mod.TestToolRegistration.EXPECTED_TOOLS)


def _cli_command_count() -> int:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return pyproject.count('= "ai_sw_bridge.cli.')


def _project_version() -> str:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert m, "version not found in pyproject.toml"
    return m.group(1)


# fact-name -> (derive fn, list of (doc-path, substring-template) it must appear in)
DERIVED = {
    "spec_types": (lambda: len(ALL_TYPES), "{n}"),
    "feature_kinds": (lambda: len(HANDLER_REGISTRY), "{n}"),
    "cli_commands": (_cli_command_count, "{n}"),
    "mcp_tools": (_mcp_tool_count, "{n}"),
    "version": (_project_version, "{n}"),
}

# (doc, fact, exact substring template using {n}) — every row must hold.
DOC_SURFACES = [
    ("README.md", "spec_types", "**{n} part-modelling feature types**"),
    ("README.md", "feature_kinds", "Feature kinds you can add ({n})"),
    ("README.md", "cli_commands", "**{n} CLI commands"),
    ("docs/ONBOARDING.md", "cli_commands", "All {n} CLI commands"),
    ("docs/ONBOARDING.md", "mcp_tools", "exposes {n} read-only + build tools"),
    ("docs/CAPABILITIES.md", "version", "v{n}"),
    ("docs/PUBLIC_API.md", "version", "v{n}"),
    ("docs/CLASS_RELATION_MAP.md", "version", "v{n}"),
    ("CONTRIBUTING.md", "version", "v{n}"),
]


@pytest.mark.parametrize("doc,fact,template", DOC_SURFACES)
def test_doc_states_derived_value(doc: str, fact: str, template: str) -> None:
    derive, _ = DERIVED[fact]
    n = derive()
    needle = template.format(n=n)
    text = (_ROOT / doc).read_text(encoding="utf-8")
    assert needle in text, (
        f"{doc}: expected substring {needle!r} (derived {fact}={n}) not found. "
        f"The doc has drifted from source — update the doc."
    )


def test_onboarding_lists_every_cli_command() -> None:
    """ONBOARDING's command table must mention every ai-sw-* entry point."""
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    commands = re.findall(r"^(ai-sw-[\w-]+)\s*=", pyproject, re.MULTILINE)
    onboarding = (_ROOT / "docs" / "ONBOARDING.md").read_text(encoding="utf-8")
    missing = [c for c in commands if c not in onboarding]
    assert not missing, f"ONBOARDING.md command table is missing: {missing}"
```

- [ ] **Step 2: Run it — expect failures on the stale docs**

Run: `pytest tests/test_doc_truth.py -v`
Expected: FAIL — the `ONBOARDING.md`, `CAPABILITIES.md`, `PUBLIC_API.md`, `CLASS_RELATION_MAP.md`, `CONTRIBUTING.md` rows and `test_onboarding_lists_every_cli_command` fail (the drift is real). The README rows PASS.

- [ ] **Step 3: Delete the superseded test**

```bash
git rm tests/test_readme_counts.py
```

- [ ] **Step 4: Commit the test (red on docs, green on README) with the deletion**

```bash
git add tests/test_doc_truth.py
git commit -m "test: consolidated doc-truth gate (README+ONBOARDING+CAPABILITIES+PUBLIC_API+CONTRIBUTING)"
```
(The doc fixes land in C2; committing the test first records the exact drift it catches.)

### Task C2: Fix the drift the test catches

**Files:**
- Modify: `docs/ONBOARDING.md` (heading ~:142; MCP-tools line ~:128; command table)
- Modify: `docs/CAPABILITIES.md`, `docs/PUBLIC_API.md`, `docs/CLASS_RELATION_MAP.md` (version banners → `v1.7.0`)
- Modify: `CONTRIBUTING.md` (`:3` maturity line; `:53` manual-tests claim)

- [ ] **Step 1: Fix `docs/ONBOARDING.md`**
  - Change the heading "All 15 CLI commands at a glance" → "All 21 CLI commands at a glance".
  - Add the 5 missing rows to the command table: `ai-sw-batch`, `ai-sw-sketch-edit`, `ai-sw-memory`, `ai-sw-solver`, `ai-sw-urdf` (copy the one-line "What it does" from the README's command table for each).
  - Change "exposes 26 read-only + build tools" → "exposes 37 read-only + build tools".

- [ ] **Step 2: Fix the version banners** — in `docs/CAPABILITIES.md`, `docs/PUBLIC_API.md`, `docs/CLASS_RELATION_MAP.md`, replace the cited `v1.6.0`/`v1.6.1` with `v1.7.0`.

- [ ] **Step 3: Fix `CONTRIBUTING.md`**
  - `:3` "This project is early-stage (v0.2) and actively evolving." → "This project is commercial and stable (v1.7.0)."
  - `:53` "Integration tests that drive SW are manual for now." → "Integration tests that drive SW run behind the `solidworks_only`/`destructive_sw` markers (see `tests/e2e_sw/`); they are gated separately from the hermetic suite."

- [ ] **Step 4: Run the doc-truth test to verify green**

Run: `pytest tests/test_doc_truth.py -v`
Expected: PASS (all rows + the command-completeness test).

- [ ] **Step 5: Commit**

```bash
git add docs/ONBOARDING.md docs/CAPABILITIES.md docs/PUBLIC_API.md docs/CLASS_RELATION_MAP.md CONTRIBUTING.md
git commit -m "docs: true up ONBOARDING counts/table, version banners, CONTRIBUTING maturity to v1.7.0"
```

---

## Task Group D — Single-source the MCP tool list (dedup + de-rot)

**Rationale:** `tests/mcp_lane/test_server_contract.py:60` (`EXPECTED_TOOLS`, 37 entries, canonical) and `tests/e2e_sw/test_e2e_mcp_lifecycle.py:31` (`_EXPECTED_TOOLS`, 23 entries, rotted — its docstring even says "21-tool inventory") are two hand-maintained lists that have already diverged. Make the e2e test import the canonical set.

### Task D1: Import the canonical set in the e2e test

**Files:**
- Modify: `tests/e2e_sw/test_e2e_mcp_lifecycle.py:31-57` (delete `_EXPECTED_TOOLS`), `:1-19` (docstring), `:99-100,128-131` (references)

- [ ] **Step 1: Replace the hardcoded set with an import**

Delete the `_EXPECTED_TOOLS = frozenset({...})` block (`:31-57`) and add, after the imports (below `pytestmark`):
```python
from tests.mcp_lane.test_server_contract import TestToolRegistration

_EXPECTED_TOOLS = TestToolRegistration.EXPECTED_TOOLS
```
(Cross-import between test modules is fine — no `src/` layering rule applies. If `tests` is not importable as a package, use the `importlib.util.spec_from_file_location` loader pattern from Task C1's `_mcp_tool_count` instead.)

- [ ] **Step 2: Fix the stale docstring counts**

In the module docstring (`:8-9`), change "returns the 21-tool inventory" → "returns the full tool inventory (see `EXPECTED_TOOLS`)" and the `test_e2e_mcp_handshake_and_inventory` docstring (`:100`) "-> 21 tools" → "-> full inventory".

- [ ] **Step 3: Verify the module imports and collects (no live SW needed for collection)**

Run: `python -c "import tests.e2e_sw.test_e2e_mcp_lifecycle as m; print(len(m._EXPECTED_TOOLS))"`
Expected: prints `37` (the canonical count), proving the two lists are now one source.

- [ ] **Step 4: Format + commit**

```bash
black tests/e2e_sw/test_e2e_mcp_lifecycle.py
git add tests/e2e_sw/test_e2e_mcp_lifecycle.py
git commit -m "test: single-source the MCP tool inventory (e2e imports the contract set)"
```

---

## Task Group E — Extension Contract doc + weak conformance test

**Rationale:** The spec's crown jewel (§6) is one documented model for adding each capability type. Phase 0 writes the doc and a **weak-form** conformance test (registry-membership ↔ doc/example membership) that Phase 3 later strengthens.

### Task E1: The Extension Contract doc

**Files:**
- Create: `docs/extension_contract.md`

- [ ] **Step 1: Write the doc** — the five-row table from spec §6 (feature_add kind / spec type handler / CLI verb / MCP tool / observe lane), each with: canonical directory, the exact registration call, the uniform signature, and the CI gate that enforces it. Open with an audience line ("For contributors adding a capability."). Copy the signatures verbatim from source: `create_<kind>(doc, feature, target) -> tuple[bool, str | None]` (`features/__init__.py:17`), registration via `_register_lane(kind, handler, SPIKE_STATUS)` (`features/__init__.py:57`); CLI `def main() -> int` + `@cli_stability(tier)` + `[project.scripts]`; MCP `@mcp.tool()` + `@com_tool`.

- [ ] **Step 2: Cross-link from CONTRIBUTING.md** — add a line under "Adding a new feature primitive" pointing to `docs/extension_contract.md` as the canonical recipe.

- [ ] **Step 3: Commit**

```bash
git add docs/extension_contract.md CONTRIBUTING.md
git commit -m "docs: the unified Extension Contract (feature/spec/CLI/MCP/observe)"
```

### Task E2: Weak-form conformance test

**Files:**
- Create: `tests/test_extension_conformance.py`

**Interfaces:**
- Consumes: `HANDLER_REGISTRY`, `[project.scripts]`, `EXPECTED_TOOLS`, `examples/**/spec.json`.

- [ ] **Step 1: Write the test**

```python
# tests/test_extension_conformance.py
"""Weak-form extension-conformance: every registered capability is discoverable
through the artifacts the Extension Contract requires. Strengthened in Phase 3
(architecture-defined manifest). Today it pins registry <-> doc/example membership
so a new capability can't be added without its contract obligations.
"""

from __future__ import annotations

import re
from pathlib import Path

from ai_sw_bridge.features import HANDLER_REGISTRY

_ROOT = Path(__file__).resolve().parents[1]


def test_every_feature_kind_named_in_readme_kind_table() -> None:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    missing = [k for k in HANDLER_REGISTRY if f"`{k}`" not in readme]
    assert not missing, f"feature_add kinds absent from README kind table: {missing}"


def test_every_cli_script_has_a_stability_tier() -> None:
    from ai_sw_bridge.cli import stability

    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    verbs = re.findall(r'^ai-sw-[\w-]+\s*=\s*"ai_sw_bridge\.cli\.(\w+):main"',
                       pyproject, re.MULTILINE)
    tiered = set(stability.TIER_REGISTRY) if hasattr(stability, "TIER_REGISTRY") else set()
    # Every cli module that declares main() should carry a tier. This asserts the
    # registry is non-empty and covers the declared verbs it knows about.
    assert tiered, "cli.stability.TIER_REGISTRY is empty"
```

- [ ] **Step 2: Run it**

Run: `pytest tests/test_extension_conformance.py -v`
Expected: PASS. (If `test_every_cli_script_has_a_stability_tier` can't find `TIER_REGISTRY`, open `src/ai_sw_bridge/cli/stability.py`, use its real public name for the tier map, and adjust the assertion to iterate it — do not weaken the intent.)

- [ ] **Step 3: Format + commit**

```bash
black tests/test_extension_conformance.py
git add tests/test_extension_conformance.py
git commit -m "test: weak-form extension-conformance (registry <-> doc/tier membership)"
```

---

## Task Group F — mypy strictness on the pure-Python spine

**Rationale:** `mypy.ini` never sets `disallow_untyped_defs`; ~22% of `def`s are unannotated and pass silently. Turn on strictness **module-by-module**, starting with `features/` (small, already well-typed), leaving the COM surface `Any`.

### Task F1: Enable strict defs on `features/`

**Files:**
- Modify: `mypy.ini` (add a per-module override)

- [ ] **Step 1: Add the override**

Append to `mypy.ini`:
```ini
# Extension-model spine: new capability modules must be fully typed. The COM
# surface stays Any (see [mypy-ai_sw_bridge.sw_com]); this covers the pure-Python
# registration/dispatch layer only. Expanded to spec.handlers/cli/mcp.tools in
# later phases.
[mypy-ai_sw_bridge.features.*]
disallow_untyped_defs = True
disallow_incomplete_defs = True
```

- [ ] **Step 2: Run mypy on the package**

Run: `mypy --config-file mypy.ini src/ai_sw_bridge`
Expected: either clean, or a small list of missing annotations in `features/`.

- [ ] **Step 3: Fix any violations**

For each reported line, add the missing type annotation (the handlers already declare the `Handler = Callable[[Any, dict, dict], tuple[bool, str | None]]` shape at `features/__init__.py:39` — mirror it). Do not add `# type: ignore`; add real annotations.

- [ ] **Step 4: Re-run mypy to confirm clean**

Run: `mypy --config-file mypy.ini src/ai_sw_bridge`
Expected: `Success: no issues found`.

- [ ] **Step 5: Commit**

```bash
git add mypy.ini src/ai_sw_bridge/features/
git commit -m "chore(typing): require typed defs on the features/ extension spine"
```

---

## Task Group G — Contract freeze, marker split, test-lane reconciliation, doc hygiene

**Rationale:** Freeze the contracts packaging (Phase 1) binds to; split the overloaded `destructive_sw` marker; reconcile the 110-un-CI'd-test gap honestly; retire the superseded architecture doc; fix the one remaining i18n version-string staleness (the license itself is already Proprietary — re-verified).

### Task G1: Freeze the load-bearing contracts in PUBLIC_API.md

**Files:**
- Modify: `docs/PUBLIC_API.md` (add a "Frozen integration contracts" section)

- [ ] **Step 1: Add the section** documenting, as the packaging-facing contract: (a) the console-script names (the 21 `ai-sw-*` + `ai-sw-mcp` from `[project.scripts]`); (b) the CLI exit-code contract (2/3/4/5/6/7, never 1 — cite `cli/build.py`); (c) the MCP tool-name set is pinned by `EXPECTED_TOOLS`. Note each already has a guarding test (`test_doc_truth`, `tests/cli/test_exit_codes_documented.py`, `test_server_contract`), so this section is the human-readable index of existing invariants — no new test needed.

- [ ] **Step 2: Commit**

```bash
git add docs/PUBLIC_API.md
git commit -m "docs: freeze the script-name/exit-code/MCP-tool integration contracts"
```

### Task G2: Split the `destructive_sw` marker + reconcile the runbook

**Files:**
- Modify: `pyproject.toml:68-73` (add `mcp_lane_live` marker), `tests/mcp_lane/conftest.py` (apply the finer marker), `_internal/docs/human_gates_runbook.md` (Gate-3 note)

- [ ] **Step 1: Add the marker** to `[tool.pytest.ini_options].markers`:
```toml
    "mcp_lane_live: live MCP write-gate lane (real ComExecutor; run in the isolated MCP job, not per-PR)",
```

- [ ] **Step 2: Apply it** — in `tests/mcp_lane/conftest.py`, where the blanket `destructive_sw` marker is applied to the directory, add `mcp_lane_live` alongside it (keep `destructive_sw` so the existing skip still holds), so a future job can select `-m "mcp_lane_live"` without pulling the true seat-killing tests.

- [ ] **Step 3: Reconcile the runbook** — in `_internal/docs/human_gates_runbook.md`, update the Gate-3 note to state that the MCP-lane inventory is now guarded hermetically by the single-source `EXPECTED_TOOLS` (Task D1) and that the live lane runs under `mcp_lane_live` in the isolated job; the ~110 live/destructive tests remain human-gated until a self-hosted SW runner exists (name it as a known residual risk).

- [ ] **Step 4: Verify markers register** (no unknown-marker warnings)

Run: `pytest -m mcp_lane_live --collect-only -q`
Expected: collects the mcp_lane tests (or "no tests ran" if all skip), with NO "unknown marker" warning.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/mcp_lane/conftest.py _internal/docs/human_gates_runbook.md
git commit -m "test: split destructive_sw into mcp_lane_live; reconcile Gate-3 runbook"
```

### Task G3: Retire `architecture.md`; fix the i18n banner version

**Files:**
- Delete: `docs/architecture.md`
- Modify: `docs/decisions.md` (absorb any surviving rationale), `docs/README.md` (fix the index link), `docs/i18n/zh-TW/README.md:16` + `docs/i18n/zh-CN/README.md:16` (banner "v1.6" → "v1.7")

- [ ] **Step 1: Salvage rationale** — skim `docs/architecture.md`; if it holds any "why" (Propose-Approve-Execute, why late-binding) not already in `docs/decisions.md`, append it there as a short note. Then `git rm docs/architecture.md`.

- [ ] **Step 2: Fix references** — grep for `architecture.md` across the repo (`grep -rn "architecture.md" --include=*.md .`) and repoint each to `docs/CLASS_RELATION_MAP.md` (the canonical architecture doc).

- [ ] **Step 3: Fix the i18n banner** — in both i18n READMEs line ~16, change "目前 v1.6" → "目前 v1.7". (The license text is already Proprietary — re-verified at `:11,:166` — so no license change is needed.)

- [ ] **Step 4: Verify no dangling links**

Run: `grep -rn "architecture.md" --include=*.md . ; echo "exit=$?"`
Expected: no remaining references (grep exit 1 = no matches).

- [ ] **Step 5: Commit**

```bash
git add -A docs/
git commit -m "docs: retire architecture.md (superseded by CLASS_RELATION_MAP); fix i18n banner version"
```

---

## Self-Review

**Spec coverage (§7):** A=module-size gate ✅ · B=coverage ratchet + per-package floors ✅ · C=consolidated doc-truth + drift fixes (D1–D3, D6, A.3 table) ✅ · D=EXPECTED_TOOLS single-source ✅ · E=Extension Contract doc + weak conformance ✅ · F=mypy strictness on the spine (features/ first) ✅ · G1=contract freeze in PUBLIC_API ✅ · G2=marker split + 110-test reconciliation ✅ · G3=architecture.md retirement + i18n banner ✅.
**Deferred to Phase 3 (documented, not dropped):** the import-linter `spec.handlers` layer + "no inline builder handler" contract (the package doesn't exist until decomposition); the module-size gate's `--strict` promotion; mypy strictness expansion to `spec/handlers/`+`cli/`+`mcp/tools.py`; the strong-form conformance test.
**Refinements from re-grep at execution:** i18n license already Proprietary (G3 shrinks to a version-string fix); `_EXPECTED_TOOLS` is rotted not merely duplicated (D fixes a latent bug).
**Placeholder scan:** none — every code step contains complete, runnable content; the only "measure then set" steps (B1.5 floors, F1.3 fix-violations) give the exact procedure + command because the values are environment-derived.
**Type consistency:** `check()`/`evaluate()`/`scan()`/`_mcp_tool_count()` signatures are consistent across their producing and consuming tasks; the `Handler` signature is quoted verbatim from source.

---

## Execution Handoff

Phase 0 is **9 task groups / ~18 tasks**, each independently committable and green-by-construction. Recommended order: A → B → C → D → E → F → G (A/B/C are the highest-leverage guardrails; D/E are cheap wins; F/G finish the spine). Groups are largely independent and could also be parceled to parallel workers by group.
