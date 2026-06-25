# W64 — Reference Geometry epoch · GLM/Sonnet worker briefs

> **Epoch:** W64 (successor to W63 reference/datum features).
> **Cluster:** the **datum spine** — `ref_plane`, `ref_axis`, `coordinate_system`, `ref_point`.
> **Why now:** reference geometry is the documented dependency for anchoring sketches/patterns/mates on user-defined datums (`api_coverage_roadmap.md` §5.2, §5.11). It is the same `IFeatureManager`/`IModelDoc2` datum-feature COM surface W63 just proved out (`bounding_box`/`com_point`/`mate_reference`), so the W63 doctrine transfers 1:1.
> **Architecture:** all four ship as `features/<kind>.py` HANDLER_REGISTRY lanes (the post-W56 seam), **not** `builder.py` 5-place primitives. Each module exposes `create_<kind>(doc, feature, target) -> tuple[bool, str|None]` + a `SPIKE_STATUS` sentinel; `features/__init__.py` gates `HANDLER_REGISTRY["<kind>"]` on `SPIKE_STATUS == "GREEN"`.

---

## 0. MANDATORY shared doctrine (every lane — non-negotiable)

These are W62/W63 seat-proven laws. A brief that violates one is rejected at `seat-prefire-review`.

1. **Reflect the signature FIRST — never trust the CHM or a recollection.** The authoritative arg-count source is `SolidWorks.Interop.sldworks.dll` (`C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist\`, asm `32.1.0.123`), reflected via PowerShell. Each lane's signature below is ALREADY reflected — but the worker re-confirms on the seat before authoring the call. (W63 caught `mate_reference` as 12-arg-not-13 and `com_point` on the wrong interface this way.)

2. **`CDispatch` escape via `typed_qi`.** The live `doc.FeatureManager` arrives out-of-process as a bare late-bound `CDispatch` (`dir(fm) == []`); every method name walls `DISP_E_UNKNOWNNAME` until you re-wrap it:
   ```python
   from ..com.earlybind import EarlyBindError, typed, typed_qi
   from ..com.sw_type_info import wrapper_module
   fm = doc.FeatureManager
   try:
       fm_t = typed_qi(fm, "IFeatureManager", module=wrapper_module())
   except EarlyBindError:
       fm_t = fm                       # raw fallback
   target_fm = fm_t if fm_t is not None else fm
   ```
   For `ref_axis` the call is on `IModelDoc2` itself — type the **doc** the same way (`typed(doc, "IModelDoc2")`) only if the raw call walls; the doc is usually not a bare CDispatch, so try raw first, typed fallback.

3. **Null entity args = plain `None`, NOT `VARIANT(VT_DISPATCH, None)`.** On the makepy early-bound typed proxy a VARIANT wrapper is not a COM object and raises `TypeError: The Python instance can not be converted to a COM object` (W63 mate_reference). The VARIANT-null recipe is ONLY for raw `InvokeTypes`/late-bound dynamic dispatch. None of the W64 signatures take optional entity args, but if a future variant does — `None`.

4. **Verify-the-EFFECT via `GetFeatures(False)`, never call-return alone.** `IModelDoc2.FirstFeature` is unreachable out-of-process; `IFeatureManager.GetFeatures(False)` returns a flat, reachable node tuple (the W62 substrate). Gate on a **node-count delta ≥ 1** AND a node whose `GetTypeName2` matches the lane's substring. `ref_axis` returns a bare `Boolean` — a `True` return is NOT proof; the delta is.

5. **A7 type-name probe — the kernel string is NOT the guessed string.** bbox returned `'BoundingBoxProfileFeat'`, com_point `'CenterOfMassRefPoint'`, mate_reference `'MateReferenceGroupFolder'` — none matched the worker guess. Each spike MUST log the actual `GetTypeName2` of the new tail nodes (`GetFeatures(False)[before:]`) and the verifier MUST match a **case-insensitive substring**, not an exact string. The new node may land EARLIER in the tree (bbox/mate_reference both did — tail was `DirectionLight`), so the verifier walks the FULL list; the delta is the liveness gate.

6. **Callable-or-property guard** on every nullary accessor (`GetTypeName2`, `Name`, …): `_v = getattr(o, a); _v() if callable(_v) else _v`.

7. **Never raise.** `create_<kind>` returns `(False, reason)` on any failure — wrap the body in `try/except`.

8. **Mode-A status.** Reference geometry has NO `swFm*` creation enum in the swconst harvest for axis/csys/point (only `swRefPlane*` constraint flags exist, which are NOT creation enums). So all four are **Mode-B only** (legacy `Insert*`), exactly like `com_point` — Mode-A is SKIPPED BY DESIGN (no candidate enum to quarantine), not quarantined.

### Fixture archetype (MANDATED for all four lanes)

Use `_feature_spike_fixtures.build_block` — the **40×30×10 mm block on the Front Plane** (the W62/W63 archetype) **plus the three default datum planes** (Front/Top/Right, always present, selectable by name). No new fixture. It exposes:

- **Planar entities:** 6 box faces (±X/±Y/±Z) + Front/Top/Right datums.
- **Linear entities:** 12 box edges.
- **Point entities:** 8 corner vertices + face centers.

Canonical deterministic selections (use these exact picks so spikes are reproducible):
- **Plane reference:** `doc.Extension.SelectByID2("Front Plane", "PLANE", 0,0,0, False, mark, null, 0)` (named datum — no coordinate fragility), or a box face by coordinate (`Extension.SelectByID2("", "FACE", BOX_W_M/2, 0, BOX_D_M/2, ...)` for +X face).
- **Edge reference:** a box edge by midpoint coordinate, captured durably (see §durable-refs).
- **Vertex reference:** a corner by coordinate, e.g. `(BOX_W_M/2, BOX_H_M/2, BOX_D_M)`.

### Durable references (where a lane binds to body topology)

`ref_plane`/`ref_axis`/`ref_point`/CSYS bind to faces/edges/vertices. In the **handler**, resolve refs through the proven path (`resolve_manifest_face` for dict refs, `resolve_ref` for DurableRef-likes), then `typed(entity, "IEntity")`. In the **spike**, capture the live entity's `persist_id` via `capture_persist_id(doc, ent)` and wrap it in a persist-only ref (the W63 mate_reference spike pattern: `resolve_ref` tier-1, no fingerprint needed). Datum-plane references (Front/Top/Right) are selected by NAME, not durable token.

### Selection-mark mechanism (ref_plane / ref_axis / coordinate_system)

These legacy `Insert*` calls consume the **pre-selection set** with role-routing **selection marks** (the PropertyManager list-box convention). The mark is the 7th arg of `Extension.SelectByID2(name, type, x, y, z, append, MARK, callout, opt)`. Marks are UI-routing integers — **the DLL cannot reveal them**; they must be confirmed empirically on the seat (probe + widen). Best-known starting marks per lane are given below and flagged UNVERIFIED.

### Spike + save→reopen

Each spike fires the SHIPPING handler, then proves survival with the SHARED fixture:
```python
from _feature_spike_fixtures import save_and_reopen   # typed OpenDoc6 — NOT bare sw.OpenDoc
doc2 = save_and_reopen(sw, doc)
```
Verdict: **PASS** = handler ok + node-delta ≥ 1 + type-substring matches + survives reopen. **PARTIAL** = materializes but does not survive. **FAIL** = handler False (run a direct-API diagnostic probe to split resolution-failure from API-failure, per the mate_reference spike).

---

## 1. Seat-fire order (lowest topological risk → boss fight)

| # | Lane | Risk | Rationale |
|---|---|---|---|
| 1 | **`ref_plane`** | **Lowest** | `InsertRefPlane` is ALREADY GREEN in `_feature_spike_fixtures.seed_line_over_top` (Distance=8, offset 20 mm). Parametric constraint+value pairs; single named/face reference. Near-certain ship — opens the epoch warm. |
| 2 | **`ref_point`** | Low–Med | `InsertReferencePoint(FaceCenter=4, 0, 0.0, 1)` needs only ONE face pre-selected, zero curve math. Fully parametric args. |
| 3 | **`ref_axis`** | Medium | `IModelDoc2.InsertAxis2(AutoSize)` returns a bare `Boolean` — verify-the-effect is load-bearing. Deterministic mode = **TwoPlanes**: pre-select Front + Right datums → intersection axis through origin (no coordinate-pick). |
| 4 | **`coordinate_system`** | **BOSS FIGHT** | 3 args are flip-toggles only; origin + X/Y/Z axes come ENTIRELY from marked pre-selection with NO parametric escape. The selection-mark routing must be empirically nailed (the marks `mate_reference` dodged). Fire last, after the mark mechanism is exercised by ref_plane/ref_axis. |

---

## 2. LANE 1 — `ref_plane`

**Objective:** create a reference plane offset from / parallel to / at-angle-to a selected planar entity.

**COM (reflected, IFeatureManager):**
```
InsertRefPlane(
    FirstConstraint: int,                 # swRefPlaneReferenceConstraints_e bit-flag
    FirstConstraintAngleOrDistance: float,
    SecondConstraint: int,                # 0 if unused
    SecondConstraintAngleOrDistance: float,
    ThirdConstraint: int,                 # 0 if unused
    ThirdConstraintAngleOrDistance: float,
) -> Object   # the new RefPlane feature dispatch
```
**Constraint enum (reflected `swRefPlaneReferenceConstraints_e`):** `Parallel=1, Perpendicular=2, Coincident=4, Distance=8, Angle=16, Tangent=32, MidPlane=128, OptionFlip=256`. Combine the geometric constraint with the value type by bit-OR where needed (e.g. offset = `Distance(8)` with distance value; angled = `Angle(16)` with radians).

**Mode-B recipe:**
1. Pre-select the reference planar entity with mark (UNVERIFIED start: **mark=0** — single reference; `seed_line_over_top` selects the face then calls with no explicit mark). Use `doc.Extension.SelectByID2("Front Plane","PLANE",0,0,0,False,0,null,0)` or a box face.
2. `target_fm.InsertRefPlane(8, 0.020, 0, 0.0, 0, 0.0)` for a 20 mm offset (the proven fixture call).
3. `doc.ClearSelection2(True)`.
4. Spec maps `feature["constraints"]` → (constraint int, value) pairs; default single Distance offset.

**Verify substring (A7 — UNVERIFIED guess):** `"refplane"` or `"plane"` in `GetTypeName2().lower()`. NOTE the block already has 3 `RefPlane` datum nodes — the **node-count delta** is the real liveness gate; the type-substring only confirms the new node IS a plane. Log the true `GetTypeName2` and widen.

**Feature spec shape:**
```jsonc
{"kind": "ref_plane", "name": "Plane1",
 "reference": {"ref": <face_ref|"Front Plane">},
 "constraint": "offset", "value_m": 0.020}
```

**Test matrix (offline, fake-COM):** offset success (delta +1, type match → True) · parallel/coincident variants · ghost (call ok, no delta → False) · wrong-type node (delta but no plane → False) · InsertRefPlane raises → False · handler never raises · `SPIKE_STATUS == "GREEN"` (after fire). Fakes: `_FakeFeatureManager.InsertRefPlane(*args)` records args + optionally adds a `RefPlane` node; patch `typed`/`typed_qi`/`wrapper_module` to identity.

---

## 3. LANE 2 — `ref_point`

**Objective:** create a reference point at a face center / along an edge / at an intersection.

**COM (reflected, IFeatureManager):**
```
InsertReferencePoint(
    NRefPointType: int,            # swRefPointType_e
    NRefPointAlongCurveType: int,  # swRefPointAlongCurveType_e (only for AlongCurve)
    DDistance_or_Percent: float,   # only for AlongCurve; 0.0 otherwise
    NumberOfRefPoints: int,        # 1 for a single point
) -> Object   # the new RefPoint feature dispatch
```
**Enums (reflected):** `swRefPointType_e`: `AlongCurve=2, CenterEdge=3, FaceCenter=4, FaceVertexProjection=5, Intersection=6, SketchPoint=7`. `swRefPointAlongCurveType_e`: `Distance=0, Percentage=1, EvenlyDistributed=2`.

**Mode-B recipe (deterministic = FaceCenter):**
1. Pre-select ONE box face (e.g. +X face by coordinate). Mark UNVERIFIED start: **mark=0**.
2. `target_fm.InsertReferencePoint(4, 0, 0.0, 1)` — FaceCenter, no curve params.
3. (AlongCurve variant: pre-select an edge, `InsertReferencePoint(2, 0, 0.5, 1)` = 50 % distance.)
4. `doc.ClearSelection2(True)`.

**Verify substring (A7 — UNVERIFIED):** `"refpoint"` or `"point"` in `GetTypeName2().lower()`. Log + widen.

**Feature spec shape:**
```jsonc
{"kind": "ref_point", "name": "Point1",
 "reference": {"ref": <face_ref>}, "point_type": "face_center"}
```

**Test matrix:** face-center success · along-curve(edge, 50 %) success · unresolved reference → False · ghost (no delta) → False · wrong-type → False · raises → False · never-raises · SPIKE_STATUS green. Fakes mirror lane 1.

---

## 4. LANE 3 — `ref_axis`

**Objective:** create a reference axis from two planes / one linear edge / two points / a cylindrical face.

**COM (reflected — NOTE: on `IModelDoc2`, NOT `IFeatureManager`):**
```
IModelDoc2.InsertAxis2(AutoSize: bool) -> Boolean
```
The **axis TYPE is implicit in the pre-selection** (`swRefAxisType_e`: `OneLine=0, TwoPlanes=1, TwoPoints=2, CylOrConeFace=3, PtAndPlane=4`). `InsertAxis2` infers the construction from what is selected. Returns a bare `Boolean` — **verify-the-effect is mandatory** (a `True` return with no node = ghost).

**Mode-B recipe (deterministic = TwoPlanes):**
1. Pre-select Front Plane (mark 0) and Right Plane (append=True, mark 0):
   ```python
   ext = doc.Extension
   ext.SelectByID2("Front Plane", "PLANE", 0,0,0, False, 0, null, 0)
   ext.SelectByID2("Right Plane", "PLANE", 0,0,0, True,  0, null, 0)   # append
   ```
   → their intersection is the vertical axis through the origin.
2. Call on the DOC (try raw first, typed fallback — the doc is usually not a bare CDispatch):
   ```python
   try:
       ok = doc.InsertAxis2(True)
   except Exception:
       doc_t = typed(doc, "IModelDoc2", module=wrapper_module())
       ok = doc_t.InsertAxis2(True)
   ```
3. `ForceRebuild3(False)`; `ClearSelection2(True)`.
4. Verify: node-delta ≥ 1 (the `ok` bool is NOT sufficient).

**Verify substring (A7 — UNVERIFIED):** `"refaxis"` or `"axis"` in `GetTypeName2().lower()`. Log + widen (likely `'RefAxis'`).

**Feature spec shape:**
```jsonc
{"kind": "ref_axis", "name": "Axis1",
 "axis_type": "two_planes",
 "references": [{"ref": "Front Plane"}, {"ref": "Right Plane"}]}
```

**Test matrix:** two-planes success (delta +1, ok=True, type match) · **bool-True-but-no-delta → False (the ghost trap — explicitly test this)** · one-line(edge) variant · raises → False · never-raises · SPIKE_STATUS green. Fake doc gets `InsertAxis2(bool)` returning a configurable bool + optionally adding a `RefAxis` node.

---

## 5. LANE 4 — `coordinate_system` (BOSS FIGHT)

**Objective:** create a coordinate system with a defined origin and X/Y/Z axis directions.

**COM (reflected, IFeatureManager):**
```
InsertCoordinateSystem(
    XFlippedIn: bool,
    YFlippedIn: bool,
    ZFlippedIn: bool,
) -> Feature
```
**The hard part:** the 3 args are ONLY axis-flip toggles. The **origin + X/Y/Z axis references come entirely from the marked pre-selection set** — there is NO parametric entity arg. This is the selection-mark routing `mate_reference` escaped by going parametric; `coordinate_system` has no such escape, so the marks MUST be empirically confirmed.

**Selection-mark hypothesis (UNVERIFIED — the boss fight):** the PropertyManager has Origin / X-axis / Y-axis / Z-axis selection boxes. Best-known additive-bit-flag starting marks:
- origin → **mark 1**
- X axis → **mark 2**
- Y axis → **mark 4**
- Z axis → **mark 8**

The worker MUST treat these as a hypothesis and confirm on the seat. **Empirical confirmation procedure (no macro recorder available):**
1. Pre-select a corner vertex as origin (mark 1), an incident edge as X (mark 2), a second incident edge as Y (mark 4) — leave Z implied.
2. Fire `target_fm.InsertCoordinateSystem(False, False, False)`; check node-delta + `GetTypeName2`.
3. **If it ghosts (no delta):** the marks are wrong. The spike runs a **mark-grid probe** (the roadmap S-DISPATCH/headless-fuzz tactic): iterate origin/X/Y over the bitfield `{1,2,4,8}` permutations, fire, break on `node_delta > 0`. Log the winning mark→role map. (Bounded: 3 roles × 4 marks is a tiny grid.)
4. Once the winning marks are known, hard-code them in `_MARK_FOR_ROLE` and document the empirical provenance inline.

**Mode-B recipe:**
1. Capture origin vertex + 2 edges durably (persist_id) OR select by coordinate with the confirmed marks.
2. `target_fm.InsertCoordinateSystem(False, False, False)`.
3. `ForceRebuild3(False)`; `ClearSelection2(True)`.

**Verify substring (A7 — UNVERIFIED):** `"coord"` in `GetTypeName2().lower()` (likely `'CoordSys'` / `'CoordinateSystem'`). Log + widen.

**Feature spec shape:**
```jsonc
{"kind": "coordinate_system", "name": "Coordinate System1",
 "origin": {"ref": <vertex_ref>},
 "x_axis": {"ref": <edge_ref>}, "y_axis": {"ref": <edge_ref>},
 "flip": {"x": false, "y": false, "z": false}}
```

**Test matrix:** origin+X+Y success (delta +1, type match) · origin-only success (axes inferred) · flip toggles pass through to args (assert `InsertCoordinateSystem(args)` got the right bools) · ghost (no delta) → False · unresolved origin → False · raises → False · never-raises · SPIKE_STATUS green. The mark-grid probe is spike-only (not an offline test); offline tests assert the role→mark dict is applied to the right `SelectByID2` calls.

---

## 6. Per-lane deliverables (each worker)

1. `src/ai_sw_bridge/features/<kind>.py` — handler + `SPIKE_STATUS = "UNFIRED"` + Mode-B recipe + verifier.
2. `tests/features/test_<kind>.py` — full offline matrix (fake-COM; patch `typed`/`typed_qi`/`wrapper_module`/resolvers on the lane module).
3. `spikes/v0_2x/spike_<kind>.py` — fires the SHIPPING handler on `build_block`, A7 probe, shared `save_and_reopen`, direct-API diagnostic on failure, writes `_results/<kind>.json`.
4. `src/ai_sw_bridge/features/__init__.py` — registration block gated on `SPIKE_STATUS == "GREEN"` (W0 merges; resolve the registry seam at integration like W63).

W0 fires each spike on the singleton seat in the order of §1, iterates the forensic rounds (reflect → CDispatch escape → mark/arg correction → A7 widen), flips `SPIKE_STATUS` to `"GREEN"`, and commits the lane on its `feat/w64-<kind>` worktree branch. Integration cascade + master promotion mirror W63.

---

## 7. Open spikes register (W64)

| ID | Spike | Gates | RED impact |
|---|---|---|---|
| S-REFPLANE | `InsertRefPlane` offset/parallel/angle | lane 1 | partly pre-proven; drop to offset-only |
| S-REFPOINT | `InsertReferencePoint` FaceCenter/AlongCurve | lane 2 | drop to FaceCenter-only |
| S-REFAXIS | `IModelDoc2.InsertAxis2` TwoPlanes/OneLine | lane 3 | drop to TwoPlanes-only; if bool-only-no-node → WALL, defer |
| S-CSYS-MARKS | `InsertCoordinateSystem` origin/axis selection-mark map | lane 4 (boss) | mark-grid probe; if no permutation materializes → WALL, defer + DEFERRED.md |
