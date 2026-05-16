# Phase 0 Spike Report

**Date**: 2026-05-16
**SW Version**: 32.1.0 (SOLIDWORKS 2024)
**Mode**: All three spikes executed direct-COM via pywin32 late-binding. No
VBA fallback needed.

## Result: GREEN — proceed to Phase 1

| Spike | Question | Outcome |
|---|---|---|
| A | FeatureExtrusion2 via late-binding? | **PASS** — 23-arg form worked first try |
| B | SelectByID face-by-coords on fresh feature? | **PASS** — `("", "FACE", 0, 0, 0.005)` selected outboard face |
| C | Add2 binding on fresh-built dim? | **PASS** — `D1@SpikeA_Box`: 5mm → 10mm via `"SPIKE_C_DEPTH"` |

All v0.2 architectural assumptions confirmed. JSON-spec → VBA-emitter is viable.

---

## Spike A — FeatureExtrusion2

**Did**: Built a 20×20×5 mm box on Front Plane via direct COM:
1. `doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)`
2. `SketchManager.InsertSketch(True)`
3. `SketchManager.CreateCornerRectangle(-0.010, -0.010, 0, 0.010, 0.010, 0)`
4. `SketchManager.InsertSketch(True)` (close)
5. `FeatureManager.FeatureExtrusion2(...)` (23-arg form)
6. `feature.Name = "SpikeA_Box"` (rename)

**Output**:
```json
{
  "status": "PASS",
  "original_name": "Boss-Extrude1",
  "renamed_to": "SpikeA_Box"
}
```

**Findings**:
- 23-arg FeatureExtrusion2 marshals cleanly through late-binding
- Returns a non-None CDispatch with readable `.Name`
- Feature is renameable immediately (`Feature.Name = "..."`)
- Auto-numbered name `Boss-Extrude1` reflects SW's internal counter
- **No OUT-parameter issues**, no COM-interface arg issues

**Gotcha hit during the spike**:
- First attempt used `Extension.SelectByID2(...Callout, ...)` — failed with
  `pywintypes.com_error: Type mismatch` (-2147352571). Known issue
  documented in `docs/known_gotchas.md`. Fix: use legacy 5-arg
  `doc.SelectByID(Name, Type, X, Y, Z)` on IModelDoc2.

---

## Spike B — SelectByID face-by-coordinates

**Did**: With SpikeA_Box still in the part:
1. `doc.ClearSelection2(True)`
2. `doc.SelectByID("", "FACE", 0, 0, 0.005)` — coord on outboard face center
3. `SketchManager.InsertSketch(True)` — opened sketch on selected face
4. `SketchManager.CreateCircle(0, 0, 0, 0.003, 0, 0)` — 6mm dia circle
5. `SketchManager.InsertSketch(True)` (close)

**Output**: Feature tree post-spike shows `SpikeA_Box` (Extrusion) →
`Sketch3` (ProfileFeature). Visual confirmation: the circle sketch is on
the box's outboard face.

**Findings**:
- `SelectByID` with empty Name + face-center coord works
- Face selection survives long enough to open a sketch on it
- `CreateCircle(xc,yc,zc, xp,yp,zp)` is the correct API (not
  `CreateCircleByRadius` — that doesn't exist; my first attempt failed with
  "Invalid number of parameters")

**Gotcha hit**:
- `doc.GetFeatureCount()` raised `TypeError: 'int' object is not callable`.
  Under late-binding, zero-arg methods auto-invoke as properties. Fix:
  access as `doc.GetFeatureCount` (no parens). Already documented in
  `sw_com.py:33`.

**Implication for v0.2**:
- The "face-by-coord" approach works for the trivial case (extrude depth
  known → outboard face at z=depth). For non-trivial cases (face on a
  feature that depended on a cut), the emitter must compute the
  face-center coord from the feature's local geometry. This is per-feature
  logic but tractable. **No need to fall back to enumerate-faces strategy.**

---

## Spike C — EquationMgr.Add2 binding

**Did**:
1. Created `spike_c_locals.txt` with `"SPIKE_C_DEPTH" = 10`
2. `eq.FilePath = <path>`
3. `eq.LinkToFile = True`
4. `eq.AutomaticRebuild = True`
5. `eq.UpdateValuesFromExternalEquationFile` (property, late-binding auto-invokes)
6. `eq.Add2(-1, '"D1@SpikeA_Box" = "SPIKE_C_DEPTH"', True)`
7. `doc.EditRebuild3`
8. Read `doc.Parameter("D1@SpikeA_Box").SystemValue`

**Output**:
```json
{
  "status": "PASS",
  "link_active": true,
  "add2_returned_index": 1,
  "dim_before_mm": 5.0,
  "dim_after_mm": 10.0
}
```

Equation manifest after Add2:
```json
[
  {"index": 0, "expression": "\"SPIKE_C_DEPTH\" = 10",
   "value": 10.0, "is_global_var": true},
  {"index": 1, "expression": "\"D1@SpikeA_Box\" = \"SPIKE_C_DEPTH\"",
   "value": 10.0, "is_global_var": false}
]
```

