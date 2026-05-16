# MMP Phase 1 debug session

Captures findings from 2026-05-16 and 2026-05-17 debug runs so the next
session can pick up without re-deriving context.

## Session log

### 2026-05-16

Cylinder example (`examples/minimal_cylinder_v2/spec.json`) built fully
end-to-end via `ai-sw-build`. MMP build (10 features) failed on
`Cut_CouplerHole` with COM error `(-2147352561, 'Parameter not optional.',
None, None)` -- i.e. wrong FeatureCut4 arg count for this SW build.

Suspected at the time: a "Modify Dimension popup" was appearing on every
sketch and seemed to be related to a SW preference toggle that had become
sticky. Stopped to restart SW fresh next session.

### 2026-05-17

**Confirmed**: cylinder still builds end-to-end (`ok: true`) after SW
restart. The "regression" was perceptual -- popup was ALWAYS appearing
even on the original "working" build; AddDimension2 just blocks
synchronously until the user ticks, then returns success. The cylinder
build returning `ok: true` does NOT imply no manual ticking happened.

**Two separate dialogs appear per AddDimension2 call**:
1. Small floating Modify Dimension popup (numeric value + green/red ticks)
2. Left-side Dimension PropertyManager pane (green/red ticks)

Both must be dismissed before AddDimension2 returns.

### Spike F (PM-pane dismissal strategies)
- `doc.ClosePropertyManager()`: AttributeError (not a member)
- `doc.Extension.CloseAndDestroyPropertyManagers()`: AttributeError
- `doc.Extension.RunCommand(1, "")`: returns True but pane NOT dismissed
- "no dismiss" control: completes if user ticks manually

### Spike H (SendKeys variants)
- `sw.SendKeys("{ENTER}")`: did NOT dismiss the Modify popup. User had to
  click manually; elapsed ~85s.
- ctypes `keybd_event(VK_RETURN)` with `SetForegroundWindow(sw_main_hwnd)`:
  did NOT dismiss (focus stolen from modal to main window)
- ctypes `keybd_event(VK_RETURN)` blind (no focus change): DID dismiss
  the Modify popup, but then the PM pane was left active and still
  required manual tick
- ctypes double-ENTER (200ms apart): unreliable -- after first ENTER
  closes the popup, focus returns to the launching terminal, second
  ENTER doesn't land in SW

SW 2024 SP1 window class is NOT "SldWorks" -- it's an `Afx:*` class.
Title prefix "SOLIDWORKS" works for FindWindow.

### Spike I (toggle 8 verification)
- `GetUserPreferenceToggle(8)` returns False BOTH before and after our
  `SetUserPreferenceToggle(8, False)` call
- AddDimension2 still blocks 12s waiting for manual tick
- **Conclusion**: ID 8 is NOT `swInputDimValOnCreate` on this build, OR
  swInputDimValOnCreate doesn't actually suppress AddDimension2's popup
  on SW 2024 SP1

### Spike J (AddSpecificDimension alternative)
- All 9 DimType values (1-9) fail with `com_error('Type mismatch.', ..., 5)`
  at ~0.1s each
- Failure is in the COM-marshalling layer -- the OUT `Error` parameter
  doesn't bind via pywin32 late-binding
- Same class of problem as SelectByID2's Callout arg (documented
  in known_gotchas.md)
- **AddSpecificDimension is unusable via pywin32 late-binding**

## Current accepted limitation

`AddDimension2` requires manual ticking (1x Modify popup + 1x PM pane)
per dimension. For the cylinder (2 dims) this is 4 manual ticks. For
MMP (~15 dims) ~30 manual ticks.

This is annoying but not a blocker for the build pipeline -- the build
completes successfully once ticks are done.

## Real MMP blocker (RESOLVED -- dead end identified)

**Cuts are unreachable via pywin32 late-binding on SW 2024 SP1.**

Spike-E variants exhausted (all in `spikes/phase0/spike_e*.py`):

