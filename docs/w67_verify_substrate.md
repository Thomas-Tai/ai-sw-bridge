# W67 Phase 2 — Verify Substrate Consolidation (`features/verify.py`)

**Status:** SHIPPED (branch `feat/w67-verify-substrate`). Pure behavior-
preserving refactor — full suite 3040 passed / 0 failed, thresholds unchanged.

## What consolidated

Before W67, 28 verify-helper defs were hand-copied across 13 feature modules,
plus the body-type and FP-epsilon constants. A fix to the `GetBodies2` +
typed-`IPartDoc` QI fallback, or a swconst constant, had to be applied N times.

`features/verify.py` is now the single source:

- **Constants:** `SW_SOLID_BODY`, `SW_SHEET_BODY`, `VOL_EPS_MM3`,
  `AREA_EPS_MM2`, `BBOX_EPS_M`, `FEATURE_TREE_WALK_LIMIT`.
- **`FeatureClass` enum:** each handler now declares `VERIFY_CLASS` — the
  verify taxonomy is a *declared property*, not inlined convention.
- **Readers:** `bodies`, `solid_metrics`, `solid_body_count`,
  `solid_volume_mm3`, `sheet_bodies`, `sheet_body_count`, `sheet_area_mm2`,
  `body_bbox`, `bbox_changed`, `feature_nodes`, `feature_node_count`,
  `type_name`, `count_nodes_by_type`, `body_centroid_m`.
- **Class gates:** `gate_additive_solid`, `gate_fold`,
  `gate_fold_volume_preserving`, `gate_surface_create`,
  `gate_surface_aggregate`, `gate_surface_to_solid`.

Each migrated handler keeps its module-local helper *names* as thin shims
delegating to `verify` — the suite's dominant idiom is
`monkeypatch.setattr(module, "_helper", fake)`, so the names must survive.

| `VERIFY_CLASS` | Handlers |
|---|---|
| `ADDITIVE_SOLID` | hem |
| `FOLD` | sketched_bend |
| `FOLD_VOL_PRESERVING` | split_line |
| `SURFACE_CREATE` | planar_surface, offset_surface |
| `SURFACE_AGGREGATE` | knit |
| `SURFACE_TO_SOLID` | thicken (DEFERRED/unregistered) |
| `CURVE` | composite, helix, project_curve |
| `REF_NODE` | bounding_box, com_point, mate_reference |
| `BODY_MOVE` | move_copy_body (UNRUN/unregistered) |

## Phase-3 tracked findings (surfaced BY the consolidation)

### 1. `GetBodies2` `visible_only` drift (latent false-negative)

The 2nd arg (`bVisibleOnly`) was historically inconsistent. Now explicit in
each shim, preserved verbatim (strict behavior-preservation; **not** silently
normalized):

| Lane | Body type | `visible_only` (historical) |
|---|---|---|
| hem, sketched_bend, split_line, thicken, move_copy_body | SOLID | **True** |
| knit (`_solid_body_count`, `_solid_volume_mm3`) | SOLID | **False** |
| planar, offset, knit | SHEET | **False** |
| thicken (`_sheet_bodies`) | SHEET | **True** |

**Risk:** a hidden/suppressed solid body is invisible to the `True` lanes'
additive gate → false-negative. The surface lanes' `False` (count all bodies)
is the safer choice. **Recommended Phase-3 fix:** normalize all readers to
`visible_only=False`, under the green suite, as a deliberate one-line change.

### 2. CURVE-class lanes lack a geometric-scalar witness

composite / helix / project_curve gate on a **feature-node count delta** only —
no curve length / edge count / `GetCurve` param-range. This is the W42 ghost
trap the solid/surface lanes were hardened against, still live for curves. A
curve that nodes-but-ghosts would pass. `composite` is weakest (any node;
helix/project_curve at least type-filter). **Phase-3 work:** add a geometry-
grade witness for `FeatureClass.CURVE`.

#### Phase-3b status — witness SCAFFOLDED, head hop SEAT-PROVEN (HEAD_PROVEN)

The geometric witness is **total arc length (mm)** (a real reference curve has
positive length; a ghost node has none). Decomposed into a proven tail and a
**now-proven** head:

- **TAIL — PROVEN OOP.** `verify.icurve_length_mm(raw_curve)` reuses the
  `brep/interrogator.py` recipe verbatim: `typed_qi(…, "ICurve")` →
  `GetEndParams()` (idx 1,2 = tmin,tmax) → `GetLength(tmin, tmax)` (metres →
  mm). Unit-tested offline.
- **HEAD — SEAT-PROVEN** (`spike_curve_length_witness` → `HEAD_PROVEN`,
  deterministic on the absolute-cold first call: **helix 80.0 mm, composite
  70.0 mm**). The real chain (`verify._node_curves`):
  ```
  typed(node,"IFeature").GetSpecificFeature2()          # IFeature re-type
    → typed(spec,"IReferenceCurve").GetSegments()        # the segments ARE edges
    → typed_qi(edge,"IEdge").GetCurve() → ICurve         # proven EDGE→ICurve tail
  ```
  Two seat findings, both load-bearing:
  1. **IFeature re-type is mandatory.** A node from `GetFeatures(False)` is a
     late-bound proxy whose `GetSpecificFeature2` trips `'Member not found'`
     (-2147352573) OOP; the typed `IFeature` compiled dispid clears it (same
     idiom as `spikes/v0_16/_seatcheck_sketch_fidelity_pae.py`).
  2. **COM edge lifetime.** An `ICurve` from `IEdge.GetCurve()` is invalidated
     the moment its parent edge is released — so `_node_curves` returns the
     typed edges in a parallel **keepalive** list the caller holds during
     measurement. Dropping the edges silently yields null lengths. (An initial
     "cold makepy gen" theory was a red herring; the real cause was lifetime.)
  - Fallbacks (unprobed): `ISketch.GetSketchSegments` for project_curve (a
    projected *sketch* — likely a different head per lane); defensive `GetCurves`.
- **GATE — HARD, WIRED.** `verify.gate_curve(d_nodes, total_len_mm)` requires
  `d_nodes > 0 AND total_len_mm > CURVE_LEN_EPS_MM`; `total_len_mm is None`
  (unreadable) is **failure**, never a fall-back to node-count (adjudication:
  no graceful degradation in a gate). **WIRED** into all three handlers
  (W67 P3b unification): each handler, after its node-count delta, locates the
  new node via `verify.newest_node_by_type(...)`, measures it through a local
  `_curve_length_mm` shim (patchable in offline tests), and gates on
  `gate_curve`. All three seat-proven: **helix 80.0 mm, composite 70.0 mm,
  project_curve 40.0 mm** (project_curve's node is a `RefCurve` → same
  `IReferenceCurve.GetSegments` head; the `ISketch` fallback was not needed).

**Seat probe:** `spikes/v0_2x/spike_curve_length_witness.py` fires the
production-candidate `verify.curve_length_mm` on real helix/composite nodes +
O1-introspects `GetSpecificFeature2()`'s `IReferenceCurve.GetSegments()` shape
and the per-segment chain.

### 3. `mate_reference._count_feature_nodes` intentionally NOT delegated

Its `TestNeverRaise` contract requires a COM failure in the node count to
*propagate* to the handler's outer safety net. The shared
`verify.feature_node_count` swallows exceptions (returns 0), as the other
REF_NODE lanes always did. mate_reference's raising form is preserved
deliberately with an in-code note.
