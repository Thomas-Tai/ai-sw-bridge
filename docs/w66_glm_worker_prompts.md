# W66 — Surfaces · GLM/Sonnet worker briefs

> **Epoch:** W66 · cut 2026-06-18 from `v0.15.2` master (`491dad9`) · **4 lanes** opening
> the surface-modeling family — the last clean greenfield (manufacturing spine + datum +
> basic sheet metal already shipped). W0 reflected every signature from the DLL
> (`docs/sw_api_full.json`, SW2024 v32.1.0.123) FIRST; arg counts below are real.
>
> **Reflect-check-existing (the W64 doctrine):** audited `mutate.py` + `spec/schema.py` —
> **NO surface-creation handler ships** (`up_to_surface`/`offset_from_surface` are
> swEndConditions enum values; `cutting_surface` is a split param). Genuine greenfield, no
> duplication. **NEW registry kinds** in `features/` — do NOT touch
> `mutate._SUPPORTED_FEATURE_TYPES`.

---

## §0 — Mandatory doctrine

0.1 **Verify-the-EFFECT by surface class — AREA is to surfaces what VOLUME is to solids.**
A surface feature creates a zero-thickness **sheet body**, so ΔVol is meaningless. The
witness is the **surface-body count** + **area**:
  - **Materialization witness:** `IModelDoc2.GetBodies2(swSheetBody, False)` count delta.
    (`swBodyType_e.swSheetBody` — value **1**; CONFIRM against the swconst harvest in the
    spike, do not trust this comment alone.)
  - **Anti-ghost witness:** `IBody2.GetArea()` on the new body > 0. A Boolean/Void-clean
    call that yields a zero-area or no-new-body result is the surface form of the W42/W65
    ghost — `ΔArea>0` catches it exactly as `ΔVol>0` catches solid ghosts. NEVER accept
    node/body presence alone.
  - **Corroborate:** bounding-box change + **survives save→reopen** (the W21 trap).

Per-lane gates (each lane uses the gate matching its PHYSICS — pre-design, the W65 lesson):
| Lane | Class | Gate |
|---|---|---|
| planar_surface | surface-CREATE | ΔSheetBodies ≥ +1 ∧ ΔArea > 0 |
| offset_surface | surface-CREATE | ΔSheetBodies ≥ +1 ∧ ΔArea > 0 |
| thicken | surface→solid BRIDGE | **ΔVol > 0** (additive) ∧ ΔSolidBodies ≥ +1 |
| knit | surface AGGREGATION | **ΔSheetBodies < 0** (N→fewer) ∧ total area conserved (±ε) |

> ⚠️ thicken and knit INVERT the create-gate. thicken consumes a sheet into a solid
> (volume gate). knit MERGES sheets (body count goes DOWN — gating on "≥1 new body" would
> false-fail it, the inverse of the W65 sketched_bend false-fail).

0.2 **Marshaling:** any object-pointer / SAFEARRAY arg null = `VARIANT(pythoncom.VT_DISPATCH,
None)`; SelectByID2 callout (arg 8) = same on the late-bound proxy (a bare `None` walls
'Type mismatch') — [[reference_selectbyid2_callout_oop_wall]]. Post-resolve selection via
the callout-free `select_entity` (`IEntity.Select2`) where possible.

0.3 **Why surfaces should marshal (W65 taxonomy):** these are entity-based / parametric or
standalone-profile (like `boss_extrude`, which works) — they do NOT relate a profile to an
existing face for folding, so they avoid the W65 profile↔face ghost wall. Confidence:
planar/offset/thicken HIGH; knit MEDIUM (aggregation solver). If a lane genuinely no-ops
after correct geometry → characterize DEFERRED, don't iterate (the W65 honest-close rule).

0.4 **Contract:** `create_<kind>(doc, feature, target) -> tuple[bool, str|None]`, never
raises, fail-closed. `SPIKE_STATUS="UNFIRED"` (W0 flips post-seat). Gated registry block in
`features/__init__.py` (`if _<kind>_status=="GREEN": HANDLER_REGISTRY[...]`). Spike plumbing:
`sys.path.insert` for `spikes/v0_15`, shared typed `save_and_reopen`, `_results/<kind>.json`.

0.5 **Mode-A vs Mode-B:** probe BOTH per [[reference_createdefinition_qi_wall]]. knit has a
candidate FeatureData iface (`ISurfaceKnitFeatureData`) → a possible Mode-A
(CreateDefinition→typed_qi→CreateFeature); the others are legacy-`Insert*` Mode-B.

---

## §1 — Seat-fire order (LOCKED)

1. **planar_surface** + **offset_surface** — vanguard. Entity-based, parametric, highest OOP
   confidence; they also produce the surface bodies the later lanes consume.
2. **thicken** — bridge. The surface→solid transition (depends on a surface body existing).
3. **knit** — boss-fight. Multi-body aggregation; method disambiguation + inverted gate.

---

## §2 — Lane: `planar_surface` (vanguard)

**Reflected:** `IModelDoc2.InsertPlanarRefSurface() -> Boolean` (**0 args**). Fills a planar
region from the **pre-selected boundary** — a closed loop of coplanar edges OR a closed
sketch contour. Boolean return ⇒ verify-the-effect mandatory.

**Fixture:** `build_block` (40×30×10). Author a closed sketch (e.g. `CreateCornerRectangle`)
on a face/plane OR select the 4 coplanar boundary edges of one face. Pre-select that
boundary, then `doc.InsertPlanarRefSurface()`.

