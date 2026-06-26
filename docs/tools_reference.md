# Tools Reference

Every CLI command, every flag. All commands print one JSON object to stdout, exit 0 on success, non-zero on failure.

## `ai-sw-probe`

COM connectivity check.

**Args**: none.

**Returns**:
```json
{
  "ok": true,
  "sw_revision": "32.1.0",
  "active_doc": { "path": "...", "type": "Part", "title": "..." },
  "error": null
}
```

## `ai-sw-observe`

Read-only inspection. `<tool>` is required, `--key=value` args parsed as JSON.

### `active_doc`
```powershell
ai-sw-observe active_doc
```
Returns path, type ("Part"|"Assembly"|"Drawing"), type_id, title, is_dirty.

### `feature_errors`
```powershell
ai-sw-observe feature_errors
```
Walks the feature tree. Returns `total_features` and `issues[]` (only non-OK features). Each issue has `name`, `type_name`, `depth`, `state_code`, `state`, `description`, `suppressed`.

### `equations`
```powershell
ai-sw-observe equations
```
Returns linked-file path, link_active flag, manager solver status, equation_count, and `equations[]` with `index`, `expression`, `value`, `is_global_var`, `is_suppressed`.

### `screenshot`
```powershell
ai-sw-observe screenshot
ai-sw-observe screenshot --width=1280 --height=720
ai-sw-observe screenshot --filename=\"my_view.png\"
ai-sw-observe screenshot --fit_view=true
```
Captures the active viewport. Default 640×360 (about 50KB, ~300 vision tokens if loaded into a multimodal model). Pass 1280×720 for detail. Output goes to `./captures/` (or `$AI_SW_BRIDGE_CAPTURES`).

### `measure`
```powershell
# Two-entity: select both in SW UI, then call:
ai-sw-observe measure

# Single named: programmatically select one entity by name:
ai-sw-observe measure --entity_a=\"Face<1>\"
```
Returns `distance`, `deltax/y/z`, `angle_rad`, `arc_length`, `area`, `perimeter`. SW returns these in document units (meters internally for MMGS). Two-entity *named* selection is unsupported on most builds (`SelectByID2` callout arg fails late-binding marshaling).

### `mate_errors`
```powershell
ai-sw-observe mate_errors
```
**Active doc must be an assembly.** Walks the MateGroup sub-features. Returns `mate_count`, per-mate `{name, type, status, components}`, and a summary `{by_status: {ok: N, over_defined: M, ...}, broken_count: K}`.

## `ai-sw-mutate`

Propose-Approve-Execute mutations.

### `propose`
```powershell
ai-sw-mutate propose --var=PART_DIAMETER --new_value=30.0
ai-sw-mutate propose --var=PART_DIAMETER --new_value=\"= \\\"OTHER_VAR\\\" + 5\"
```
The active part must have a linked `*_locals.txt`. The new_value can be a literal number or any SW expression (mind your shell quoting). Returns `proposal_id`, `old_expression`, `new_expression`, `line_index`, `state: "proposed"`.

### `dry_run`
```powershell
ai-sw-mutate dry_run --proposal_id=abc123def456
```
Applies the change, force-rebuilds, captures before/after manager status + var value, **rolls back**. Returns `before`, `after`, `rebuild_ok`, `rolled_back`, `state: "dry_run_ok"` or `"dry_run_broke"`. Rollback is verified by reading the file back and comparing against the snapshot.

### `commit`
```powershell
ai-sw-mutate commit --proposal_id=abc123def456
```
Only allowed if proposal state is `dry_run_ok`. Re-applies the change, rebuilds, attempts `doc.Save()`. Returns `doc_saved`, `state: "committed"`. `doc_saved: false` is NOT an error — it just means the active doc has no dimensions consuming the changed variable.

### `undo_last_commit`
```powershell
ai-sw-mutate undo_last_commit
```
Finds the most recently committed proposal, restores its `snapshot_text`, rebuilds, saves. Returns `proposal_id`, `var`, `restored_to`, `doc_saved`.

## `ai-sw-codegen`

### `parameterize`
```powershell
ai-sw-codegen parameterize recorded.swp spec.json
```
Reads the binary `.swp`, extracts VBA via `oletools.olevba`, injects equation-link + dim-binding blocks per the spec, writes `recorded_parameterized.bas` next to the input.

**spec.json schema**:
```json
{
  "locals_path": "C:\\absolute\\path\\to\\your_locals.txt",
  "bindings": [
    { "dim": "D1@<feature-or-sketch-name>", "var": "<VAR_NAME>" },
    ...
  ]
}
```

