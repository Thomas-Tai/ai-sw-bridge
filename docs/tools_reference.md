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
