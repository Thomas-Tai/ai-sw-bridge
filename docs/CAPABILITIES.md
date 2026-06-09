# ai-sw-bridge — Capability Matrix

> **Source of truth** for the shipped declarative→SOLIDWORKS-COM surface.
> Generated from the live repo (`_SUPPORTED_FEATURE_TYPES`, `export/formats.py`,
> the `ai-sw-*` CLI entry points, the `sw_*` MCP tools) cross-checked with
> `docs/DEFERRED.md`. Paradigm: **declarative JSON is the only authoring surface;
> propose→approve→execute; zero arbitrary code exec; out-of-process Python.**
>
> Last reconciled: 2026-06-09 (through W39 — sketch relations; W36/W37/W38/W39
> batch). Suite: **2085 passed** (serial; xdist unavailable in this env), 58 skipped.

## 0. Surfaces

**15 CLI entry points:** `ai-sw-build` · `ai-sw-mutate` · `ai-sw-assembly` ·
`ai-sw-drawing` · `ai-sw-properties` · `ai-sw-configurations` ·
`ai-sw-sketch-relations` · `ai-sw-observe` · `ai-sw-probe` ·
`ai-sw-checkpoint` · `ai-sw-history` · `ai-sw-codegen` · `ai-sw-apidoc` ·
`ai-sw-mcp` · `ai-sw-bridge`

**§6.5 rule:** approval-gated **mutations** (propose/dry_run/commit) are **CLI-only,
never MCP**. **Read-only** interrogation (`observe`) may be both CLI **and** MCP.

## 1. Part features — `feature_add` (18 advertised kinds)

The `feature_add` mutation in `mutate.py`; each kind is in `_SUPPORTED_FEATURE_TYPES`
(propose fails-closed on anything outside it).

| Kind | COM recipe (abbrev.) | Origin |
|---|---|---|
| `fillet_constant_radius` | CreateDefinition(1)→typed_qi→CreateFeature | F1 |
| `variable_radius_fillet` | IsMultipleRadius + per-edge SetRadius | F2 |
| `chamfer` | legacy `InsertFeatureChamfer` (8-arg) | W24 |
| `base_flange` | CreateDefinition(34)→typed_qi | F2 |
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
| `delete_body` | `InsertDeleteBody2(False)` (1-arg) on a `SelectByID2(…,"SOLIDBODY")` body | W41 |

*(Plus the pre-W1 core: extrude / cut / revolve / 7 sketch primitives with
construction + text fidelity — `spec/builder.py`.)*

**Load-bearing lessons:** instance-count gate = measure **volume/face delta**, not
count+type+reopen (caught the circular-pattern radians bug); SAFEARRAY args must be
`VARIANT(VT_ARRAY|VT_DISPATCH, (obj,))` — a bare object silently no-ops.

**⛔ `edge_flange` QUARANTINED 2026-06-09 (W42 ghost finding):** it was advertised
(W7) but is a **ghost** — `_create_edge_flange` returns `ok=True` + an
error-code-0 `Edge-Flange1` node yet adds **ZERO** geometry (ΔVol=0, reproduced
3×). The W7 PAE verified node-**presence**, never the B-rep. De-advertised
(propose fails-closed); handler kept as characterized code. This exposed a
**systemic verification gap** — ~6 other kinds (`base_flange`, `shell`, `draft`,
`sweep`, `sweep_cut`, `dome`) shipped on the same node-presence proof and are
under B-rep-effect re-verification (W44). See `docs/DEFERRED.md` Wave-44.

## 2. Assembly — `ai-sw-assembly` (W9–W32)

