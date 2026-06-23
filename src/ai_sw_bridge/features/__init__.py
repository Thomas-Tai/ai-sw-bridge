"""Per-lane ``feature_add`` handler registry (the W56 parallel-wiring seam).

Why this package exists: every shipped ``_create_*`` handler lives in
``ai_sw_bridge.mutate`` and STAYS there — their offline tests monkeypatch
the COM seams (``typed_qi`` / ``select_entity`` / ``get_sw_app`` / ...) on
the ``mutate`` module namespace, so relocating them would break that
resolution for the whole suite. NEW feature_add kinds land here instead:
one module per lane, one registry entry, so parallel waves never collide
inside ``mutate.py`` (the single-file constraint that forced W56 wiring to
be sequenced one-lane-at-a-time).

Lane protocol (W56+):

1. Add ``features/<kind>.py`` defining a handler with the uniform
   ``_apply_feature`` contract::

       def create_<kind>(doc, feature, target) -> tuple[bool, str | None]

   (shared by dry-run and commit; return ``(False, <reason>)`` rather than
   raising). Verify-the-EFFECT inside the handler — volume/face/scalar
   delta, never count+name+"no error" (the W21/W42 ghost trap).
2. Register it below its module: ``HANDLER_REGISTRY["<kind>"] = create_<kind>``
   (imported and merged here, one line per lane).
3. Registry kinds are auto-advertised by ``sw_propose_feature_add`` and
   dispatched by ``_apply_feature`` after the built-in chain; built-in
   kinds win on a name collision, so keep keys disjoint from
   ``mutate._SUPPORTED_FEATURE_TYPES``.
4. Propose-time parameter validation does NOT run for registry kinds —
   the handler must fail closed at dry-run on bad parameters.
5. Lane tests patch COM seams on the lane module itself (e.g.
   ``monkeypatch.setattr(features.rib, "typed_qi", ...)``), not on
   ``mutate``.
"""

from __future__ import annotations

from typing import Any, Callable

Handler = Callable[[Any, dict, dict], "tuple[bool, str | None]"]

# kind -> handler. Populated by per-lane modules; ships empty until W56
# wires the first proven W55 recipe in.
HANDLER_REGISTRY: dict[str, Handler] = {}

# --- W67 Phase 4 (Debt #4): fail-loud registration gate ---------------------
# Before W67, each lane hand-wrote ``if SPIKE_STATUS == "GREEN": HANDLER_REGISTRY
# [k] = h``.  A lane author who forgot the guard, or typo'd the sentinel, would
# silently advertise an UNPROVEN (possibly OOP-walled) handler — the exact class
# of regression the proven-recipe-first rule exists to prevent.  ``_register_lane``
# is now the SOLE sanctioned path in: it registers iff seat-proven GREEN, allows
# an explicitly-dormant sentinel through untouched, and FAILS LOUD on anything
# else (a forgotten flip / typo'd "GREEN" is a bug, not a silent no-register).
_GREEN_STATUS = "GREEN"
_DORMANT_STATUSES = frozenset({"UNFIRED", "UNRUN", "DEFERRED", "WALLED", "DORMANT"})


def _register_lane(kind: str, handler: Handler, status: str) -> bool:
    """Register *handler* under *kind* iff its lane is seat-proven (GREEN).

    Returns True if registered, False if the lane is a recognized dormant
    sentinel (imported for provenance/fail-loud, intentionally not advertised).
    Raises ``RuntimeError`` if *status* is neither GREEN nor a known dormant
    sentinel — a lane MUST be seat-proven to join the registry, or declare an
    explicit dormant status; a malformed status fails loud (W67 Phase 4).
    """
    if status == _GREEN_STATUS:
        HANDLER_REGISTRY[kind] = handler
        return True
    if status in _DORMANT_STATUSES:
        return False
    raise RuntimeError(
        f"feature lane {kind!r} declares SPIKE_STATUS={status!r}, which is "
        f"neither {_GREEN_STATUS!r} nor a recognized dormant sentinel "
        f"({sorted(_DORMANT_STATUSES)}). A lane must be seat-proven (GREEN) to "
        f"register, or explicitly dormant — refusing to register an unproven "
        f"handler (W67 Phase 4 / Debt #4)."
    )


