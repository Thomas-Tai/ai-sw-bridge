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

## Real MMP blocker (still unresolved)

**`FeatureCut4` PARAMNOTOPTIONAL on SW 2024 SP1**:
- 25-arg form failed
- 24-arg form untested (current builder.py uses it)
- Need to run `spike_e_cut.py` to discover the working signature

## Resume plan for next session

1. **Skip popup suppression work** -- accept manual ticks for now
2. Open SW with a part that has: a boss extrude + an active sketch on
   one face with a circle that doesn't fully cover it (this is the
   precondition for `spike_e_cut.py`)
3. Run `spike_e_cut.py` to find the FeatureCut4 arg-count that works on
   this build
4. Update `_call_feature_cut` in builder.py with the working signature
5. Re-run MMP build end-to-end
6. (Eventually) revisit popup suppression with one of:
   - VBA macro fallback: write SW macro that does AddDimension2 inside
     SW's context, invoke from Python via `RunMacro2`
   - `gencache.EnsureDispatch` with handcrafted typelib stubs for
     AddSpecificDimension OUT-param marshalling
   - Native Python COM with explicit VARIANT byref args

## Files referenced

- `spikes/phase0/spike_e_cut.py` -- written, NOT YET RUN
- `spikes/phase0/spike_f_close_pm.py` -- PM-pane dismissal probe (this session)
- `spikes/phase0/spike_h_sendkeys.py` -- key-injection probe (this session)
- `spikes/phase0/spike_h_window_probe.py` -- SW HWND discovery (this session)
- `spikes/phase0/spike_i_verify_toggle.py` -- toggle ID 8 verification (this session)
- `spikes/phase0/spike_j_specific_dim.py` -- AddSpecificDimension marshalling test (this session)
- `src/ai_sw_bridge/spec/builder.py` -- `_dismiss_dim_pane` remains a no-op;
  toggle code remains in place (harmless even though toggle 8 doesn't
  actually suppress on this build)
