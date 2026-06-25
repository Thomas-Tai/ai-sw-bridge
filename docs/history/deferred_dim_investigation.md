# `--deferred-dim` Investigation Report

Compiled summary of the spike series and architectural attempts behind the v0.6 `--deferred-dim` build mode. Captures what shipped, what doesn't work, and the empirical evidence for each dead end. Pairs with [known_limitations.md](known_limitations.md) (user-facing) and the spike scripts under [`spikes/v0_6/`](../spikes/v0_6/).

**Date:** 2026-05-19 (original); 2026-05-20 update.

> **🟢 RECT LIMITATION RESOLVED 2026-05-20.** Spike ZF identified the root cause as a spurious Type-14 (Midpoint) relation added by API-side `CreateCenterRectangle` that the UI version does not add. Fix is `_strip_centerrectangle_midpoint_relation()` in [`builder.py`](../src/ai_sw_bridge/spec/builder.py), called from both rectangle handlers. Rectangle specs (including MMP) now ship clean equation links in `--deferred-dim` mode. The "what we tried" sections below are kept as historical record of routes that did NOT work — useful for understanding the SW 2024 SP1 API surface limits and avoiding revisiting dead ends in future investigations.
>
> **Popup-tick behavior unchanged:** `--deferred-dim` still requires one popup tick per dimensioned entity (same total as inline mode). The user-visible improvement is *predictable per-sketch batching*, not popup-free execution. See section §2 for the empirical evidence on popup suppression dead-ends.

---

## Context

**Goal:** give `ai-sw-build` a third build mode alongside default-parametric (live link, popups everywhere) and `--no-dim` (no popups, no link). The target: live equation link to `locals.txt` AND no popups scattered through the multi-minute geometry phase.

**Environment:** SOLIDWORKS 2024 SP1 (RevisionNumber 32.1.0), Python 3.14, pywin32 late-binding (no typelib-compiled stubs), Windows 11.

---

## What ships

`--deferred-dim` mode. Per-sketch popup batching:

1. **Geometry phase:** each sketch handler builds at PLACEHOLDER sizes (no `AddDimension2` calls inline). Records `DeferredDim` entries describing the dims to add.
2. **Per-sketch deferred replay:** immediately after each handler returns, `build()` re-enters that sketch via `EditSketch`, replays all of its `AddDimension2` calls in one session, closes via `InsertSketch(True)`.
3. **Per-feature bindings:** `EquationMgr.Add2` applied for that feature's parametric `{rhs}` fields, then `EditRebuild3` rebuilds with the bound values.
4. Loop to next feature.

**Verified working:**
- `minimal_cylinder_v2` (2 features, 1 dim on a circle sketch): GREEN end-to-end, both bindings (`D1@SK_Body`, `D1@Extrude_Body`) attach correctly.
- `motor_mount_plate` (10 features, 8 dims across 5 sketches): builds without error, 7 of 8 bindings attach correctly.

**Verified failing in a documented way:** the rectangle sketch `SK_PlateSlab` in MMP has its **second** edge-dim (`D2@SK_PlateSlab`) demoted to a **driven** (reference) dimension by SW after the close/re-open cycle. The binding `"D2@SK_PlateSlab" = "S1B_MMP_W"` is rejected by SW's solver and appears red in Equation Manager with the tooltip:

> *"A driven or reference dimension is not selectable as the dependent variable of the equation."*

CLI emits a `WARN` when this combination is detected.

---

## Why the rectangle case fails — what we know