# W59 — sheet-metal hem via legacy InsertSheetMetalHem. CreateDefinition is
# E_NOINTERFACE for hem (W55-C), but the legacy route is GENERATIVE: seat-
# proven 2026-06-16 (spike_hem_v5, faces +8 / vol +1103.84 mm³ / survives
# reopen) via VARIANT(VT_DISPATCH,None) PCBA-null + a boundary edge_ref.
from .hem import SPIKE_STATUS as _hem_status  # noqa: E402
from .hem import create_hem  # noqa: E402

_register_lane("hem", create_hem, _hem_status)

# W59 — move_copy_body. Imports DORMANT and stays that way: both OOP routes
# are characterized walls (W58 InsertMoveCopyBody2 + CreateDefinition,
# W59 InsertMoveFace3 — all silent no-ops). The module's _register() gate
# never fires (SPIKE_STATUS != "GREEN"), so the registry advertises nothing;
# the move/copy intent is covered by the sketch-offset workaround (author
# geometry at the target coords via boss_extrude). Kept for fail-loud + the
# wall provenance.
from . import move_copy_body as _move_copy_body  # noqa: E402,F401

# Route move/copy_body through the centralized gate too (UNRUN → dormant skip);
# keeps every lane on one sanctioned path. The module's own _register() is the
# wall-provenance gate; this is the registry-seam mirror.
_register_lane("move_body", _move_copy_body.create_move_body, _move_copy_body.SPIKE_STATUS)
_register_lane("copy_body", _move_copy_body.create_copy_body, _move_copy_body.SPIKE_STATUS)

# W62 — composite curve (curves group, lane 1). Mode-A QUARANTINED on this
# SW build: the swconst harvest (docs/sw_api_full.json @ 32.1.0.123) exposes
# only two curve enums (14/61), neither yields a CreateDefinition object
# that accepts ICompositeCurveFeatureData (QI E_NOINTERFACE on the live
# seat). The interface is edit-only via IFeature.GetDefinition. Mode-B
# fires generative via legacy InsertCompositeCurve with mark=1 selection
# (the "Edges to join" PropertyManager list-box mark) and the callable-OR-
# property invocation guard (auto-invoked dispid trap). Seat-proven 2026-06-17
# (spike_composite, nodes +1 on a 40x30x10 block, survives save->reopen).
from .composite import SPIKE_STATUS as _composite_status  # noqa: E402
from .composite import create_composite  # noqa: E402

_register_lane("composite", create_composite, _composite_status)

# W62 — helix curve (curves group, lane 2). Mode-A QUARANTINED: the SW2024
# swconst harvest exposes NO swFeatureNameID for helix (DLL reflection
# 2026-06-17). Like composite, IHelixFeatureData is edit-only via
# IFeature.GetDefinition(); no creation enum exists. Mode-B fires
# generative via legacy InsertHelix (10-arg method) after selecting the
# sketch with Extension.SelectByID2 + VARIANT(VT_DISPATCH, None) callout.
# Seat-proven 2026-06-17 (spike_helix Mode-B PASS — helices_before=0,
# helices_after=1, survives save->reopen).
from .helix import SPIKE_STATUS as _helix_status  # noqa: E402
from .helix import create_helix  # noqa: E402

_register_lane("helix", create_helix, _helix_status)

# W62 — project_curve (curves group, boss-fight lane). Mode-A QUARANTINED:
# the swconst harvest exposes no creation enum (ids 14/61 only; the v1
# spike's QI scan rejected all 5 candidate ref-curve FeatureData ifaces
# on the live seat 2026-06-17). Mode-B fires via legacy
# IModelDoc2.InsertProjectedSketch2(Reverse: int) — the typelib-discovered
# operative method (the worker brief named InsertProjectCurve / etc which
# don't exist). Seat-proven 2026-06-17 (spike_project_curve_v2 PASS —
# ref-curve nodes 0->1, survives save->reopen).
from .project_curve import SPIKE_STATUS as _project_curve_status  # noqa: E402
from .project_curve import create_project_curve  # noqa: E402

