# W68 Wave-4 — Offline Worker Prompts (4 pattern-family lanes)

**Authored 2026-06-21 (W0).** Four net-new feature lanes, all under the
**IFeatureManager** interface (owning interface CONFIRMED against
`docs/sw_api_full.md` lines 8295–8587 — this de-risks the curve_driven
wrong-object trap that crashed the seat: do NOT call these on `IModelDoc2`).

Each lane is the standard **3-file convention** (touch NOTHING else):
- `src/ai_sw_bridge/features/<kind>.py`
- `spikes/v0_2x/spike_<kind>.py`
- `tests/features/test_<kind>.py`

Base every branch on **`origin/master`** tip (`03a2453`). Branch name
`feat/w68-<kind>`. `SPIKE_STATUS = "UNFIRED"`. Do **NOT** touch
`features/__init__.py`, `verify.py`, `mutate.py`, or `docs/` — W0 wires the
registry (`_register_lane`) and flips GREEN only after a live seat-proof.

**Canonical handler template** = the shipped `features/sketch_driven_pattern.py`
(read it verbatim). Reuse its exact spine:
- `from ..selection.live import select_entity`; `from . import verify`
- `SPIKE_STATUS = "UNFIRED"`; `VERIFY_CLASS = verify.FeatureClass.ADDITIVE_SOLID`
- `_metrics(doc)` → `verify.solid_metrics(doc)`
- seed selection via `doc.FeatureByName(name)` → `select_entity(feat, mark=4)`
- `_fire(...)` with the **callable-or-property guard** (`method = fm.X; method(...) if callable(method) else None`)
- `ForceRebuild3(False)` after fire
- gate with `verify.gate_additive_solid(d_faces, d_vol)`
- **fail-closed** (return `(False, reason)`, never raise)
- NO module-level self-register block (registration is W0's `_register_lane`)

**Spike template** = the shipped `spikes/v0_2x/spike_sketch_driven_pattern.py`:
- `import _feature_spike_fixtures as fx`; `fx.connect()`; build a fixture with a
  real seed feature; measure faces/vol before; fire the handler; measure after;
  probe `GetTypeName2` of new feature nodes; **save→reopen survival** via
  `fx.save_and_reopen`; write `_results/<kind>.json`; print per-finding to stderr.
- Headless-runnable, A7 GetTypeName2, direct-API diagnostic on failure.
- The spike is the W0 HARNESS — write it to be debuggable at the seat. The
  handler is the DELIVERABLE — keep it clean.

**Tests** = mirror `tests/features/test_<sibling>.py`: offline unit tests only
(mock the COM doc), assert the arg marshaling + fail-closed branches + that the
handler is dormant (registry-disjoint) while UNFIRED.

---

## LANE 1 — `chain_pattern`

**Signature (IFeatureManager, line 8326):**
```
FeatureChainPattern(Int32 PitchMethod, Boolean FlipDirection, Boolean FillPath,
    Int32 Number, Double Spacing, Boolean GroupOneFlipPlane,
    Boolean GroupTwoChain, Boolean GroupTwoFlipPlane, Int32 AlignMethod,
    Int32 Options) -> Feature
```
Patterns a seed feature along a **chain of connected edges/curves**. Pre-select
the SEED (mark 4) and the chain path. Spacing is in **meters** (Double); convert
mm→m at the boundary.

**UNKNOWNS the spike must resolve (log which the solver rejected):**
- The path-chain selection mark — try **mark=1** first (linear-pattern family
  convention), fall back to mark=2, then mark=0. Log which seats.
- `SelectByID2` type string for the chain path — try `"EDGE"` first, fall back
  to `"SKETCHSEGMENT"` (same EDGE/SKETCHSEGMENT ambiguity the curve_driven brief
  flagged).
- `PitchMethod` enum (`swChainPatternPitchType_e`) — reflect the enum; the spike
  fires with the spacing-defined value (likely 0) and logs.
- `AlignMethod` / `Options` — fire with 0/0, log if rejected.

**Fixture:** block + a seed boss-extrude, plus a chain of edges along one face to
ride. Gate = `gate_additive_solid` (additive seed replicated). Witness: ΔFaces>0
∧ ΔVol>0; report `GetTypeName2` of the new node.

---

## LANE 2 — `dimension_pattern`

**Signature (IFeatureManager, line 8339):**
```
FeatureDimensionPattern(Int32 Num1, Double Spacing1, Int32 Num2, Double Spacing2,
    Boolean DiagonalOnly, String DName1, String DName2, Boolean VaryInstance)
    -> Feature
```
Patterns a seed by **driving named dimensions** (DName1/DName2). This is the
trickiest lane: the spike must first CREATE the fixture with **named dimensions**
the pattern can drive (e.g. the seed boss's position dimensions), then pass those
exact dimension names as `DName1`/`DName2`.

**UNKNOWNS:**
- The exact dimension-name string format — SOLIDWORKS dimension names are
  `"<DimName>@<FeatureOrSketchName>"` (e.g. `"D1@Sketch2"`). The spike must read
  back a real dimension name from the fixture (via the dimension's `.FullName` /
  `IDisplayDimension`) and feed THAT, not a guessed literal. **Log the exact
  string used.**
- Seed selection mark — mark=4 (pattern-family), confirm.
- `Num2`/`Spacing2`/`DName2` — for a 1-direction pattern pass `Num2=1`,
  `Spacing2=0`, `DName2=""`; confirm the kernel accepts the empty 2nd direction.
- `DiagonalOnly` / `VaryInstance` — fire `False`/`False`, log.

**Fixture:** block + seed boss whose location is governed by a NAMED dimension.
Gate = `gate_additive_solid`. Witness ΔFaces>0 ∧ ΔVol>0; report `GetTypeName2`.
**This lane may BOUNCE if the dimension-name contract can't be satisfied
headlessly — that is an acceptable honest finding; log the rejected name.**

---

## LANE 3 — `table_driven_pattern`

**Signature (IFeatureManager, line 8520):**
```
InsertTableDrivenPattern(String FileName, Object PointVar, Boolean UseCentrod,
    Boolean GeomPatt) -> Feature
```
Patterns a seed at **explicit XY coordinates** supplied as a point array. Prefer
the **in-memory point array** path: `FileName=""`, `PointVar =
VARIANT(VT_ARRAY|VT_R8, [x0,y0, x1,y1, ...])` (flat doubles, **meters**). This is
the cleanest pattern lane — no external dimension dependency, no chain geometry.

**UNKNOWNS:**
- `PointVar` marshaling — `Object` = a VARIANT. Build it as
  `VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [..flat doubles..])`. If that
  ghosts, probe the sibling `InsertTableDrivenPattern2(FileName, PointVar,
  UseCentroid, GeomPattern, PropVisProps)` (line 8521, 5-arg) and the
  `IInsertTableDrivenPattern(FileName, Count, ref Double PointArr, UseCentrod,
  GeomPatt)` form (line 8402, explicit Count + by-ref array). Log which seats.
- Point coordinate frame — likely **model-space meters**; the spike fires 2–3
  points offset from the seed and verifies the instances land there.
- Seed selection mark — mark=4, confirm.

**NOTE the SAFEARRAY doctrine** ([[reference_makepy_safearray_faceset_unlock]]):
if a bare Python list ghosts, wrap it in an explicit `VARIANT(VT_ARRAY|VT_R8, …)`
— a bare list is the silent-no-op trap. **This is the exact class of wall that
masquerades as a kernel ghost.** Readback-probe if the API exposes a count.

**Fixture:** block + seed boss. Gate = `gate_additive_solid`. Witness ΔFaces>0 ∧
ΔVol>0 with instance count matching the point array; report `GetTypeName2`.

---

## LANE 4 — `derived_pattern`

**Signature (IFeatureManager, line 8427):**
```
InsertDerivedPattern2() -> Feature
```
**Zero-arg.** Derives a NEW pattern on the current body from an **existing pattern
feature** copied from elsewhere (the SW "derived pattern" = reuse another
pattern's instance layout). The entire contract is in the **pre-selection**:
the spike must select the source pattern feature (and/or the seed faces) BEFORE
the zero-arg call.

**UNKNOWNS (this lane is selection-only — that IS the puzzle):**
- What must be pre-selected — try selecting an EXISTING pattern feature (build a
  `FeatureLinearPattern5` in the fixture first via the shipped W21 linear-pattern
  path, then select it) plus the seed faces to derive onto. Probe marks 4 / 1 / 0.
- This API may require a **second body or a parent pattern in the same doc** to
  derive FROM. The spike builds: body + seed boss + one real linear pattern, then
  selects the seed-to-derive + the source pattern and fires the zero-arg call.
- **High BOUNCE risk** — derived patterns are often a UI-context feature. If it
  ghosts (ret None, Δ0) across the selection permutations, that is an honest
  Route-C/OOP wall finding. Log every selection combo tried and its Δ.

**Fixture:** block + seed boss + a shipped linear pattern (the "source"). Gate =
`gate_additive_solid`. Witness ΔFaces>0 ∧ ΔVol>0; report `GetTypeName2`. **Do not
guess API string identifiers on geometry you can't see — enumerate selection
permutations in the spike and let the seat adjudicate.**

---

## Reception (W0 runs on delivery)

`tools/w0_feature_lane_gate.sh <kind> --local` — audits 3-file isolation +
dormancy (registry-disjoint while UNFIRED) + offline pytest. Then W0 fires
`spike_<kind>.py` on the singleton live seat, confirms the effect-witness, flips
UNFIRED→GREEN, wires `_register_lane`, and guarded-FF pushes. **"Lane done" =
offline-green + dormant, NOT shipped.**

**Predicted disposition** (set expectations honestly): `table_driven_pattern` is
the strongest (clean in-memory point array, SAFEARRAY doctrine de-risks the
marshaling); `chain_pattern` is moderate (selection-mark probe like the shipped
siblings); `dimension_pattern` and `derived_pattern` carry real BOUNCE risk
(named-dimension contract / UI-context derivation) — bounce-with-evidence is a
valid outcome, not a failure.