| Spike | Method | Result |
|-------|--------|--------|
| E     | FeatureCut4 23/24/25/26 args, THROUGH_ALL | All PARAMNOTOPTIONAL |
| E2    | FeatureCut4 24-arg BLIND/THROUGH_ALL/THROUGH_NEXT, Sd True/False, +FeatureCut3, +FeatureCut | All PARAMNOTOPTIONAL or wrong arg count |
| E3    | SelectByID2 marks 0/1/2/4/8/16/32 before FeatureCut4 | SelectByID2 fails Type mismatch (param 8 = Callout) |
| E4    | gencache typed FeatureManager wrapper | Returns CDispatch (late-bound); FeatureCut4 still PARAMNOTOPTIONAL. typelib probe fails "Invalid index". |
| E5    | FeatureExtrusion2 with overlap intent | Always produces "Boss", never "Cut". SW does not auto-detect cut intent. |
| E6    | FeatureExtrusion3 (combined boss/cut) at arg counts 24-28 | All fail PARAMNOTOPTIONAL or "Invalid number of parameters" |

The pywin32 late-binding cut path is dead on this build. Pattern:
**operations that produce material (boss) work fine; operations that
remove material (cut) all fail to marshal.** The exact reason is in
the COM IDL signatures for cut methods — pywin32 cannot generate proper
VARIANT type wrappers without the gencache stubs, which the SW typelib
won't produce ("Invalid index" on `GetTypeInfo`).

## RESOLUTION (2026-05-17 later): FeatureCut4 needs 27 args, not 24

The CHM API help shipped in
`Hardware/S1b_Conveyor/Model/example/api/sldworksapi.chm` was decompiled
via `hh.exe -decompile`. The `IFeatureManager~FeatureCut4.html` file
shows the true signature is **27 args** -- our spikes were missing
three optional-looking parameters:
- arg 22: `AutoSelectComponents` (bool)
- arg 23: `PropagateFeatureToParts` (bool)
- arg 27: `OptimizeGeometry` (bool, sheet metal only)

**Spike E7** verified the 27-arg form on SW 2024 SP1: produced
`Cut-Extrude1` of type "Cut". Builder updated. The PARAMNOTOPTIONAL
error means literally "missing required parameters", not a
marshalling issue. Our pywin32 late-binding pessimism was wrong.

Other CHM-driven fixes from the same investigation:
- `swEndCondThroughAll = 1` (we had 4, which is the deprecated
  `swEndCondUpToSurface`)
- `FeatureExtrusion2` is 23 args (confirmed in CHM)
- `FeatureExtrusion3` is also 23 args (not a combined boss/cut method,
  just a near-identical newer variant)

**Key lesson**: when an SW API call fails PARAMNOTOPTIONAL, the very
first check is whether the arg count matches sldworksapi.chm.
Decompile via `hh.exe -decompile <dst> <src.chm>` and grep the per-method
html file. Confirmed authoritative.

## Tooling added

- `tools/chm_extract.py` -- decompiled-CHM parser; produces JSON refs
- `tools/gen_api_markdown.py` -- JSON -> docs/api_reference.md
- `tools/gen_sw_types.py` -- JSON -> src/ai_sw_bridge/sw_types.py
  (enum constants + METHOD_SIGNATURES dict + assert_args runtime check)
- `docs/api_reference.json` -- machine-readable signatures of all 23
  in-use methods + 5 enums
- `docs/api_reference.md` -- human-readable form

## MMP end-to-end status: GREEN 10/10 (2026-05-17 final)

After all fixes (cut signature, end-cond enum, face-selection offset,
interleaved per-feature binding, -z face X-axis mirror, center-rect)
the MMP builds fully end-to-end with all 10 features and 7 parametric
bindings. Verified visually via screenshot: plate centered, coupler
hole concentric with flange recess, motor+frame hole pairs at ±15mm.

### What was actually wrong (the prior "v1 geometric limitation" was wrong)

