# Phase 1 — Stop Burning Seats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ai-sw-build --lint` tell an author the truth about what it did and did not check, and settle whether a one-directional plane-sketched cut is a kernel constraint or a bridge bug before encoding either answer as a permanent ERROR.

**Architecture:** Three independent changes to the seat-free tier. (1) A one-shot live probe resolves the open mechanism question behind issue #40; its verdict selects which of two mutually exclusive resolutions Task 6 applies. (2) Issue #33 is implemented by tagging the pre-flight's existing honest-skip notes with a stable machine code, deriving a coverage summary from those tags rather than from a second copy of the modeling predicate, and surfacing it in the `--lint` JSON. (3) A new `--strict` flag gates on that summary at a new exit code, leaving the default ERROR-only contract byte-for-byte unchanged.

**Tech Stack:** Python 3.14, pytest, `black`, `flake8`, `mypy`, argparse CLI, SOLIDWORKS 2024 SP1 COM (Task 1 only).

**Spec:** `docs/superpowers/specs/2026-09-02-cold-authorability-design.md` — §6 (Phase 1), §5 (dependency chain), §11 (success criteria). Read it before starting; this plan implements its Phase 1 and nothing else.

## Global Constraints

- **Phase 1 only.** Issues #40 and #33. Do not touch #28–#32, #34–#39, #41–#43 — they are Phases 2–4 and have unimplemented dependencies (spec §5).
- **`cli/build.py` is grandfathered shrink-only** in `tools/module_size_baseline.json` at **925 LOC** and currently sits at **911**. It may not exceed 925. Only Task 5 touches it, adding exactly one 11-line argparse block (911 → 922). All other logic goes in `spec/preflight.py` (438 LOC, 800 ceiling) and `cli/_lint_preflight.py` (82 LOC, 800 ceiling).
- **Exit codes 0–7 are taken** (`docs/tools_reference.md:166`): `0` ok, `1` handled failure, `2` bad args, `3` validation, `4` build, `5` rhs-resolution, `6` lint ERROR, `7` `--auto-retry` refusal. The new strict-coverage code is **`8`**.
- **The never-false-ERROR invariant holds.** Pre-flight may only emit `severity="error"` for a condition it can prove. Coverage incompleteness is not an error; it gates only under `--strict`, and only at exit 8.
- **Default behaviour is unchanged.** Without `--strict`, exit codes, `payload["ok"]`, and every existing finding stay exactly as they are. A new `coverage` key in the payload is additive.
- **`LintFinding.to_dict()` stays backward-compatible** — the new `code` key appears only when set, so existing consumers and tests that compare finding dicts are unaffected.
- **Run the gates before every commit:** `black .`, `flake8`, `mypy`, `pytest`. Delete a stray `nul` file on Windows before `mypy`.
- **Never append `Co-Authored-By: Claude`** to any commit.
- Work happens in the throwaway clone `C:\D\_grok_agnostic_test\bridge_work`. Its `origin` is a **local path to the real read-only repo** — push only to the `gh` remote. Run `git remote -v` before any push.

---

### Task 1: Resolve O2 — does arg 3 `Dir` build a plane-sketched one-directional cut?

**Why this is first:** PR #44 encodes "a one-directional plane-sketched cut can *never* build" as a permanent ERROR. That claim rests on four live controls that varied `FeatureCut4`'s arg 2 (`Flip`) and never its arg 3 (`Dir`), which is hardcoded `False` and unreachable from any spec field. If `Dir=True` builds, the guard is a false ERROR and the correct fix is in the builder, not the pre-flight. This task produces a recorded verdict that selects Task 6's branch. **Nothing downstream of Task 6 depends on it — Tasks 2–5 may proceed in parallel.**

**⚠ OPERATOR GATE:** This is the only task in the plan that touches a live SOLIDWORKS seat. It opens SW and builds parts. The operator approves the run before it happens; an agent proposes and stops. Background/task notifications are not approval.