**Findings**:
- The Path C 4-step link sequence (`FilePath` → `LinkToFile=True` →
  `AutomaticRebuild=True` → `UpdateValuesFromExternalEquationFile`) is
  **mandatory**. Setting only `FilePath` leaves `link_active: false` and
  no globals load — Add2 then silently rejects equations that reference
  variables it can't resolve (returns -1 instead of an index).
- After full link sequence, Add2 accepts and returns 1 (≥0 = success)
- Dim `D1@SpikeA_Box` adopts the variable's value after rebuild
- The feature was created via API, then bound via API, with no human
  intervention — end-to-end build-and-bind round trip works

**Implication for v0.2**:
- The emitter's per-part output must include the full 4-step link block
  before any Add2 calls.
- The Path C bind pattern is correct as-is; we lift it into the emitter
  library wholesale.
- Dim names use the feature's *current* name (e.g. `D1@SpikeA_Box` after
  rename, not `D1@Boss-Extrude1`). The emitter should rename features
  immediately after creation, then bind using the new name.

---

## Late-binding scorecard (after Phase 0)

| API surface | Direct COM via late-binding? | Notes |
|---|---|---|
| `ISldWorks.ActiveDoc` | ✅ property | already validated |
| `IModelDoc2.SelectByID` (5-arg) | ✅ | use this, not SelectByID2 |
| `IModelDoc2.Extension.SelectByID2` (9-arg) | ❌ | Callout arg unmarshallable |
| `IModelDoc2.SketchManager.InsertSketch` | ✅ | |
| `IModelDoc2.SketchManager.CreateCornerRectangle` | ✅ | |
| `IModelDoc2.SketchManager.CreateCircle` | ✅ | NOT `CreateCircleByRadius` |
| `IFeatureManager.FeatureExtrusion2` (23-arg) | ✅ | works; first try |
| `IFeature.Name` (get + set) | ✅ | rename works immediately |
| `IFeature.GetTypeName2` | ✅ property | |
| `IModelDoc2.FirstFeature` / `GetNextFeature` | ✅ properties | walk the tree |
| `IModelDoc2.GetFeatureCount` | ✅ property | NO parens (late-binding) |
| `IModelDoc2.FeatureByPositionReverse(int)` | ✅ | |
| `IModelDoc2.ClearSelection2` | ✅ | |
| `IModelDoc2.EditRebuild3` | ✅ property | |
| `IModelDoc2.GetEquationMgr` | ✅ property | returns IEquationMgr |
| `IEquationMgr.FilePath` (get + set) | ✅ | |
| `IEquationMgr.LinkToFile` (set) | ✅ | required for vars to load |
| `IEquationMgr.AutomaticRebuild` (set) | ✅ | |
| `IEquationMgr.UpdateValuesFromExternalEquationFile` | ✅ property | |
| `IEquationMgr.Add2(idx, formula, solve)` | ✅ | returns int; -1=failure |
| `IModelDoc2.Parameter(name)` | ✅ | returns IDimension |
| `IDimension.SystemValue` (get) | ✅ | meters |

---

## Decisions for Phase 1

1. **Build via direct-COM, not VBA emission, where possible.** Spikes
   proved Python can drive SW for the entire build pipeline. The VBA
   emitter approach in the v0.2 plan was the conservative fallback; we can
   skip straight to direct calls.
   - **Caveat**: VBA emission still has value as a *diff artifact* (the
     generated `.bas` is the human-auditable record of what the AI built).
     Keep emission, but execute direct.

2. **Standardize on the 5-arg `SelectByID`** throughout the emitter.
   Document that the Callout overload is forbidden.

3. **EquationMgr link sequence** is a 4-call block. Bake it into a
   utility function `link_locals(doc, path)`. Don't let any emitter try to
   set `FilePath` alone.

4. **Rename features immediately after creation**. The auto-numbered names
   (`Boss-Extrude1`, `Sketch3`) are fragile — they change if the user reorders
   or if the spec's feature creation order shifts. Use spec's `name` as the
   single source of truth, rename right after creation, then bind dims by
   the renamed identifier.

5. **No need for Phase 0 yellow/red mitigations.** The architecture review's
   risk register flagged FeatureExtrusion2 as "Medium likelihood / Fatal
   impact" — we now downgrade to "Low / Fatal". Face-by-coord was "Medium /
   High" — downgrade to "Low / Medium" for parts where face coords are
   computable from feature geometry.

## Time spent

- Spike A: ~25 min (10 min for the SelectByID2 detour)
- Spike B: ~20 min (10 min for the CreateCircleByRadius detour)
- Spike C: ~15 min (5 min for the missing LinkToFile=True)
- Total: ~60 min — well under the budgeted 4-6 hours

## Next step

Per the architecture review:
> **Phase 1 — Minimum viable library (2-3 days, ~12-16 hours)**

Cost estimate now adjusts: the direct-COM path removes the per-feature VBA
emitter complexity. Revised Phase 1 estimate: **1.5-2 days, ~8-12 hours**
for the 6 feature types + spec schema + validator + ai-sw-build CLI +
cylinder example + MMP build.
