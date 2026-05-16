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

## Path forward decision (next session)

Two viable options to unblock cuts:

**Option A: VBA macro fallback for cut features only**
- Keep direct-COM for everything else (boss, sketch, dim, equation)
- Emit a tiny `.bas` per cut, invoke via `RunMacro2`
- The cut runs in SW's own VBA context where FeatureCut4 works
- Reference: `Path C` (record-and-parameterize) already proved RunMacro2
  works on `.swp` files (OLE compound, not plain text). For cuts, we
  emit a fresh macro per call rather than reusing recorded ones.
- Pro: focused workaround, minimal disruption to existing builder.py
- Con: requires `.swp` packaging (OLE compound document writing) OR
  the user must paste .bas content manually

**Option B: Different automation library**
- pywin32 is unique in its marshalling limitations. Alternatives:
  - `comtypes` (different COM library) — may handle the IDL differently
  - `pyswx`, `SolidWorks.Interop` via pythonnet — both .NET-based, may
    bypass the COM marshalling layer
- Pro: potentially solves cuts, AddDimension2 popup, and SelectByID2 in
  one go
- Con: major library migration; unproven on this build; pyswx is dormant

## Suggested next-session approach

1. Spike A (VBA macro fallback for cuts) — 60-90 min:
   - Generate a `.swp`-as-OLE wrapping the cut VBA
   - OR fall back to "Path C lite": save `.bas`, ask user to paste +F5
   - Build a single cut via this path; confirm geometry result
2. If A works: refactor builder.py to route `cut_extrude_*` features
   through the VBA path. Keep boss/sketch/dim direct-COM.
3. Re-run MMP build end-to-end.

## Files referenced

- `spikes/phase0/spike_e_cut.py` -- arg-count sweep on FeatureCut4 (2026-05-17)
- `spikes/phase0/spike_e2_cut_args.py` -- arg-value variants + FeatureCut3/FeatureCut alternatives
- `spikes/phase0/spike_e3_sel_mark.py` -- SelectByID2 marks before FeatureCut4
- `spikes/phase0/spike_e4_typed_fm.py` -- gencache typed FeatureManager attempt
- `spikes/phase0/spike_e5_extrude_as_cut.py` -- FeatureExtrusion2 cut-mode check
- `spikes/phase0/spike_e6_extrusion3.py` -- FeatureExtrusion3 (combined boss/cut) at arg counts 24-28
- `spikes/phase0/spike_f_close_pm.py` -- PM-pane dismissal probe (2026-05-17)
- `spikes/phase0/spike_h_sendkeys.py` -- key-injection probe
- `spikes/phase0/spike_h_window_probe.py` -- SW HWND discovery
- `spikes/phase0/spike_i_verify_toggle.py` -- toggle ID 8 verification
- `spikes/phase0/spike_j_specific_dim.py` -- AddSpecificDimension marshalling test
- `src/ai_sw_bridge/spec/builder.py` -- `_dismiss_dim_pane` remains a no-op;
  `_call_feature_cut` will need rerouting through VBA path (Option A above)