| Capability | Detail |
|---|---|
| Multi-part placement | W8 `OpenDoc6` pre-open → `AddComponent4` (real B-rep) |
| Rotated placement | `rpy_deg` via CreateTransform→`SetTransformAndSolve` |
| **8 mate types** | coincident · distance · concentric · parallel · perpendicular · tangent · angle · **width** |
| Limit modifier | distance/angle limit mates |
| **component_arrays** | linear + circular via **placement expansion** (zero new COM) |
| **mirror component** | `IAssemblyDoc.MirrorComponents` v1 (9-arg, raw Plane + VT_ARRAY\|VT_DISPATCH) |
| **Exploded views** | `CreateExplodedView` → `AddExplodeStep` with 2-entity selection (component + direction ref plane); Transform delta verified (W32) |
| Interactive edit | declarative add/remove component+mate → re-commit |
| L4 persistence | manifest v2 (verbatim spec + runtime overlay, lossless `to_spec()`) |

**Walls:** linear/circular **component** patterns (assembly-level) = no `IAssemblyDoc`
creation method → Route-C/VBA. `ShowExploded2` VARIANT dispatch fails (but transform
proves effect). *Deferred: rotational steps, radial patterns, explode-line sketches,
multiple views per config, animation.*

## 3. Export — `ai-sw-` export (W25v + W33 + W34)

| Format | Flag | verify-the-bytes proof |
|---|---|---|
| `pdf` | ✅ | **W25v** — page-count discrimination (Solo=1pg, Quad=1pg, all=2pg) |
| `dxf` | ✅ | **W33** — entity parse (box front view → 4 LINE) |
| `step214` | ✅ | **W34** — 27 CARTESIAN_POINT + 6 ADVANCED_FACE + 1 CLOSED_SHELL |
| `iges` | ✅ | **W34** — 79 DE entities + 109 P lines (⚠️ only `.igs` ext works; `.iges` → error 256) |
| `stl` | ✅ | **W34** — binary, 12 triangles (box = 6 faces × 2) |
| `step203` | ⚠️ | same SaveAs3_DIRECT path as step214 (save_version=1); not independently byte-verified |
| `parasolid` | ⚠️ | same SaveAs3_DIRECT path; not independently byte-verified |
| `3mf` | ⚠️ | same SaveAs3_DIRECT path; not independently byte-verified |
| `dxf_flat` | ✅ | **W42** — developed flat-pattern OUTLINE; L-bracket unrolls to 86.28×40.0 mm (> 60 mm folded face, < 90 mm naive sum). Inner bend lines deferred (drawing flat-pattern view / W33; see DEFERRED Wave-42) |

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
| **Title block** | `title_block:{field:value}` → drawing custom props (W29 `Add3`/`Get4`); fields resolve via `$PRP:`/`$PRPSHEET:`; DRAWING-owned (.SLDDRW) | W38 |

**Tolerance types:** symmetric=4 / bilateral=2 / limit=3.
**Title-block fields:** DrawingNo · Title · Revision · DrawnBy · CheckedBy ·
ApprovedBy · Date · Scale · Material · SheetOf · Company · Project (closed vocab,
unknown field rejected).

## 5. Observe — read-only perception (CLI **+ MCP**)

| Capability | MCP tool | COM recipe | Origin |
|---|---|---|---|
| Inertia / mass-props | `sw_inertia` | `GetMomentOfInertia(0)` 9-tuple → `eigh` | E1 |
| Interference | `sw_interference` | `InterferenceDetectionManager` (dispid 126, prop-get) | W27 |
| Measure (selection) | `sw_measure` / `sw_measure_selection` | `CreateMeasure`→`Calculate(None)` | W30 |
| Bounding box (part) | `sw_bbox` / `sw_bounding_box` | `IPartDoc.GetPartBox(True)` (part-only) | W30 |
| **Clearance (min-distance)** | `sw_clearance` | `IComponent2.Select2`×2 → `IMeasure.Distance` (assembly-only) | W35 |
| **Draft analysis (DFM)** | `sw_draft_analysis` | `IPartDoc.GetBodies2` (QI from IModelDoc2) → `GetFaces` → `IFace2.Normal` vs pull (part-only) | W37 |
| **Current selection** | `sw_current_selection` | `SelectionManager` (memid 65537 prop-get) → `GetSelectedObjectCount2`/`GetSelectedObjectType3`/`GetSelectedObject6` → durable persist-ref; `swSelectType_e` table (edge=1/face=2/…/solid_body=76) | W43 |