**Files:**
- Create: `C:\D\_grok_agnostic_test\probe_D_dir_true.json`
- Create: `C:\D\_grok_agnostic_test\probe_E_dir_true_flip_true.json`
- Modify (temporarily, on a throwaway branch, never merged): `src/ai_sw_bridge/spec/handlers/extrude.py:147`
- Create: `C:\D\_grok_agnostic_test\O2_VERDICT.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `O2_VERDICT.md` containing the literal string `VERDICT: KERNEL_CONSTRAINT` or `VERDICT: BRIDGE_BUG`. Task 6 reads this file and applies branch A or branch B accordingly.

- [ ] **Step 1: Create the two probe specs**

Both reuse the geometry of the original control set exactly — Front-plane 140×90 plate, `boss_extrude_blind` depth 20 (verified live bbox `X[-70,70] Y[-45,45] Z[0,20]`), and an 8×8 cut profile at `{-20,-18}` that sits well inside the footprint. The only variable is the direction booleans.

`C:\D\_grok_agnostic_test\probe_D_dir_true.json`:

```json
{"schema_version":1,"name":"PD_dir_true","features":[
{"type":"sketch_rectangle_on_plane","name":"SK_Base","plane":"Front","width":140.0,"height":90.0,"center":{"x":0.0,"y":0.0}},
{"type":"boss_extrude_blind","name":"EX_Base","sketch":"SK_Base","depth":20.0},
{"type":"sketch_rectangle_on_plane","name":"SK_C","plane":"Front","width":8.0,"height":8.0,"center":{"x":-20.0,"y":-18.0}},
{"type":"cut_extrude_blind","name":"CUT","sketch":"SK_C","depth":6.0}
]}
```

`C:\D\_grok_agnostic_test\probe_E_dir_true_flip_true.json` — identical but with `"flip": true` on the cut:

```json
{"schema_version":1,"name":"PE_dir_true_flip_true","features":[
{"type":"sketch_rectangle_on_plane","name":"SK_Base","plane":"Front","width":140.0,"height":90.0,"center":{"x":0.0,"y":0.0}},
{"type":"boss_extrude_blind","name":"EX_Base","sketch":"SK_Base","depth":20.0},
{"type":"sketch_rectangle_on_plane","name":"SK_C","plane":"Front","width":8.0,"height":8.0,"center":{"x":-20.0,"y":-18.0}},
{"type":"cut_extrude_blind","name":"CUT","sketch":"SK_C","depth":6.0,"flip":true}
]}
```

- [ ] **Step 2: Create a throwaway probe branch**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
git checkout master
git checkout -b probe/issue-40-dir-arg
```

- [ ] **Step 3: Make arg 3 `Dir` switchable by environment variable**

This is deliberately ugly and deliberately temporary — it exists so one patched build serves both `Dir=False` and `Dir=True` runs without a second edit. It is never merged.

In `src/ai_sw_bridge/spec/handlers/extrude.py`, add near the top of the module (after the existing imports):

```python
import os

# PROBE ONLY (branch probe/issue-40-dir-arg, issue #40 / O2). Not for merge.
# FeatureCut4 arg 3 "Dir" is hardcoded False everywhere; this lets one build
# exercise Dir=True so the two direction booleans can be told apart.
_PROBE_CUT_DIR = os.environ.get("AI_SW_PROBE_CUT_DIR") == "1"
```

Then change line 147 inside `_cut4_args_2024` from:

```python
        False,  # 3  Dir
```

to:

```python
        _PROBE_CUT_DIR,  # 3  Dir  (PROBE ONLY -- normally False)
```

- [ ] **Step 4: Confirm the probe patch changes nothing when the variable is unset**

Run: `pytest tests/ -q -k "cut or extrude or preflight"`
Expected: PASS — with `AI_SW_PROBE_CUT_DIR` unset, `_PROBE_CUT_DIR` is `False` and the arg tuple is byte-for-byte the shipped one.

- [ ] **Step 5: STOP. Request operator approval for the live runs**

Present to the operator: the two spec files, the four commands in Step 6, and the fact that this opens SOLIDWORKS and builds two throwaway parts. Wait for an explicit go. Do not proceed on a notification, a timeout, or silence.

- [ ] **Step 6: Run the four live builds**

Run each and record the exit code and the JSON separately. The first two are the known-failing baselines re-run under the patched build to prove the patch itself changed nothing:

```bash
cd /c/D/_grok_agnostic_test/bridge_work
export PYTHONPATH=$PWD/src

# Baseline reproduction (Dir=False) -- expect FeatureCut4 None, as originally observed
python -m ai_sw_bridge.cli.build C:/D/_grok_agnostic_test/probe_D_dir_true.json --no-dim > /c/D/_grok_agnostic_test/probe_D_dirfalse.json; echo "exit=$?"

# The actual experiment (Dir=True)
AI_SW_PROBE_CUT_DIR=1 python -m ai_sw_bridge.cli.build C:/D/_grok_agnostic_test/probe_D_dir_true.json --no-dim > /c/D/_grok_agnostic_test/probe_D_dirtrue.json; echo "exit=$?"

AI_SW_PROBE_CUT_DIR=1 python -m ai_sw_bridge.cli.build C:/D/_grok_agnostic_test/probe_E_dir_true_flip_true.json --no-dim > /c/D/_grok_agnostic_test/probe_E_dirtrue.json; echo "exit=$?"
```

`--no-dim` is mandatory — parametric mode triggers the blocking `AddDimension2` popup that needs a human to tick it.

Note the shell trap: `cmd | tail; echo $?` reports `tail`'s exit code, not the build's. Capture to a file and echo `$?` on the same line, as above.

- [ ] **Step 7: Write the verdict**

Create `C:\D\_grok_agnostic_test\O2_VERDICT.md` with the four exit codes, the relevant JSON excerpt from each run, and one of these two lines verbatim:

- `VERDICT: BRIDGE_BUG` — if either `Dir=True` run **built the cut** (exit 0, four features). The failure is a bridge-side direction-selection bug: the builder never exposes the `Dir` axis, so a spec cannot express the working form.
- `VERDICT: KERNEL_CONSTRAINT` — if **all four runs** returned `FeatureCut4 None`. The direction space is now fully spanned and the constraint is real.