Returns the output path + `next_steps` array reminding you to paste & F5 in VBE.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `AI_SW_BRIDGE_CAPTURES` | `./captures/` | Where `sw_screenshot` writes PNGs |
| `AI_SW_BRIDGE_PROPOSALS` | `./proposals/` | Where `sw_propose_local_change` etc. persist JSON records |

Both directories are created on first use.

## Exit codes

- `0` — `ok: true` in the returned JSON
- `1` — `ok: false` (the tool ran but reported a failure)
- `2` — bad command-line arguments

Stderr is unused; everything goes to stdout. If the JSON parse fails, the exit code is your fallback signal.

---

# SW-version compatibility matrix runner

_Consolidated from the former `sw_version_matrix_runner.md`._


## What this is

`tests/version_matrix/` provides a parametrise-based harness so seat tests can
run against two SOLIDWORKS major versions (N and N-1) in one pytest invocation.
The scaffold was introduced in W58 to address D-4 (the one open cross-cutting
recommendation in `central_idea_vs_implementation_audit.md`).

**Revision map** (from `src/ai_sw_bridge/spec/_version_resolver.py`):

| Revision string | Major | SW release |
|---|---|---|
| `32.x.x` | 32 | SW 2024 (the proven build; usual **N** in dev) |
| `33.x.x` | 33 | SW 2025 (adjacent target; usual **N-1** in the matrix) |

---

## Normal dev / CI (N only)

Nothing to configure.  Tests tagged `sw_version_n1` are auto-skipped with a
clear reason:

```
SKIPPED — N-1 SW seat not configured — set AI_SW_BRIDGE_N1_REVISION=<major> to enable;
           see docs/sw_version_matrix_runner.md
```

The N-variant of every parametrised test runs normally alongside the rest of
the suite.

---

## Enabling the N-1 run (W0 versioned seat)

### Prerequisites

1. A second SOLIDWORKS installation (e.g. SW 2025, major revision **33**) is
   present on the machine.
2. The N-1 SOLIDWORKS process is running and visible to the COM Running Object
   Table (ROT).  `sw_com.get_sw_app()` must be able to attach to it.

### Steps

```powershell
# 1. Launch the N-1 SW process (SW 2025) — COM ProgID includes the major:
#    SldWorks.Application.33 for SW 2025.
#    The process must be in the foreground before the tests run.

# 2. Set the env var so the skip wiring lifts:
$env:AI_SW_BRIDGE_N1_REVISION = "33"

# 3. Run the version matrix suite (isolated from the rest to avoid SEH risk):
pytest -m sw_version_n1 tests/version_matrix/ -v

# 4. Or run the full suite; N-1 items run alongside N items:
pytest -n auto tests/
```

### How tests select the right seat

Tests that use `SW_VERSION_MATRIX` receive `sw_version` as `"N"` or `"N-1"`.
They are responsible for wiring the appropriate COM target.  A typical pattern:

```python
@pytest.mark.parametrize("sw_version", SW_VERSION_MATRIX)
@pytest.mark.solidworks_only
def test_feature_on_both_versions(sw_version, live_runtime):
    if sw_version == "N-1":
        # Re-attach sw_com to the N-1 process before exercising the handler.
        # (Implementation detail: future fixture or helper — not yet wired.)
        pytest.skip("N-1 COM re-attachment fixture not yet implemented")
    # ... exercise the handler normally against the N seat ...
```

The fixture-level N-1 re-attachment is the next step after the scaffold lands
and is gated on the first real seat-gated N/N-1 test being authored.

---

## Marker reference

| Marker | Registered in | Effect |
|---|---|---|
| `sw_version_n1` | `tests/version_matrix/conftest.py` | Skipped unless `AI_SW_BRIDGE_N1_REVISION` is set |
| `solidworks_only` | `tests/conftest.py` | Skipped unless a live SW session is detected |

Both markers combine: an N-1 seat test should carry both `solidworks_only`
(needs any SW session) and the implicit `sw_version_n1` mark from
`pytest.param("N-1", marks=pytest.mark.sw_version_n1)`.

---

## Backlog reference

- Audit item: **D-4** (`central_idea_vs_implementation_audit.md` §5 #24)
- Burndown entry: `BACKLOG_BURNDOWN.md` §A #24 — `OFFLINE`, Gate R5
- Wave: **W58**
