# W65 — Sheet-Metal Completion · GLM/Sonnet worker briefs

> **Epoch:** W65 · cut 2026-06-18 · **4 lanes** finishing the sheet-metal family by
> applying the W59 *legacy-`InsertSheetMetal*` + PCBA-null* lever to the members
> `CreateDefinition` walled (W56). W0 (Opus) reflected every signature from the DLL
> (`docs/sw_api_full.json`, SW2024 v32.1.0.123) BEFORE this brief — the arg counts
> below are real, not CHM-guessed.
>
> **Authoritative template:** `src/ai_sw_bridge/features/hem.py` (W59, SHIPPED). Every
> lane is a near-clone of it — read it first. **Authoritative fixture:**
> `spikes/v0_2x/spike_hem_v5.py::_build_fixture_v5` (builds a base-flange sheet +
> returns the longest boundary edge). **Authoritative recipe proof:** the W59 hem
> seat result (faces +8, vol +1103.84 mm³, survives reopen).

---

## §0 — Mandatory doctrine (every lane obeys, no exceptions)

0.1 **Mode-A is SKIPPED/QUARANTINED.** `CreateDefinition` is `E_NOINTERFACE` for the
sheet-metal secondary features (W55-C / W56 proved the wall). Do **not** re-probe random
swFm IDs. Go straight to the legacy `IFeatureManager.InsertSheetMetal*` (Mode-B). If a
genuine wall is hit in BOTH modes, it is a **characterized `DEFERRED.md` entry**, not a
forced ship (the `rib` precedent — walled both modes W59).

0.2 **The PCBA null is load-bearing.** Every method below takes a trailing
`PCBA : CustomBendAllowance` pointer. Pass `VARIANT(pythoncom.VT_DISPATCH, None)` — a bare
Python `None` walls `DISP_E_TYPEMISMATCH`. This is the W59 hem lock #1, verbatim
(`hem.py:181`). See also [[reference_selectbyid2_callout_oop_wall]] — the SAME class.

0.3 **Selection-based.** These features fold/bend an existing sheet-metal body. The target
entity (a boundary EDGE for edge_flange/jog/hem; a sketch line on a face for jog/3dBend;
a flange edge for miter) MUST be pre-selected before the call. Resolve a durable
`edge_ref` via `selection.live.resolve_edge_ref` → `select_entity(edge, mark=0)` (the hem
pattern). Do NOT coordinate-pick raw; the durable token survives the rebuild.

0.4 **Verify-the-EFFECT, ΔVol-honest.** Success = **ΔFaces > 0 AND |ΔVol| > 1e-6 mm³**,
surviving save→reopen. A non-None feature return, a feature-node, or a face-count delta
ALONE is the **W42 ghost trap** — and `edge_flange` (lane 1) is literally the ghost that
defined that trap. Reuse `hem.py::_metrics(doc)` verbatim (faces via `GetFaces`, vol via
`GetMassProperties(1.0)[3]*1e9`). NEVER report ghost success.

0.5 **The fixture is a SHEET-METAL body, not a block.** Plain `build_block` has no
sheet-metal feature manager state. Reuse `_build_fixture_v5(sw, mod)` (base-flange +
longest boundary edge). For features needing a *sketch* on a face (jog, 3dBend), the spike
authors that sketch on the base-flange's major face (see per-lane fixture notes).

0.6 **Handler contract.** `create_<kind>(doc, feature, target) -> tuple[bool, str|None]`.
Never raises (wrap the body; return `(False, reason)`). Fail-closed on bad params. Mirror
`hem.py` exactly: enum maps via a `_enum()` helper, mm→m conversion, deg→rad conversion.

0.7 **Enums come from the harvest, not your head.** Pull every enum value from
`docs/sw_api_full.json` (already reflected). Confirmed values you will need are inline
below; any not listed (relief types, sharp types), grep the harvest for the `*_e` array —
do NOT guess (the `sgSAMELENGTH`-not-`sgEQUAL` lesson).

0.8 **Registry deferral.** Author with `SPIKE_STATUS = "UNFIRED"`. In
`features/__init__.py` add the gated block (`if _<kind>_status == "GREEN":
HANDLER_REGISTRY["<kind>"] = create_<kind>`) — it stays dormant until W0 flips GREEN
post-seat. **Do NOT** add the kind to `mutate._SUPPORTED_FEATURE_TYPES` (these are NEW
registry kinds, disjoint from the built-in chain — the W64 collision lesson; the
`test_registry_keys_disjoint_from_builtin_chain` guard enforces it).

0.9 **Spike plumbing.** `spikes/v0_2x/spike_<kind>.py` must
`sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "v0_15"))` (for
`spike_earlybind_persist`), import `build`/`save_and_reopen` from the shared fixtures, and
write `_results/<kind>.json` (gitignored). Use the SHARED typed `save_and_reopen` (bare
`sw.OpenDoc6` walls arg-5).