If the runs disagree in some third way (e.g. it builds but removes the wrong material), record exactly what happened and stop — Task 6 does not apply and the design's §6 open question needs re-opening with the maintainer.

- [ ] **Step 8: Revert the probe patch and commit the evidence only**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
git checkout src/ai_sw_bridge/spec/handlers/extrude.py
git status --porcelain   # expect: clean
```

The verdict and probe JSON live in `C:\D\_grok_agnostic_test\`, outside the repo. Nothing from this task is committed to the bridge. Delete the probe branch once the verdict is written:

```bash
git checkout master
git branch -D probe/issue-40-dir-arg
```

---

### Task 2: Tag findings with a stable machine code

**Files:**
- Modify: `src/ai_sw_bridge/spec/lint.py:10-33`
- Modify: `src/ai_sw_bridge/spec/preflight.py:228-238`
- Test: `tests/test_lint.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LintFinding(severity: str, path: str, message: str, code: Optional[str] = None)` with attribute `.code`, and `to_dict() -> dict[str, str]` that includes `"code"` only when `code is not None`. Module constant `preflight.PREFLIGHT_SKIP_CODE = "preflight_skip"`. Task 3 consumes both.

- [ ] **Step 0: Create the issue #33 branch**

Tasks 2 through 5 are one shippable unit — the coverage signal — and share a branch. Do not commit them to `master`.

```bash
cd /c/D/_grok_agnostic_test/bridge_work
git checkout master
git status --porcelain   # expect clean; Task 1's probe patch must already be reverted
git checkout -b fix/issue-33-preflight-coverage-signal
```

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_lint.py`:

```python
from ai_sw_bridge.spec.lint import LintFinding


def test_finding_without_code_omits_the_key():
    f = LintFinding(severity="info", path="features/0/X", message="m")
    assert f.code is None
    assert f.to_dict() == {"severity": "info", "path": "features/0/X", "message": "m"}


def test_finding_with_code_includes_the_key():
    f = LintFinding(severity="info", path="features/0/X", message="m", code="preflight_skip")
    assert f.to_dict()["code"] == "preflight_skip"


def test_preflight_skip_notes_carry_the_skip_code():
    from ai_sw_bridge.spec.preflight import (
        PREFLIGHT_SKIP_CODE,
        material_envelope_scan,
    )

    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 40,
                "height": 30,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10},
            {"type": "linear_pattern", "name": "PAT", "seed": "EX", "count": 3},
        ]
    }
    findings = material_envelope_scan(spec)
    skips = [f for f in findings if f.code == PREFLIGHT_SKIP_CODE]
    assert len(skips) == 1
    assert skips[0].path == "features/2/PAT"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_lint.py -q -k "code or skip_code"`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'code'`, and `AttributeError: 'LintFinding' object has no attribute 'code'`.

- [ ] **Step 3: Add the optional code to LintFinding**

In `src/ai_sw_bridge/spec/lint.py`, change the import line from:

```python
from typing import Any
```

to:

```python
from typing import Any, Optional
```

and replace the `LintFinding` body:

```python
class LintFinding:
    """One lint warning. Not fatal — the spec may still build correctly.

    ``code`` is an optional stable machine tag (e.g. ``"preflight_skip"``)
    for consumers that need to identify a finding class without parsing its
    prose. It is omitted from ``to_dict()`` when unset, so the serialized
    shape is unchanged for every finding that does not set one.
    """

    def __init__(
        self,
        severity: str,
        path: str,
        message: str,
        code: Optional[str] = None,
    ) -> None:
        self.severity = severity  # "info", "warning", or "error"
        self.path = path
        self.message = message
        self.code = code

    def to_dict(self) -> dict[str, str]:
        d = {
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }
        if self.code is not None:
            d["code"] = self.code
        return d

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}: {self.message}"
```

- [ ] **Step 4: Tag the honest-skip notes**

In `src/ai_sw_bridge/spec/preflight.py`, add above `_skip` (after the `_NON_BODY_TYPES` line at 225):

```python
# Stable machine tag on every honest-skip note. Consumers derive pre-flight
# coverage from these rather than re-deriving the modeling predicate, so the
# summary cannot drift from what the analyzers actually skipped.
PREFLIGHT_SKIP_CODE = "preflight_skip"
```

and change the `LintFinding(...)` inside `_skip` to pass it:

```python
    return LintFinding(
        severity="info",
        path=f"features/{i}/{name}",
        message=(
            f"pre-flight skip: '{name}' ({ftype}) is not modeled by the "
            f"axis-aligned envelope; downstream geometry checks are relaxed."
        ),
        code=PREFLIGHT_SKIP_CODE,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_lint.py tests/test_preflight.py tests/test_preflight_cli.py -q`
Expected: PASS, including every pre-existing test — the serialized shape of untagged findings is unchanged.

- [ ] **Step 6: Run the gates and commit**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
rm -f nul
black . && flake8 && mypy && pytest -q
git add src/ai_sw_bridge/spec/lint.py src/ai_sw_bridge/spec/preflight.py tests/test_lint.py
git commit -m "feat(lint): optional stable code tag on findings; tag pre-flight skips"
```

---

### Task 3: Derive a coverage summary from the skip tags

**Files:**
- Modify: `src/ai_sw_bridge/spec/preflight.py` (add `coverage`, exported alongside `preflight`)
- Test: `tests/test_preflight.py`

**Interfaces:**
- Consumes: `preflight.PREFLIGHT_SKIP_CODE`, `LintFinding.code` (Task 2).
- Produces: `coverage(spec: dict[str, Any], findings: list[LintFinding]) -> dict[str, Any]` returning `{"total": int, "modeled": int, "skipped": int, "skipped_types": list[str], "complete": bool}`. Tasks 4 and 5 consume it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preflight.py`:

```python
def test_coverage_counts_only_solid_ops_and_is_complete_when_nothing_skipped():
    from ai_sw_bridge.spec.preflight import coverage, preflight

    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 40,
                "height": 30,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10},
        ]
    }
    cov = coverage(spec, preflight(spec))
    # The sketch is body-less and is not a coverage denominator; only EX counts.
    assert cov == {
        "total": 1,
        "modeled": 1,
        "skipped": 0,
        "skipped_types": [],
        "complete": True,
    }


