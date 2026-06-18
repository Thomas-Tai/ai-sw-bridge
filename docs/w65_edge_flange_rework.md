# W65 · edge_flange REWORK brief — profile-sketch recipe

> **Why:** the seat fire (2026-06-18, 2 rounds) proved the null-`SketchFeat` path is a
> dead end. Round 1: bare `None` SketchFeat walled `Type mismatch arg 2` (fixed →
> `VARIANT(VT_DISPATCH,None)`). Round 2: the call now returns cleanly (status OK,
> NoneType) but **adds ZERO geometry** (ΔFaces=0, ΔVol=0, no feature node) — for BOTH
> the single-edge and the array forms. Root cause: **`InsertSheetMetalEdgeFlange` has NO
> flange-length argument** (re-read the 13-arg sig). A null `SketchFeat` ⇒ a zero-extent
> default flange ⇒ no geometry. The flange's extent can ONLY come from a real
> `SketchFeat` profile sketch. This rework authors that sketch.

## The recipe (deterministic, leverages SHIPPED machinery)

A 90° edge flange of length L on a boundary edge = a flange whose **profile is a single
line of length L, on a plane perpendicular to the selected edge, anchored at the edge**.
The project ALREADY ships the perpendicular-plane construction —
`mutate.py::_create_ref_plane_normal_to_edge` (T6 v2, seat-GREEN `13b35e3`): select the
edge's start vertex (Coincident, mark 0) + the edge (Perpendicular, mark 1) →
`InsertRefPlane(4, 0, 2, 0, 0, 0)`. Reuse that exact pattern.

**Spike + handler steps:**
1. `_build_fixture_v5` → base flange + the longest boundary edge (durable `edge_ref`).
2. Resolve the edge; derive its **start vertex** via typed `IEdge.GetStartVertex()`
   (the `_create_ref_plane_normal_to_edge` pattern).
3. Build a reference plane **normal to the edge at the start vertex**:
   select vertex (mark 0) + edge (mark 1) → `fm.InsertRefPlane(4, 0, 2, 0, 0, 0)`
   (Coincident=4 anchor, Perpendicular=2 edge). Verify via `GetFeatures` delta.
4. Open a sketch on that ref plane (`SelectByID2(plane, "PLANE", ...)` →
   `SketchManager.InsertSketch(True)`).
5. Draw the flange **profile line**: from the edge's start point, length = `length_mm`,
   in the flange direction (for a 90° flange, perpendicular to the sheet's major face).
   A single `CreateLine` segment is the minimal profile. Exit sketch
   (`InsertSketch(True)`); capture the sketch feature (`doc.SelectionManager` /
   `FeatureByName("Sketch<N>")`).
6. **Pre-select the boundary edge** (the FlangeEdge), then fire:
   ```
   null_disp = VARIANT(VT_DISPATCH, None)
   fm.InsertSheetMetalEdgeFlange(
       edge,            # FlangeEdge (resolved live edge)
       sketch_feat,     # SketchFeat = the profile sketch from step 5  <-- the fix
       0, angle_rad, radius_m, position, offset_m,
       relief_type, 0.5, 0.0, 0.0, sharp_type,
       null_disp,       # PCBA
   )
   ```
7. `ForceRebuild3(False)`; **verify ΔFaces>0 ∧ |ΔVol|>1e-6 mm³** (unchanged gate); A7
   GetTypeName2; save→reopen survival.

## Handler signature change

`create_edge_flange(doc, feature, target)` — `feature["length_mm"]` (default 10) now
DRIVES the profile-line length (no longer "reserved/unused"). `target["edge_ref"]`
unchanged. The handler must author the ref-plane + profile sketch itself (steps 2-5) —
factor a `_author_flange_profile(doc, edge, length_m, angle_rad) -> sketch_feat` helper.

## Risks / open unknowns (flag in telemetry, don't guess)

- **Profile-line orientation.** The line must lie in the perpendicular plane AND start
  on the edge. If the flange folds the wrong way or self-intersects, log the plane normal
  + line endpoints and try the reversed direction. Budget 2-3 seat rounds here.
- **Sketch must be CLOSED vs open.** SW edge-flange profiles are typically a single open
  line (the flange wall) — but if SW rejects an open profile, try an L-contour. Probe both.
- **If the profile-sketch route ALSO no-ops** after orientation iteration → characterize
  edge_flange as DEFERRED with the full ΔVol evidence chain (null-sketch no-op +
  profile-sketch no-op). It stays quarantined; no regression. (The honest 3/4 outcome.)

## Offline tests to add

- `_author_flange_profile` builds the expected sketch calls (mock SketchManager).
- `length_mm` → profile-line length mapping (mm→m).
- SketchFeat passed to InsertSheetMetalEdgeFlange is the authored sketch, NOT None/VARIANT-null.
- The existing PCBA-VARIANT spy + ΔVol ghost-gate + fail-closed stay green.

Deliver into `wt_w65edgeflange` on `feat/w65-edge-flange`; W0 re-fires the seat.