## 5b. Metadata — `ai-sw-properties` (W29, **CLI-only mutation**)

Custom **file** properties (TEXT, file-level) via a `kind:"properties"` spec
through the `metadata/` module + `ai-sw-properties` CLI (propose→dry_run→commit;
**CLI-only per §6.5 — properties is a MUTATION, never MCP**).

| Capability | COM recipe (abbrev.) | Origin |
|---|---|---|
| Set custom props (TEXT) | `CustomPropertyManager("")` → `Add3(name, 30, value, 1)` | W29 |
| Read-back verify | `Get4(name, False)` 3-tuple (Get6 dead) + `GetNames()` existence | W29 |
| Save | `SaveAs3(path, 0, 0)` → `swFileSaveError_e` (Save3 dead) | W29 |
| `overwrite:false` skip | `name in GetNames()` → preserve existing | W29 |

**W29 seat lessons (three makepy out-param traps, offline-test-blind):** `Count`
is a **property** not a method; `Get6`/`Save3` both **raise "Type mismatch"** on
early-bind ([out]-param mis-marshaling) → use `Get4`/`SaveAs3`. PAE 7/7 GREEN
(count 0→3, read-back exact across close+reopen). *Deferred: Number/Date/YesOrNo
types, configuration-specific props, linked props, deletion.*

## 5c. Sketch relations — `ai-sw-sketch-relations` (W39, **CLI-only mutation**)

Geometric constraints between sketch entities, added to a feature spec's sketch
block as `relations:[{type, entities:[seg_idx…]}]`. **6 effect-verified relations**
(each proven to MOVE geometry on the seat, not just "no error"):

| Relation | Token | Arity | Seat proof |
|---|---|---|---|
| `horizontal` | `sgHORIZONTAL2D` | 1 | dy→0 |
| `vertical` | `sgVERTICAL2D` | 1 | dx→0 |
| `parallel` | `sgPARALLEL` | 2 | cross→0 |
| `perpendicular` | `sgPERPENDICULAR2D` | 2 | dot→0 |
| `equal` | `sgSAMELENGTH` | 2 | lengths equalize |
| `concentric` | `sgCONCENTRIC` | 2 | centers coincide |

**Recipe:** raw `seg.Select2(append,mark)` → **`IModelDoc2.SketchAddConstraints(token)`**
(NOT `ISketchManager`); `GetSketchSegments` read as a property (no parens). **W39
seat lessons:** the W21 no-op trap — guessed tokens pass with no error but no effect
(`sgEQUAL`/`sgPARALLEL2D` were silent no-ops → corrected to `sgSAMELENGTH`/`sgPARALLEL`).
*Deferred (fail-closed, tokens unproven): `collinear`, `coincident` (endpoint selection),
`symmetric` (3-ref centerline) — DEFERRED.md Wave-39.*

## 5d. Configurations — `ai-sw-configurations` (W36v, **CLI-only mutation**, multi-file)

Family-of-parts as **N distinct part files** (NOT in-file SW configs — that's an earned
COM wall, DEFERRED.md Wave-36). A `variants:[{name, overrides}]` spec → one proven
`.SLDPRT` per variant via `builder.build(no_dim=True, save_as=…)` + `CreateMassProperty`
volume-discrimination. `propose` (offline validate) + `materialize` (build+measure).
Overrides: flat string (locals) OR nested dict/list (deep-merged into the spec). Seat-
proven: 3 variants → 3 distinct volumes (4000/13500/50000 mm³ exact). *Deferred: in-file
native configs, suppress-state, design tables.*

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
| drawing **ordinate / baseline** dims | all 6 Insert*/Add*/baseline methods produce zero dims with confirmed datum; interactive-mode starters, not one-shot creators (W31v2 earned NO-GO) |

---

*Per-feature COM recipes, marshaling gotchas, and full wall characterizations live in
`docs/DEFERRED.md` and the persistent memory. This file is the at-a-glance index.*