**Necessary conditions for the failure (all present in inline mode that works, AND in deferred mode that fails — so they're not sufficient explanations on their own):**

- `CreateCenterRectangle` (the rectangle handler's primitive) — Z5 showed it produces 6 segments: 4 lines + 2 construction diagonals.
- Two edge-dims (D1 = top edge / width, D2 = left edge / height).
- `EquationMgr.Add2` bindings for both dims.

**Difference between working inline mode and failing deferred mode:**

- Inline mode adds D1 and D2 **inside the same EditSketch session as `CreateCenterRectangle`**, while the sketch is still in its original "fluid" edit state.
- Deferred mode adds D1 and D2 **after a close (`InsertSketch(True)`) and re-open (`EditSketch`)** — even if D1 and D2 are added within ONE re-opened session.

The hypothesis we currently believe:

> When SW closes an under-defined sketch, it "freezes" the un-dimensioned entities at their current coordinate lengths to prevent arbitrary shape collapse during model rebuilds. When you reopen and add D1, the construction-diagonal/symmetry relations force opposite sides to move. SW treats the orthogonal lengths as a stiff wireframe until proven otherwise. Adding D2 over-constrains the sketch → SW demotes D2 to driven.

**D1 lands as driving** because it replaces one of the implicit length-constraints.
**D2 lands as driven** because by then the sketch is fully-defined and D2 is geometrically redundant.

---

## What we tried, with errors

Five hypothesis families. Each was tested with a dedicated spike before being ruled out.

### 1. Toggle-based popup suppression (Spike Y / Spike Y-probe)

**Files:** [spike_y_instant2d_toggle.py](../spikes/v0_6/spike_y_instant2d_toggle.py), [spike_y_probe_only.py](../spikes/v0_6/spike_y_probe_only.py)

Hypothesis: a hidden second popup pathway (Instant2D) requires a separate toggle to suppress, in addition to `swInputDimValOnCreate=False`.

**Result: FALSIFIED.**

| Config | toggle 8 | toggle 200 | AddDimension2 returned in | Popup required tick? |
|---|---|---|---|---|
| CONTROL (unchanged) | False (existing) | True | 5.1 ms | YES |
| only toggle 8 = False | False | True | 27,048 ms | YES |
| only toggle 200 = False | False | False | 1.8 ms | YES |
| BOTH = False | False | False | 1,440 ms | YES |

Toggle 433 (the codestack-canonical "Instant2D" lead) was **not togglable** on this SW build — `SetUserPreferenceToggle(433, X)` did not change the readback value. Probed 8 candidates around 433; only IDs 200, 201, 95 were togglable. None suppressed the popup.

---

### 2. SendKeys / SendKeystrokes for autonomous popup dismissal (Spike Z2 / Z2b)

**Files:** [spike_z2_sendkeys_dismiss.py](../spikes/v0_6/spike_z2_sendkeys_dismiss.py), [spike_z2b_probe_sendkeys.py](../spikes/v0_6/spike_z2b_probe_sendkeys.py)

Hypothesis: spawn a background thread that sleeps then calls `sw.SendKeys("{ENTER}")` to dismiss popups autonomously.

**Result: FALSIFIED. The method is unreachable from late-bound pywin32.**

Errors:
```
sw.SendKeys("{ENTER}")        →  AttributeError('SldWorks.Application.SendKeys')
sw.SendKeystrokes("{ENTER}")  →  AttributeError('SldWorks.Application.SendKeystrokes')
sw.SendKeyStrokes("{ENTER}")  →  AttributeError
sw.sendkeystrokes(...)        →  AttributeError
sw.sendkeys(...)              →  AttributeError
```

Tried `EnsureDispatch`:
```
win32com.client.gencache.EnsureDispatch("SldWorks.Application")
→ TypeError('This COM object can not automate the makepy process - please run makepy manually for this object')
```

`dir(sw)` and `dir(doc)` errored with `com_error('Element not found')` / `com_error('Invalid index')` — late binding cannot enumerate dispatch members on these objects at all.

**Root cause:** keystroke-injection methods may exist in the SW typelib but are invisible to `pywin32.Dispatch`. Reaching them requires manually running `makepy.py` against `sldworks.tlb` — a yak we have not shaved.

---

### 3. Construction-diagonal deletion (Spike Z6)

**File:** [spike_z6_delete_diagonals.py](../spikes/v0_6/spike_z6_delete_diagonals.py)

Hypothesis: the 2 construction diagonals from `CreateCenterRectangle` over-constrain the sketch after close-reopen → demote D2 to driven. Deleting them should free the DOF for D2.

**Result: FALSIFIED.**

Three cases, all fresh parts:

| Case | Diagonals deleted | After-delete segment count | D2 outcome |
|---|---|---|---|
| Z6a baseline | 0 | 6 segs / 2 construction | Red equation, D2 driven (visual confirm) |
| Z6b | 2 (both) | 4 segs / 0 construction | Red equation, D2 driven (visual confirm) |
| Z6c | 1 | 5 segs / 1 construction | Red equation, D2 driven (visual confirm) |

Each Add2 binding test wrote `"D2@SK_*" = "TEST_VAR"` and got `idx=1` (binding accepted into eqmgr) and `eq.Value=5.0` — but visual inspection confirmed D2 is still driven and the equation is still red. **The eqmgr accepts the equation; the solver rejects driving D2.**

**Side note on the API used:**
- `SketchSegment.Select4(False, None)` → `com_error('Type mismatch')` (pywin32 can't marshal `None` for the callout param).
- `SketchSegment.Select4(False, win32com.client.VARIANT(VT_DISPATCH, None))` → works.

---

### 4. `IDisplayDimension.DrivenState` override (Spike Z7 Route 1)

**File:** [spike_z7_driven_state_fix.py](../spikes/v0_6/spike_z7_driven_state_fix.py)

Hypothesis: capture the `IDisplayDimension` returned by `AddDimension2` and explicitly set `dim.DrivenState = swDimensionDriving (=1)` to bypass SW's auto-demotion.

**Result: FALSIFIED. Property not exposed via late-binding.**

Errors:
```
dim2.DrivenState (read)   →  AttributeError('<unknown>.DrivenState')
dim2.DrivenState = 1       →  AttributeError("Property '<unknown>.DrivenState' can not be set.")
```

Same family of typelib-only-access limitation that killed Z2 / Z2b.

---

### 5. Mid-edit `EditRebuild3` between dims (Spike Z7 Route 3)

Hypothesis: keep the sketch open through D1 → mid-edit `EditRebuild3` → D2 (one EditSketch session, no close-reopen). The rebuild "relaxes" frozen-line state so D2 lands driving.

**Result: FALSIFIED. Mid-edit rebuild breaks downstream selection.**

Sequence observed:
```
[Z7b.D1] segment select=True
[Z7b.D1] AddDimension2 -> dim=True
-- mid-edit EditRebuild3 --
   EditRebuild3 -> True
[Z7b.D2] primary segment pick (-0.01, 0, 0)  -> select=False
[Z7b.D2] fallback pick    (-0.01, 0.001, 0)  -> select=False
[Z7b.D2] fallback pick    (-0.01, -0.001, 0) -> select=False
[Z7b.D2] fallback pick    (-0.0099, 0, 0)    -> select=False
[Z7b.D2] fallback pick    (-0.00999, 0, 0)   -> select=False
[Z7b.D2] fallback pick    (-0.01, 0.005, 0)  -> select=False
[Z7b.D2] fallback pick    (-0.01, -0.005, 0) -> select=False

Add2('"D2@SK_B" = "Z7_TEST_VAR"') -> idx=-1
Parameter(D2@SK_B) after rebuild = None mm
```

After the mid-edit rebuild, **`SelectByID("", "SKETCHSEGMENT", ...)` can't find any segment at any of 7 probed coordinates around the left edge.** Subsequent AddDimension2 is never called; the binding fails (idx=-1) because there's no D2 to bind to.

**Mechanism unclear:** the rebuild itself succeeds (`EditRebuild3 -> True`), but it puts the sketch into a state where external-COM `SelectByID` returns False even though the geometry is visibly unchanged.

---

### 6. Manual `CreateCornerRectangle` + diagonal + Midpoint relation (Spike Z8)

**File:** [spike_z8_corner_rect.py](../spikes/v0_6/spike_z8_corner_rect.py)

Hypothesis: `CreateCenterRectangle` is a macro-feature with hidden state that misbehaves across close-reopen. Build the rectangle manually via `CreateCornerRectangle` (4 plain lines, no hidden symmetry) + explicit construction diagonal + Midpoint relation (to recover centering invariant). Standard relations should behave better.

**Result: INCONCLUSIVE due to two compounding confounders, investigation halted.**

**Confound 1 — toggle state leak:**
```
[Z8a.D1] segment select=True
[Z8a.D1] AddDimension2 -> dim=False    ← !!
[Z8a.D2] segment select=True
[Z8a.D2] AddDimension2 -> dim=True
```

A prior `--deferred-dim` build had left `swInputDimValOnCreate=False`. With the popup suppressed, D1's AddDimension2 returned None silently (no dim created), so D2 had no D1 to anchor against. Z8 was patched to explicitly toggle popup behavior, but the toggle change wasn't reconciled with what production uses.

**Confound 2 — `AddSketchRelation` unreachable:**
```
sm.AddSketchRelation     → AttributeError
sm.AddRelation           → AttributeError
sm.AddSketchConstraint   → AttributeError
```

Tried multiple naming variants with both integer enum (`swConstraintType_MIDPOINT=3`) and string ("Midpoint") arguments. None resolved. We did NOT find the correct late-bound name for adding a sketch relation.

`SketchSegment.ConstructionGeometry = True` does work (read-modify-write succeeded — `False -> True` round-trip), so we CAN mark a line as construction, but we can't apply a Midpoint relation between two entities from late-bound pywin32 using the names tried.

**This route may still be viable** if (a) the toggle confound is fixed and (b) the correct `AddSketchRelation`-equivalent API path is found.

---

### 7. Per-sketch dim grouping in `_apply_deferred_dims` (architectural variant)

Not a spike — a refactor that was tested directly against MMP.

Hypothesis: one EditSketch per dim (open, add, close, open, add, close) is what's causing the demotion. Grouping all of a sketch's dims into one EditSketch session (open, add, add, close) should work.

**Result: FALSIFIED.** Re-tested on MMP with the grouping refactor; `D2@SK_PlateSlab` is still red. Multi-dim addition within a single EditSketch session doesn't help if the session was opened via re-entry — the freeze had already occurred.

---

### 8. Resolve-`{rhs}`-upfront for deferred-dim mode (earlier architectural variant)

Hypothesis: build geometry at literal target sizes (same as `--no-dim`), then add deferred dims at the end against already-correct geometry. The dims would have no work to do and just attach as bindings.

**Result: FALSIFIED.** Caused the SAME red-D2 issue at the rectangle (because the dim landed redundant against the already-sized rectangle and got demoted to driven). Also showed an entirely different failure mode — when the geometry phase was built at placeholders without per-feature binding/rebuild:

```
FeatureCut4 returned None  (on Cut_FlangeRecess)
```

A cut feature with a 20.5mm sketch can't operate on a placeholder host that's only 10×10mm. Confirmed the original "MMP Cut_FlangeRecess scenario" warning in the code is real — per-feature binding+rebuild is necessary mid-loop, you can't truly defer geometry-correctness to the end.

---

## Diagnostic gaps we hit

These limit how far we can probe SW state from external Python:

| API surface | Status | Impact |
|---|---|---|
| `IDimension.IsDriving` / `IDisplayDimension.DrivenState` | Returns `None` / raises `AttributeError` | Cannot programmatically detect whether a dim landed as driving vs driven; must inspect SW UI visually |
| `EquationMgr.Status(i)` | Returns same fallback for all entries; not the per-equation status flag | Cannot detect red equations programmatically; must use SW UI |
| `dir(sw_dispatch)`, `dir(doc)` | `com_error('Element not found')` or `'Invalid index'` | Cannot enumerate available COM methods to discover the right API name |
| `EnsureDispatch("SldWorks.Application")` | `TypeError: COM object can not automate the makepy process` | Cannot generate the typelib stubs that would expose `DrivenState`, `SendKeystrokes`, etc. without running `makepy.py` manually |
| `AddSketchRelation` / `AddRelation` / `AddSketchConstraint` | All return `AttributeError` | Cannot apply Midpoint/Coincident/Parallel/etc. relations between sketch entities from late-bound code |

---

## Things we know SW does that we don't understand

1. **Why a fresh-rect inline AddDimension2 cycle produces driving D2, but the same rectangle re-opened later produces driven D2.** What state changes during `InsertSketch(True)` that the re-opened session can't reverse?
2. **Why mid-edit `EditRebuild3` breaks `SelectByID` for sketch segments.** The geometry visually unchanged; segments are presumably still there.
3. **Why deleting both construction diagonals from a CenterRectangle doesn't help.** Suggests the demotion mechanism isn't the diagonals themselves — there are additional implicit relations we're not seeing.
4. **What relation/constraint set SW believes is on a CenterRectangle after close.** Z5/Z6 reported `relations=0` via `GetSketchRelations`, but `GetSketchRelations` errored with `AttributeError`, so the value is unreliable. The sketch is over-constrained against external dims yet shows zero relations on inspection.

---

## Open leads worth re-visiting if priorities change

1. **Run `makepy.py sldworks.tlb` to generate typelib stubs.** Would unblock `DrivenState`, `SendKeystrokes`, and likely the `AddSketchRelation` API path. Roughly 1-2 sessions of plumbing once you commit to it; brittle across SW upgrades.

2. **Z8 retry with confounds fixed.** Explicitly set `swInputDimValOnCreate=True` for the spike, and find the right `AddSketchRelation` path (likely via makepy stubs). If `CornerRectangle` + Midpoint dodges the demotion, the fix is "use CornerRectangle in `--deferred-dim` rectangle handlers".

3. **VBA macro fallback (Direction B').** Emit a tiny `.bas` file with the AddDimension2 call and run via `RunMacro2`. The hypothesis is that **VBA context** behaves differently from external COM and may honor things that late-binding doesn't. Untested.

4. **Locals.txt live-link check on the rectangle.** We never got to confirm whether the equation REALLY does nothing or just looks broken — the active doc got displaced during spike runs. If the equation actually does drive D2 (just shows red cosmetically), the limitation is much smaller than documented.

5. **Sketch-relations introspection via `MakeSelectedDriven` / `MakeSelectedDriving`.** These are documented SW methods on ISketchManager — we never tried them. If reachable, they'd directly answer the demotion question and potentially fix it.

---

## What's in the repo right now

**Commit `e6c5291` — spike trail (12 files, 2437 lines):**
- `spike_y_instant2d_toggle.py`, `spike_y_probe_only.py`
- `spike_z1_deferred_dim.py`, `spike_z2_sendkeys_dismiss.py`, `spike_z2b_probe_sendkeys.py`, `spike_z3_two_deferred_dims.py`, `spike_z4_multifeature_deferred.py`
- `spike_z5_center_rect_dims.py`, `spike_z6_delete_diagonals.py`, `spike_z7_driven_state_fix.py`, `spike_z8_corner_rect.py`
- `probe_eqmgr_state.py` (helper)

**Commit `5ac3b14` — `v0.6` feature (4 files, 442+/45−):**
- [src/ai_sw_bridge/spec/builder.py](../src/ai_sw_bridge/spec/builder.py) — `DeferredDim`, `ctx.deferred_dim`/`ctx.deferred_dims`, 5 handlers wired, `_apply_deferred_dims` with per-sketch grouping, `build(..., deferred_dim=False)` parameter
- [src/ai_sw_bridge/cli/build.py](../src/ai_sw_bridge/cli/build.py) — `--deferred-dim` flag, mutual-exclusion check, rectangle WARN
- [README.md](../README.md) — three-mode table with caveats
- [docs/known_limitations.md](known_limitations.md) — `--deferred-dim` section with the rectangle limitation

Tests 84/84 pass. Black clean.