def test_coverage_reports_skipped_types_sorted_and_deduplicated():
    from ai_sw_bridge.spec.preflight import coverage, preflight

    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 40,
                "height": 30,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10},
            {"type": "linear_pattern", "name": "P1", "seed": "EX", "count": 3},
            {"type": "linear_pattern", "name": "P2", "seed": "EX", "count": 2},
            {"type": "boss_extrude_midplane", "name": "BM", "sketch": "SK", "depth": 4},
        ]
    }
    cov = coverage(spec, preflight(spec))
    assert cov["total"] == 4
    assert cov["skipped"] == 3
    assert cov["modeled"] == 1
    assert cov["skipped_types"] == ["boss_extrude_midplane", "linear_pattern"]
    assert cov["complete"] is False


def test_coverage_of_an_empty_spec_is_complete():
    from ai_sw_bridge.spec.preflight import coverage

    assert coverage({"features": []}, []) == {
        "total": 0,
        "modeled": 0,
        "skipped": 0,
        "skipped_types": [],
        "complete": True,
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_preflight.py -q -k coverage`
Expected: FAIL with `ImportError: cannot import name 'coverage' from 'ai_sw_bridge.spec.preflight'`.

- [ ] **Step 3: Implement coverage**

Append to `src/ai_sw_bridge/spec/preflight.py`, immediately before `def preflight(`:

```python
def coverage(
    spec: dict[str, Any], findings: list[LintFinding]
) -> dict[str, Any]:
    """Summarize how much of ``spec`` the geometric pre-flight actually modeled.

    Derived from the honest-skip notes the analyzers emitted (tagged
    ``PREFLIGHT_SKIP_CODE``) rather than from a second copy of the modeling
    predicate, so the summary cannot drift from the real skip logic.

    The denominator is solid-modifying features only. ``sketch_*`` features
    carry no body -- they define a profile a later boss/cut consumes -- so
    counting them would inflate coverage with features there is nothing to
    check. This is the same prefix rule ``material_envelope_scan`` uses to
    decide which features may stay quiet.

    ``skipped_types`` is sorted and de-duplicated so the summary is stable
    across runs and diffable in CI.
    """
    features = spec.get("features", [])
    solid_ops = [
        (i, f)
        for i, f in enumerate(features)
        if not str(f.get("type", "")).startswith("sketch_")
    ]
    skipped_paths = {f.path for f in findings if f.code == PREFLIGHT_SKIP_CODE}
    skipped = [
        f
        for i, f in solid_ops
        if f"features/{i}/{f.get('name', '')}" in skipped_paths
    ]
    return {
        "total": len(solid_ops),
        "modeled": len(solid_ops) - len(skipped),
        "skipped": len(skipped),
        "skipped_types": sorted({str(f.get("type", "")) for f in skipped}),
        "complete": len(skipped) == 0,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_preflight.py -q`
Expected: PASS, all tests including the pre-existing ones.

- [ ] **Step 5: Run the gates and commit**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
rm -f nul
black . && flake8 && mypy && pytest -q
git add src/ai_sw_bridge/spec/preflight.py tests/test_preflight.py
git commit -m "feat(preflight): coverage summary derived from honest-skip tags"
```

---

### Task 4: Surface coverage in the `--lint` JSON payload

**Files:**
- Modify: `src/ai_sw_bridge/cli/_lint_preflight.py:19-35` and `:60-75`
- Modify: `docs/tools_reference.md`
- Test: `tests/test_preflight_cli.py`

**Interfaces:**
- Consumes: `preflight.coverage` (Task 3).
- Produces: `assemble_lint_findings(spec, *, no_preflight) -> tuple[list[LintFinding], list[dict[str, Any]], bool, dict[str, Any]]` — a **fourth** element, the coverage dict. `payload["coverage"]` in the lint-only response. Task 5 consumes both.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preflight_cli.py`:

```python
def test_lint_payload_carries_a_coverage_summary(tmp_path):
    rc, payload = _run(_CLEAN, tmp_path)
    assert rc == 0
    assert payload["coverage"] == {
        "total": 1,
        "modeled": 1,
        "skipped": 0,
        "skipped_types": [],
        "complete": True,
    }


def test_lint_payload_coverage_names_unmodeled_types(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"].append(
        {"type": "linear_pattern", "name": "PAT", "seed": "EX", "count": 3}
    )
    rc, payload = _run(spec, tmp_path)
    assert rc == 0  # coverage gaps are not errors without --strict
    assert payload["coverage"]["complete"] is False
    assert payload["coverage"]["skipped_types"] == ["linear_pattern"]


def test_no_preflight_reports_zero_coverage_rather_than_claiming_completeness(tmp_path):
    rc, payload = _run(_CLEAN, tmp_path, "--no-preflight")
    assert rc == 0
    assert payload["coverage"]["complete"] is False
    assert payload["coverage"]["modeled"] == 0
```

The third test is the one that matters most: with the pre-flight suppressed, nothing was checked, so the summary must not report a clean bill of health.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_preflight_cli.py -q -k coverage`
Expected: FAIL with `KeyError: 'coverage'`.

- [ ] **Step 3: Compute coverage in the assembler**

In `src/ai_sw_bridge/cli/_lint_preflight.py`, replace `assemble_lint_findings` with:

```python
def assemble_lint_findings(
    spec: dict[str, Any], *, no_preflight: bool
) -> tuple[list[LintFinding], list[dict[str, Any]], bool, dict[str, Any]]:
    """Run semantic lint and (unless suppressed) the geometric pre-flight.

    Returns ``(findings, findings_as_dicts, has_error, coverage)`` where
    ``has_error`` is True iff any finding is ERROR severity (the ERROR-only
    exit-gating contract) and ``coverage`` summarizes how much of the spec the
    geometric pre-flight modeled.

    When ``no_preflight`` suppresses the pre-flight entirely, coverage reports
    zero modeled features and ``complete: False`` -- nothing was checked, and
    saying so is the honest answer. It must not read as a clean bill of health.
    """
    findings = spec_lint(spec)
    if not no_preflight:
        from ..spec.preflight import coverage as preflight_coverage
        from ..spec.preflight import preflight

        pre = preflight(spec)
        findings = findings + pre
        cov = preflight_coverage(spec, pre)
    else:
        solid_ops = sum(
            1
            for f in spec.get("features", [])
            if not str(f.get("type", "")).startswith("sketch_")
        )
        cov = {
            "total": solid_ops,
            "modeled": 0,
            "skipped": solid_ops,
            "skipped_types": [],
            "complete": False,
        }
    findings_dicts = [f.to_dict() for f in findings]
    has_error = any(f.severity == "error" for f in findings)
    return findings, findings_dicts, has_error, cov
```

- [ ] **Step 4: Put coverage in the payload**

In the same file, change the unpack inside `lint_dryrun_response` from:

```python
    findings, findings_dicts, has_error = assemble_lint_findings(
        spec, no_preflight=getattr(args, "no_preflight", False)
    )
```

to:

```python
    findings, findings_dicts, has_error, cov = assemble_lint_findings(
        spec, no_preflight=getattr(args, "no_preflight", False)
    )
```

and add `"coverage": cov,` to the `payload` dict literal, immediately after the `"warning_count"` entry.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_preflight_cli.py tests/test_cli_build_dry_run.py -q`
Expected: PASS. If any other caller of `assemble_lint_findings` fails on the new arity, fix it — run `grep -rn "assemble_lint_findings" src/ tests/` to find them all.

- [ ] **Step 6: Document the payload key**

In `docs/tools_reference.md`, at the end of the `### CI integration (--lint)` section (after the paragraph ending "...surface those too."), add:

````markdown
### Coverage (`--lint`)

The geometric pre-flight models a subset of the feature vocabulary exactly and
**honestly skips** the rest rather than guessing. A clean exit therefore means
"nothing I checked is wrong", not "this will build". The `coverage` object in
the `--lint` payload says which of the two you got:

```json
"coverage": {
  "total": 12,
  "modeled": 9,
  "skipped": 3,
  "skipped_types": ["boss_extrude_midplane", "linear_pattern"],
  "complete": false
}
```

`total` counts solid-modifying features only — `sketch_*` features carry no
body, so they are not part of the denominator. `complete` is `true` only when
every one of them was modeled. Passing `--no-preflight` reports
`modeled: 0, complete: false`: nothing was checked.

Coverage gaps are **not** errors and never change the default exit code. To
gate on them, see `--strict`.
````

- [ ] **Step 7: Run the gates and commit**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
rm -f nul
black . && flake8 && mypy && pytest -q
git add src/ai_sw_bridge/cli/_lint_preflight.py tests/test_preflight_cli.py docs/tools_reference.md
git commit -m "feat(lint): report geometric pre-flight coverage in the JSON payload"
```

---

### Task 5: `--strict` gates on incomplete coverage at exit 8

**Files:**
- Modify: `src/ai_sw_bridge/cli/build.py` (argparse block only — 11 lines, 911 → 922, cap 925)
- Modify: `src/ai_sw_bridge/cli/_lint_preflight.py` (return-code branch)
- Modify: `docs/tools_reference.md:166-181` (exit-code table)
- Test: `tests/test_preflight_cli.py`

**Interfaces:**
- Consumes: `payload["coverage"]` (Task 4), `args.strict`.
- Produces: exit code `8` — "`--strict`: the geometric pre-flight could not model every feature".

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preflight_cli.py`:

```python
def test_strict_exits_eight_on_incomplete_coverage(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"].append(
        {"type": "linear_pattern", "name": "PAT", "seed": "EX", "count": 3}
    )
    rc, payload = _run(spec, tmp_path, "--strict")
    assert rc == 8
    assert payload["coverage"]["complete"] is False
    # ok tracks ERROR findings, not coverage -- an incomplete spec is not invalid
    assert payload["ok"] is True


def test_strict_exits_zero_when_coverage_is_complete(tmp_path):
    rc, payload = _run(_CLEAN, tmp_path, "--strict")
    assert rc == 0
    assert payload["coverage"]["complete"] is True


def test_strict_does_not_mask_a_geometric_error(tmp_path):
    # An empty-air cut is exit 6; --strict must not downgrade it to 8.
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"] += [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SKA",
            "plane": "Front",
            "width": 4,
            "height": 4,
            "center": {"x": 500.0, "y": 500.0},
        },
        {"type": "cut_extrude_blind", "name": "CUTA", "sketch": "SKA", "depth": 5},
        {"type": "linear_pattern", "name": "PAT", "seed": "EX", "count": 3},
    ]
    rc, _ = _run(spec, tmp_path, "--strict")
    assert rc == 6


def test_default_run_is_unaffected_by_the_new_flag(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"].append(
        {"type": "linear_pattern", "name": "PAT", "seed": "EX", "count": 3}
    )
    rc, _ = _run(spec, tmp_path)
    assert rc == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_preflight_cli.py -q -k strict`
Expected: FAIL — exit `2` from argparse, `unrecognized arguments: --strict`.

- [ ] **Step 3: Add the flag**

In `src/ai_sw_bridge/cli/build.py`, immediately after the `--no-preflight` block (which ends at line 418), insert exactly:

```python
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        help=(
            "Exit 8 when the geometric pre-flight could not model every "
            "solid-modifying feature. Default gating is unchanged: only "
            "ERROR findings gate, at exit 6."
        ),
    )
```

Verify the size gate immediately — this file is grandfathered shrink-only:

Run: `python tools/module_size_gate.py`
Expected: exit 0. `wc -l src/ai_sw_bridge/cli/build.py` should read 922, at or under the 925 baseline.

- [ ] **Step 4: Branch on it**

In `src/ai_sw_bridge/cli/_lint_preflight.py`, replace the lint-only return:

```python
        return payload, 0 if not has_error else 6
```

with:

```python
        if has_error:
            return payload, 6
        # --strict promotes an honest coverage gap to a failure. ERROR still
        # wins: 6 is never downgraded to 8. ``ok`` deliberately stays True --
        # it tracks ERROR findings, and an unmodeled feature is not a defect
        # in the spec, only a limit of what the seat-free tier can promise.
        if getattr(args, "strict", False) and not cov["complete"]:
            return payload, 8
        return payload, 0
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_preflight_cli.py -q`
Expected: PASS, all tests.

- [ ] **Step 6: Document exit 8**

In `docs/tools_reference.md`, add to the `ai-sw-build` exit-code list (after the `7` entry):

```markdown
- `8` — `--lint --strict` found the geometric pre-flight could not model every
  solid-modifying feature (see the `coverage` object). Only emitted with
  `--strict`; without it, coverage gaps never change the exit code.
```

And extend the paragraph beginning "A non-zero exit means the spec failed the gate:" to mention `8` alongside `6`, `3` and `2`.

- [ ] **Step 7: Check the docs gates**

Run: `python tools/doc_coverage_gate.py && python tools/honesty_gate.py`
Expected: exit 0 for both. The honesty gate rejects claims about behaviour that does not ship — `--strict` and exit `8` now do ship, so documenting them is truthful.

- [ ] **Step 8: Run the gates and commit**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
rm -f nul
black . && flake8 && mypy && pytest -q
python tools/module_size_gate.py
git add src/ai_sw_bridge/cli/build.py src/ai_sw_bridge/cli/_lint_preflight.py tests/test_preflight_cli.py docs/tools_reference.md
git commit -m "feat(lint): --strict exits 8 on incomplete geometric coverage"
```

- [ ] **Step 9: Verify the whole unit against the spec that started this, then push**

The 46-feature exerciser spec is the baseline the design measures against (spec §11). Under `--strict` it must now name what it could not check, instead of exiting 0 in silence:

```bash
cd /c/D/_grok_agnostic_test/bridge_work
PYTHONPATH=$PWD/src python -m ai_sw_bridge.cli.build \
  C:/D/_grok_agnostic_test/exerciser.json --lint --strict \
  > /c/D/_grok_agnostic_test/lint_strict_after33.json; echo "exit=$?"
```

Expected: exit `8`, and `coverage.skipped_types` in the output naming the unmodeled types. Record the before/after (`lint_out.json` is the original exit-0 run) — that pair is the evidence for the PR.

```bash
git remote -v   # origin is the local read-only repo -- push only to gh
git push gh fix/issue-33-preflight-coverage-signal
```

Open the PR against `master` with the before/after exit codes in the description, and link it from issue #33.

---

### Task 6: Resolve #40 per the Task 1 verdict

**Read `C:\D\_grok_agnostic_test\O2_VERDICT.md` first.** Apply exactly one branch. They are mutually exclusive.

**Files (branch A):**
- Modify: `docs/spec_reference.md` (cut-type sections), `docs/coordinate_conventions.md` §4
- The existing PR #44 branch `fix/issue-40-one-dir-cut-on-plane` is retained

**Files (branch B):**
- Modify: `src/ai_sw_bridge/spec/handlers/extrude.py`, `src/ai_sw_bridge/spec/schema.py`, `docs/spec_reference.md`
- The existing PR #44 branch is closed unmerged

**Interfaces:**
- Consumes: `O2_VERDICT.md` (Task 1).
- Produces: nothing consumed by later tasks.

#### Branch A — `VERDICT: KERNEL_CONSTRAINT`

The four-control direction space is fully spanned and the constraint is real. PR #44's guard is correct and may land.

- [ ] **A1: Record the verdict on the PR and the issue**

Post the four exit codes and the JSON excerpts from Task 1 as a comment on PR #44 and on issue #40, then edit the PR description to replace the "Open question carried on the PR" paragraph with the settled answer. The guard's docstring in `preflight.py` already asserts "always fails FeatureCut4" — that claim is now backed, so leave it.

- [ ] **A2: State the rule in the reference docs**

In `docs/spec_reference.md`, add this line to the `sketch` field row description of `cut_extrude_blind`, `cut_extrude_through_all` and `cut_extrude_midplane` (three separate edits — the tables are per-type):

```markdown
Must be a sketch on a **modeled face** (`*_on_face`). A one-directional cut sketched on a reference plane returns `FeatureCut4 None` at build time; use `cut_extrude_two_direction` to straddle a plane instead.
```

In `docs/coordinate_conventions.md` §4, promote the existing style advice to a rule by replacing "Build flat profiles as Front-plane bosses, then put any holes on the resulting `+z` face" with:

```markdown
Build flat profiles as Front-plane bosses, then put any holes on the resulting
`+z` face. This is a **rule, not a preference**: a one-directional cut
(`cut_extrude_blind` / `_through_all` / `_midplane`) sketched on a reference
plane fails at build time with `FeatureCut4 None`. The one sanctioned
plane-sketched cut is `cut_extrude_two_direction`, which straddles the plane —
give it a generous depth each way (a plate a few mm thick is typically cut
`±8`).
```

- [ ] **A3: Run the gates and commit**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
git checkout fix/issue-40-one-dir-cut-on-plane
rm -f nul
black . && flake8 && mypy && pytest -q && python tools/honesty_gate.py
git add docs/spec_reference.md docs/coordinate_conventions.md
git commit -m "docs: state the plane-sketched cut rule under every cut type"
git remote -v   # confirm before pushing -- origin is the local read-only repo
git push gh fix/issue-40-one-dir-cut-on-plane
```

#### Branch B — `VERDICT: BRIDGE_BUG`

`Dir=True` builds. The failure is a bridge-side direction-selection bug, PR #44's guard would be a **false ERROR**, and the never-false-ERROR invariant forbids landing it.

- [ ] **B1: Close PR #44 unmerged, with the evidence**

Post the Task 1 verdict on PR #44 explaining that the guard forbids a form that in fact builds, and close it. Re-title issue #40 to name the real defect: the builder never exposes `FeatureCut4`'s `Dir` axis, so a spec cannot express the working direction.

- [ ] **B2: Write the failing test**

Add to `tests/test_preflight.py` — a unit test on the arg tuple, no seat required:

```python
def test_cut_arg_builder_exposes_the_reverse_direction_axis():
    from ai_sw_bridge.spec.handlers.extrude import _cut4_args_2024

    args = _cut4_args_2024(
        end_cond=0, depth_m=0.006, flip=False, reverse_direction=True
    )
    assert args[2] is True, "arg 3 Dir must carry reverse_direction"


def test_cut_arg_builder_default_is_byte_for_byte_unchanged():
    from ai_sw_bridge.spec.handlers.extrude import _cut4_args_2024

    args = _cut4_args_2024(end_cond=0, depth_m=0.006, flip=False)
    assert args[2] is False
```

- [ ] **B3: Run the test to verify it fails**

Run: `pytest tests/test_preflight.py -q -k reverse_direction`
Expected: FAIL — `TypeError: _cut4_args_2024() got an unexpected keyword argument 'reverse_direction'`.

- [ ] **B4: Thread the axis through**

In `src/ai_sw_bridge/spec/handlers/extrude.py`, add `reverse_direction: bool = False` to the keyword-only signature of `_cut4_args_2024`, `_cut4_args_2025` and `_call_feature_cut`; change arg 3 from `False` to `reverse_direction`; and in each of `_build_cut_extrude_blind`, `_build_cut_extrude_through_all` and `_build_cut_extrude_midplane`, read it from the spec and pass it:

```python
    reverse = bool(feat.get("reverse_direction", False))
```

Add `reverse_direction` as an optional boolean to those three cut types in `src/ai_sw_bridge/spec/schema.py`, following the shape of the existing `flip` property, with the description: `"Reverse the cut direction (FeatureCut4 Dir). Distinct from flip, which selects which side of the profile is removed."`

- [ ] **B5: Run the tests to verify they pass**

Run: `pytest tests/ -q`
Expected: PASS. The default-path test proves the shipped arg tuple is unchanged for every existing spec.

- [ ] **B6: Document it and re-verify on the seat**

Add the field to the three cut-type tables in `docs/spec_reference.md`. Then — **operator-gated, same rules as Task 1** — re-run `probe_D_dir_true.json` with `"reverse_direction": true` on the cut through the normal build path and confirm exit 0.

- [ ] **B7: Run the gates and commit**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
git checkout master && git checkout -b fix/issue-40-expose-cut-direction
rm -f nul
black . && flake8 && mypy && pytest -q && python tools/module_size_gate.py
git add src/ai_sw_bridge/spec/handlers/extrude.py src/ai_sw_bridge/spec/schema.py tests/test_preflight.py docs/spec_reference.md
git commit -m "fix(build): expose FeatureCut4 reverse-direction axis to cut specs"
git remote -v
git push gh fix/issue-40-expose-cut-direction
```

---

### Task 7: Reconcile the `flip` documentation with what the code binds

Independent of the Task 1 verdict — true either way.

**Files:**
- Modify: `docs/spec_reference.md:658` and `:710` (the `flip` rows for `cut_extrude_blind` and `cut_extrude_through_all`)
- Test: none — documentation only

**Interfaces:**
- Consumes: nothing. Produces: nothing.

**Background:** `spec_reference.md` describes `flip` on a cut as *"Cut in -normal direction"* — a direction claim. The code binds `flip` to `FeatureCut4` arg 2, which the repo's own signature table (`sw_types.py:1218`) names `Flip`, while the arg named `Dir` (arg 3) is pinned `False`. `flip: true` on a cut has **zero** coverage: no shipped example uses it, and it appears in none of the 88 extrude/cut features across the 20 production specs surveyed. The doc therefore promises behaviour nothing has verified.

- [ ] **Step 1: Determine what to write from the Task 1 evidence**

Task 1's probe E ran `Flip=True` together with `Dir=True`; probe B in the original control set ran `Flip=True` with `Dir=False`. Between them the two booleans are separable. Write the row to match what was observed, not what was assumed.

- [ ] **Step 2: Replace both `flip` rows**

If Task 1 showed `Flip` selects which side of the profile is removed rather than the direction, replace the description in both rows with:

```markdown
| `flip` | no | boolean | Remove the material *outside* the profile instead of inside (`FeatureCut4 Flip`). This does **not** reverse the cut direction. Default `false`. Untested on a seat — no shipped example or production spec sets it. |
```

If Task 1 showed `Flip` does reverse the direction, keep the existing wording and instead append: `Verified on a seat 2026-09-05.`

- [ ] **Step 3: Check the honesty gate**

Run: `python tools/honesty_gate.py`
Expected: exit 0. The gate exists to reject claims about behaviour that does not ship; an "untested" qualifier is the honest form.

- [ ] **Step 4: Commit**

```bash
cd /c/D/_grok_agnostic_test/bridge_work
git add docs/spec_reference.md
git commit -m "docs: correct the cut flip description to match the bound arg"
```

---

## Out of scope for this plan

Named here so a later reader does not mistake the omissions for oversights:

- **Issues #28–#32, #34, #37** — Phase 2. PR #45 stays blocked until schema `description`s are backfilled (spec §5, E1); merging it as-is would blank hand-written prose.
- **Issue #42** — Phase 3, and its text needs correcting first (spec §4, D4).
- **Issues #35, #36, #38, #39, #41, #43** — Phase 4, no dependencies, no urgency.
- **`schema_v2`** — dormant, default-off, no published v2 artifact (spec §10).