_register_lane("project_curve", create_project_curve, _project_curve_status)

# W63 — bounding_box (doctrine-asymmetry probe). swFmBoundingBox (114) IS
# named in CreateDefinition's CHM-listed enumerations — the first W63
# candidate to potentially break the W62 quarantine streak. Mode-A FIRST
# (CreateDefinition -> IBoundingBoxFeatureData -> CreateFeature); Mode-B
# fallback via legacy IFeatureManager.InsertGlobalBoundingBox with the
# callable-or-property invocation guard (auto-invoked dispid trap).
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .bounding_box import SPIKE_STATUS as _bounding_box_status  # noqa: E402
from .bounding_box import create_bounding_box  # noqa: E402

_register_lane("bounding_box", create_bounding_box, _bounding_box_status)

# W63 — com_point (Center-of-Mass reference point). Mode-A SKIPPED BY DESIGN:
# InsertCenterOfMass is a no-arg legacy method with no FeatureData interface
# and no creation enum in swFeatureNameID_e — the W62 quarantine doctrine
# is asymmetric here (quarantine requires a candidate enum; com_point has
# none). Mode-B fires via legacy IModelDoc2.InsertCenterOfMass() with the
# callable-or-property invocation guard. SPIKE_STATUS gate: UNFIRED until
# W0 fires on the live seat.
from .com_point import SPIKE_STATUS as _com_point_status  # noqa: E402
from .com_point import create_com_point  # noqa: E402

_register_lane("com_point", create_com_point, _com_point_status)

# W63 — mate_reference (boss-fight lane, SHIPPED 2026-06-17). Mode-A
# QUARANTINE: the SW2024 swconst harvest exposes no swFmMateReference enum,
# so Mode-A is a no-op stub (W62 quarantine doctrine — never speculative-
# probe random IDs). Mode-B fires PARAMETRIC via IFeatureManager.
# InsertMateReference2 — a 12-arg call (DLL reflection 32.1.0.123) that
# passes IEntity references directly, abandoning the brittle SelectByID2
# selection-mark routing. Absent secondary/tertiary entities are nulled with
# plain None (NOT VARIANT — the typed proxy can't convert a VARIANT). The
# kernel materializes a 'MateReferenceGroupFolder' node (verified by
# case-insensitive 'materef' substring, surviving save->reopen).
from .mate_reference import SPIKE_STATUS as _mate_reference_status  # noqa: E402
from .mate_reference import create_mate_reference  # noqa: E402

_register_lane("mate_reference", create_mate_reference, _mate_reference_status)

# W65 — sketched_bend (sheet-metal completion, boss-fight lane).  Mode-A
# QUARANTINED: CreateDefinition is E_NOINTERFACE for sheet-metal secondary
# features (W55-C / W56).  Mode-B fires via legacy IFeatureManager.
# InsertSheetMetal3dBend (6-arg → Feature) — the method-name ambiguity
# between Candidate A (InsertSheetMetal3dBend) and Candidate B (InsertBends2)
# is resolved by the seat spike.  PCBA null via VARIANT(VT_DISPATCH, None).
# Target is a sketch line on a flat sheet-metal face (not a boundary edge).
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .sketched_bend import SPIKE_STATUS as _sketched_bend_status  # noqa: E402
from .sketched_bend import create_sketched_bend  # noqa: E402

_register_lane("sketched_bend", create_sketched_bend, _sketched_bend_status)

# W66 — planar_surface (surfaces group, vanguard lane). Planar reference
# surface via legacy IModelDoc2.InsertPlanarRefSurface (0-arg, Boolean).
# Pre-select a closed sketch boundary (FeatureByName → select_entity with
# mark=0), then call. Gate: surface-CREATE (ΔSheetBodies ≥ +1 ∧ ΔArea > 0).
# No CreateDefinition route — Mode-B only (the §0.5 legacy-Insert probe).
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .planar_surface import SPIKE_STATUS as _planar_surface_status  # noqa: E402
from .planar_surface import create_planar_surface  # noqa: E402