The "face-based sketch origin must lie on material" hypothesis was a
red herring. **Spike K** built a box + through-hole + concentric circle
cut and it worked fine on all three workaround variants. The
MMP-specific failure was actually three separate bugs:

1. **Placeholder-vs-target mismatch**: parametric circle's placeholder
   diameter (6mm) was smaller than the existing through-hole (12mm),
   so the cut profile was entirely inside a void at the time
   `FeatureCut4` ran (bindings were applied AFTER all features).
   **Fix**: interleave bindings -- apply each feature's Add2 + rebuild
   immediately after the feature is built, so downstream geometry sees
   target sizes.

2. **-z face X-axis mirror**: SW mirrors sketch X when viewing a -z
   face from outside. `CreateCircle` uses sketch-local coords (the
   circle ends up at the spec u, v) but `SelectByID("SKETCHSEGMENT",...)`
   uses PART-frame coords. On -z faces, sketch (15, 0) is at part
   (-15, 0), so clicking at sketch (17, 0) misses the circle entirely.
   **Fix**: mirror u in the click coords for -z (and -x, -y) faces.

3. **Rectangle dim-resize asymmetry**: `CreateCornerRectangle` makes
   an unconstrained rect; when dims bind it from placeholder to target,
   SW's solver picks an arbitrary corner to anchor and grows the rect
   asymmetrically -- the centroid ends up off origin, so all downstream
   features (which use the origin as reference) are wrong.
   **Fix**: use `CreateCenterRectangle` instead -- it anchors via
   construction diagonals through the center, so resize stays centered.

### Spike K outcome

`spikes/phase0/spike_k_concentric_cut.py` tested three workaround
patterns against the original failure hypothesis. All three succeeded:
- A: face-based concentric circle (the supposed v1 limitation)
- B: plane-based sketch with `StartOffset` for blind cut at z-offset
- C: face-based off-center circle

The original v1 limitation hypothesis was disproved. The real bug was
the placeholder-vs-target mismatch (bug 1 above).

## Files referenced

- `spikes/phase0/spike_e_cut.py` -- arg-count sweep on FeatureCut4 (2026-05-17)
- `spikes/phase0/spike_e2_cut_args.py` -- arg-value variants + FeatureCut3/FeatureCut alternatives
- `spikes/phase0/spike_e3_sel_mark.py` -- SelectByID2 marks before FeatureCut4
- `spikes/phase0/spike_e4_typed_fm.py` -- gencache typed FeatureManager attempt
- `spikes/phase0/spike_e5_extrude_as_cut.py` -- FeatureExtrusion2 cut-mode check
- `spikes/phase0/spike_e6_extrusion3.py` -- FeatureExtrusion3 (combined boss/cut) at arg counts 24-28
- `spikes/phase0/spike_e7_cut_27args.py` -- **the FeatureCut4 resolution**; 27-arg works
- `spikes/phase0/spike_k_concentric_cut.py` -- disproved the "face-sketch origin must lie on material" hypothesis
- `spikes/phase0/spike_f_close_pm.py` -- PM-pane dismissal probe (2026-05-17)
- `spikes/phase0/spike_h_sendkeys.py` -- key-injection probe
- `spikes/phase0/spike_h_window_probe.py` -- SW HWND discovery
- `spikes/phase0/spike_i_verify_toggle.py` -- toggle ID 8 verification
- `spikes/phase0/spike_j_specific_dim.py` -- AddSpecificDimension marshalling test
- `tools/chm_extract.py` -- generic CHM signature/enum extractor
- `tools/gen_api_markdown.py` and `tools/gen_sw_types.py` -- generators
- `docs/api_reference.{json,md}` -- the verified reference
- `src/ai_sw_bridge/sw_types.py` -- auto-generated constants + assert_args
- `src/ai_sw_bridge/spec/builder.py` -- FeatureCut4 = 27 args (fixed),
  FeatureExtrusion2 = 23 args (verified), THROUGH_ALL = 1 (fixed),
  face selection uses 1-15mm offset fallback for holes