---

## §1 — Seat-fire order (LOCKED by W0 2026-06-18)

1. **edge_flange** (re-proof / un-ghost) — vanguard. Best-understood member, unambiguous
   ΔVol>0 gate, validates the legacy+PCBA-null approach end-to-end *and* retires the W42
   quarantine.
2. **jog** — `InsertSheetMetalJog` returns **Void**, forcing the effect-verify discipline
   early. Single selection.
3. **miter_flange** — 14-arg Feature; more selection setup (a sketch on the flange edge).
4. **sketched_bend** — boss-fight: the method-name ambiguity is the unknown to crack.

---

## §2 — Lane: `edge_flange` (re-proof / UN-GHOST) — VANGUARD

**Status today:** advertised as a QUARANTINED ghost (`mutate.py`, W42: returns ok=True,
creates an Edge-Flange1 node, but ΔVol=0 — adds NOTHING). This lane re-proves it via the
legacy route with the ΔVol>0 gate, then un-quarantines.

**Reflected signature (DLL 32.1.0.123):**
```
IFeatureManager.InsertSheetMetalEdgeFlange(
    FlangeEdge      : Edge,      # the boundary edge to flange (pre-resolved durable)
    SketchFeat      : Feature,   # flange profile sketch; None for a simple rectangular flange
    BooleanOptions  : Int32,     # bit flags; 0 for defaults (confirm swEdgeFlangeOptions_e)
    DAngle          : Double,    # flange angle (rad)
    DRadius         : Double,    # bend radius (m)
    BendPosition    : Int32,     # swFlangePositionTypes_e
    DOffsetDist     : Double,    # offset (m); 0 if none
    ReliefType      : Int32,     # swBendReliefType_e (grep harvest to confirm)
    DReliefRatio    : Double,
    DReliefWidth    : Double,
    DReliefDepth    : Double,
    FlangeSharpType : Int32,     # swFlangeSharpType_e (grep harvest to confirm)
    PCBA            : CustomBendAllowance,   # -> VARIANT(VT_DISPATCH, None)
) -> Feature
```
NB there is also `InsertSheetMetalEdgeFlange2` (array form: `FlangeEdges:Object`,
`SketchFeats:Object`). Use the **single-edge** form first; fall back to the array form
(passing `VARIANT(VT_ARRAY|VT_DISPATCH,(edge,))`) only if the single form no-ops.

**Confirmed enums:** `swFlangePositionTypes_e` = MaterialInside=1, MaterialOutside=2,
BendOutside=3, BendCenterLine=4, BendSharp=5, BendTangent=6. (Default BendPosition =
MaterialInside=1.)

**Recipe (mirror hem.py):**
1. `_build_fixture_v5` → base-flange + longest boundary edge as a durable `edge_ref`.
2. `resolve_edge_ref` → `select_entity(edge, mark=0)`.
3. `faces_before, vol_before = _metrics(doc)`.
4. `fm.InsertSheetMetalEdgeFlange(edge, None, 0, math.radians(90), 0.001, 1, 0.0,
   relief_type, 0.5, 0.0, 0.0, sharp_type, VARIANT(VT_DISPATCH,None))` — FlangeEdge is the
   resolved live edge object (NOT a name); SketchFeat `None` = auto rectangular flange of
   `feature["length_mm"]`. **If a length-driven simple flange needs the length elsewhere**
   (the single sig has no length arg → SketchFeat or a follow-on `EditFlange` sets it),
   the spike must discover where the length lands — flag in telemetry, do not guess.
5. `doc.ForceRebuild3(False)`; re-`_metrics`; gate ΔFaces>0 ∧ |ΔVol|>eps.

**`feature` keys:** `angle_deg` (default 90), `radius_mm` (default 1), `length_mm`
(default 10), `position` (default "material_inside"), `offset_mm` (default 0).
**`target` keys:** `edge_ref` (durable dict).

**Verify matrix (offline, fake-COM):** enum mapping (each position token → value, bad
token → fail-closed); mm→m / deg→rad; PCBA arg is a VARIANT not None (spy the call, the
W64-guard pattern); ΔVol-gate logic (ghost → False, real fold → True); never-raise.

**Seat verdict:** GO = ΔFaces>0 ∧ ΔVol>0 ∧ survives reopen ∧ GetTypeName2 logged (A7).
This un-ghosts edge_flange — at integration, REMOVE it from the `mutate.py` quarantine and
the advertised-failing surface (coordinate with W0).

---

## §3 — Lane: `jog`