_register_lane("planar_surface", create_planar_surface, _planar_surface_status)

# W66 — offset_surface (surfaces group, vanguard lane). Offset surface via
# legacy IModelDoc2.InsertOffsetSurface(Thickness, Reverse) (2-arg, Void).
# Pre-select a face (select_entity with mark=0), then call with thickness
# in metres. Gate: surface-CREATE (ΔSheetBodies ≥ +1 ∧ ΔArea > 0). No
# CreateDefinition route — Mode-B only (the §0.5 legacy-Insert probe).
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .offset_surface import SPIKE_STATUS as _offset_surface_status  # noqa: E402
from .offset_surface import create_offset_surface  # noqa: E402

_register_lane("offset_surface", create_offset_surface, _offset_surface_status)

# W66 — thicken (surfaces group, lane 3 — bridge: surface→solid).  Mode-B
# only: IThickenFeatureData has no creation enum in the SW2024 swconst
# harvest (edit-only via IFeature.GetDefinition).  Mode-B fires via legacy
# IFeatureManager.FeatureBossThicken (7-arg → Feature) — all args are
# primitives (Double, Int32, Boolean), no VARIANT-null marshaling needed.
# Additive gate (REVERTS TO VOLUME): ΔVol > 0 ∧ ΔSolidBodies ≥ +1 (the
# sheet body is consumed into a solid; the surface-create gate is WRONG
# here — sheet body count may DECREASE).  Chained fixture: the spike
# creates a surface body first (InsertOffsetSurface), then thickens it.
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .thicken import SPIKE_STATUS as _thicken_status  # noqa: E402
from .thicken import create_thicken  # noqa: E402

_register_lane("thicken", create_thicken, _thicken_status)  # UNFIRED → dormant skip

# W66 — knit (surfaces group, BOSS FIGHT lane — aggregation).  Mode-B only:
# InsertSewRefSurface (5-arg → Feature) sews two or more sheet bodies into
# one.  AGGREGATION gate (INVERTED): ΔSheetBodies < 0 ∧ area > 0 (the sheet
# body count goes DOWN — gating on "≥1 new body" is WRONG here, the inverse
# of the W65 sketched_bend false-fail).  Selection requires mark=1 via
# Extension.SelectByID2 (not IEntity.Select2) — the CHM VB6 recipe.  Target
# is ≥2 body_refs (feature names) or auto-discovered sheet bodies.
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .knit import SPIKE_STATUS as _knit_status  # noqa: E402
from .knit import create_knit  # noqa: E402

_register_lane("knit", create_knit, _knit_status)

# W68 — fillet_face (face fillet).  Seat-proven 2026-06-21: the face-set wall
# was a makepy SAFEARRAY-of-IDispatch marshaling boundary, not a Parasolid
# refusal.  CreateDefinition(swFmFillet=1) -> typed_qi(ISimpleFilletFeatureData2)
# -> Initialize(swFaceFillet=2) -> SetFaces(which, VARIANT(VT_ARRAY|VT_DISPATCH,
# [face])) binds (GetFaceCount readback-guarded) -> CreateFeature (DISP_E_
# MEMBERNOTFOUND on return swallowed; the solid is already built).  Gate =
# |d_vol| > eps (face cert -57.94 mm³, GetTypeName2 'Fillet', survives reopen).
# full_round SHIPPED 2026-06-21 (Initialize(3), SetFaces 3/4/5 side1/center/
# side2; seat-proven dVol -1716.81mm³ on a 40x20x10 box — the prior slab ghost
# was a fixture artifact, not a wall).  Both fillet_type kinds ship via this lane.
from .fillet_face_fullround import SPIKE_STATUS as _fillet_face_status  # noqa: E402
from .fillet_face_fullround import create_fillet_face_fullround  # noqa: E402

_register_lane("fillet_face", create_fillet_face_fullround, _fillet_face_status)

