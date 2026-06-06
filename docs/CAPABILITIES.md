# ai-sw-bridge — Capability Matrix

> **Source of truth** for the shipped declarative→SOLIDWORKS-COM surface.
> Generated from the live repo (`_SUPPORTED_FEATURE_TYPES`, `export/formats.py`,
> the `ai-sw-*` CLI entry points, the `sw_*` MCP tools) cross-checked with
> `docs/DEFERRED.md`. Paradigm: **declarative JSON is the only authoring surface;
> propose→approve→execute; zero arbitrary code exec; out-of-process Python.**
>
> Last reconciled: 2026-06-06 (through W33). **The Export §3 is held pending the
> W34 handback** — six 3D-neutral formats carry `seat_confirmed=True` but have no
> verify-the-bytes PAE evidence; W34 is auditing them.

## 0. Surfaces

**12 CLI entry points:** `ai-sw-build` · `ai-sw-mutate` · `ai-sw-assembly` ·
`ai-sw-drawing` · `ai-sw-observe` · `ai-sw-probe` · `ai-sw-checkpoint` ·
`ai-sw-history` · `ai-sw-codegen` · `ai-sw-apidoc` · `ai-sw-mcp` · `ai-sw-bridge`

**§6.5 rule:** approval-gated **mutations** (propose/dry_run/commit) are **CLI-only,
never MCP**. **Read-only** interrogation (`observe`) may be both CLI **and** MCP.

## 1. Part features — `feature_add` (22 advertised kinds)

The `feature_add` mutation in `mutate.py`; each kind is in `_SUPPORTED_FEATURE_TYPES`
(propose fails-closed on anything outside it).

| Kind | COM recipe (abbrev.) | Origin |
|---|---|---|
| `fillet_constant_radius` | CreateDefinition(1)→typed_qi→CreateFeature | F1 |
| `variable_radius_fillet` | IsMultipleRadius + per-edge SetRadius | F2 |
| `chamfer` | legacy `InsertFeatureChamfer` (8-arg) | W24 |
| `base_flange` | CreateDefinition(34)→typed_qi | F2 |
| `edge_flange` | legacy `InsertSheetMetalEdgeFlange2` (13-arg, SAFEARRAY VT_ARRAY\|VT_DISPATCH) | W7 |
| `wizard_hole` | CreateDefinition(25)→InitializeHole→CreateFeature | F2 |
| `shell` | `IModelDoc2.InsertFeatureShell` | F2 |
| `draft` | `InsertMultiFaceDraft` (neutral mark=1 / faces mark=2) | F2 |
| `dome` | `InsertDome` (via durable face_ref) | W6 |
| `sweep` | CreateDefinition(17)→ISweepFeatureData (path must leave profile plane) | D4 |
| `sweep_cut` | CreateDefinition(18) (path must pierce solid) | W6 |
| `ref_plane` | `InsertRefPlane` — offset OR normal-to-edge (edge_ref) | W3/W6 |
| `ref_axis` | `IModelDoc2.InsertAxis2(True)` | W3 |
| `coordinate_system` | `InsertCoordinateSystem` | W3 |
| `ref_point` | `InsertReferencePoint(4,…)` (face-centroid via face_ref) | W5.3 |
| `linear_pattern` | `FeatureLinearPattern5` (22-arg, seed mark=4/dir mark=1) | W21 |
| `circular_pattern` | `FeatureCircularPattern5` (14-arg; spacing in RADIANS) | W21 |
| `mirror_feature` | `InsertMirrorFeature2` (5-arg, seed mark=1/plane mark=2) | W21 |

*(Plus the pre-W1 core: extrude / cut / revolve / 7 sketch primitives with
construction + text fidelity — `spec/builder.py`.)*

**Load-bearing lessons:** instance-count gate = measure **volume/face delta**, not
count+type+reopen (caught the circular-pattern radians bug); SAFEARRAY args must be
`VARIANT(VT_ARRAY|VT_DISPATCH, (obj,))` — a bare object silently no-ops.

## 2. Assembly — `ai-sw-assembly` (W9–W26)

| Capability | Detail |
|---|---|
| Multi-part placement | W8 `OpenDoc6` pre-open → `AddComponent4` (real B-rep) |
| Rotated placement | `rpy_deg` via CreateTransform→`SetTransformAndSolve` |
| **8 mate types** | coincident · distance · concentric · parallel · perpendicular · tangent · angle · **width** |
| Limit modifier | distance/angle limit mates |
| **component_arrays** | linear + circular via **placement expansion** (zero new COM) |
| **mirror component** | `IAssemblyDoc.MirrorComponents` v1 (9-arg, raw Plane + VT_ARRAY\|VT_DISPATCH) |
| Interactive edit | declarative add/remove component+mate → re-commit |
| L4 persistence | manifest v2 (verbatim spec + runtime overlay, lossless `to_spec()`) |

