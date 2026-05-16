# MMP Phase 1 debug session — 2026-05-16 (incomplete)

Captures the half-finished debugging of the MMP end-to-end build so the next
session can pick up without re-deriving context.

## What worked

The cylinder example (`examples/minimal_cylinder_v2/spec.json`) built fully
end-to-end via `ai-sw-build` earlier in this session. Tree confirmed:
SK_Body + Extrude_Body, equations 0-3 (2 globals + 2 dim bindings). That
proved the v0.2 architecture is sound.

## What failed

MMP build (10 features) failed on `Cut_CouplerHole` with COM error
`(-2147352561, 'Parameter not optional.', None, None)` — i.e. wrong
FeatureCut4 arg count for this SW build.

But before that, **the Modify Dimension popup started appearing on every
sketch** including the cylinder which had previously been silent. Cylinder
regressed during the debug session.

## Diagnoses

### Bug 2 (FeatureCut4 signature)

Tried 25-arg form first (failed: PARAMNOTOPTIONAL). Reduced to 24 args
(reordering NormalCut to position 18). Untested due to popup blocking the
re-run.

### Bug 1 (Modify popup escapes suppression)

`sw.SetUserPreferenceToggle(8, False)` had worked for Spike D (rectangle on
plane) and the cylinder build. But on MMP it stopped working at SK_CouplerHole
(first face-based sketch).

Tried fixes that made it worse, not better:
1. Added `doc.SetUserPreferenceToggle(8, False)` after NewDocument.
   Result: cylinder regressed — popup appeared on the rectangle that had
   previously been suppressed.
2. Reverted #1 + added `doc.Extension.RunCommand(-1, "")` after each
   AddDimension2. Result: cylinder STILL hit the popup.
3. Reverted both. Cylinder STILL hits the popup.

**Working hypothesis**: `swInputDimValOnCreate` is a persistent SW preference,
not just a session toggle. Setting it programmatically *toggles* the stored
value rather than overriding for the session. Possibly: the GetUserPreferenceToggle
returned the wrong value (or my interpretation was wrong), so we wrote
True instead of False at some point and now it's stuck True in the registry.

## Recovery plan for next session

Order of operations:
1. **Quit SOLIDWORKS completely** (File → Exit, wait for it to fully close).
2. **Open SW Tools → Options → Document Properties (or System Options) →
   Sketch**. Look for "Prompt to set driven state" or similar — the GUI
   exposure of `swInputDimValOnCreate`. Set to OFF (unchecked).
3. **Open a blank Part**.
4. Re-run cylinder build: `ai-sw-build examples/minimal_cylinder_v2/spec.json`.
   Should pass without any popup.
5. If cylinder passes: investigate Bug 2 (FeatureCut4). Spike with
   `spikes/phase0/spike_e_cut.py` first to find the right arg count on this
   build, before retrying MMP.
6. If cylinder still fails: the preference is more sticky than expected.
   Check `%APPDATA%\SolidWorks\SolidWorks 2024\swSettings.sldreg` or
   equivalent for the saved toggle value.

## Code state at session end

- `src/ai_sw_bridge/spec/builder.py`: reverted close to its earlier-working
  state. `_dismiss_dim_pane` is a no-op (the RunCommand attempt was reverted).
  The cut signature is the 24-arg form (untested).
- `examples/motor_mount_plate/spec.json`: complete spec for MMP. Untested
  end-to-end.
- `examples/minimal_cylinder_v2/spec.json`: previously verified, currently
  regressed due to SW preference state.

## Lesson for the project

Don't toggle SW user preferences via API on persistent registry-backed keys
without restoring on exit. The `try/finally restore` block at the end of
`build()` would only fire if Python reached the end of `build()` — if the
process is killed mid-build (which happened multiple times in this session),
the restore never runs and the preference is left in whatever state we
wrote.

**Future builder pattern**: wrap the entire SW preference manipulation in
a context manager that registers an `atexit` handler in case the process
exits abnormally. Or, simpler: use a SW pref that can be restored from a
known-good baseline file at session start.