**Reflected signature:**
```
IFeatureManager.InsertSheetMetalJog(
    Angle      : Double,   # rad
    Radius     : Double,   # m
    OffsetDist : Double,   # m
    FlipDir    : Boolean,
    FixProjLen : Boolean,
    DimPos     : Int16,    # dimension position enum (grep harvest)
    BendPos    : Int16,    # swSMBendPosition / swFlangePositionTypes_e (grep)
) -> Void          # <-- RETURNS VOID. The return is USELESS. Effect-verify is the ONLY truth.
```
No PCBA arg on this one — but the Void return makes ΔVol-verify *more* load-bearing, not
less (this is the InsertDome/hem class: success is silent).

**Fixture:** a jog needs a **sketch line on a flat face** of the sheet-metal body. The
spike: `_build_fixture_v5` → select the major planar face → `InsertSketch2(True)` → draw a
single line across the face (`CreateLine`) → exit sketch → pre-select that sketch (or its
line) → fire `InsertSheetMetalJog`. The jog folds the sheet along the line.

**Recipe:** select the sketch-line → `_metrics` before →
`fm.InsertSheetMetalJog(math.radians(90), 0.001, 0.005, False, False, dim_pos, bend_pos)`
→ `ForceRebuild3(False)` → `_metrics` after → gate ΔFaces>0 ∧ |ΔVol|>eps.

**`feature` keys:** `angle_deg` (90), `radius_mm` (1), `offset_mm` (5), `flip` (False),
`fix_projected_length` (False). **`target` keys:** `sketch` (name of the on-face sketch) OR
a durable ref to the line; the spike owns sketch authoring on the fixture.

**Risk:** the sketch-line-on-face selection is the failure-prone step. If the jog no-ops,
the direct-API diagnostic must split selection-failure from API-failure (the mate_reference
/ ref_axis spike pattern).

---

## §4 — Lane: `miter_flange`

**Reflected signature (use the 14-arg → Feature overload, NOT the 11-arg Void one):**
```
IFeatureManager.InsertSheetMetalMiterFlange(
    UseDefaultRadius : Boolean,
    GlobalRadius     : Double,   # m
    RipGap           : Double,   # m
    UseDefaultRelief : Boolean,
    UseReliefRatio   : Boolean,
    ReliefRatio      : Double,
    ReliefWidth      : Double,
    ReliefDepth      : Double,
    ReliefType       : Int32,    # swBendReliefType_e (grep harvest)
    TrimSideBends    : Boolean,
    FlangePos        : Int32,    # swFlangePositionTypes_e (see §2 confirmed values)
    OffsetDist1      : Double,
    OffsetDist2      : Double,
    PCBA             : CustomBendAllowance,   # -> VARIANT(VT_DISPATCH, None)
) -> Feature
```
There are TWO overloads in the typelib (14-arg→Feature and 11-arg→Void). Bind the
**Feature-returning** one. If late-bound dispatch resolves to the Void overload, force the
14-arg form via the typed `typed_qi(IFeatureManager)` proxy (the W63 CDispatch escape).

**Fixture:** a miter flange runs along a **chain of edges with a profile sketch** on the
end face of the base flange. The spike: `_build_fixture_v5` → select an edge → author a
small profile sketch perpendicular at the edge → pre-select the profile sketch + the edge
chain → fire. (Miter is the most selection-heavy member — budget the most forensic rounds.)

**Recipe:** select profile sketch + edge(s) → `_metrics` before →
`fm.InsertSheetMetalMiterFlange(True, 0.001, 0.0, True, False, 0.5, 0.0, 0.0, relief_type,
True, 1, 0.0, 0.0, VARIANT(VT_DISPATCH,None))` → rebuild → gate.

**`feature` keys:** `radius_mm` (default-radius=True ⇒ ignored), `position`
("material_inside"), `rip_gap_mm` (0), `trim_side_bends` (True). **`target`:** `edge_ref`
(+ the spike authors the profile sketch).

---

## §5 — Lane: `sketched_bend` (BOSS FIGHT — method disambiguation)

**The unknown:** the harvest exposes NO method literally named `InsertSketchedBend`. Two
candidates carry the semantics — the spike MUST probe both and report which materializes
(do NOT pick blind):

```
# Candidate A (preferred — Feature return, has PCBA):
IFeatureManager.InsertSheetMetal3dBend(
    Angle            : Double,   # rad
    BUseDefaultRadius: Boolean,
    Radius           : Double,   # m
    FlipDir          : Boolean,
    BendPos          : Int16,    # swFlangePositionTypes_e (confirmed §2)
    PCBA             : CustomBendAllowance,   # -> VARIANT(VT_DISPATCH, None)
) -> Feature

# Candidate B (Boolean return — the "Insert Bends" auto-bend pass):
IFeatureManager.InsertBends2(
    Radius:Double, UseBendTable:String, UseKfactor:Double, UseBendAllowance:Double,
    UseAutoRelief:Boolean, OffsetRatio:Double, DoFlatten:Boolean,
) -> Boolean
```

