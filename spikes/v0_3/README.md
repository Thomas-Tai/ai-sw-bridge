# v0.3 spikes: chamfer, linear pattern, mirror

Three spike scripts that probed the SW COM API for the three new v0.3
primitives before wiring them into the bridge proper.

## Results (2026-05-17, SW 2024 SP1)

| Spike | Result | Path used by bridge |
|---|---|---|
| Q chamfer | GREEN | `InsertFeatureChamfer` (8-arg, single call). CreateDefinition probe of `swFmChamfer` failed (not in 0..49 range or has no `EqualDistance` property accessible) -- single-call is the path. |
| R linear pattern | GREEN, after one pivot | See "selection pivot" below |
| S mirror | GREEN, same pivot | Same approach as Spike R |

## Selection pivot (Spikes R and S)

`doc.Extension.SelectByID2` -- the marked-selection variant we wanted --
raises `com_error('Type mismatch.', ..., 8)` under pywin32 late binding.
Position 8 is `Callout` (`IDispatch` OUT-typed); same class of failure
documented in `spikes/phase0/MMP_DEBUG_SESSION.md`.

Workaround that works:

1. Select the **direction edge (pattern) / mirror plane (mirror)** via
   the plain 5-arg `IModelDoc2::SelectByID(name, type, x, y, z)`. This
   is non-appending -- it starts a fresh selection set.
2. Apply the selection mark via `ISelectionMgr::SetSelectedObjectMark(
   AtIndex=1, Mark, Action=swSelectionMarkSet=0)`.
3. Add the **seed feature** with `IFeature::Select2(append=True, mark)`.
   `Select2` takes only `(append, mark)` -- no name lookup, no Callout.
   `IFeature` instances are already in hand from prior `BuiltFeature`
   records, so no SelectByID2 is needed.

**Order matters:** step 1 must precede step 3, because `SelectByID`
is non-appending and would clear the seed if done second.

## Why spike first

The same lessons from Phase 0 apply: pywin32 late-binding has surprising
failure modes (OUT-param marshalling, hidden arg counts) that no amount of
CHM-reading can fully predict. Each spike builds a tiny test geometry,
calls the candidate API, and reports GREEN/RED. The handlers in
`src/ai_sw_bridge/spec/builder.py` only get written for what passes.

## How to run

From the ai-sw-bridge venv with SOLIDWORKS open (any state -- the spike
creates its own new doc):

```powershell
.\.venv-freshtest\Scripts\activate
python spikes\v0_3\spike_q_chamfer.py
python spikes\v0_3\spike_r_linear_pattern.py
python spikes\v0_3\spike_s_mirror.py
```

Each prints a `GREEN` or `RED (rc=...)` per attempted path. Paste the full
stdout back into the conversation; the bridge code gets shaped to whichever
path worked.

## What's being tested

### Spike Q -- chamfer

Two API paths attempted in sequence:

- **Path 1**: `InsertFeatureChamfer(Options, ChamferType, Width, Angle,
  OtherDist, V1, V2, V3)` -- single-call, 8 args, present since SW 2005 FCS.
  CHM doesn't mark it obsolete (unlike fillet's single-call equivalent).
- **Path 2**: `CreateDefinition(swFmChamfer)` + `IChamferFeatureData2`
  property set + `CreateFeature(data)` -- SW 2020+ canonical, parallel to
  the fillet pipeline that already ships.

If Path 1 works the handler is dead simple. Path 2 is the fallback.
`swFmChamfer` numeric value isn't in the decompiled CHM enum table so it's
probed empirically.

### Spike R -- linear pattern

Tests `FeatureLinearPattern5` (22 args, marked obsolete in CHM but
historically still works). The harder question is whether
`doc.Extension.SelectByID2` -- needed to apply selection MARKS that
distinguish seed-feature from direction-reference -- marshals correctly
under late binding. SelectByID2 has previously failed with Callout
OUT-param errors; if the marked-selection variant we need works without
those, the bridge can ship the pattern primitive.

### Spike S -- mirror

`InsertMirrorFeature2` (5 args, simplest of the three). Same
SelectByID2 marshalling risk as Spike R.

## Exit codes

- `0` -- at least one API path worked GREEN
- `2` -- could not create a new doc (no template found)
- `3` -- all attempted paths RED; spike conclusions printed in detail
- `99` -- unhandled exception; full traceback printed