**Walls:** linear/circular **component** patterns (assembly-level) = no `IAssemblyDoc`
creation method → Route-C/VBA. *In flight: W32v exploded views (re-probe).*

## 3. Export — `ai-sw-` export ⚠️ HELD FOR W34

<!-- W34-HOLD: this section is intentionally incomplete.
     pdf (W25v) and dxf (W33) are verify-the-bytes PROVEN.
     step214/step203/iges/parasolid/stl/3mf carry seat_confirmed=True from
     commit daa7e4f but have NO PAE evidence — W34 is auditing whether those
     flags are honest or silent-no-op stubs (the W25 trap). Finalize this
     table from W34's export_3d.json. -->

| Format | Flag | verify-the-bytes proof |
|---|---|---|
| `pdf` | ✅ | **W25v** — page-count discrimination (Solo=1pg, Quad=1pg, all=2pg) |
| `dxf` | ✅ | **W33** — entity parse (box front view → 4 LINE) |
| `step214` `step203` `iges` `parasolid` `stl` `3mf` | ⚠️ | **flagged `seat_confirmed=True` at `daa7e4f`, NO PAE — W34 auditing** |
| `dxf_flat` | ⬜ | deferred (sheet-metal flat pattern) |

## 4. Drawing — `ai-sw-drawing` (W4, W16–W28)

| Capability | COM recipe (abbrev.) | Origin |
|---|---|---|
| Ortho + iso views | `CreateDrawViewFromModelView3` (IDrawingDoc via typed_qi) | W4/W16 |
| Section view | `CreateSectionViewAt5` (cut line via SketchManager) | W19 |
| Detail view | `CreateDetailViewAt4` | W19 |
| Multi-sheet | per-sheet view placement | W23 |
| Model dimensions | `InsertModelAnnotations3` (suppress popup via toggles 9/10/22/23) | W17 |
| **Dim tolerances** | `IDimension.SetToleranceType/Values` (model-owned, persists in .SLDPRT) | W28 |
| BOM table | `IView.InsertBomTable4` (dispid 414) | W18 |

**Tolerance types:** symmetric=4 / bilateral=2 / limit=3. *In flight: W31v2
ordinate/baseline (Gate 1 solved via `IView.SelectEntity`; Gate-2 Insert* re-probe).*

## 5. Observe — read-only perception (CLI **+ MCP**)

| Capability | MCP tool | COM recipe | Origin |
|---|---|---|---|
| Inertia / mass-props | `sw_inertia` | `GetMomentOfInertia(0)` 9-tuple → `eigh` | E1 |
| Interference | `sw_interference` | `InterferenceDetectionManager` (dispid 126, prop-get) | W27 |
| Measure (selection) | `sw_measure` / `sw_measure_selection` | `CreateMeasure`→`Calculate(None)` | W30 |
| Bounding box (part) | `sw_bbox` / `sw_bounding_box` | `IPartDoc.GetPartBox(True)` (part-only) | W30 |
| Custom properties | `sw_custom_props` | (read side) | W29* |

*W29 properties write-side parked offline; seat PAE unrun. In flight: W35 clearance
(min-distance between components).*

## 6. Persistence / infra

Durable selection (persist-ref, edge/face match predicates) · checkpoint + history
(`ai-sw-checkpoint` / `ai-sw-history`, L4 SQLite per-feature) · L1 B-rep
interrogation · L2 COM error envelope + hint catalog + RetryGuard · L3 RAG API-doc
retrieval (`ai-sw-apidoc`) · codegen (`ai-sw-codegen`) · MCP lane (`ai-sw-mcp`).

## 7. Characterized walls (NO-GO — by design / deferred)

| Wall | Why |
|---|---|
| `loft` | CreateDefinition(9)→None with 2 profiles pre-selected; legacy paths None too (W20 re-confirmed) |
| `rib` / `wrap` / `boundary-boss` | solver-deep, out-of-process COM wall |
| `miter flange` | no SW2024 interface |
| linear/circular **component** patterns | no `IAssemblyDoc` creation method |

**Held (NOT yet earned NO-GOs, under re-probe):** drawing ordinate/baseline (W31v2),
assembly exploded view (W32v). A NO-GO is a claim of impossibility → earned only
after the *proven* sibling techniques + preconditions are exhausted.

---

*Per-feature COM recipes, marshaling gotchas, and full wall characterizations live in
`docs/DEFERRED.md` and the persistent memory. This file is the at-a-glance index.*