**Discriminator:** "Sketched Bend" in the SW UI = select a sketch line on a flat face,
then bend the sheet along it. Candidate **A** (`InsertSheetMetal3dBend`) takes the
per-bend params (Angle/Radius/FlipDir/BendPos/PCBA) and operates on the pre-selected
sketch — it is the strong favorite. Candidate **B** is the global "find all bends on a
converted shell" pass (different intent). **Fire A first** with a pre-selected on-face
sketch line; only if A no-ops in both selection arrangements, characterize B.

**Fixture:** same as `jog` (§3) — base flange + a line sketch on the major face.

**Recipe (A):** select sketch line → `_metrics` →
`fm.InsertSheetMetal3dBend(math.radians(90), True, 0.001, False, 1,
VARIANT(VT_DISPATCH,None))` → rebuild → gate ΔFaces>0 ∧ |ΔVol|>eps.

**`feature` keys:** `angle_deg` (90), `radius_mm` (1, default-radius=True ⇒ ignored),
`flip` (False), `position` ("material_inside"). **`target`:** `sketch` (on-face line
sketch the spike authors).

**Seat telemetry MUST record** which candidate fired, both returns, ΔFaces/ΔVol for each,
and GetTypeName2 — so the doctrine memory captures the resolved method name.

---

## §6 — Per-lane deliverables (each lane, in its own worktree)

1. `src/ai_sw_bridge/features/<kind>.py` — handler, `SPIKE_STATUS = "UNFIRED"`, mirrors
   `hem.py` (enum maps, `_metrics`, durable-edge resolve+select, legacy `InsertSheetMetal*`
   + PCBA-null, ΔVol-gate, never-raise).
2. `spikes/v0_2x/spike_<kind>.py` — builds the sheet-metal fixture, authors any required
   on-face sketch, fires the handler, A7 GetTypeName2 probe, direct-API diagnostic on
   failure, save→reopen survival, writes `_results/<kind>.json`. Plumbing per §0.9.
3. `tests/features/test_<kind>.py` — offline matrix (fake-COM): enum mapping + fail-closed,
   unit conversion, **PCBA-is-a-VARIANT-not-None spy** (the W64 OOP-guard pattern), ΔVol
   ghost-gate (ghost→False / real→True), never-raise, `SPIKE_STATUS == "UNFIRED"`.
4. `features/__init__.py` — gated registry block (dormant until GREEN). Do NOT touch
   `mutate._SUPPORTED_FEATURE_TYPES`.

**Worktree isolation:** each lane in its own `wt_w65<kind>` worktree on `feat/w65-<kind>`
(per [[feedback_parallel_worktree_isolation]]). Hot file = `features/__init__.py` — each
lane appends its own block; W0 resolves the 4-way at integration (the W63/W64 pattern).

---

## §7 — Open-spikes register & risk notes (W0 tracks)

| Lane | Method | Return | Primary risk | Wall fallback |
|---|---|---|---|---|
| edge_flange | InsertSheetMetalEdgeFlange (13) | Feature | the W42 ghost recurs (ΔVol=0) under the legacy route too; or SketchFeat=None gives a degenerate flange | array form `EdgeFlange2`; then DEFERRED w/ ΔVol evidence |
| jog | InsertSheetMetalJog (7) | **Void** | sketch-line-on-face selection; Void return hides no-op | direct-API diagnostic; DEFERRED if no ΔVol |
| miter_flange | InsertSheetMetalMiterFlange (14) | Feature | overload binding (Void vs Feature); profile-sketch selection | typed_qi force; DEFERRED |
| sketched_bend | InsertSheetMetal3dBend (6) **?** | Feature | method-name ambiguity (A vs B) | probe both; DEFERRED w/ both telemetries |

**Doctrine carried in:** PCBA-null = `VARIANT(VT_DISPATCH,None)` ([[reference_selectbyid2_callout_oop_wall]]);
ΔVol>0 verify, never node-presence ([[project_body_ops_epoch]] W42 ghost); reflect-first
on the DLL ([[feedback_reflect_check_existing_handlers]]); legacy-Insert un-walls what
CreateDefinition can't ([[reference_createdefinition_qi_wall]] Mode-B; W59 hem
[[project_wave55_plan]]); pause-on-errors ([[feedback_pause_on_errors]]).

**Honest expectation:** 3/4 GREEN is a win; `rib` walled both modes (W59), so one member
resisting even the legacy route is a plausible characterized DEFERRED — not a failure.