# W68 — curve_through_xyz (4th curve type, sibling to composite/helix/project).
# Seat-proven 2026-06-21: Mode-B IModelDoc2 InsertCurveFileBegin -> N x
# InsertCurveFilePoint(x_m,y_m,z_m) -> InsertCurveFileEnd materializes a
# "CurveInFile" node (arc 119mm on a 3-point fire, ΔVol 0, survives reopen).
# CURVE gate = node-count delta ∧ readable arc length (the W42 ghost trap needs
# the geometric check, not node-count alone).
from .curve_through_xyz import SPIKE_STATUS as _curve_through_xyz_status  # noqa: E402
from .curve_through_xyz import create_curve_through_xyz  # noqa: E402

_register_lane("curve_through_xyz", create_curve_through_xyz, _curve_through_xyz_status)

# W68 — sketch_driven_pattern (4th pattern family: linear/circular/mirror/sketch).
# Seat-proven 2026-06-21: fm.FeatureSketchDrivenPattern(use_centroid, geom_patt)
# on seed(mark 4) + ref-sketch(mark 1) materializes a 'SketchPattern' node
# (+5 faces/+423mm³ from a 3-point sketch, survives reopen). gate_additive_solid.
from .sketch_driven_pattern import SPIKE_STATUS as _sketch_driven_pattern_status  # noqa: E402
from .sketch_driven_pattern import create_sketch_driven_pattern  # noqa: E402

_register_lane("sketch_driven_pattern", create_sketch_driven_pattern, _sketch_driven_pattern_status)

# W71 — scale (closed-form volume transform; locks the Part-Feature axis).
# IFeatureManager.InsertScale(Type, Uniform, X, Y, Z) -> Feature: a uniform
# scale is a pure matrix transform, so the kernel never traverses/solves
# geometry mid-invocation — the boundary law's MATERIALIZE column (W71 probe:
# 1.5× → Δvol ×3.375 = 1.5³ exact). VOLUME_TRANSFORM gate witnesses the
# commanded f**3 ratio (a no-op leaves ratio==1). Target body via the
# IBody2.Select doctrine. SPIKE_STATUS gate: UNFIRED until W0 fires the spike.
from .scale import SPIKE_STATUS as _scale_status  # noqa: E402
from .scale import create_scale  # noqa: E402

_register_lane("scale", create_scale, _scale_status)

# W73 — structural_weldment (the boundary-law macro-feature corollary).
# IFeatureManager.InsertStructuralWeldment5 sweeps a library .sldlfp profile
# along an explicit 3D-sketch path AND solves the member end-trim/coped/miter
# intersection in ONE generative transaction — the encapsulated macro-feature
# bypasses the raw-B-rep traversal wall (W73 probe: ΔVol +26739.822 mm³ / 2
# bodies; miter-merge fuses 2->1). swConnectedSegmentsOption is 1/2 — NEVER 0
# (0 ghosts the whole feature). Segments + Groups marshal via
# VARIANT(VT_ARRAY|VT_DISPATCH). ADDITIVE_SOLID gate (Δfaces>0 ∧ |ΔVol|>eps).
# SPIKE_STATUS gate: UNFIRED until W0 fires the production seat-proof.
from .structural_weldment import SPIKE_STATUS as _structural_weldment_status  # noqa: E402
from .structural_weldment import create_structural_weldment  # noqa: E402

_register_lane("structural_weldment", create_structural_weldment, _structural_weldment_status)

# Recipe-C — pattern family (linear/circular/mirror). Relocated from mutate.py
# into the registry (the first 1.0.0 strangler-fig cut). Seat-proven W21
# (spike 5a94b05); the handlers and their propose-time validation are unchanged,
# only their home moved. GREEN.
from .patterns import SPIKE_STATUS as _patterns_status  # noqa: E402
from .patterns import (  # noqa: E402
    create_circular_pattern,
    create_linear_pattern,
    create_mirror_feature,
)

_register_lane("linear_pattern", create_linear_pattern, _patterns_status)
_register_lane("circular_pattern", create_circular_pattern, _patterns_status)
_register_lane("mirror_feature", create_mirror_feature, _patterns_status)
