# COM Failure-Mode Taxonomy

An incident registry, not a how-to. Every row is a real failure caught
in this codebase that had a misleading sentinel (the API said "OK"
when it wasn't). Use it when triaging a new "but the call returned
success and nothing happened" mystery — chances are it's already here.

**North-star principle:** *Verify the postcondition, not the return
code.* Every entry below exists because someone trusted a sentinel
value that didn't reflect reality. The mitigations all follow the
same pattern: stop trusting "the call returned, therefore it worked."

## How to read a row

- **Symptom** — what the failing call did or didn't do, observable
  without a debugger.
- **Real cause** — the underlying SW or COM behavior, usually
  documented somewhere obscure.
- **Diagnostic** — the one CLI invocation or code snippet that
  confirms the cause within seconds.
- **Mitigation** — code link to where this is currently caught.
- **First seen** — date + session/PR where it cost us hours so we
  could write this row.

## Registry

### Save / persistence

| # | Symptom | Real cause | Diagnostic | Mitigation | First seen |
|---|---|---|---|---|---|
| S-01 | `SaveAs3` returns 0 (NoError) but file is not on disk; `doc.GetSaveFlag` stays True | OneDrive / Dropbox sync client briefly holds an exclusive handle on the target folder; SW's write is queued but not yet visible when `out_path.exists()` is probed | `out_path.exists()` False AND `bool(doc.GetSaveFlag)` True after `SaveAs3` returns 0 | `_save_as_with_verification` in `src/ai_sw_bridge/spec/builder.py` — 3 independent postconditions with retry (200/400/600 ms) | 2026-05 DriveRoller session (P0.1) |
| S-02 | Early `SaveAs3` code returned `bool(err)` which is False for 0=NoError, so the success case was misreported as failure | `swFileSaveError_e` enum: 0 means NoError, non-zero means failure. Wrapping in `bool()` inverts the contract. | Compare with `int(err) == 0` instead of `bool(err)` | Same as S-01; the verifier checks `int(err) != 0` explicitly | Pre-P0.1 builder.py |

### Sketch / geometry creation

| # | Symptom | Real cause | Diagnostic | Mitigation | First seen |
|---|---|---|---|---|---|
| G-01 | `FeatureRevolve2` returns None for a sketch that looks valid in UI | Sketch geometry misses the body (wrong plane mapping). Most common: sketcher's local +Y mapped to wrong part axis on Top / Right Plane | `tools/feature_tree_diff.py capture` shows feature missing, OR `ai-sw-observe volume` reports `volume_mm3` unchanged across the revolve. Add a slug extrude on the same sketch and read its bbox to confirm sketch coords. | `_call_feature_revolve` emits an explicit diagnostic that names the most common causes; `_face_geometry._sketch_uv_to_part` is the canonical plane-axis remap | v0.7 revolve_cut development (Spikes ZG–ZN, 2026-05-21); [[feedback_sw_bridge_verify_geometry_first]] |
| G-02 | `FeatureCut4` returns None silently when the spec looks fine | Profile sketch is geometrically empty after a `Merge=True` boolean (e.g. parent body smaller than cut profile due to placeholder size in deferred-dim mode) | `ai-sw-observe volume` before vs after; delta=0 → silent no-op | `build()` per-feature `_apply_bindings` runs before the next downstream feature so cuts see resized geometry, not placeholders. Comment chain at `builder.py:1681–1693`. | MMP `Cut_FlangeRecess` debug 2026-05-16 |
| G-03 | `FeatureRevolve2` returns None — sketch contains no centerline | API requires a construction-line centerline INSIDE the sketch for SW to auto-pick the revolve axis | Walk the sketch via `inspect_sketch` (if it existed) or check that handler called `_draw_centerline_if_present` | Validator's `_check_references` rejects `revolve_boss` / `revolve_cut` whose target sketch has no `centerline` field (`validator.py:139–148`) | Pre-Spike X (2026-05-19) |
| G-04 | `AddDimension2` rejects coordinates / commits but D2 silently becomes DRIVEN (reference) | API `CreateCenterRectangle` adds a spurious Type-14 Midpoint relation absent from the UI's version, collapsing 2-DOF to 1-DOF | `Sketch.GetRelations` lists a Type-14 Midpoint not visible in the UI's Display/Delete Relations pane | `_strip_centerrectangle_midpoint_relation` in `_sketch_primitives.py`, called by both rectangle handlers AFTER `CreateCenterRectangle` and BEFORE `AddDimension2` | Spike ZF (2026-05-20); [[project_sw_bridge_deferred_dim_spike]] |

### Selection / accumulator

| # | Symptom | Real cause | Diagnostic | Mitigation | First seen |
|---|---|---|---|---|---|
| X-01 | `SelectByID2(... Append=True ...)` raises `com_error('Type mismatch', ..., 8)` | The 8th positional arg (`Callout`, OUT-typed IDispatch) cannot be marshalled by pywin32 late-binding | Try the same call without the Append arg — works. Confirms it's the Callout, not your inputs. | Use 5-arg legacy `SelectByID(name, type, x, y, z)` and apply marks retroactively via `SelectionMgr.SetSelectedObjectMark`. See `_mark_first_selection` in `builder.py`. | Spike R 2026-05-17 (linear_pattern), and prior MMP debug session |
| X-02 | Loop of `SelectByID('', 'EDGE', x, y, z)` only selects the LAST edge | 5-arg `SelectByID` is non-appending: every call replaces the prior selection | `SelectionMgr.GetSelectedObjectCount2(-1)` stays at 1 across N calls | Walk bodies, find edges by `GetClosestPointOn`, call `IEntity.Select2(Append=True, Mark=0)` — see `_select_edges_by_points` in `builder.py:673–758` | Spike Q3 2026-05-17 |
| X-03 | `GetErrorCode2(...)` raises pywin32 marshalling error | OUT parameter pywin32 can't unmarshal in late-binding mode | Try legacy `GetErrorCode` (auto-invoked property) — returns int directly | `observe.sw_get_feature_errors` uses `GetErrorCode` not `GetErrorCode2` | Pre-v0.2 (architecture.md) |

### Equation manager

| # | Symptom | Real cause | Diagnostic | Mitigation | First seen |
|---|---|---|---|---|---|
| E-01 | `EquationMgr.Add3(...)` returns -1 with no error | `Add3` (4 args) silently rejects on SW 2024 (rev 32.1.0); `Add2` (3 args) works | Compare return index: `Add2` returns >=0 on success, `Add3` returns -1 unconditionally on this build | All bindings go through `Add2` in `_apply_bindings` (`builder.py:1356–1367`); see [`docs/known_gotchas.md`](known_gotchas.md) | Pre-v0.2 |
| E-02 | Locals file edit doesn't reach the part — equations still show old values | `EditRebuild3` re-solves what SW already loaded but does NOT re-read the linked locals file | `ai-sw-observe equations` shows stale values; new values visible in the `*_locals.txt` file | Call `EquationMgr.UpdateValuesFromExternalEquationFile` BEFORE `EditRebuild3`; both bundled in `_force_rebuild` | Pre-v0.2 |
| E-03 | Driven (reference) dim can't be bound via `Add2` — Add2 returns -1 | An over-constrained sketch demotes the dim to driven; you can't make a driven dim depend on a variable | `ai-sw-observe equations` shows no entry for that dim name | --deferred-dim cadence: per-sketch replay BEFORE downstream features, so the sketch stays under-constrained until the dim adds (`builder.py:1654–1679`). For sketch G-04 above, also strip the Midpoint relation. | MMP 2026-05-19 |

### Popups / UX

| # | Symptom | Real cause | Diagnostic | Mitigation | First seen |
|---|---|---|---|---|---|
| U-01 | `AddDimension2` opens Modify-Dimension popup mid-build | App-level `swInputDimValOnCreate` toggle (ID=8) is read True but does NOT suppress the popup on SW 2024 SP1. No combination of doc-level toggles works either. | Set the toggle to False, call `AddDimension2`, popup still fires | Three build modes — see `build()` docstring (`builder.py:1534+`). Production paths: `--no-dim` (zero popups, no equation link) and `--deferred-dim` (popups batched per sketch). | Pre-v0.2 |
| U-02 | `_dismiss_dim_pane` is a no-op; PM-pane stays leaky after `AddDimension2` | `RunCommand(-1)` regressed cylinder; no clean dismiss API found yet | Tick a popup, observe pane state via UI inspector | Known limitation; documented in `_sketch_primitives.py`. Spike P1.6 (`spikes/v0_10/spike_p16_pm_dismiss.py`) prepared with untested approaches (RunCommand(2421), ClosePM after ForceRebuild3, toggle 78) — requires live SW session to run | MMP debug 2026-05 |

### Lane M — MCP transport (placeholder, populates when Lane M opens)

Reserved for FastMCP-specific (or chosen-framework-specific)
failure modes per [`docs/central_idea/spec.md`](central_idea/spec.md)
§6.8 risk register. Lane M is deferred per
[`decisions.md`](central_idea/decisions.md) 2026-05-23 entry #2
("adoption-driven"); rows below get populated only after the lane
opens.

Anticipated rows (sketched from `SolidworksMCP-python/CLAUDE.md`
runbook; promoted to real entries once observed):

| # | Symptom | Real cause | Diagnostic | Mitigation | First seen |
|---|---|---|---|---|---|
| M-XX | (placeholder) `AttributeError` at attribute lookup on a COM call from an MCP-handler thread | pywin32 late-binding surfaces cross-thread invocation as `AttributeError`, not `pywintypes.com_error` — boundaries that catch only the latter miss it | The error trace shows attribute access in the MCP transport thread, not the STA worker | Route every COM-touching call through `ComExecutor.submit(...)` (FR-v0.11-M-02); cross-thread `AttributeError` becomes a typed `MCPThreadingError` at the boundary | TBD (Lane M E1 port) |
| M-XX | (placeholder) `0x800401FD` / `0x80010108` after user closes SW mid-MCP-session | SW process death; cached `IDispatch` handle goes stale | `ComExecutor` `_sw_app_is_dead` flag flips on `_DEAD_HRESULTS` (spec.md §6.9) | `--reconnect` flag fires `pythoncom.CoInitialize` on a fresh STA thread + re-Dispatch + `RevisionNumber` floor check | TBD |

### Add-in interference (W7.1)

Placeholder rows for add-in-related failure modes. Populated when
`spikes/v0_13/spike_addin_enumeration.py` returns results from a live
SW session. See [`docs/addins_research.md`](addins_research.md) for
the full research note.

| # | Symptom | Real cause | Diagnostic | Mitigation | First seen |
|---|---|---|---|---|---|
| A-01 | (placeholder) Build succeeds but output dimensions differ from spec targets between runs | SOLIDWORKS Toolbox add-in auto-resizes inserted hardware or rewrites mate references | `ai-sw-observe addins` lists "SOLIDWORKS Toolbox" in `known_problematic` | `--disable-addins` flag warns at build start; `--strict-addins` blocks build (rc=4) until user disables via Tools → Add-Ins | TBD (spike pending) |
| A-02 | (placeholder) `SaveAs3` returns 0 but file is unchanged; S-01 verifier reports misleading cause | SOLIDWORKS PDM add-in intercepts save events; vault-bound files require check-out | `ai-sw-observe addins` lists "SOLIDWORKS PDM Standard" or "SOLIDWORKS PDM Professional" in `known_problematic` | `--disable-addins` / `--strict-addins` pre-flight check; user must check out file or disable PDM add-in | TBD (spike pending) |
| A-03 | (placeholder) Custom properties contain unexpected values after build | 3DEXPERIENCE PLM Connector captures save events and modifies custom properties | `ai-sw-observe addins` lists "3DEXPERIENCE PLM Connector" in `known_problematic`; `ai-sw-observe custom_props` shows unexpected entries | `--disable-addins` / `--strict-addins` pre-flight check | TBD (spike pending) |
| A-04 | (placeholder) `GetEnabledAddIns` returns None or raises; enumeration fails entirely | SW build does not expose the API when no add-ins are loaded, or the method is absent on older versions | `sw_get_enabled_addins()` returns `ok=True, addins=[], error="api_not_present"` | Fail-soft: build proceeds with a stderr warning. No add-in interference possible when the API is absent. | TBD (spike pending) |

## How to add a row

When you spend > 30 minutes triaging a "the API said success and nothing
happened" failure:

1. Add a row in the appropriate section above. The row is the artifact;
   the conversation, branch, and PR are not.
2. Pick a stable ID prefix:
   - `S-*` save / persistence
   - `G-*` geometry creation
   - `X-*` selection / accumulator
   - `E-*` equation manager
   - `U-*` popup / UX
   - `A-*` add-in interference (W7.1; see `docs/addins_research.md`)
   - `M-*` Lane M / MCP transport (populates when Lane M opens)
   - new prefix if none fit (document the convention here)
3. Cross-link: the **Mitigation** column MUST point to the file/function
   where the fix lives. Tests must reference the row ID in a comment
   so future grep finds them together.

## What this doc is NOT

- Not a tutorial. See [`docs/architecture.md`](architecture.md) and the
  spec primer for that.
- Not a complete API reference. See
  [`docs/api_reference.md`](api_reference.md) for the CHM-extracted
  surface.
- Not a list of "things to do later" — that's the enhancement plan.
  This is strictly an incident registry of failures that have already
  cost time.