**Recipe:** count sheet bodies + (optional) total area before → select boundary →
`InsertPlanarRefSurface()` → `ForceRebuild3(False)` → gate **ΔSheetBodies ≥ +1 ∧ ΔArea > 0**
→ A7 `GetTypeName2` (log the kernel string) → save/reopen survival.

**`feature`/`target`:** `{"boundary": <sketch name or durable edge_refs>}`.

## §3 — Lane: `offset_surface` (vanguard)

**Reflected:** `IModelDoc2.InsertOffsetSurface(Thickness:Double, Reverse:Boolean) -> Void`
(**2 args**). Pre-select a **face** (or existing surface); offsets it into a new sheet body.
`Thickness=0` = a surface copy of the face. Void ⇒ verify mandatory.

**Fixture:** `build_block` → coordinate-pick the +X face (VARIANT callout) or a durable
`face_ref` → `select_entity` → `doc.InsertOffsetSurface(0.005, False)`.

**Recipe + gate:** same surface-CREATE gate (ΔSheetBodies ≥ +1 ∧ ΔArea > 0, survives reopen).
**`feature`:** `offset_mm` (default 5), `reverse` (default False). **`target`:** `face_ref`
(durable manifest face) or a coordinate pick.

## §4 — Lane: `thicken` (bridge — surface→solid)

**Reflected:** `IFeatureManager.FeatureBossThicken(Thickness:Double, Direction:Int32,
FaceIndex:Int32, FillVolume:Boolean, Merge:Boolean, UseFeatScope:Boolean,
UseAutoSelect:Boolean) -> Feature` (**7 args**). Pre-select a **surface body**; thickens it
into a solid. (`FeatureBossThicken2` is the 4-arg Void variant — use the 7-arg **Feature**
form.) `Direction`: 0/1/2 = side1/side2/both.

**Fixture (chained):** thicken needs a surface to consume — FIRST create one
(`InsertOffsetSurface` or `InsertPlanarRefSurface` on the block), select that sheet body,
then `fm.FeatureBossThicken(0.002, 0, 0, False, False, False, True)`.

**Gate — ADDITIVE (reverts to volume):** **ΔVol > 0 ∧ ΔSolidBodies ≥ +1**, survives reopen.
Returns a Feature; still verify the effect (don't trust the return).
**`feature`:** `thickness_mm` (default 2), `direction` (default "side1"). **`target`:** the
surface body ref / the chained-surface handle.

## §5 — Lane: `knit` (BOSS FIGHT — aggregation)

**Reflected (disambiguate on the seat — do NOT guess):**
- **Mode-B:** `IModelDoc2.InsertSewRefSurface(...)` — confirm its exact arity in the spike
  (the harvest entry's params must be re-read; W0's verb-grep surfaced the name, not the
  full sig). Pre-select 2+ adjacent sheet bodies; sews/knits them.
- **Mode-A candidate:** `ISurfaceKnitFeatureData` via `CreateDefinition → typed_qi →
  AccessSelections → CreateFeature` (probe; QI may E_NOINTERFACE → fall back to Mode-B).
- Related flags seen: `KnitTolerance`, `BKnit`, `TrimAndKnit` — knit gap tolerance may be a
  required parameter.

**Fixture (multi-body):** create **two** adjacent surface bodies sharing an edge (e.g. two
`InsertOffsetSurface` of adjacent faces, or two planar surfaces), select BOTH, then knit.

**Gate — AGGREGATION (INVERTED):** **ΔSheetBodies < 0** (e.g. 2 → 1) ∧ **total sheet area
conserved (±1e-6 m²)** ∧ survives reopen. If the knit closes a watertight volume a solid may
form (ΔVol>0) — log it but the pass condition is the body-count reduction + area
conservation. **Gating on "≥1 new body" is WRONG here** (knit removes bodies).

---

## §6 — Per-lane deliverables (own `wt_w66*` worktree)

1. `src/ai_sw_bridge/features/<kind>.py` — handler, `SPIKE_STATUS="UNFIRED"`, a
   `_sheet_bodies(doc)`/`_surface_area(body)` verify helper (mirror `hem.py::_metrics`
   shape), class-correct gate, never-raise.
2. `spikes/v0_2x/spike_<kind>.py` — fixture (chained for thicken/knit), fires the handler,
   A7 `GetTypeName2`, direct-API diagnostic on failure, save→reopen, writes
   `_results/<kind>.json`.
3. `tests/features/test_<kind>.py` — offline matrix (fake-COM): the class-correct gate
   (ghost → False), body-count + area deltas, VARIANT-null spy, fail-closed, `UNFIRED`.
4. Gated registry block in `features/__init__.py` (dormant until GREEN); do NOT touch
   `mutate._SUPPORTED_FEATURE_TYPES`.

## §7 — Risk register

| Lane | Method | Return | Risk | Confidence |
|---|---|---|---|---|
| planar_surface | InsertPlanarRefSurface (0) | Bool | boundary-selection closure | HIGH |
| offset_surface | InsertOffsetSurface (2) | Void | face selection; Void no-op | HIGH |
| thicken | FeatureBossThicken (7) | Feature | needs a surface first (chained fixture) | HIGH |
| knit | InsertSewRefSurface / ISurfaceKnitFeatureData | ? | method+arity unknown; multi-body select; gap tol | MEDIUM |

Carried doctrine: surface verify taxonomy ([[reference_sheetmetal_verify_fold_vs_additive]]
extended), reflect-first ([[feedback_reflect_check_existing_handlers]]), Mode-A/B probe
([[reference_createdefinition_qi_wall]]), verify the worktree against the brief before
firing (W65 worker-targeting lesson), never node/body-presence alone (W42 ghost).
