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

# W59 — sheet-metal hem via legacy InsertSheetMetalHem. CreateDefinition is
# E_NOINTERFACE for hem (W55-C), but the legacy route is GENERATIVE: seat-
# proven 2026-06-16 (spike_hem_v5, faces +8 / vol +1103.84 mm³ / survives
# reopen) via VARIANT(VT_DISPATCH,None) PCBA-null + a boundary edge_ref.
from .hem import create_hem  # noqa: E402

HANDLER_REGISTRY["hem"] = create_hem

# W59 — move_copy_body. Imports DORMANT and stays that way: both OOP routes
# are characterized walls (W58 InsertMoveCopyBody2 + CreateDefinition,
# W59 InsertMoveFace3 — all silent no-ops). The module's _register() gate
# never fires (SPIKE_STATUS != "GREEN"), so the registry advertises nothing;
# the move/copy intent is covered by the sketch-offset workaround (author
# geometry at the target coords via boss_extrude). Kept for fail-loud + the
# wall provenance.
from . import move_copy_body as _move_copy_body  # noqa: E402,F401

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

if _composite_status == "GREEN":
    HANDLER_REGISTRY["composite"] = create_composite

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

if _helix_status == "GREEN":
    HANDLER_REGISTRY["helix"] = create_helix

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

if _project_curve_status == "GREEN":
    HANDLER_REGISTRY["project_curve"] = create_project_curve

# W63 — bounding_box (doctrine-asymmetry probe). swFmBoundingBox (114) IS
# named in CreateDefinition's CHM-listed enumerations — the first W63
# candidate to potentially break the W62 quarantine streak. Mode-A FIRST
# (CreateDefinition -> IBoundingBoxFeatureData -> CreateFeature); Mode-B
# fallback via legacy IFeatureManager.InsertGlobalBoundingBox with the
# callable-or-property invocation guard (auto-invoked dispid trap).
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .bounding_box import SPIKE_STATUS as _bounding_box_status  # noqa: E402
from .bounding_box import create_bounding_box  # noqa: E402

if _bounding_box_status == "GREEN":
    HANDLER_REGISTRY["bounding_box"] = create_bounding_box

# W63 — com_point (Center-of-Mass reference point). Mode-A SKIPPED BY DESIGN:
# InsertCenterOfMass is a no-arg legacy method with no FeatureData interface
# and no creation enum in swFeatureNameID_e — the W62 quarantine doctrine
# is asymmetric here (quarantine requires a candidate enum; com_point has
# none). Mode-B fires via legacy IModelDoc2.InsertCenterOfMass() with the
# callable-or-property invocation guard. SPIKE_STATUS gate: UNFIRED until
# W0 fires on the live seat.
from .com_point import SPIKE_STATUS as _com_point_status  # noqa: E402
from .com_point import create_com_point  # noqa: E402

if _com_point_status == "GREEN":
    HANDLER_REGISTRY["com_point"] = create_com_point

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

if _mate_reference_status == "GREEN":
    HANDLER_REGISTRY["mate_reference"] = create_mate_reference

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

if _sketched_bend_status == "GREEN":
    HANDLER_REGISTRY["sketched_bend"] = create_sketched_bend

# W66 — planar_surface (surfaces group, vanguard lane). Planar reference
# surface via legacy IModelDoc2.InsertPlanarRefSurface (0-arg, Boolean).
# Pre-select a closed sketch boundary (FeatureByName → select_entity with
# mark=0), then call. Gate: surface-CREATE (ΔSheetBodies ≥ +1 ∧ ΔArea > 0).
# No CreateDefinition route — Mode-B only (the §0.5 legacy-Insert probe).
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .planar_surface import SPIKE_STATUS as _planar_surface_status  # noqa: E402
from .planar_surface import create_planar_surface  # noqa: E402

if _planar_surface_status == "GREEN":
    HANDLER_REGISTRY["planar_surface"] = create_planar_surface

# W66 — offset_surface (surfaces group, vanguard lane). Offset surface via
# legacy IModelDoc2.InsertOffsetSurface(Thickness, Reverse) (2-arg, Void).
# Pre-select a face (select_entity with mark=0), then call with thickness
# in metres. Gate: surface-CREATE (ΔSheetBodies ≥ +1 ∧ ΔArea > 0). No
# CreateDefinition route — Mode-B only (the §0.5 legacy-Insert probe).
# SPIKE_STATUS gate: UNFIRED until W0 fires on the live seat.
from .offset_surface import SPIKE_STATUS as _offset_surface_status  # noqa: E402
from .offset_surface import create_offset_surface  # noqa: E402

if _offset_surface_status == "GREEN":
    HANDLER_REGISTRY["offset_surface"] = create_offset_surface

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

if _thicken_status == "GREEN":
    HANDLER_REGISTRY["thicken"] = create_thicken

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

if _knit_status == "GREEN":
    HANDLER_REGISTRY["knit"] = create_knit
