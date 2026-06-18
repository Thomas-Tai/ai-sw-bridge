# W65 round-2 — worker fixture-fix brief (post seat round 1)

> Seat round 1 (2026-06-18) fired all 4 lanes. The **API lever works** — but the worker
> spikes have fixture/recipe bugs that fail before (or mis-judge) the real call. W0 has
> already corrected the **fold-class verify gate** in the jog + sketched_bend HANDLERS
> (ΔVol>0 → ΔFaces>0 ∧ bbox-change; offline tests updated, green) and banked the doctrine.
> **Do NOT touch those handler gates or their offline tests.** This brief is the SPIKE
> fixture work only. After delivery, W0 re-fires all 4.

## Doctrine you must apply (W0 seat finding)

A **bend/fold is volume-preserving** (jog, sketched_bend) → verify on **ΔFaces>0 ∧
bounding-box change** (`IBody2.GetBodyBox()`), NOT ΔVol. **Additive** features
(edge_flange, miter) ADD a wall → ΔVol>0 stays correct. The SPIKE verdict logic must match
the handler's class (the spikes currently gate on ΔVol uniformly — that false-rejected the
real `SM3dBend`).

---

## Lane: sketched_bend  (closest to GREEN — the API already worked)

Round-1 telemetry: `InsertSheetMetal3dBend` returned `'SM3dBend'`, ΔFaces +8, ΔVol 0 — a
**real bend** the spike's ΔVol gate scored NO_OP.

Fixes to `spikes/v0_2x/spike_sketched_bend.py`:
1. **Drop candidate B** (`InsertBends2`) — it's wrong-interface (AttributeError:
   `<unknown>.InsertBends2`); not the sketched-bend API. Keep candidate A only.
2. **Switch the spike verdict to the FOLD-class gate**: capture `IBody2.GetBodyBox()`
   before/after; PASS = candidate-A returned a feature ∧ ΔFaces>0 ∧ bbox moved >1e-6 m ∧
   survives save→reopen. Remove the ΔVol>0 condition.
3. Run the save→reopen survival probe (round 1 short-circuited before it). A7: log
   `GetTypeName2` ('SM3dBend' expected).
Handler is already correct (W0 fixed the gate). Expect GREEN on re-fire.

## Lane: jog  (handler fine; spike face-finder bug)

Round-1 error: `_author_on_face_line_sketch` → "no planar +Z face found". The base flange
thickened in −Z, so its major faces have ±Z normals; the `nz > 0.95` test missed them, and
the `GetSurface().Params` probing is fragile.

Fixes to `spikes/v0_2x/spike_jog.py::_author_on_face_line_sketch`:
1. **Robust major-face pick**: use `IFace2.Normal` (returns [nx,ny,nz] directly) instead of
   `GetSurface().Params`. Accept the face whose normal is parallel to Z (`abs(nz) > 0.9`,
   `abs(nx),abs(ny) < 0.1`) — EITHER the +Z or −Z major face works for a jog line sketch.
   If `Normal` is unavailable late-bound, fall back to the largest-area planar face
   (`IFace2.GetArea()`), which is always a major face on a flat sheet.
2. Draw the line ACROSS that face (e.g. mid-span), exit sketch, return its name.
3. The spike verdict already needs the FOLD-class gate (bbox, not ΔVol) — mirror the
   sketched_bend spike fix #2 here.
Handler gate already correct (W0). Expect GREEN on re-fire (jog is fold-class).

## Lane: miter_flange  (additive; spike profile-sketch ref-plane failed)

Round-1 error: profile-sketch `InsertRefPlane returned None` (pre-fire). The miter profile
plane construction needs the two-reference recipe.

Fixes to `spikes/v0_2x/spike_miter_flange.py`:
1. Build the profile plane via the SHIPPED two-reference recipe (mirror
   `mutate.py::_create_ref_plane_normal_to_edge`): select the edge's start vertex
   (Coincident, mark 0) + the edge (Perpendicular, mark 1) → `InsertRefPlane(4, 0, 2, 0,
   0, 0)`; verify the plane via a `GetFeatures` delta before sketching on it. Bare
   `InsertRefPlane` with a single under-defined reference returns None (the v1 ref-plane
   lesson).
2. Sketch the miter profile on that plane, pre-select profile + edge, fire the 14-arg
   `InsertSheetMetalMiterFlange` (Feature overload) with `VARIANT(VT_DISPATCH,None)` PCBA.
3. Verify ADDITIVE: ΔFaces>0 ∧ ΔVol>0 ∧ survives reopen (miter ADDS a wall — keep ΔVol).

## Lane: edge_flange  (separate rework — see docs/w65_edge_flange_rework.md)

Genuine no-length-arg wall; needs a real flange-profile sketch as `SketchFeat`. Follow
`docs/w65_edge_flange_rework.md` in full. Additive verify (ΔVol>0). If the profile route
also no-ops after orientation iteration → DEFERRED with evidence (honest 3/4).

---

## Deliverable & guardrails

- Touch ONLY the spike files (+ edge_flange handler per its rework brief). Leave the
  jog/sketched_bend handler gates + their offline tests as W0 left them.
- Keep `SPIKE_STATUS="UNFIRED"` (W0 flips GREEN post-seat).
- Don't touch `mutate._SUPPORTED_FEATURE_TYPES` (disjoint-registry guard).
- Each lane stays in its own `wt_w65*` worktree; ping W0 per lane when fixture-ready and
  W0 re-fires in the locked order.
