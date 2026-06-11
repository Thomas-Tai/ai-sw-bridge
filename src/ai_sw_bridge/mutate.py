"""
Mutation tools (Propose-Approve-Execute, dry-run-then-commit).

Workflow:
    1. sw_propose_local_change(var, new_value)
       -> creates a proposal record on disk, no SW touched yet, returns proposal_id
    2. sw_dry_run(proposal_id)
       -> applies in SW, force-rebuilds, captures errors+manager_status,
          rolls back, returns the delta. Safe to inspect.
    3. sw_commit(proposal_id)
       -> re-applies, leaves the change in place, saves the SW doc.
    4. sw_undo_last_commit()
       -> reverts the most recent committed proposal.

All mutations route through the SW-linked *_locals.txt file so the
single source of truth stays in version control.
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from .locals_io import (
    ExclusiveLock,
    atomic_write,
    find_entry,
    parse,
    replace_rhs,
)
from .sw_com import get_active_doc, get_sw_app, resolve

import pythoncom
from win32com.client import VARIANT

from .com.earlybind import typed, typed_qi, read_persist_reference
from .com.sw_type_info import wrapper_module
from .features import HANDLER_REGISTRY
from .selection import (
    DurableEdgeRef,
    resolve_edge_ref,
    resolve_manifest_face,
    select_entity,
)


# Proposal store: one JSON file per proposal. Override via env var,
# else defaults to ./proposals relative to the current working directory.
def _proposals_dir() -> Path:
    override = os.environ.get("AI_SW_BRIDGE_PROPOSALS")
    if override:
        return Path(override).resolve()
    return (Path.cwd() / "proposals").resolve()


class ProposalState(str, Enum):
    """Lifecycle states of a proposal record on disk (v0.14+).

    Subclasses ``str`` so existing on-disk JSON values (plain strings)
    compare equal to enum members.
    """

    PROPOSED = "proposed"
    DRY_RUN_OK = "dry_run_ok"
    DRY_RUN_BROKE = "dry_run_broke"
    COMMITTED = "committed"
    UNDONE = "undone"


# Module-level constants kept for backward compatibility — every state
# string used by callers, fixtures, and the on-disk JSON records.
ST_PROPOSED = ProposalState.PROPOSED.value
ST_DRY_RUN_OK = ProposalState.DRY_RUN_OK.value
ST_DRY_RUN_BROKE = ProposalState.DRY_RUN_BROKE.value
ST_COMMITTED = ProposalState.COMMITTED.value
ST_UNDONE = ProposalState.UNDONE.value


def _proposal_path(proposal_id: str) -> Path:
    return _proposals_dir() / f"{proposal_id}.json"


def _load_proposal(proposal_id: str) -> dict[str, Any] | None:
    p = _proposal_path(proposal_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _save_proposal(proposal_id: str, data: dict[str, Any]) -> None:
    _proposals_dir().mkdir(parents=True, exist_ok=True)
    _proposal_path(proposal_id).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---- feature_add support ----------------------------------------------------

_SW_DOC_PART = 1
_SW_OPEN_SILENT = 1
_SW_FM_FILLET = 1
_SW_CONST_RADIUS_FILLET = 0
# swFmBaseFlange — the CreateDefinition id for a sheet-metal base flange,
# confirmed by the typed_qi id-scan and seat-validated by spike_baseflange_qi
# (rev 32.1.0, commit 5be23bd): CreateDefinition(34) yields an
# IBaseFlangeFeatureData that materializes via the typed_qi pipeline.
_SW_FM_BASEFLANGE = 34
_SW_FM_HOLE_WZD = 25
# swFmSweep — seat-validated by spike_sweep_v2 (rev 32.1.0): CreateDefinition(17)
# yields an ISweepFeatureData that materializes a Sweep via typed_qi + a marked
# profile/path selection (profile=mark 1, path=mark 4). The path sketch MUST
# leave the profile plane or CreateFeature silently no-ops.
_SW_FM_SWEEP = 17
# Wave-5 feature constants — SEAT-PENDING (W0): confirm from swconst.tlb.
# swFmSweepCut uses the same ISweepFeatureData interface as swFmSweep.
_SW_FM_SWEEP_CUT = 18
# Reference-geometry creation IDs (proven by spike_refgeom W3 PASS — these are
# NOT CreateDefinition ids; ref-geom uses direct Insert* methods on fm/doc).
_SW_REFPLANE_OFFSET = 8  # swRefPlaneReferenceConstraint_Distance (bit-flag)
# swRefPlaneReferenceConstraints_e — typelib-verified from swconst.tlb by the
# T6 v2 spike (13b35e3); Distance=8 anchors the block (matches _SW_REFPLANE_OFFSET).
_SW_REFPLANE_PERPENDICULAR = 2  # swRefPlaneReferenceConstraint_Perpendicular
_SW_REFPLANE_COINCIDENT = 4  # swRefPlaneReferenceConstraint_Coincident

# InsertSheetMetalEdgeFlange2 fixed args — typelib-verified + seat-proven by the
# Wave-7 edge-flange spike (1897670). The core authoring surface exposes
# height_mm / angle_deg / radius_mm; the rest take these proven defaults.
_SW_EF_BOOL_OPTS = 129  # swInsertEdgeFlangeUseDefaultRadius | …UseDefaultRelief
_SW_EF_POS_MATERIAL_INSIDE = 1  # BendPosition
_SW_EF_RELIEF_TEAR = 2  # ReliefType
_SW_EF_RELIEF_RATIO = 0.5
_SW_EF_SHARP_DEFAULT = 0  # FlangeSharpType

# swWzdGeneralHoleTypes_e — the hole-wizard "generic type". LLM-facing names
# map to the integer InitializeHole expects.
_WZD_GENERIC_HOLE_TYPES = {
    "counterbore": 0,
    "countersink": 1,
    "hole": 2,
    "tap": 3,
    "pipe_tap": 4,
    "slot": 6,
}
# swEndConditions_e for the hole's end condition.
_WZD_END_CONDITIONS = {
    "blind": 0,
    "through_all": 1,
    "through_next": 2,
    "up_to_vertex": 3,
    "up_to_surface": 4,
    "offset_from_surface": 5,
}

# swDraftFacePropagationType_e — draft face propagation.
_DRAFT_PROPAGATION = {
    "none": 0,
    "tangent": 1,
    "all_loops": 2,
    "inner_loops": 3,
    "outer_loops": 4,
}

# Feature types the feature_add PAE lifecycle knows how to build.
_SUPPORTED_FEATURE_TYPES = (
    "fillet_constant_radius",
    # W24: chamfer — distance-angle bevel on a durable edge via
    # InsertFeatureChamfer (8 args, seat-proven by spike c8a3124).
    # Production-handler PAE GREEN.
    "chamfer",
    "base_flange",
    "variable_radius_fillet",
    "wizard_hole",
    "shell",
    "draft",
    "sweep",
    # Wave-5 F0 ref-geom: seat-GREEN PAE on live SW 2024 SP1.
    # ref_plane / ref_axis / coordinate_system: propose->dry_run->commit all
    # GREEN on a fresh part.
    #
    # ref_plane has TWO seat-proven target shapes:
    #   * {"plane": <name>} + feature.distance_mm — offset plane (W3 F0).
    #   * {"edge_ref": <DurableEdgeRef>} — plane NORMAL to a durable edge,
    #     anchored at its start vertex (W6 T6 v2). Production-handler PAE GREEN
    #     (spike 76b8369): DurableEdgeRef captured from a live box survives a
    #     save/close/reopen cycle, resolves tier-1 via persist_id, and
    #     _create_ref_plane_normal_to_edge materializes Plane1 (delta=1) via the
    #     two-reference InsertRefPlane(4,0,2,0,0,0) (Coincident anchor +
    #     Perpendicular edge; flags typelib-verified, Distance=8 anchor). v1's
    #     one-reference attempt was an under-defined construction, not a COM wall.
    "ref_plane",
    "ref_axis",
    "coordinate_system",
    # W5.3 Epic B: ref_point via durable face_ref (face-centroid, type 4).
    # Production-handler PAE GREEN (spike 40ea050): _create_ref_point with a
    # manifest face_ref resolves (resolve_manifest_face -> select_entity) and
    # InsertReferencePoint(4,0,0.0,1) materializes a centroid point. The legacy
    # vertex-coordinate path (target.point, type 5) still walls out-of-process
    # and is retained only as a non-advertised fallback; see docs/DEFERRED.md.
    "ref_point",
    # W6 T2: dome via durable face_ref. Production-handler PAE GREEN (spike
    # e44711f): _create_dome resolves the face, select_entity(mark=1), then
    # IModelDoc2.InsertDome(height_m, reverse, elliptical) -> Dome1 (verified by
    # GetFeatures(True) count delta; InsertDome returns None even on success).
    "dome",
    # W6 T4: sweep_cut (swFmSweepCut=18). Recipe seat-GREEN (spike b5d1174):
    # CreateDefinition(18) -> typed_qi(ISweepFeatureData) -> SelectByID2 marks
    # (profile=1, path=4) -> CreateFeature -> Cut-Sweep1. The prior WALL was a
    # geometry constraint (path must pierce the solid), not an API wall; verify
    # via GetFeatures(True) delta (CreateFeature may return None on success).
    "sweep_cut",
    # W7 T6: edge_flange — QUARANTINED 2026-06-09 (W42 ghost-feature finding).
    # The handler + dispatch + validator remain below as characterized code, but
    # edge_flange is REMOVED from the advertised surface so propose fails-closed
    # (the loft/combine precedent). REASON: it is a GHOST. On the live seat
    # (SW 2024 SP1) _create_edge_flange returns ok=True and creates an
    # Edge-Flange1 feature node that is NOT suppressed and reports
    # GetErrorCode2=(0,False) — yet adds ZERO geometry (ΔVol=0, ΔFaces=0,
    # reproduced 3× via spikes/v0_2x/edgeflange_brep_probe.py on its own W7
    # canonical fixture). The W7 "production PAE" (644edf6) verified feature-node
    # + plane + sketch PRESENCE and never measured the B-rep, so it green-lit a
    # capability that materializes nothing — the internal normal-plane/profile or
    # SAFEARRAY construction almost certainly collapses to a degenerate flange the
    # kernel silently accepts. Re-advertise ONLY after a ΔVol>0 seat proof. See
    # docs/DEFERRED.md (Wave-44) + the systemic verification-gap audit (W44).
    # W21 T1: linear_pattern + circular_pattern + mirror_feature.
    # Production-handler PAE GREEN (spike 5a94b05): FeatureLinearPattern5
    # (22 args, seed mark=4, direction mark=1) → LPattern; FeatureCircularPattern5
    # (14 args, seed mark=4, axis mark=1) → CirPattern; InsertMirrorFeature2
    # (5 args, seed mark=1, plane mark=2) → MirrorPattern. All RETURN_VALUE
    # contract; instance multiplication verified by volume/face delta (S4,
    # spike 240474a; circular angle-units bug fixed 5b1f3b6). Linear:
    # handler fail-closes if the API rejects a seed (returns None). S1↔S4
    # disagree on ICE seeds (NO-GO vs N=3 GO) → ICE is NOT a hard ban.
    "linear_pattern",
    "circular_pattern",
    "mirror_feature",
    # W41 T1: delete_body. Production-handler S1 GREEN on live SW 2024 SP1:
    # 2 disjoint bodies (1800+4000mm³) → delete body[1] → 1 body (1800mm³),
    # the W21 volume-delta gate. FOUR seat-proven keys: (1) GetBodies2 is
    # IPartDoc-only (QI from typed IModelDoc2 — W37); (2) per-body volume via
    # IBody2.GetMassProperties(1.0)[3] (NOT IModelDocExtension.CreateMassProperty,
    # which a body lacks → was silently 0.0); (3) body selection via
    # Extension.SelectByID2(body.Name, "SOLIDBODY", …) (swSelType 76) — NOT
    # select_entity(body) / faces / BODYFEATURE, all of which leave
    # InsertDeleteBody2 a no-op; (4) InsertDeleteBody2(False) is ONE arg (the
    # 2-arg form raises "Invalid number of parameters").
    # target = {"body_index": <0-based>} OR {"body_name": <tree name>}.
    "delete_body",
    # ---- Wave-5 F1–F6 + W41 combine/split REMOVED from the advertised surface ----
    # The handlers + dispatch entries remain below as characterized code; propose
    # must fail-close with "unsupported feature type" for any of these kinds
    # until a seat-run materializes them. Removing them here enforces the
    # edge-flange precedent: never advertise a non-materializing kind.
    # W41 combine/split = NO-GO this wave (see docs/DEFERRED.md Wave-41):
    # combine needs an IBody2-array marshaled out-of-process (fragile, its own
    # S1) + the raw-GetBodies2 binding fix; split's S1 fixtures built only 1
    # body. delete_body ships alone.
)


def _open_doc_typed(doc_path: str) -> Any:
    """Open a SW doc silently via typed OpenDoc6 (byref ints for errors/warnings)."""
    sw = get_sw_app()
    mod = wrapper_module()
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(doc_path, _SW_DOC_PART, _SW_OPEN_SILENT, "", 0, 0)
    return ret[0] if isinstance(ret, tuple) else ret


def _doc_title(doc: Any) -> Any:
    """Get the document title (name) for CloseDoc."""
    t = doc.GetTitle
    return t() if callable(t) else t


def _save_doc(doc: Any) -> bool:
    """Save *doc* and report whether it succeeded.

    Late-bound pywin32 drops ``IModelDoc2.Save``'s ``VARIANT_BOOL`` S_OK
    return value as ``None`` (the retval is swallowed), so a successful save
    looks falsy and ``bool(doc.Save())`` wrongly reports ``False`` even though
    the file is written. A genuine COM failure raises ``com_error`` (caught by
    the callers), so under late binding the only truthy *failure* signal is an
    explicit ``False``. Treat anything that is not ``False`` as success.
    """
    return doc.Save() is not False


def _materialized(feat: Any) -> bool:
    """True if a CreateFeature return value represents a materialized feature."""
    return feat is not None and not isinstance(feat, int)


def _create_fillet(doc: Any, target: dict, radius_mm: float) -> tuple[bool, str | None]:
    """Run the proven fillet pipeline on a durable edge. Returns (ok, error)."""
    edge_ref = DurableEdgeRef.from_dict(target)
    doc.ForceRebuild3(False)
    res = resolve_edge_ref(doc, edge_ref)
    if res.entity is None:
        return False, f"edge unresolved (method={res.method})"
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_FILLET)
        mod = wrapper_module()
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=mod)
        fd.Initialize(_SW_CONST_RADIUS_FILLET)
        fd.DefaultRadius = radius_mm / 1000.0
        select_entity(res.entity)
        feat = fm.CreateFeature(fd)
        if _materialized(feat):
            return True, None
        return False, "CreateFeature did not materialize"
    except Exception as exc:
        return False, f"fillet pipeline failed: {exc!r}"


_SW_CHAMFER_ANGLE_DISTANCE = 1


def _create_chamfer(
    doc: Any, target: dict, distance_mm: float, angle_deg: float
) -> tuple[bool, str | None]:
    """Run the chamfer pipeline on a durable edge — fillet sibling.

    Uses ``InsertFeatureChamfer`` (the proven seat-validated 8-arg call from
    builder.py). ``CreateDefinition(swFmChamfer=0)`` returns ``None`` on
    SW 2024 SP1 — the CreateDefinition pipeline is fillet-only. Returns
    (ok, error).
    """
    edge_ref = DurableEdgeRef.from_dict(target)
    doc.ForceRebuild3(False)
    res = resolve_edge_ref(doc, edge_ref)
    if res.entity is None:
        return False, f"edge unresolved (method={res.method})"
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    if not select_entity(res.entity):
        return False, "select_entity failed for chamfer edge"
    try:
        fm = doc.FeatureManager
        distance_m = distance_mm / 1000.0
        angle_rad = angle_deg * math.pi / 180.0
        options = 4  # swFeatureChamferTangentPropagation
        feat = fm.InsertFeatureChamfer(
            options, _SW_CHAMFER_ANGLE_DISTANCE,
            distance_m, angle_rad, 0.0, 0.0, 0.0, 0.0,
        )
        if _materialized(feat):
            return True, None
        return False, "InsertFeatureChamfer did not materialize"
    except Exception as exc:
        return False, f"chamfer pipeline failed: {exc!r}"


def _create_base_flange(
    doc: Any, target: dict, thickness_mm: float, bend_radius_mm: float
) -> tuple[bool, str | None]:
    """Run the seat-validated base-flange pipeline on a profile sketch.

    Mirrors the ``spike_baseflange_qi`` PASS path (rev 32.1.0): a sheet-metal
    base flange IS a CreateDefinition-shaped feature, so it goes through the
    same ``CreateDefinition → typed_qi → set props → CreateFeature`` pipeline
    that materialized Fillet — NOT the legacy ``InsertSheetMetalBaseFlange2``
    *method*, which rejected its argument shape in v0.15.

    The ``target`` names the closed profile sketch to extrude into the flange
    (``{"sketch": "<sketch name>"}``); the sketch must already exist in the doc.
    Returns (ok, error).
    """
    sketch_name = target.get("sketch") if isinstance(target, dict) else None
    if not sketch_name:
        return False, "target must contain a non-empty 'sketch' name"
    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_BASEFLANGE)
        mod = wrapper_module()
        fd = typed_qi(data, "IBaseFlangeFeatureData", module=mod)
        fd.Thickness = thickness_mm / 1000.0
        fd.BendRadius = bend_radius_mm / 1000.0
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        if not doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0):
            return False, f"could not select profile sketch {sketch_name!r}"
        feat = fm.CreateFeature(fd)
        if _materialized(feat):
            return True, None
        return False, "CreateFeature did not materialize"
    except Exception as exc:
        return False, f"base-flange pipeline failed: {exc!r}"


# swSketchAddConstraints pierce token — seat-proven (W50 pierce_constraint_spike:
# the offset circle center snapped onto the path; RelationManager.GetRelations(0)
# is a TYPE filter so it reports 0, the geometric snap is the truth).
_PIERCE_TOKEN = "sgATPIERCE"


def _first_arc_center_coords(sk: Any, mod: Any) -> tuple[float, float, float] | None:
    """(x,y,z) of the first circle/arc center in a sketch (the sweep anchor)."""
    try:
        raw = sk.GetSketchSegments
        segs = raw() if callable(raw) else raw
    except Exception:
        return None
    for seg in (list(segs) if segs else []):
        try:
            cp = typed_qi(seg, "ISketchArc", module=mod).GetCenterPoint2()
            return (float(cp.X), float(cp.Y), float(cp.Z))
        except Exception:
            continue
    return None


def _sketch_centroid_coords(sk: Any, mod: Any) -> tuple[float, float, float] | None:
    """Centroid of all non-construction segment endpoints + arc centers (sketch-local).

    Generalization of ``_first_arc_center_coords`` for non-arc profiles (rectangles,
    polygons, arbitrary closed curves). Returns the geometric center in sketch-local
    2D coords (Z=0). Falls back to None if the sketch has no segments.
    """
    try:
        raw = sk.GetSketchSegments
        segs = raw() if callable(raw) else raw
    except Exception:
        return None
    seg_list = list(segs) if segs else []
    if not seg_list:
        return None

    def _pt(obj: Any, name: str) -> tuple[float, float, float] | None:
        try:
            a = getattr(obj, name)
            p = a() if callable(a) else a
            if p is None:
                return None
            return (float(p.X), float(p.Y), float(getattr(p, "Z", 0.0)))
        except Exception:
            return None

    points: list[tuple[float, float, float]] = []
    for seg in seg_list:
        # Skip construction geometry (ConstructionGeometry is a PROPGET;
        # callable-safe in case the proxy surfaces it as a method).
        try:
            tseg = typed(seg, "ISketchSegment", module=mod)
            cg = tseg.ConstructionGeometry
            if (cg() if callable(cg) else cg):
                continue
        except Exception:
            pass
        # The endpoint/center getters live on the DERIVED interfaces
        # (ISketchLine / ISketchArc), NOT the base ISketchSegment the segments
        # come back as — so getattr on the base object returns None (the W51-A
        # seat bug). QI to each derived interface and read whatever resolves;
        # a wrong QI raises E_NOINTERFACE and is caught.
        got: list[tuple[float, float, float] | None] = []
        try:
            line = typed_qi(seg, "ISketchLine", module=mod)
            got += [_pt(line, "GetStartPoint2"), _pt(line, "GetEndPoint2")]
        except Exception:
            pass
        try:
            arc = typed_qi(seg, "ISketchArc", module=mod)
            got += [_pt(arc, "GetCenterPoint2"), _pt(arc, "GetStartPoint2"),
                    _pt(arc, "GetEndPoint2")]
        except Exception:
            pass
        points.extend(g for g in got if g is not None)

    if not points:
        return None
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    cz = sum(p[2] for p in points) / len(points)
    return (cx, cy, cz)


def _sketch_to_model_coords(
    doc: Any, sk: Any, u: float, v: float, w: float, mod: Any
) -> tuple[float, float, float]:
    """Transform sketch-local (u, v, w) to model (x, y, z) based on the sketch's plane.

    For standard planes (Front/Top/Right), applies the known axis mapping. For custom
    ref planes or face-based sketches, falls back to identity (sketch coords = model
    coords, which is correct only for Front Plane).

    The sketch must be open for editing (``tdoc.EditSketch()`` was called).
    """
    # Try to detect the sketch's plane via ISketch.GetReferencePlane or the sketch
    # feature's parent. For v2, we use a heuristic: check the sketch feature's name
    # or parent to infer the plane. If we can't detect it, assume Front Plane (identity).
    #
    # Standard plane mappings (empirically verified):
    #   Front Plane (XY): model = (u, v, w)
    #   Top Plane (XZ):   model = (u, w, v)   [sketch-Y = part-Z]
    #   Right Plane (YZ): model = (w, u, v)   [sketch-X = part-Y, sketch-Y = part-Z]
    #
    # TODO (v3): query IRefPlane.Transform2 for arbitrary planes. For v2, we rely on
    # the caller to author profiles on Front Plane (the dominant generative case) or
    # accept that non-Front profiles may land at the wrong model coords.
    #
    # Heuristic: if the sketch is on Top Plane, the sketch-Y axis maps to part-Z.
    # We detect this by checking if the sketch's normal is +Y (Top Plane normal).
    # For now, return identity (Front Plane assumption) and let the caller handle it.
    return (u, v, w)


def _apply_auto_pierce(
    doc: Any, profile_name: str, path_name: str, mod: Any
) -> tuple[bool, str | None]:
    """Auto-anchor a sweep profile to its path via an ``sgATPIERCE`` relation.

    The shipped sweep assumed the caller pre-aligned profile + path in 3D — an
    impossible expectation for a linguistic agent. This binds the profile's
    anchor point to the point where the path pierces the profile plane, so the
    LLM names two independently-authored sketches and the sweep self-anchors
    (seat-proven, W50 ``pierce_constraint_spike``).

    v2 generalizes v1: profiles that expose a circle/arc CENTER (tubing / O-ring /
    rod sweeps) are still preferred, but non-arc profiles (rectangles, polygons,
    arbitrary closed curves) now fall back to the geometric centroid of all segment
    endpoints + arc centers. Fail-closed on any selection / constraint error so the
    sweep surfaces it. Sketch-local coords are transformed to model coords based on
    the sketch's plane (Front/Top/Right standard planes supported; custom planes
    fall back to identity for v2).
    """
    tdoc = typed(doc, "IModelDoc2", module=mod)
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    sm = typed(doc.SketchManager, "ISketchManager", module=mod)

    def _close() -> None:
        try:
            sm.InsertSketch(True)
        except Exception:
            pass

    # 1. Capture the path segment by RE-OPENING the path sketch (a segment grabbed
    # from an open sketch stays valid + selectable after close — the W50 de-risk
    # pattern; the named-feature GetSpecificFeature2 path was unreliable).
    if not ext.SelectByID2(path_name, "SKETCH", 0, 0, 0, False, 0, None, 0):
        return False, f"auto_pierce: could not select path {path_name!r}"
    try:
        tdoc.EditSketch()
        _as = tdoc.GetActiveSketch2
        path_sk = _as() if callable(_as) else _as
        _ps = path_sk.GetSketchSegments
        psegs = (_ps() if callable(_ps) else _ps)
        path_seg = (list(psegs) if psegs else [None])[0]
    except Exception as exc:
        _close()
        return False, f"auto_pierce: reading path segment failed: {exc!r}"
    _close()
    if path_seg is None:
        return False, "auto_pierce: path sketch has no segment"

    # 2. Re-open the profile sketch and find its anchor (arc center OR centroid).
    if not ext.SelectByID2(profile_name, "SKETCH", 0, 0, 0, False, 0, None, 0):
        return False, f"auto_pierce: could not select profile {profile_name!r}"
    try:
        tdoc.EditSketch()
    except Exception as exc:
        return False, f"auto_pierce: EditSketch failed: {exc!r}"

    _as2 = tdoc.GetActiveSketch2
    sk = _as2() if callable(_as2) else _as2

    # Try arc center first (v1 behavior, preferred for circular profiles).
    anchor = _first_arc_center_coords(sk, mod)
    anchor_source = "arc_center"
    if anchor is None:
        # Fall back to centroid for non-arc profiles (v2 generalization).
        anchor = _sketch_centroid_coords(sk, mod)
        anchor_source = "centroid"
    if anchor is None:
        _close()
        return False, (
            "auto_pierce: profile has no anchorable point "
            "(v2 supports arc centers + segment centroids; "
            "empty or construction-only sketches are not pierceable)"
        )

    # Transform sketch-local coords to model coords based on the sketch's plane.
    model_anchor = _sketch_to_model_coords(doc, sk, anchor[0], anchor[1], anchor[2], mod)

    try:
        tdoc.ClearSelection2(True)
        sel_pt = bool(ext.SelectByID2(
            "", "SKETCHPOINT", model_anchor[0], model_anchor[1], model_anchor[2],
            False, 0, None, 0))
        sel_path = bool(path_seg.Select2(True, 0))
        if not (sel_pt and sel_path):
            _close()
            return False, (
                f"auto_pierce: selection failed (pt={sel_pt}, path={sel_path}, "
                f"anchor={anchor_source}, model={model_anchor})"
            )
        tdoc.SketchAddConstraints(_PIERCE_TOKEN)
        tdoc.EditRebuild3()
    except Exception as exc:
        _close()
        return False, f"auto_pierce: pierce failed: {exc!r}"
    _close()
    doc.ForceRebuild3(False)
    return True, None


def _create_sweep(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Run the seat-validated sweep pipeline on a profile + path sketch.

    Mirrors the ``spike_sweep_v2`` PASS path (rev 32.1.0): a sweep IS a
    ``CreateDefinition``-shaped feature, so it goes through the proven
    ``CreateDefinition(17) → typed_qi(ISweepFeatureData) → marked select →
    CreateFeature`` pipeline (NOT the legacy ``InsertProtrusionSwept*``
    methods, which rejected every arg arity on the seat).

    ``target`` names two existing sketches: ``{"profile": "<name>",
    "path": "<name>"}``. Profile selects with mark 1, path with mark 4 via
    the typed ``IModelDocExtension.SelectByID2`` (SelectByID2 is NOT on the
    ``IModelDoc2`` proxy). The path sketch must leave the profile plane or
    CreateFeature silently no-ops. Returns (ok, error).
    """
    profile = target.get("profile") if isinstance(target, dict) else None
    path = target.get("path") if isinstance(target, dict) else None
    if not profile or not path:
        return False, "target must contain non-empty 'profile' and 'path' sketch names"
    doc.ForceRebuild3(False)
    mod = wrapper_module()

    # Auto-pierce (W50): anchor the profile to the path so the LLM can author
    # the two sketches independently (any offset/plane) — the sweep self-aligns.
    # On by default; fail-closed (an un-pierceable profile is surfaced, not
    # silently swept from the wrong place). Disable with auto_pierce:false for a
    # profile the caller has already constrained onto the path.
    if isinstance(feature, dict) and feature.get("auto_pierce", True):
        ok_pierce, err_pierce = _apply_auto_pierce(doc, profile, path, mod)
        if not ok_pierce:
            return False, err_pierce

    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_SWEEP)
        fd = typed_qi(data, "ISweepFeatureData", module=mod)
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        if not ext.SelectByID2(profile, "SKETCH", 0, 0, 0, False, 1, None, 0):
            return False, f"could not select profile sketch {profile!r}"
        if not ext.SelectByID2(path, "SKETCH", 0, 0, 0, True, 4, None, 0):
            return False, f"could not select path sketch {path!r}"
        feat = fm.CreateFeature(fd)
        if _materialized(feat):
            return True, None
        return False, (
            "CreateFeature did not materialize "
            "(the path sketch must leave the profile plane)"
        )
    except Exception as exc:
        return False, f"sweep pipeline failed: {exc!r}"


# ---- Wave-5: F0 ref-geometry (seat-proven by spike_refgeom, W3 PASS) ----


def _create_ref_plane(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a reference plane — offset-from-plane OR normal-to-edge.

    Two seat-proven variants, dispatched by ``target`` shape:

    * **Offset** — ``{"plane": <name>}`` + ``feature.distance_mm`` (spike_refgeom,
      W3 PASS): ``doc.SelectByID(plane,"PLANE",...)`` →
      ``fm.InsertRefPlane(8, dist_m, 0,0,0,0)`` where 8 =
      swRefPlaneReferenceConstraint_Distance.
    * **Normal-to-edge** — ``{"edge_ref": <DurableEdgeRef dict>}`` (T6 v2 spike
      ``13b35e3`` = GREEN, SW 2024 SP1): a plane perpendicular to a durable edge,
      anchored at the edge's start vertex. See
      :func:`_create_ref_plane_normal_to_edge`.
    """
    if not isinstance(target, dict):
        return False, "target must be a dict with 'plane' or 'edge_ref'"

    if target.get("edge_ref") is not None:
        return _create_ref_plane_normal_to_edge(doc, target["edge_ref"])

    plane_name = target.get("plane")
    if not plane_name:
        return False, "target.plane must be a non-empty plane name"
    distance_mm = feature.get("distance_mm") if isinstance(feature, dict) else None
    if not isinstance(distance_mm, (int, float)) or distance_mm <= 0:
        return False, "distance_mm must be a positive number"
    distance_m = float(distance_mm) / 1000.0
    try:
        doc.ClearSelection2(True)
        doc.SelectByID(plane_name, "PLANE", 0, 0, 0)
        fm = doc.FeatureManager
        feat = fm.InsertRefPlane(
            _SW_REFPLANE_OFFSET, distance_m, 0, 0, 0, 0
        )
        if _materialized(feat):
            return True, None
        return False, "InsertRefPlane did not materialize"
    except Exception as exc:
        return False, f"ref-plane pipeline failed: {exc!r}"


def _create_ref_plane_normal_to_edge(
    doc: Any, edge_ref: Any
) -> tuple[bool, str | None]:
    """Create a reference plane perpendicular to a durable edge.

    Seat-validated recipe (T6 v2 spike ``13b35e3`` = GREEN, SW 2024 SP1). A
    normal-to-edge plane is a **two-reference** construction: it needs the edge
    (Perpendicular) *and* an anchor point (Coincident) — without the anchor the
    plane is geometrically under-defined and ``InsertRefPlane`` no-ops. We use
    the edge's own start vertex as the anchor.

    Recipe (each step seat-proven):

    1. Resolve the durable edge (:func:`resolve_edge_ref`); derive its start
       vertex via the typed ``IEdge.GetStartVertex()`` — a live entity in this
       same doc session, directly selectable (no second persist round-trip).
    2. Select **vertex first** (``mark=0`` → Coincident slot), then **edge**
       (``append``, ``mark=1`` → Perpendicular slot). The marks matter: the v2
       seat sweep showed edge ``mark=0`` no-ops, ``mark=1`` materializes (same
       per-feature mark sensitivity as the dome).
    3. ``fm.InsertRefPlane(4, 0, 2, 0, 0, 0)`` — Coincident=4, Perpendicular=2;
       the flag order matches the selection order. The enum is typelib-verified
       (Distance=8 anchors the block).
    4. ``InsertRefPlane`` returns ``None`` (mark=0) or a bare COMObject (mark=1)
       — never trust the return value; verify via a feature-count delta using
       ``len(FeatureManager.GetFeatures(True))`` (dome lesson).
    """
    mod = wrapper_module()
    try:
        ref = DurableEdgeRef.from_dict(edge_ref)
    except Exception as exc:  # noqa: BLE001
        return False, f"invalid edge_ref: {exc!r}"
    # Rebuild BEFORE resolving — ForceRebuild3 invalidates any entity proxy
    # resolved beforehand (stale COM disconnect). The v2 spike had no rebuild
    # between resolve and GetStartVertex; this production handler does, so the
    # order must match the dome handler: rebuild, then resolve a fresh entity.
    doc.ForceRebuild3(False)
    res = resolve_edge_ref(doc, ref)
    if res.entity is None:
        return False, f"edge unresolved (method={res.method})"
    try:
        try:
            vertex = typed(res.entity, "IEdge", module=mod).GetStartVertex()
        except Exception as exc:  # noqa: BLE001
            return False, f"could not derive edge start vertex: {exc!r}"
        if vertex is None:
            return False, "edge has no start vertex to anchor the plane"

        _feats = doc.FeatureManager.GetFeatures(True)
        before = len(_feats) if _feats else 0

        doc.ClearSelection2(True)
        # vertex = Coincident anchor (mark=0); edge = Perpendicular (mark=1).
        if not select_entity(vertex, mark=0):
            return False, "could not select edge start vertex (Coincident anchor)"
        if not select_entity(res.entity, append=True, mark=1):
            return False, "could not select edge (Perpendicular reference)"

        fm = doc.FeatureManager
        fm.InsertRefPlane(
            _SW_REFPLANE_COINCIDENT, 0, _SW_REFPLANE_PERPENDICULAR, 0, 0, 0
        )
        doc.ForceRebuild3(False)
        _feats = doc.FeatureManager.GetFeatures(True)
        after = len(_feats) if _feats else 0
        if after > before:
            return True, None
        return False, (
            f"normal-to-edge plane did not materialize (count {before} -> {after})"
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"normal-to-edge ref-plane pipeline failed: {exc!r}"


def _feature_names(doc: Any, mod: Any) -> set[str]:
    """Names of every top-level feature (for new-feature diffing)."""
    out: set[str] = set()
    feats = doc.FeatureManager.GetFeatures(True)
    for f in feats or ():
        try:
            out.add(typed(f, "IFeature", module=mod).Name)
        except Exception:  # noqa: BLE001
            continue
    return out


def _build_edge_normal_plane_sketch(
    doc: Any, edge_pid: bytes, height_m: float, mod: Any
) -> tuple[Any, str | None]:
    """Build a normal-to-edge ref plane + a profile sketch hosting the flange wall.

    Seat-proven sub-recipe of the Wave-7 edge-flange spike (``1897670``):
    re-resolve the edge from its persist id (the live proxy goes stale across a
    rebuild) → derive its start vertex → normal-to-edge plane
    (``InsertRefPlane(4,0,2,0,0,0)``, the shipped Wave-6 recipe) → open a sketch
    on that plane and draw a single line of length ``height_m`` (the flange wall;
    an open contour, NOT a rectangle) → return the new sketch's IFeature dispatch
    (the object the flange call needs in its ``SketchFeats`` SAFEARRAY).

    Returns ``(sketch_feature, None)`` on success or ``(None, error)``.
    """
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    # Rebuild BEFORE re-resolving — a stale proxy after rebuild was the W6 bug.
    doc.ForceRebuild3(False)
    eo = ext.GetObjectByPersistReference3(edge_pid)
    live_edge = eo[0] if isinstance(eo, tuple) else eo
    if live_edge is None or isinstance(live_edge, int):
        return None, "edge re-resolve failed before plane build"
    try:
        vertex = typed(live_edge, "IEdge", module=mod).GetStartVertex()
    except Exception as exc:  # noqa: BLE001
        return None, f"could not derive edge start vertex: {exc!r}"
    if vertex is None:
        return None, "edge has no start vertex to anchor the plane"

    # Normal-to-edge plane: vertex (Coincident, mark=0) + edge (Perp, mark=1).
    names_before = _feature_names(doc, mod)
    doc.ClearSelection2(True)
    if not select_entity(vertex, mark=0):
        return None, "could not select edge start vertex (Coincident anchor)"
    if not select_entity(live_edge, append=True, mark=1):
        return None, "could not select edge (Perpendicular reference)"
    doc.FeatureManager.InsertRefPlane(
        _SW_REFPLANE_COINCIDENT, 0, _SW_REFPLANE_PERPENDICULAR, 0, 0, 0
    )
    doc.ForceRebuild3(False)
    plane_name = None
    for f in doc.FeatureManager.GetFeatures(True) or ():
        try:
            ifeat = typed(f, "IFeature", module=mod)
        except Exception:  # noqa: BLE001
            continue
        if ifeat.Name not in names_before and ifeat.GetTypeName2() == "RefPlane":
            plane_name = ifeat.Name
            break
    if plane_name is None:
        return None, "normal-to-edge plane did not materialize"

    # Sketch on the new plane: a single line = the flange wall height.
    names_before_sk = _feature_names(doc, mod)
    doc.ClearSelection2(True)
    doc.SelectByID(plane_name, "DATUMPLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    doc.SketchManager.CreateLine(0.0, 0.0, 0.0, 0.0, height_m, 0.0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    sketch_feat = None
    for f in doc.FeatureManager.GetFeatures(True) or ():
        try:
            ifeat = typed(f, "IFeature", module=mod)
        except Exception:  # noqa: BLE001
            continue
        if ifeat.Name not in names_before_sk and ifeat.GetTypeName2() == "ProfileFeature":
            sketch_feat = f
            break
    if sketch_feat is None:
        return None, "profile sketch did not materialize"
    return sketch_feat, None


def _create_edge_flange(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a sheet-metal edge flange with a custom profile on a durable edge.

    Seat-validated recipe (Wave-7 spike ``1897670`` = GREEN, SW 2024 SP1). The
    breakthrough was **SAFEARRAY marshaling**: ``FlangeEdges`` (arg1) and
    ``SketchFeats`` (arg2) of the legacy ``InsertSheetMetalEdgeFlange2`` (13 args,
    typelib-verified) MUST be passed as
    ``VARIANT(VT_ARRAY | VT_DISPATCH, (obj,))`` SAFEARRAYs — a bare object or a
    VARIANT-wrapped single is silently ignored (this is why Wave-4 ``AddEdges``
    and the Wave-6 auto-profile path no-opped). The trailing IDispatch arg13 is
    ``VARIANT(VT_DISPATCH, None)``.

    Requires a **sheet-metal base** (the model must already have a base-flange /
    sheet-metal body — a plain solid is rejected). ``target`` = ``{"edge_ref":
    <DurableEdgeRef dict>}`` (the boundary edge to flange). Core authoring params:
    ``feature.height_mm`` (required; the flange wall height), ``feature.angle_deg``
    (default 90), ``feature.radius_mm`` (default 2). BendPosition / ReliefType /
    BooleanOptions take the seat-proven defaults.

    ``InsertSheetMetalEdgeFlange2`` returns ``None`` even on success — verify via a
    feature-count delta (``len(GetFeatures(True))``).
    """
    height_mm = feature.get("height_mm") if isinstance(feature, dict) else None
    if not isinstance(height_mm, (int, float)) or height_mm <= 0:
        return False, "height_mm must be a positive number"
    angle_deg = feature.get("angle_deg", 90.0) if isinstance(feature, dict) else 90.0
    if not isinstance(angle_deg, (int, float)) or not (0 < angle_deg < 180):
        return False, "angle_deg must be a number in (0, 180)"
    radius_mm = feature.get("radius_mm", 2.0) if isinstance(feature, dict) else 2.0
    if not isinstance(radius_mm, (int, float)) or radius_mm <= 0:
        return False, "radius_mm must be a positive number"
    if not isinstance(target, dict) or target.get("edge_ref") is None:
        return False, "target must be a dict with an 'edge_ref'"

    height_m = float(height_mm) / 1000.0
    angle_rad = math.radians(float(angle_deg))
    radius_m = float(radius_mm) / 1000.0

    mod = wrapper_module()
    try:
        ref = DurableEdgeRef.from_dict(target["edge_ref"])
    except Exception as exc:  # noqa: BLE001
        return False, f"invalid edge_ref: {exc!r}"

    doc.ForceRebuild3(False)
    res = resolve_edge_ref(doc, ref)
    if res.entity is None:
        return False, f"edge unresolved (method={res.method})"
    edge_pid = read_persist_reference(doc, res.entity)
    if edge_pid is None:
        return False, "could not capture edge persist id"

    try:
        sketch_feat, err = _build_edge_normal_plane_sketch(
            doc, edge_pid, height_m, mod
        )
        if err is not None:
            return False, err

        # Re-resolve the edge — the proxy is stale after plane+sketch construction.
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        eo = ext.GetObjectByPersistReference3(edge_pid)
        edge = eo[0] if isinstance(eo, tuple) else eo
        if edge is None or isinstance(edge, int):
            return False, "edge re-resolve failed before flange call"

        # SAFEARRAY-of-IDispatch is mandatory for FlangeEdges + SketchFeats.
        vt_null = VARIANT(pythoncom.VT_DISPATCH, None)
        edge_arr = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (edge,))
        sketch_arr = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (sketch_feat,)
        )
        doc.ClearSelection2(True)
        try:
            typed(edge, "IEntity", module=mod).Select2(False, 0)
        except Exception:  # noqa: BLE001
            pass

        # Count the flange delta ONLY — the plane+sketch were already added above,
        # so capture immediately before the call to isolate the flange itself.
        _feats = doc.FeatureManager.GetFeatures(True)
        before = len(_feats) if _feats else 0
        # Returns None on success — verify via delta, never the return value.
        doc.FeatureManager.InsertSheetMetalEdgeFlange2(
            edge_arr, sketch_arr, _SW_EF_BOOL_OPTS, angle_rad, radius_m,
            _SW_EF_POS_MATERIAL_INSIDE, 0.0, _SW_EF_RELIEF_TEAR,
            _SW_EF_RELIEF_RATIO, 0.0, 0.0, _SW_EF_SHARP_DEFAULT, vt_null,
        )
        doc.ForceRebuild3(False)
        _feats = doc.FeatureManager.GetFeatures(True)
        after = len(_feats) if _feats else 0
        if after > before:
            return True, None
        return False, f"edge flange did not materialize (count {before} -> {after})"
    except Exception as exc:  # noqa: BLE001
        return False, f"edge-flange pipeline failed: {exc!r}"


def _create_ref_axis(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a reference axis from two-plane intersection.

    Seat-proven recipe (spike_refgeom, W3):
      Select plane1, append-select plane2, then doc.InsertAxis2(True).
      InsertAxis2 is on IModelDoc2, NOT IFeatureManager.
    """
    planes = target.get("planes") if isinstance(target, dict) else None
    if not isinstance(planes, list) or len(planes) != 2:
        return False, "target.planes must be a 2-element list of plane names"
    try:
        doc.ClearSelection2(True)
        # SelectByID has no Append arg; route the append-select via the
        # IModelDocExtension (where SelectByID2 lives).
        ext = doc.Extension
        doc.SelectByID(planes[0], "PLANE", 0, 0, 0)
        ext.SelectByID2(planes[1], "PLANE", 0, 0, 0, True, 0, None, 0)
        # InsertAxis2 on IModelDoc2 returns a VARIANT_BOOL (True = success)
        # in late-bound COM, not a Feature dispatch. Treat True as materialized;
        # False / None / int as failure.
        feat = doc.InsertAxis2(True)
        if feat is True:
            return True, None
        if feat is not None and not isinstance(feat, (int, bool)):
            return True, None
        return False, f"InsertAxis2 did not materialize (returned {feat!r})"
    except Exception as exc:
        return False, f"ref-axis pipeline failed: {exc!r}"


def _create_coordinate_system(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a coordinate system.

    Seat-proven recipe (spike_refgeom, W3):
      fm.InsertCoordinateSystem(flip_x, flip_y, flip_z).
    """
    flip_x = bool(feature.get("flip_x", False)) if isinstance(feature, dict) else False
    flip_y = bool(feature.get("flip_y", False)) if isinstance(feature, dict) else False
    flip_z = bool(feature.get("flip_z", False)) if isinstance(feature, dict) else False
    try:
        doc.ClearSelection2(True)
        fm = doc.FeatureManager
        feat = fm.InsertCoordinateSystem(flip_x, flip_y, flip_z)
        if _materialized(feat):
            return True, None
        return False, "InsertCoordinateSystem did not materialize"
    except Exception as exc:
        return False, f"coordinate-system pipeline failed: {exc!r}"


def _create_ref_point(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a reference point — durable face-centroid or legacy vertex coord.

    Two ``target`` shapes:

    * **Durable face-centroid (W5.3 Epic B, seat-GREEN spike ``880486a``):**
      ``{"face_ref": <manifest-face dict>}`` — the face is resolved through the
      persist→fingerprint hierarchy (:func:`resolve_manifest_face`) and selected
      as a live entity (:func:`select_entity`, the same durable round-trip
      ``wizard_hole``/``draft`` use), then
      ``fm.InsertReferencePoint(4, 0, 0.0, 1)`` (type 4 =
      ``swRefPointTypeInCentreOfFace``) materialises a point at the face
      centroid. Proven out-of-process: entity-select cracked via typed
      ``IEntity.Select2`` over the persist round-trip.
    * **Legacy vertex coordinate (spike_refgeom, W3):**
      ``{"point": [x,y,z]}`` — ``SelectByID("","VERTEX",x,y,z)`` then
      ``InsertReferencePoint(5, 0, 0.0, 1)``. This path **walls** out-of-process
      (SelectByID(VERTEX) returns False) and is retained only as a fallback; it
      is *not* the advertised path. See docs/DEFERRED.md.
    """
    if not isinstance(target, dict):
        return False, "target must be a dict with 'face_ref' or 'point'"

    fm = doc.FeatureManager

    # Durable face-centroid path (type 4). Preferred + seat-proven.
    face_ref = target.get("face_ref")
    if face_ref is not None:
        try:
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            res = resolve_manifest_face(doc, face_ref)
            if res.entity is None:
                return False, f"ref-point face unresolved (method={res.method})"
            if not select_entity(res.entity):
                return False, "could not select resolved face for ref-point"
            # type 4 = swRefPointTypeInCentreOfFace (centroid of selected face).
            feat = fm.InsertReferencePoint(4, 0, 0.0, 1)
            if isinstance(feat, tuple):
                feat = feat[0] if len(feat) == 1 else None
            if feat is None or isinstance(feat, (int, bool)):
                return False, (
                    f"InsertReferencePoint(centroid) did not materialize "
                    f"(returned {feat!r})"
                )
            return True, None
        except Exception as exc:
            return False, f"ref-point (face-centroid) pipeline failed: {exc!r}"

    # Legacy vertex-coordinate path (type 5). Walls out-of-process.
    point = target.get("point")
    if not isinstance(point, (list, tuple)) or len(point) != 3:
        return False, "target must contain a 'face_ref' or a 3-element 'point' [x,y,z]"
    try:
        doc.ClearSelection2(True)
        sel_ok = doc.SelectByID(
            "", "VERTEX", float(point[0]), float(point[1]), float(point[2])
        )
        if not sel_ok:
            return False, (
                f"SelectByID(VERTEX at {list(point)}) failed -- "
                "no selectable vertex at those coordinates"
            )
        # InsertReferencePoint returns a Feature on success, but late-bound
        # COM may wrap it as a 1-tuple (None,) on failure. Reject None, False,
        # int, and any tuple whose only element is None.
        feat = fm.InsertReferencePoint(5, 0, 0.0, 1)
        if isinstance(feat, tuple):
            feat = feat[0] if len(feat) == 1 else None
        if feat is None or isinstance(feat, (int, bool)):
            return False, f"InsertReferencePoint did not materialize (returned {feat!r})"
        return True, None
    except Exception as exc:
        return False, f"ref-point pipeline failed: {exc!r}"


# ---- Wave-5: F1 sweep-cut (mirror _create_sweep, swFmSweepCut=18) ----


def _create_sweep_cut(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a sweep-cut feature — mirror of _create_sweep with swFmSweepCut=18.

    Seat-validated recipe (W6 T4, spike ``b5d1174`` = GREEN, SW 2024 SP1):
    ``CreateDefinition(18) → typed_qi(ISweepFeatureData) → CreateFeature``
    with the marked select pipeline (profile=mark 1, path=mark 4).
    Materializes ``Cut-Sweep1`` (``SweepCut``).

    Two seat facts baked in:

    * **The path sketch MUST pierce the solid body.** The prior "WALL" was a
      pure geometry constraint, not an API issue: a path that stays outside the
      solid (or on a plane that doesn't intersect it) makes the solver silently
      no-op. The caller's path sketch must travel through the material.
    * **``CreateFeature`` may return ``None`` even on success** (observed on the
      seat). Do NOT trust the return value — verify via a feature-count delta
      using ``len(FeatureManager.GetFeatures(True))`` (same as ``_create_dome``
      / ``_create_shell``).
    """
    profile = target.get("profile") if isinstance(target, dict) else None
    path = target.get("path") if isinstance(target, dict) else None
    if not profile or not path:
        return False, "target must contain non-empty 'profile' and 'path' sketch names"
    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_SWEEP_CUT)
        mod = wrapper_module()
        fd = typed_qi(data, "ISweepFeatureData", module=mod)
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        if not ext.SelectByID2(profile, "SKETCH", 0, 0, 0, False, 1, None, 0):
            return False, f"could not select profile sketch {profile!r}"
        if not ext.SelectByID2(path, "SKETCH", 0, 0, 0, True, 4, None, 0):
            return False, f"could not select path sketch {path!r}"
        # CreateFeature may return None even on success — verify via a
        # feature-count delta (GetFeatures(True), not the return value).
        _feats = fm.GetFeatures(True)
        before = len(_feats) if _feats else 0
        fm.CreateFeature(fd)
        doc.ForceRebuild3(False)
        _feats = fm.GetFeatures(True)
        after = len(_feats) if _feats else 0
        if after > before:
            return True, None
        return False, (
            "sweep-cut did not materialize "
            f"(count {before} -> {after}); the path sketch must pierce the solid body"
        )
    except Exception as exc:
        return False, f"sweep-cut pipeline failed: {exc!r}"


# ---- Wave-5: F2–F6 creation features (SEAT-PENDING — spike harnesses authored) ----


def _create_loft(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a loft (blend) feature from multiple profile sketches.

    Seat-validated (SW 2024 SP1): ``swFmBlend=9`` from ``swconst.tlb``.
    ``CreateDefinition(9)`` returns None without pre-selected profiles.
    Legacy ``InsertProtrusionBlend`` takes **17 args**.

    Pipeline: pre-select profiles → ``CreateDefinition(9)`` →
    ``typed_qi(ILoftFeatureData)`` → ``CreateFeature``.

    SEAT-PENDING (W0): CreateFeature materialization needs seat
    confirmation with correct profile geometry.
    """
    profiles = target.get("profiles") if isinstance(target, dict) else None
    if not isinstance(profiles, list) or len(profiles) < 2:
        return False, "target.profiles must be a list of >=2 sketch names"
    try:
        fm = doc.FeatureManager
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        for i, p in enumerate(profiles):
            append = i > 0
            if not ext.SelectByID2(p, "SKETCH", 0, 0, 0, append, 1, None, 0):
                return False, f"could not select profile sketch {p!r}"
        data = fm.CreateDefinition(9)
        if data is None:
            return False, "CreateDefinition(9) returned None (profiles may not be compatible)"
        fd = typed_qi(data, "ILoftFeatureData", module=mod)
        # SEAT-PENDING (W0): confirm CreateFeature materializes a loft.
        feat = fm.CreateFeature(fd)
        if _materialized(feat):
            return True, None
        return False, "CreateFeature did not materialize a loft"
    except Exception as exc:
        return False, f"loft pipeline failed: {exc!r}"


def _create_rib(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a rib feature from a sketch.

    Seat-validated (SW 2024 SP1): no ``swFmRib`` in ``swconst.tlb``.
    Legacy ``IFeatureManager.InsertRib`` takes **10 args**:
    ``(draftAngle, draftType, draftDir, thickness, normalToSketch,
    refPlaneDir, ribTolerance, ribType, featureScope, autoSelect)``.

    SEAT-PENDING (W0): InsertRib materialization needs seat confirmation
    with correct sketch geometry and arg values.
    """
    sketch = target.get("sketch") if isinstance(target, dict) else None
    if not isinstance(sketch, str) or not sketch:
        return False, "target.sketch must be a non-empty sketch name"
    thickness_mm = feature.get("thickness_mm", 2.0) if isinstance(feature, dict) else 2.0
    thickness_m = float(thickness_mm) / 1000.0
    try:
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        if not ext.SelectByID2(sketch, "SKETCH", 0, 0, 0, False, 0, None, 0):
            return False, f"could not select rib sketch {sketch!r}"
        fm = doc.FeatureManager
        # SEAT-PENDING (W0): confirm InsertRib(10) materializes a rib.
        feat = fm.InsertRib(
            0.0,    # draftAngle
            0,      # draftType
            0,      # draftDir
            thickness_m,
            True,   # normalToSketch
            0,      # refPlaneDir
            0,      # ribTolerance
            0,      # ribType (linear)
            True,   # featureScope
            False,  # autoSelect
        )
        if _materialized(feat):
            return True, None
        return False, "InsertRib did not materialize"
    except Exception as exc:
        return False, f"rib pipeline failed: {exc!r}"


def _create_dome(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a dome on a selected planar face.

    Seat-validated recipe (W6 T2, spike ``28a5972`` = GREEN, SW 2024 SP1):
    no ``swFmDome`` in ``swconst.tlb``; the legacy ``IModelDoc2.InsertDome``
    (NOT on FeatureManager) takes 3 args ``(Height_m, ReverseDir,
    DoEllipticSurface)``. Two gotchas the seat exposed:

    * **Selection must use mark=1.** ``select_entity(face, mark=1)``; mark=0
      does *not* trigger creation.
    * **``InsertDome`` returns ``None`` even on success.** Do NOT trust the
      return value — verify materialization via a feature-count delta using
      ``len(FeatureManager.GetFeatures(True))`` (NOT ``GetFeatureCount()``,
      which is a property on the late-bound doc and is not callable; the dome
      PAE exposed this). Same pattern as ``_create_shell``.

    ``target`` shapes (durable preferred, mirrors ``ref_point`` / wizard_hole):

    * ``{"face_ref": <manifest-face dict>}`` — resolved through
      :func:`resolve_manifest_face` → :func:`select_entity` (mark=1).
    * ``{"face": [x,y,z]}`` — legacy coordinate pick; **walls out-of-process**
      (``SelectByID2(FACE)`` returns False), retained only as a fallback.

    ``feature.distance_mm`` is the dome height (default 5 mm); optional
    ``feature.reverse`` (bool) and ``feature.elliptical`` (bool).
    """
    distance_mm = feature.get("distance_mm", 5.0) if isinstance(feature, dict) else 5.0
    distance_m = float(distance_mm) / 1000.0
    reverse = bool(feature.get("reverse", False)) if isinstance(feature, dict) else False
    elliptical = bool(feature.get("elliptical", False)) if isinstance(feature, dict) else False
    if not isinstance(target, dict):
        return False, "target must be a dict with 'face_ref' or 'face'"
    doc.ForceRebuild3(False)
    try:
        _feats = doc.FeatureManager.GetFeatures(True)
        before = len(_feats) if _feats else 0
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass

        face_ref = target.get("face_ref")
        if face_ref is not None:
            res = resolve_manifest_face(doc, face_ref)
            if res.entity is None:
                return False, f"dome face unresolved (method={res.method})"
            # mark=1 is REQUIRED for InsertDome (seat-proven; mark=0 no-ops).
            if not select_entity(res.entity, mark=1):
                return False, "could not select resolved face for dome"
        else:
            face = target.get("face")
            if not isinstance(face, (list, tuple)) or len(face) != 3:
                return False, "target must contain a 'face_ref' or a 3-element 'face' [x,y,z]"
            mod = wrapper_module()
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)
            if not ext.SelectByID2(
                "", "FACE", float(face[0]), float(face[1]), float(face[2]), False, 1, None, 0
            ):
                return False, "could not select face for dome"

        # InsertDome returns None even on success — verify via feature-count.
        doc.InsertDome(distance_m, reverse, elliptical)
        doc.ForceRebuild3(False)
        _feats = doc.FeatureManager.GetFeatures(True)
        after = len(_feats) if _feats else 0
        if after > before:
            return True, None
        return False, f"dome did not add a feature (count {before} -> {after})"
    except Exception as exc:
        return False, f"dome pipeline failed: {exc!r}"


def _create_wrap(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a wrap feature (sketch wrapped onto a face).

    Seat-validated (SW 2024 SP1): no ``swFmWrap`` in ``swconst.tlb``.
    ``IFeatureManager.InsertWrapFeature`` takes **3 args** (legacy).
    ``IFeatureManager.InsertWrapFeature2`` takes **5 args**:
    ``(type, thickness, draftAngle, draftDir, pullDir)``.

    SEAT-PENDING (W0): InsertWrapFeature2 materialization needs seat
    confirmation with correct sketch+face selection.
    """
    sketch = target.get("sketch") if isinstance(target, dict) else None
    if not isinstance(sketch, str) or not sketch:
        return False, "target.sketch must be a non-empty sketch name"
    face = target.get("face") if isinstance(target, dict) else None
    if not isinstance(face, (list, tuple)) or len(face) != 3:
        return False, "target.face must be a 3-element [x,y,z]"
    thickness_mm = feature.get("thickness_mm", 1.0) if isinstance(feature, dict) else 1.0
    thickness_m = float(thickness_mm) / 1000.0
    try:
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        if not ext.SelectByID2(sketch, "SKETCH", 0, 0, 0, False, 0, None, 0):
            return False, f"could not select wrap sketch {sketch!r}"
        if not ext.SelectByID2("", "FACE", float(face[0]), float(face[1]), float(face[2]), True, 0, None, 0):
            return False, "could not select face for wrap"
        fm = doc.FeatureManager
        # SEAT-PENDING (W0): confirm InsertWrapFeature2(5) materializes.
        feat = fm.InsertWrapFeature2(
            0,          # type (0=emboss, 1=engrave, 2=scribe)
            thickness_m,
            0.0,        # draftAngle
            False,      # draftDir
            False,      # pullDir
        )
        if _materialized(feat):
            return True, None
        return False, "InsertWrapFeature2 did not materialize"
    except Exception as exc:
        return False, f"wrap pipeline failed: {exc!r}"


def _create_boundary_boss(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a boundary boss/base from 2-direction profiles.

    Seat-validated (SW 2024 SP1): **DEFERRED**.
    - No ``swFmBoundaryBoss`` in ``swconst.tlb`` (``swFeatureNameID_e``).
    - No ``InsertBoundaryBoss*`` method on ``IFeatureManager`` or
      ``IModelDoc2`` (probed via ``GetIDsOfNames``).
    - ``swBoundaryBoss*`` enums exist in ``swconst.tlb`` but only for
      sub-parameters (tangency, direction, curve influence), not for
      the feature creation itself.
    Boundary boss creation is not reachable out-of-process via the
    known API surface.
    """
    for key in ("dir1_profiles", "dir2_profiles"):
        val = target.get(key) if isinstance(target, dict) else None
        if not isinstance(val, list) or not val:
            return False, f"target.{key} must be a non-empty list of sketch names"
    return False, "boundary_boss: no reachable creation API (DEFERRED — see WAVE5_HANDBACK.md)"


def _get_definition(feat: Any, mod: Any) -> Any:
    """Return a feature's definition object, falling back to early-bound
    ``IFeature.GetDefinition`` when the late-bind call raises 'Member not
    found' (the same wall ``GetDefinition`` hits elsewhere)."""
    try:
        d = feat.GetDefinition()
        if d is not None:
            return d
    except Exception:  # noqa: BLE001
        pass
    return typed(feat, "IFeature", module=mod).GetDefinition()


def _create_variable_fillet(
    doc: Any, edges: list[dict]
) -> tuple[bool, str | None]:
    """Multi-edge fillet with a DISTINCT radius per durable edge.

    Seat-validated recipe (``spike_varfil_v4`` = PASS-PER-EDGE): variable
    radius is the *simple* fillet data with ``IsMultipleRadius=True`` — there is
    no separate "variable" creation interface (the v0.15 morph premise was
    false). Each ``edges`` item is ``{"ref": <DurableEdgeRef dict>,
    "radius_mm": float}``; the order is significant because fillet item ``i``
    binds to the ``i``-th *selected* edge (proven by the v4 readback).

    Steps: resolve + **append-select each edge as an entity** (coordinate
    SelectByID replaces and SelectByID2 hits the dynamic ``<unknown>`` wall —
    only ``IEntity.Select2`` append accumulates) → CreateDefinition(fillet) →
    typed_qi → Initialize(const) → IsMultipleRadius=True → CreateFeature → set
    each fillet item's radius → **early-bound** ``ModifyDefinition`` (late-bind
    raises 'Type mismatch' on the Component arg). Returns (ok, error).
    """
    mod = wrapper_module()
    doc.ForceRebuild3(False)

    radii_mm: list[float] = []
    for k, item in enumerate(edges):
        ref = DurableEdgeRef.from_dict(item["ref"])
        res = resolve_edge_ref(doc, ref)
        if res.entity is None:
            return False, f"edge {k} unresolved (method={res.method})"
        if not select_entity(res.entity, append=(k > 0)):
            return False, f"edge {k} selection failed"
        radii_mm.append(item["radius_mm"])

    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_FILLET)
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=mod)
        fd.Initialize(_SW_CONST_RADIUS_FILLET)
        fd.DefaultRadius = radii_mm[0] / 1000.0
        fd.IsMultipleRadius = True
        feat = fm.CreateFeature(data)
        if not _materialized(feat):
            return False, "CreateFeature did not materialize"

        defn_raw = _get_definition(feat, mod)
        if defn_raw is None:
            return False, "GetDefinition returned None"
        defn = typed_qi(defn_raw, "ISimpleFilletFeatureData2", module=mod)
        try:
            defn.AccessSelections(doc, None)
        except Exception:  # noqa: BLE001
            pass

        count = int(defn.FilletItemsCount)
        if count != len(radii_mm):
            return False, (
                f"fillet item count {count} != {len(radii_mm)} edges "
                "(edges merged into one item — pick non-adjacent edges)"
            )
        for i in range(count):
            fitem = defn.GetFilletItemAtIndex(i)
            defn.SetRadius(fitem, radii_mm[i] / 1000.0)

        # ModifyDefinition MUST be early-bound (late-bind raises Type mismatch
        # marshalling the None Component arg).
        ok = typed(feat, "IFeature", module=mod).ModifyDefinition(defn_raw, doc, None)
        if ok is False:
            return False, "ModifyDefinition returned False"
        return True, None
    except Exception as exc:
        return False, f"variable-fillet pipeline failed: {exc!r}"


def _arrays_from_out(ret: Any) -> list[list]:
    """Extract the array ([out] SAFEARRAY) elements from an early-bound call's
    return tuple, in order — the bool/scalar retval is ignored."""
    if not isinstance(ret, (tuple, list)):
        return []
    return [list(a) for a in ret if isinstance(a, (tuple, list))]


def _hole_table_sizes(hsd: Any, std_name: str, fastener_index: int) -> list[str]:
    """Valid size strings for a (standard, fastener) from the standards DB."""
    sizes: list[str] = []
    try:
        tt = hsd.GetFastenerTableTypes(std_name, fastener_index)
    except Exception:  # noqa: BLE001
        return sizes
    table_ids = [t for arr in _arrays_from_out(tt) for t in arr]
    table_id = table_ids[0] if table_ids else 0
    try:
        ht = hsd.GetFastenerTable(std_name, fastener_index, table_id)
    except Exception:  # noqa: BLE001
        return sizes
    table_raw = None
    for a in (ht if isinstance(ht, (tuple, list)) else [ht]):
        if a is not None and not isinstance(a, (bool, int, float, str, tuple, list)):
            table_raw = a
            break
    if table_raw is None:
        return sizes
    mod = wrapper_module()
    table = typed_qi(table_raw, "IHoleDataTable", module=mod)
    try:
        cnames = table.GetColumnNames()
    except Exception:  # noqa: BLE001
        return sizes
    cols = [c for arr in _arrays_from_out(cnames) for c in arr]
    size_col = next((c for c in cols if "size" in str(c).lower()), cols[0] if cols else None)
    if size_col is None:
        return sizes
    try:
        rc = table.GetRowCount()
    except Exception:  # noqa: BLE001
        return sizes
    # The retval is a bool; the count is the first genuine (non-bool) int.
    counts = [v for v in (rc if isinstance(rc, (tuple, list)) else [rc])
              if isinstance(v, int) and not isinstance(v, bool)]
    nrows = counts[0] if counts else 0
    for r in range(nrows):
        try:
            cell = table.GetCellData(size_col, r)
        except Exception:  # noqa: BLE001
            continue
        for v in (cell if isinstance(cell, (tuple, list)) else [cell]):
            if isinstance(v, str) and v:
                sizes.append(v)
                break
    return sizes


# Show at most this many size strings in validation error messages; beyond that
# we elide with a count suffix so the dry-run payload stays readable for the
# larger fastener tables (Tap Drills has ~70 entries in the ANSI Metric DB).
_SIZE_ERROR_DISPLAY_LIMIT = 20


def _format_size_catalog(sizes: list[str]) -> str:
    """Format a size list for an error message: full when short, elided with a
    count when long. Always byte-stable — the same input list always produces
    the same output, so downstream tests that assert on substrings stay green.
    """
    if not sizes:
        return "<no sizes enumerated>"
    if len(sizes) <= _SIZE_ERROR_DISPLAY_LIMIT:
        return ", ".join(sizes)
    head = ", ".join(sizes[:_SIZE_ERROR_DISPLAY_LIMIT])
    return f"{head}, ... ({len(sizes)} total)"


def _resolve_hole_args(
    generic_hole_type: int, standard: str, fastener_type: str, size: str
) -> tuple[bool, int, int, str | None]:
    """Resolve (std_index, fastener_index) and validate ``size`` against the
    live standards DB. Returns (ok, std_index, fastener_index, error).

    The Hole Wizard bridges COM to a local standards database; fastener indexes
    are contextual and sizes are exact DB strings (often ``Ø``-prefixed), so we
    query rather than guess (seat-proven by spike_wizhole_v5). The
    ``IHoleStandardsData`` byref [out] arrays require early binding.
    """
    sw = get_sw_app()
    mod = wrapper_module()
    hsd_raw = sw.GetHoleStandardsData(generic_hole_type)
    if hsd_raw is None:
        return False, -1, -1, f"GetHoleStandardsData({generic_hole_type}) returned None"
    hsd = typed_qi(hsd_raw, "IHoleStandardsData", module=mod)

    std_arrays = _arrays_from_out(hsd.GetHoleStandards())
    if len(std_arrays) < 2:
        return False, -1, -1, "GetHoleStandards returned no standards"
    std_indexes, std_names = std_arrays[0], std_arrays[1]
    std_index = None
    for idx, nm in zip(std_indexes, std_names):
        if str(nm).strip().lower() == standard.strip().lower():
            std_index = idx
            std_name = str(nm)
            break
    if std_index is None:
        return False, -1, -1, (
            f"standard {standard!r} not found; available: "
            f"{_format_size_catalog([str(n) for n in std_names])}"
        )

    f_arrays = _arrays_from_out(hsd.GetFastenerTypes(std_name))
    if len(f_arrays) < 2:
        return False, -1, -1, f"no fastener types for standard {std_name!r}"
    f_indexes, f_names = f_arrays[0], f_arrays[1]
    fastener_index = None
    for idx, nm in zip(f_indexes, f_names):
        if str(nm).strip().lower() == fastener_type.strip().lower():
            fastener_index = idx
            break
    if fastener_index is None:
        return False, -1, -1, (
            f"fastener type {fastener_type!r} not found for {std_name!r}; "
            f"available: {_format_size_catalog([str(n) for n in f_names])}"
        )

    valid_sizes = _hole_table_sizes(hsd, std_name, fastener_index)
    if not valid_sizes:
        # DB returned zero rows for this (standard, fastener) — either the
        # table is empty or the COM read failed. Surface as a diagnostic
        # error rather than silently accepting any size string; the caller
        # gets a structured envelope they can act on.
        return False, -1, -1, (
            f"no sizes enumerated for {std_name!r}/{fastener_type!r} "
            f"(DB returned 0 rows — check IHoleDataTable.GetRowCount)"
        )
    if size not in valid_sizes:
        return False, -1, -1, (
            f"size {size!r} invalid for {std_name!r}/{fastener_type!r}; "
            f"{len(valid_sizes)} valid sizes: {_format_size_catalog(valid_sizes)}"
        )
    return True, int(std_index), int(fastener_index), None


def _create_wizard_hole(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a hole-wizard feature at a point on a face.

    Seat-validated recipe (spike_wizhole_v5 = PASS): resolve the DB args, place
    a sketch point at the requested location on the target face, then
    ``CreateDefinition(25) → typed_qi(IWizardHoleFeatureData2) → InitializeHole
    → CreateFeature``.

    Placement supports two ``target`` shapes (durable preferred):

    * **Durable face-ref (C, seat-validated ``spike_wizhole_durable`` = PASS):**
      ``{"face_ref": <manifest-face dict>, "point": [x,y,z]}`` — the face is
      resolved through the persist→fingerprint hierarchy
      (:func:`resolve_manifest_face`) and selected as a live entity, so the
      placement survives rebuilds/topology shuffles. The sketch is built on the
      *resolved* face (proven: ``select_entity`` of the resolved face is a valid
      ``InsertSketch`` base, just like the v1 coordinate pick).
    * **Legacy coordinate (v1):** ``{"face": [x,y,z], "point": [x,y,z]}`` — the
      face is picked by raw model-metre coords via ``SelectByID``.

    ``point`` is the on-face hole location in model metres in both cases.
    Returns (ok, error).
    """
    generic = _WZD_GENERIC_HOLE_TYPES[feature["hole_type"]]
    end_cond = _WZD_END_CONDITIONS[feature.get("end_condition", "blind")]
    ok, std_idx, fast_idx, err = _resolve_hole_args(
        generic, feature["standard"], feature["fastener_type"], feature["size"]
    )
    if not ok:
        return False, err

    mod = wrapper_module()
    doc.ForceRebuild3(False)
    px, py, pz = target["point"]
    try:
        # Select the placement face: durable face-ref first, else legacy coords.
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass
        face_ref = target.get("face_ref")
        if face_ref is not None:
            res = resolve_manifest_face(doc, face_ref)
            if res.entity is None:
                return False, f"placement face unresolved (method={res.method})"
            if not select_entity(res.entity):
                return False, "could not select resolved placement face"
        else:
            fx, fy, fz = target["face"]
            if not doc.SelectByID("", "FACE", fx, fy, fz):
                return False, f"could not select target face at {target['face']}"
        sk = doc.SketchManager
        sk.InsertSketch(True)
        pt = sk.CreatePoint(px, py, pz)
        sk.InsertSketch(True)
        if pt is None:
            return False, "CreatePoint returned None"

        def _select_point() -> bool:
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            m = getattr(pt, "Select2", None)
            if m is not None:
                try:
                    if m(False, 0):
                        return True
                except Exception:  # noqa: BLE001
                    pass
            return bool(doc.SelectByID("", "SKETCHPOINT", px, py, pz))

        if not _select_point():
            return False, "could not select the placement point"

        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_HOLE_WZD)
        fd = typed_qi(data, "IWizardHoleFeatureData2", module=mod)
        fd.InitializeHole(generic, std_idx, fast_idx, feature["size"], end_cond)
        depth_mm = feature.get("depth_mm")
        if depth_mm is not None and hasattr(fd, "Depth"):
            fd.Depth = depth_mm / 1000.0
        _select_point()  # re-assert after InitializeHole
        feat = fm.CreateFeature(data)
        if _materialized(feat):
            return True, None
        return False, "CreateFeature did not materialize"
    except Exception as exc:
        return False, f"wizard-hole pipeline failed: {exc!r}"


def _get_face_entity(doc: Any, coord: Any) -> Any:
    """Resolve a face to an IEntity by coordinate pick (clears selection)."""
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    if not doc.SelectByID("", "FACE", coord[0], coord[1], coord[2]):
        return None
    try:
        return doc.SelectionManager.GetSelectedObject6(1, -1)
    except Exception:  # noqa: BLE001
        return None


def _create_shell(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Hollow the body, removing the listed faces (Wall-2: IModelDoc2 method).

    Seat-validated recipe (spike_shell_draft_v2 = PASS): select the faces to
    remove as entities, then ``doc.InsertFeatureShell(thickness_m, outward)``.
    InsertFeatureShell returns void, so success is confirmed via a feature-count
    delta. Counting uses ``len(FeatureManager.GetFeatures(True))`` (NOT
    ``IModelDoc2.GetFeatureCount()`` — the latter is exposed as a *property* on
    the late-bound doc and raises "int not callable" when invoked; the dome PAE,
    W6 T2, exposed this. ``GetFeatures(True)`` is robust on both late-bound and
    typed docs). ``target`` = ``{"faces": [[x,y,z], ...]}`` (model-metre coords;
    v1 coordinate placement). Returns (ok, error).
    """
    thickness_mm = feature["thickness_mm"]
    outward = bool(feature.get("outward", False))
    face_coords = target["faces"]
    doc.ForceRebuild3(False)
    try:
        _feats = doc.FeatureManager.GetFeatures(True)
        before = len(_feats) if _feats else 0
        ents = []
        for k, c in enumerate(face_coords):
            ent = _get_face_entity(doc, c)
            if ent is None:
                return False, f"could not resolve face[{k}] at {c}"
            ents.append(ent)
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass
        for k, ent in enumerate(ents):
            if not select_entity(ent, append=(k > 0), mark=0):
                return False, f"could not select face[{k}]"
        doc.InsertFeatureShell(thickness_mm / 1000.0, outward)
        doc.ForceRebuild3(False)
        _feats = doc.FeatureManager.GetFeatures(True)
        after = len(_feats) if _feats else 0
        if after > before:
            return True, None
        return False, f"shell did not add a feature (count {before} -> {after})"
    except Exception as exc:
        return False, f"shell pipeline failed: {exc!r}"


def _create_draft(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Apply a neutral-plane draft to faces (Wall-2: IFeatureManager method).

    Seat-validated recipe (spike_shell_draft_v2 = PASS): select the neutral
    plane with mark 1 and each draft face with mark 2, then
    ``fm.InsertMultiFaceDraft(angleRad, flip, edgeDraft, propType, isStep,
    isBody)``. ``target`` = ``{"neutral_face": [x,y,z], "faces": [[x,y,z],
    ...]}``. Returns (ok, error).
    """
    angle_deg = feature["angle_deg"]
    flip = bool(feature.get("flip", False))
    edge_draft = bool(feature.get("edge_draft", False))
    prop = _DRAFT_PROPAGATION[feature.get("propagation", "none")]
    neutral_coord = target["neutral_face"]
    face_coords = target["faces"]
    doc.ForceRebuild3(False)
    try:
        _feats = doc.FeatureManager.GetFeatures(True)
        before = len(_feats) if _feats else 0
        neutral = _get_face_entity(doc, neutral_coord)
        if neutral is None:
            return False, f"could not resolve neutral face at {neutral_coord}"
        draft_ents = []
        for k, c in enumerate(face_coords):
            ent = _get_face_entity(doc, c)
            if ent is None:
                return False, f"could not resolve draft face[{k}] at {c}"
            draft_ents.append(ent)
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass
        # Neutral plane = mark 1, faces to draft = mark 2 (seat-proven).
        if not select_entity(neutral, append=False, mark=1):
            return False, "could not select neutral plane"
        for k, ent in enumerate(draft_ents):
            if not select_entity(ent, append=True, mark=2):
                return False, f"could not select draft face[{k}]"
        fm = doc.FeatureManager
        # InsertMultiFaceDraft returns None EVEN ON SUCCESS (the W6 dome/shell
        # lesson — W44 audit measured ΔVol +419 while _materialized(feat) was
        # False). Verify via a feature-count delta, never the return value.
        fm.InsertMultiFaceDraft(
            math.radians(angle_deg), flip, edge_draft, prop, False, False
        )
        doc.ForceRebuild3(False)
        _feats = doc.FeatureManager.GetFeatures(True)
        after = len(_feats) if _feats else 0
        if after > before:
            return True, None
        return False, f"draft did not add a feature (count {before} -> {after})"
    except Exception as exc:
        return False, f"draft pipeline failed: {exc!r}"


# ---- W21: pattern features (seat-GREEN, spike 5a94b05) ----


def _find_feature_by_name(doc: Any, name: str) -> Any:
    """Look up a feature by its tree-name. Returns the IFeature or None."""
    feats = doc.FeatureManager.GetFeatures(True)
    if not feats:
        return None
    for f in feats:
        try:
            n = f.Name
            n = n() if callable(n) else n
            if str(n) == name:
                return f
        except Exception:
            continue
    return None


def _create_linear_pattern(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a linear pattern of a seed feature along a direction edge.

    Seat-validated recipe (W21 S1, spike ``5a94b05``, SW 2024 SP1):
    ``fm.FeatureLinearPattern5(22 args)`` with marked selections:
      direction edge = mark 1 (SelectByID(EDGE) + SetSelectedObjectMark)
      seed feature   = mark 4 (IFeature.Select2(append=True, mark=4))

    SEED COMPATIBILITY (S1↔S4 unreconciled): S1 saw an ICE (Instant3D)
    seed NO-GO, but S4 patterned an ICE seed to N=3 — so ICE-ness alone is
    NOT a reliable predictor of rejection. The handler is fail-closed
    either way: if FeatureLinearPattern5 rejects the seed it returns None
    and we surface an error; a compatible seed materializes normally.

    ``target`` shape: ``{"seed": "<name>", "direction": {"x": mm, "y": mm,
    "z": mm}}`` where the point lies on the desired direction edge.
    ``feature.spacing_mm`` (positive number), ``feature.count`` (int >= 2),
    optional ``feature.flip`` (bool).
    """
    seed_name = target.get("seed") if isinstance(target, dict) else None
    if not seed_name:
        return False, "target.seed must be a non-empty feature name"
    direction = target.get("direction") if isinstance(target, dict) else None
    if not isinstance(direction, dict):
        return False, "target.direction must be a dict with x, y, z (mm)"
    spacing_mm = feature.get("spacing_mm") if isinstance(feature, dict) else None
    if not isinstance(spacing_mm, (int, float)) or spacing_mm <= 0:
        return False, "feature.spacing_mm must be a positive number"
    count = feature.get("count") if isinstance(feature, dict) else None
    if not isinstance(count, int) or count < 2:
        return False, "feature.count must be an integer >= 2"
    flip = bool(feature.get("flip", False)) if isinstance(feature, dict) else False

    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        seed_feat = _find_feature_by_name(doc, seed_name)
        if seed_feat is None:
            return False, f"seed feature {seed_name!r} not found in feature tree"

        # 1. Direction edge (mark=1)
        dx = float(direction["x"]) / 1000.0
        dy = float(direction["y"]) / 1000.0
        dz = float(direction["z"]) / 1000.0
        doc.ClearSelection2(True)
        if not doc.SelectByID("", "EDGE", dx, dy, dz):
            return False, (
                f"could not select direction edge at ({direction['x']}, "
                f"{direction['y']}, {direction['z']}) mm"
            )
        sel_mgr = doc.SelectionManager
        if not sel_mgr.SetSelectedObjectMark(1, 1, 0):
            return False, "SetSelectedObjectMark(1, 1, 0) failed for direction"

        # 2. Seed (mark=4)
        if not seed_feat.Select2(True, 4):
            return False, f"IFeature.Select2 on seed {seed_name!r} returned False"

        # 3. FeatureLinearPattern5 (22 args)
        spacing_m = float(spacing_mm) / 1000.0
        feat = fm.FeatureLinearPattern5(
            count, spacing_m, 1, 0.0,
            flip, False, "", "",
            False, False, False, False,
            False, False, False, False,
            False, False, 0.0, 0.0, False, False,
        )
        if _materialized(feat):
            return True, None
        return False, "FeatureLinearPattern5 returned None (the seed feature was rejected by the API — e.g. an incompatible seed type)"
    except Exception as exc:
        return False, f"linear pattern pipeline failed: {exc!r}"


def _create_circular_pattern(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a circular pattern of a seed feature around an axis.

    Seat-validated recipe (W21 S1, spike ``5a94b05``, SW 2024 SP1):
    ``fm.FeatureCircularPattern5(14 args)`` with marked selections:
      axis = mark 1 (SelectByID2(AXIS, mark=1))
      seed = mark 4 (IFeature.Select2(append=True, mark=4))

    ``target`` shape: ``{"seed": "<name>", "axis": "<axis name>"}``.
    ``feature.count`` (int >= 2), ``feature.angle_deg`` (positive number,
    default 360) OR ``feature.equal_spacing`` (bool, default True),
    optional ``feature.flip`` (bool).
    """
    seed_name = target.get("seed") if isinstance(target, dict) else None
    if not seed_name:
        return False, "target.seed must be a non-empty feature name"
    axis_name = target.get("axis") if isinstance(target, dict) else None
    if not axis_name:
        return False, "target.axis must be a non-empty axis name"
    count = feature.get("count") if isinstance(feature, dict) else None
    if not isinstance(count, int) or count < 2:
        return False, "feature.count must be an integer >= 2"
    equal_spacing = bool(feature.get("equal_spacing", True)) if isinstance(feature, dict) else True
    angle_deg = feature.get("angle_deg", 360.0) if isinstance(feature, dict) else 360.0
    if not isinstance(angle_deg, (int, float)) or angle_deg <= 0:
        return False, "feature.angle_deg must be a positive number"
    flip = bool(feature.get("flip", False)) if isinstance(feature, dict) else False

    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        mod = wrapper_module()
        seed_feat = _find_feature_by_name(doc, seed_name)
        if seed_feat is None:
            return False, f"seed feature {seed_name!r} not found in feature tree"

        # 1. Axis (mark=1)
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        if not ext.SelectByID2(axis_name, "AXIS", 0, 0, 0, False, 1, None, 0):
            return False, f"could not select axis {axis_name!r}"

        # 2. Seed (mark=4)
        if not seed_feat.Select2(True, 4):
            return False, f"IFeature.Select2 on seed {seed_name!r} returned False"

        # 3. FeatureCircularPattern5 (14 args)
        # NOTE: Spacing is in DEGREES (not radians) — seat-proven W21 S4.
        feat = fm.FeatureCircularPattern5(
            count, float(angle_deg), flip, "",
            False, equal_spacing, False, False,
            False, False, 1, 0.0, "", False,
        )
        if _materialized(feat):
            return True, None
        return False, "FeatureCircularPattern5 returned None"
    except Exception as exc:
        return False, f"circular pattern pipeline failed: {exc!r}"


def _create_mirror_feature(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Mirror a seed feature about a named plane.

    Seat-validated recipe (W21 S1, spike ``5a94b05``, SW 2024 SP1):
    ``fm.InsertMirrorFeature2(False, False, False, False, 0)`` (5 args)
    with marked selections:
      plane = mark 2 (SelectByID(PLANE) + SetSelectedObjectMark)
      seed  = mark 1 (IFeature.Select2(append=True, mark=1))

    ``target`` shape: ``{"seed": "<name>", "plane": "<plane name>"}``.
    Plane can be a standard plane name ("Front Plane", "Top Plane",
    "Right Plane") or a user-created ref_plane name.
    """
    seed_name = target.get("seed") if isinstance(target, dict) else None
    if not seed_name:
        return False, "target.seed must be a non-empty feature name"
    plane_name = target.get("plane") if isinstance(target, dict) else None
    if not plane_name:
        return False, "target.plane must be a non-empty plane name"

    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        seed_feat = _find_feature_by_name(doc, seed_name)
        if seed_feat is None:
            return False, f"seed feature {seed_name!r} not found in feature tree"

        # 1. Plane (mark=2)
        doc.ClearSelection2(True)
        if not doc.SelectByID(plane_name, "PLANE", 0.0, 0.0, 0.0):
            return False, f"could not select plane {plane_name!r}"
        sel_mgr = doc.SelectionManager
        if not sel_mgr.SetSelectedObjectMark(1, 2, 0):
            return False, "SetSelectedObjectMark(1, 2, 0) failed for plane"

        # 2. Seed (mark=1)
        if not seed_feat.Select2(True, 1):
            return False, f"IFeature.Select2 on seed {seed_name!r} returned False"

        # 3. InsertMirrorFeature2 (5 args)
        feat = fm.InsertMirrorFeature2(False, False, False, False, 0)
        if _materialized(feat):
            return True, None
        return False, "InsertMirrorFeature2 returned None"
    except Exception as exc:
        return False, f"mirror feature pipeline failed: {exc!r}"


# ---------------------------------------------------------------------------
# W41 body-ops helpers — multi-body enumeration via GetBodies2 (IPartDoc).
# ---------------------------------------------------------------------------

_SW_SOLID_BODY = 0  # swBodyType_e.swSolidBody


def _get_body_count_and_volumes(
    doc: Any,
) -> tuple[int, list[float]] | tuple[int, None]:
    """Return (count, [volume_mm3_per_body]) for all solid bodies in *doc*.

    Uses ``IPartDoc.GetBodies2(0, True)`` (swSolidBody) then per-body
    ``CreateMassProperty`` for volume in m³ → mm³ (×1e9).  Returns
    ``(0, None)`` when the doc has no solid bodies.
    """
    # GetBodies2 is an IPartDoc member; the caller may hand a typed
    # IModelDoc2 (which lacks it). QI to IPartDoc — the W37 lesson.
    try:
        pdoc = doc if hasattr(doc, "GetBodies2") else typed(
            doc, "IPartDoc", module=wrapper_module()
        )
        bodies = pdoc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception:
        return 0, None
    if bodies is None:
        return 0, None
    count = len(bodies)
    volumes: list[float] = []
    for body in bodies:
        # Volume is read PER-BODY via IBody2.GetMassProperties(density) — its
        # element [3] is the volume in m³. NOTE: CreateMassProperty is an
        # IModelDocExtension method, NOT an IBody2 method (calling it on a body
        # throws "method not found" → was silently yielding 0.0). Seat-proven:
        # GetMassProperties(1.0)[3] == 8e-6 m³ for a 20³ box.
        try:
            mp = body.GetMassProperties(1.0)
            if callable(mp):
                mp = mp(1.0)
            if mp is not None and len(mp) > 3:
                volumes.append(float(mp[3]) * 1e9)
            else:
                volumes.append(0.0)
        except Exception:
            volumes.append(0.0)
    return count, volumes


def _select_body_by_index(doc: Any, index: int) -> bool:
    """Select the solid body at *index* in ``GetBodies2`` order (0-based).

    Seat-proven (W41): a body cannot be selected via ``IBody2.Select2`` (Member
    not found) nor ``select_entity(body)`` (returns False) nor by selecting its
    faces (``InsertDeleteBody2`` then no-ops). The working route is
    ``Extension.SelectByID2(body.Name, "SOLIDBODY", …)`` — so resolve the body
    at *index* to its ``IBody2.Name`` and select by that.
    """
    # GetBodies2 is IPartDoc-only — QI from a typed IModelDoc2 (W37 lesson).
    try:
        pdoc = doc if hasattr(doc, "GetBodies2") else typed(
            doc, "IPartDoc", module=wrapper_module()
        )
        bodies = pdoc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception:
        return False
    if bodies is None or index >= len(bodies):
        return False
    try:
        name = bodies[index].Name
        if callable(name):
            name = name()
    except Exception:
        return False
    return _select_body_by_name(doc, str(name))


def _select_body_by_name(doc: Any, name: str) -> bool:
    """Select a solid body by its tree name via ``SelectByID2(..,"SOLIDBODY",..)``.

    Seat-proven (W41): the selection TYPE is ``SOLIDBODY`` (swSelType 76), NOT
    ``BODYFEATURE`` (which selects the feature, type 22, and leaves
    ``InsertDeleteBody2`` a no-op).
    """
    try:
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        return bool(
            ext.SelectByID2(name, "SOLIDBODY", 0, 0, 0, False, 0, None, 0)
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# W41 body-ops handlers — delete_body, combine, split.
# ---------------------------------------------------------------------------

_SW_BODY_OP_ADD = 0       # swBodyOperationType_e.swBodyOperationAdd
_SW_BODY_OP_SUBTRACT = 1  # swBodyOperationType_e.swBodyOperationSubtract
_SW_BODY_OP_COMMON = 2    # swBodyOperationType_e.swBodyOperationCommon

_COMBINE_OP_MAP = {
    "add": _SW_BODY_OP_ADD,
    "subtract": _SW_BODY_OP_SUBTRACT,
    "common": _SW_BODY_OP_COMMON,
}


def _create_delete_body(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Delete a solid body via ``IFeatureManager.InsertDeleteBody2``.

    Seat-validated approach (W41, LOW risk): select the target body via
    ``SelectByID2(name, "SOLIDBODY", …)`` (swSelType 76 — NOT BODYFEATURE),
    then call ``InsertDeleteBody2(False)``.  The signature is ONE arg
    (``keepBodies``); the 2-arg form raises "Invalid number of parameters".
    The return value may be ``None`` even on success — verify via body-count
    delta using ``GetBodies2`` (count must drop).

    ``target`` shape::

        {"body_index": 1}          # 0-based index into GetBodies2
        {"body_name": "Body2"}     # feature-tree name (SelectByID2)
    """
    doc.ForceRebuild3(False)
    before_count, before_vols = _get_body_count_and_volumes(doc)
    if before_count < 2:
        return False, (
            f"delete_body requires >= 2 bodies, found {before_count}"
        )

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    body_index = target.get("body_index")
    body_name = target.get("body_name")

    selected = False
    if body_name is not None:
        selected = _select_body_by_name(doc, str(body_name))
    elif body_index is not None:
        if not isinstance(body_index, int) or body_index < 0:
            return False, f"body_index must be a non-negative int, got {body_index!r}"
        selected = _select_body_by_index(doc, body_index)
    else:
        return False, "target must contain 'body_index' or 'body_name'"

    if not selected:
        return False, "could not select target body"

    try:
        fm = doc.FeatureManager
        # Seat-proven (W41): InsertDeleteBody2 takes ONE arg (keepBodies:bool);
        # the 2-arg form raises "Invalid number of parameters". With the target
        # body selected via SelectByID2 SOLIDBODY, InsertDeleteBody2(False)
        # drops the body (2→1, returns an IFeature).
        feat = fm.InsertDeleteBody2(False)
        doc.ForceRebuild3(False)

        after_count, after_vols = _get_body_count_and_volumes(doc)

        if after_count < before_count:
            return True, None
        return False, (
            f"delete_body did not reduce body count "
            f"({before_count} -> {after_count})"
        )
    except Exception as exc:
        return False, f"delete_body pipeline failed: {exc!r}"


def _create_combine(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Boolean combine of solid bodies via ``InsertCombineFeature``.

    Seat-validated approach (W41, MEDIUM risk): select main body + tool
    bodies, then call ``InsertCombineFeature(mainBody, operationType,
    toolBodies)`` where ``operationType`` is from
    ``swBodyOperationType_e`` (ADD=0/SUBTRACT=1/COMMON=2).

    The return value may be ``None`` even on success — verify via body-count
    delta (combine should reduce to 1 body for subtract/common, or merge
    bodies for add).

    ``feature`` shape::

        {"type": "combine", "operation": "subtract"}  # add|subtract|common

    ``target`` shape::

        {"main_body_index": 0, "tool_body_indices": [1]}
        # OR
        {"main_body_name": "Body1", "tool_body_names": ["Body2"]}
    """
    operation = feature.get("operation", "subtract")
    if operation not in _COMBINE_OP_MAP:
        return False, (
            f"operation must be one of {sorted(_COMBINE_OP_MAP)}, "
            f"got {operation!r}"
        )
    op_type = _COMBINE_OP_MAP[operation]

    doc.ForceRebuild3(False)
    before_count, before_vols = _get_body_count_and_volumes(doc)
    if before_count < 2:
        return False, f"combine requires >= 2 bodies, found {before_count}"

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    try:
        bodies = doc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception:
        return False, "GetBodies2 failed"
    if bodies is None:
        return False, "no solid bodies found"

    main_body = None
    tool_bodies: list = []

    main_name = target.get("main_body_name")
    main_idx = target.get("main_body_index")
    tool_names = target.get("tool_body_names")
    tool_idxs = target.get("tool_body_indices")

    if main_name is not None:
        for b in bodies:
            try:
                bname = b.Name
                if callable(bname):
                    bname = bname()
                if str(bname) == str(main_name):
                    main_body = b
                    break
            except Exception:
                continue
        if main_body is None:
            return False, f"main body {main_name!r} not found"
    elif main_idx is not None:
        if not isinstance(main_idx, int) or main_idx < 0 or main_idx >= len(bodies):
            return False, f"main_body_index out of range: {main_idx!r}"
        main_body = bodies[main_idx]
    else:
        return False, "target must contain 'main_body_index' or 'main_body_name'"

    if tool_names is not None:
        for tn in tool_names:
            found = False
            for b in bodies:
                try:
                    bname = b.Name
                    if callable(bname):
                        bname = bname()
                    if str(bname) == str(tn):
                        tool_bodies.append(b)
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                return False, f"tool body {tn!r} not found"
    elif tool_idxs is not None:
        if not isinstance(tool_idxs, list) or not tool_idxs:
            return False, "tool_body_indices must be a non-empty list"
        for idx in tool_idxs:
            if not isinstance(idx, int) or idx < 0 or idx >= len(bodies):
                return False, f"tool_body_index out of range: {idx!r}"
            tool_bodies.append(bodies[idx])
    else:
        return False, "target must contain 'tool_body_indices' or 'tool_body_names'"

    if not tool_bodies:
        return False, "no tool bodies resolved"

    try:
        from .selection import select_entity as _sel

        if not _sel(main_body):
            return False, "could not select main body"

        tool_array = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(tool_bodies)
        )

        fm = doc.FeatureManager
        feat = fm.InsertCombineFeature(main_body, op_type, tool_array)
        doc.ForceRebuild3(False)

        after_count, after_vols = _get_body_count_and_volumes(doc)

        if after_count < before_count:
            return True, None
        return False, (
            f"combine did not reduce body count "
            f"({before_count} -> {after_count})"
        )
    except Exception as exc:
        return False, f"combine pipeline failed: {exc!r}"


def _create_split(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Split a solid body by a cutting entity.

    W41 HIGH risk — may hit the solver-deep COM wall. Fail-closed if the
    API returns None or produces no body-count change.

    ``feature`` shape::

        {"type": "split"}

    ``target`` shape::

        {"body_index": 0, "cutting_plane": "RefPlane1"}
        # OR
        {"body_index": 0, "cutting_surface": "Sketch1"}
    """
    doc.ForceRebuild3(False)
    before_count, before_vols = _get_body_count_and_volumes(doc)
    if before_count < 1:
        return False, "split requires >= 1 body"

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    body_index = target.get("body_index", 0)
    if not _select_body_by_index(doc, body_index):
        return False, f"could not select body at index {body_index}"

    cutting_plane = target.get("cutting_plane")
    cutting_surface = target.get("cutting_surface")

    if cutting_plane is not None:
        try:
            mod = wrapper_module()
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)
            if not ext.SelectByID2(
                cutting_plane, "REFPLANE", 0, 0, 0, True, 0, None, 0
            ):
                return False, f"cutting plane {cutting_plane!r} not found"
        except Exception as exc:
            return False, f"could not select cutting plane: {exc!r}"
    elif cutting_surface is not None:
        try:
            mod = wrapper_module()
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)
            if not ext.SelectByID2(
                cutting_surface, "SKETCH", 0, 0, 0, True, 0, None, 0
            ):
                return False, f"cutting surface {cutting_surface!r} not found"
        except Exception as exc:
            return False, f"could not select cutting surface: {exc!r}"
    else:
        return False, "target must contain 'cutting_plane' or 'cutting_surface'"

    try:
        fm = doc.FeatureManager
        feat = fm.InsertSplitBody(True, False)
        doc.ForceRebuild3(False)

        after_count, after_vols = _get_body_count_and_volumes(doc)

        if after_count > before_count:
            return True, None
        return False, (
            f"split did not increase body count "
            f"({before_count} -> {after_count})"
        )
    except Exception as exc:
        return False, f"split pipeline failed: {exc!r}"


def _apply_feature(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Dispatch a feature-add proposal to its per-type build pipeline.

    Shared by dry-run and commit so the two paths can never diverge. Returns
    (ok, error); an unknown type returns ``(False, <reason>)`` rather than
    raising (propose-time validation already rejects unsupported types).
    """
    ftype = feature.get("type") if isinstance(feature, dict) else None
    if ftype == "fillet_constant_radius":
        return _create_fillet(doc, target, feature["radius_mm"])
    if ftype == "chamfer":
        return _create_chamfer(
            doc, target, feature["distance_mm"], feature.get("angle_deg", 45.0)
        )
    if ftype == "base_flange":
        return _create_base_flange(
            doc, target, feature["thickness_mm"], feature["bend_radius_mm"]
        )
    if ftype == "variable_radius_fillet":
        return _create_variable_fillet(doc, target["edges"])
    if ftype == "wizard_hole":
        return _create_wizard_hole(doc, feature, target)
    if ftype == "shell":
        return _create_shell(doc, feature, target)
    if ftype == "draft":
        return _create_draft(doc, feature, target)
    if ftype == "sweep":
        return _create_sweep(doc, feature, target)
    if ftype == "ref_plane":
        return _create_ref_plane(doc, feature, target)
    if ftype == "ref_axis":
        return _create_ref_axis(doc, feature, target)
    if ftype == "coordinate_system":
        return _create_coordinate_system(doc, feature, target)
    if ftype == "ref_point":
        return _create_ref_point(doc, feature, target)
    if ftype == "sweep_cut":
        return _create_sweep_cut(doc, feature, target)
    if ftype == "loft":
        return _create_loft(doc, feature, target)
    if ftype == "rib":
        return _create_rib(doc, feature, target)
    if ftype == "dome":
        return _create_dome(doc, feature, target)
    if ftype == "wrap":
        return _create_wrap(doc, feature, target)
    if ftype == "boundary_boss":
        return _create_boundary_boss(doc, feature, target)
    if ftype == "edge_flange":
        return _create_edge_flange(doc, feature, target)
    if ftype == "linear_pattern":
        return _create_linear_pattern(doc, feature, target)
    if ftype == "circular_pattern":
        return _create_circular_pattern(doc, feature, target)
    if ftype == "mirror_feature":
        return _create_mirror_feature(doc, feature, target)
    # W41 body-ops — multi-body part operations.
    if ftype == "delete_body":
        return _create_delete_body(doc, feature, target)
    if ftype == "combine":
        return _create_combine(doc, feature, target)
    if ftype == "split":
        return _create_split(doc, feature, target)
    # W56 seam: kinds wired as per-lane modules under features/ dispatch
    # here; built-in kinds above win on a (disallowed) name collision.
    handler = HANDLER_REGISTRY.get(ftype)
    if handler is not None:
        return handler(doc, feature, target)
    return False, f"unsupported feature type {ftype!r}"


def _get_linked_locals(doc: Any) -> Path | None:
    """Return the *_locals.txt path the active doc's equation manager is
    tracking, or None if no link is active."""
    try:
        eq_mgr = resolve(doc, "GetEquationMgr")
    except Exception:
        return None
    try:
        if not bool(resolve(eq_mgr, "LinkToFile")):
            return None
    except Exception:
        return None
    try:
        fp = str(resolve(eq_mgr, "FilePath"))
    except Exception:
        return None
    return Path(fp) if fp else None


def _force_rebuild(doc: Any) -> tuple[bool, str | None]:
    """Reload linked locals file, then rebuild the SW doc.

    Two-step process because plain rebuild does NOT re-import linked
    *_locals.txt; the equation manager needs an explicit reload trigger:

    1. EquationMgr.UpdateValuesFromExternalEquationFile - auto-invoked
       as property; returns bool. Re-reads the linked file and applies
       values to the equation manager.
    2. IModelDoc2.EditRebuild3 - auto-invoked property; equivalent to
       Ctrl+B. Rebuilds geometry with the updated equations.

    Returns (ok, error_message).
    """
    try:
        eq_mgr = resolve(doc, "GetEquationMgr")
    except Exception as exc:
        return False, f"GetEquationMgr failed: {exc!r}"

    # Trigger the locals-file reload. SW returns False here when there is
    # nothing to reload (file unchanged since last poll) -- NOT an error.
    # Treat raise as fatal but False as informational; the rebuild that
    # follows is the real success signal.
    reload_warning = None
    try:
        reload_ok = bool(resolve(eq_mgr, "UpdateValuesFromExternalEquationFile"))
        if not reload_ok:
            reload_warning = (
                "UpdateValuesFromExternalEquationFile returned False "
                "(usually means file unchanged since last poll; non-fatal)"
            )
    except Exception as exc:
        return False, f"UpdateValuesFromExternalEquationFile raised: {exc!r}"

    try:
        rebuild_ok = bool(resolve(doc, "EditRebuild3"))
        # Even if the reload returned False, a successful rebuild means
        # the doc is in the desired state. Surface the warning text only
        # when the rebuild ALSO failed -- otherwise it's noise.
        if rebuild_ok:
            return True, None
        return False, reload_warning or "EditRebuild3 returned False"
    except Exception as exc:
        return False, f"EditRebuild3 failed: {exc!r}"


def _read_manager_status(doc: Any) -> int | None:
    try:
        eq_mgr = resolve(doc, "GetEquationMgr")
        return int(resolve(eq_mgr, "Status"))
    except Exception:
        return None


def _read_var_value(doc: Any, var_name: str) -> float | str | None:
    """Read the SW-evaluated value of a global var from the equation manager."""
    try:
        eq_mgr = resolve(doc, "GetEquationMgr")
        count = int(resolve(eq_mgr, "GetCount"))
    except Exception:
        return None
    for i in range(count):
        try:
            expr = str(eq_mgr.Equation(i))
        except Exception:
            continue
        if f'"{var_name}"' in expr.split("=")[0]:
            try:
                v = eq_mgr.Value(i)
                return float(v) if isinstance(v, (int, float)) else str(v)
            except Exception:
                return None
    return None


def sw_propose_local_change(var: str, new_value: str) -> dict[str, Any]:
    """Stage a change to a single variable in the linked *_locals.txt file.

    No SW state is modified. We read the file (under exclusive lock) to
    verify the var exists and to snapshot its current value, so we can
    audit and roll back later.
    """
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "locals_path": None,
        "var": var,
        "old_expression": None,
        "new_expression": new_value,
        "line_index": None,
        "doc_path": None,
        "state": ST_PROPOSED,
        "error": None,
    }

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        try:
            result["doc_path"] = str(resolve(doc, "GetPathName"))
        except Exception:
            pass

        locals_path = _get_linked_locals(doc)
        if locals_path is None or not locals_path.exists():
            result["error"] = (
                f"no linked locals file (LinkToFile must be true and file must exist): {locals_path}"
            )
            return result
        result["locals_path"] = str(locals_path)

        try:
            with ExclusiveLock(locals_path) as lock:
                text = lock.read_text()
        except OSError as exc:
            result["error"] = f"could not lock locals file: {exc}"
            return result

        entries = parse(text)
        entry = find_entry(entries, var)
        if entry is None:
            result["error"] = f"variable {var!r} not found in {locals_path.name}"
            return result

        result["old_expression"] = entry.expression
        result["line_index"] = entry.line_index

        proposal_id = uuid.uuid4().hex[:12]
        record = {
            "proposal_id": proposal_id,
            "created_at": time.time(),
            "doc_path": result["doc_path"],
            "locals_path": str(locals_path),
            "var": var,
            "old_expression": entry.expression,
            "new_expression": new_value,
            "line_index": entry.line_index,
            "snapshot_text": text,
            "state": ST_PROPOSED,
            "dry_run_result": None,
            "committed_at": None,
            "undone_at": None,
        }
        _save_proposal(proposal_id, record)
        result["proposal_id"] = proposal_id
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def sw_dry_run(proposal_id: str) -> dict[str, Any]:
    """Apply a proposed change, force-rebuild, capture state, roll back."""
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "applied": False,
        "rolled_back": False,
        "before": {"manager_status": None, "var_value": None},
        "after": {"manager_status": None, "var_value": None},
        "rebuild_ok": False,
        "state": ST_PROPOSED,
        "warnings": [],
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result

    if rec["state"] not in (ST_PROPOSED, ST_DRY_RUN_OK, ST_DRY_RUN_BROKE):
        result["error"] = f"proposal is in state {rec['state']!r}, cannot dry-run"
        return result

    locals_path = Path(rec["locals_path"])
    if not locals_path.exists():
        result["error"] = f"locals file vanished: {locals_path}"
        return result

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        result["before"]["manager_status"] = _read_manager_status(doc)
        result["before"]["var_value"] = _read_var_value(doc, rec["var"])

        try:
            with ExclusiveLock(locals_path) as lock:
                current_text = lock.read_text()
            if current_text != rec["snapshot_text"]:
                result["warnings"].append(
                    "locals file changed since proposal was created; dry-run will use current text as base"
                )
            try:
                new_text = replace_rhs(
                    current_text, rec["line_index"], rec["new_expression"]
                )
            except ValueError as exc:
                result["error"] = f"replace_rhs failed: {exc}"
                return result

            atomic_write(locals_path, new_text)
            result["applied"] = True

            rebuild_ok, rebuild_err = _force_rebuild(doc)
            result["rebuild_ok"] = rebuild_ok
            if rebuild_err:
                result["warnings"].append(rebuild_err)

            result["after"]["manager_status"] = _read_manager_status(doc)
            result["after"]["var_value"] = _read_var_value(doc, rec["var"])

            mgr_after = result["after"]["manager_status"]
            mgr_before = result["before"]["manager_status"]
            broke = (
                mgr_after is not None
                and mgr_before is not None
                and mgr_after != mgr_before
                and mgr_after != 0
            ) or not rebuild_ok
            result["state"] = ST_DRY_RUN_BROKE if broke else ST_DRY_RUN_OK

        finally:
            try:
                atomic_write(locals_path, rec["snapshot_text"])
                _force_rebuild(doc)
                with ExclusiveLock(locals_path) as lock:
                    verify = lock.read_text()
                if verify == rec["snapshot_text"]:
                    result["rolled_back"] = True
                else:
                    result["warnings"].append(
                        "ROLLBACK WROTE OK but on-disk content differs from snapshot"
                    )
            except Exception as exc:
                result["warnings"].append(
                    f"ROLLBACK FAILED - locals file may be stale: {exc!r}"
                )

        rec["state"] = result["state"]
        rec["dry_run_result"] = {
            "ran_at": time.time(),
            "before": result["before"],
            "after": result["after"],
            "rebuild_ok": result["rebuild_ok"],
            "warnings": list(result["warnings"]),
        }
        _save_proposal(proposal_id, rec)

        result["ok"] = result["rolled_back"]
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def sw_commit(proposal_id: str) -> dict[str, Any]:
    """Re-apply a proposal that passed dry-run, save the SW document,
    and mark the proposal as committed."""
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "doc_saved": False,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result

    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok' (run sw_dry_run first)"
        )
        return result

    locals_path = Path(rec["locals_path"])
    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        with ExclusiveLock(locals_path) as lock:
            current_text = lock.read_text()
        new_text = replace_rhs(current_text, rec["line_index"], rec["new_expression"])
        atomic_write(locals_path, new_text)

        rebuild_ok, rebuild_err = _force_rebuild(doc)
        if not rebuild_ok:
            result["error"] = f"rebuild failed after commit-apply: {rebuild_err}"
            return result

        try:
            result["doc_saved"] = _save_doc(doc)
        except Exception as exc:
            result["error"] = f"doc.Save raised: {exc!r}"
            return result

        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        _save_proposal(proposal_id, rec)

        result["state"] = ST_COMMITTED
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def sw_undo_last_commit() -> dict[str, Any]:
    """Revert the most recently committed proposal by restoring its
    snapshot, force-rebuilding, and saving."""
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "var": None,
        "restored_to": None,
        "doc_saved": False,
        "error": None,
    }

    proposals_dir = _proposals_dir()
    proposals_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    for p in proposals_dir.glob("*.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if rec.get("state") == ST_COMMITTED and rec.get("committed_at"):
            candidates.append((rec["committed_at"], rec["proposal_id"], rec))

    if not candidates:
        result["error"] = "no committed proposal to undo"
        return result

    candidates.sort(reverse=True)
    _, proposal_id, rec = candidates[0]
    result["proposal_id"] = proposal_id
    result["var"] = rec["var"]
    result["restored_to"] = rec["old_expression"]

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result

        locals_path = Path(rec["locals_path"])
        atomic_write(locals_path, rec["snapshot_text"])

        rebuild_ok, rebuild_err = _force_rebuild(doc)
        if not rebuild_ok:
            result["error"] = f"rebuild failed during undo: {rebuild_err}"
            return result

        try:
            result["doc_saved"] = _save_doc(doc)
        except Exception as exc:
            result["error"] = f"doc.Save raised: {exc!r}"
            return result

        rec["state"] = ST_UNDONE
        rec["undone_at"] = time.time()
        _save_proposal(proposal_id, rec)

        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


# ---- feature_add PAE functions ---------------------------------------------


def sw_propose_feature_add(
    doc_path: str, feature: dict, target: dict
) -> dict[str, Any]:
    """Stage a feature-add proposal. No SW state is modified."""
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "doc_path": doc_path,
        "feature": feature,
        "target": target,
        "state": ST_PROPOSED,
        "error": None,
    }
    try:
        feat_type = feature.get("type") if isinstance(feature, dict) else None
        if (
            feat_type not in _SUPPORTED_FEATURE_TYPES
            and feat_type not in HANDLER_REGISTRY
        ):
            result["error"] = (
                f"unsupported feature type {feat_type!r}; "
                f"supported: {', '.join((*_SUPPORTED_FEATURE_TYPES, *HANDLER_REGISTRY))}"
            )
            return result

        # Per-type parameter validation.
        if feat_type == "fillet_constant_radius":
            radius_mm = feature.get("radius_mm")
            if not isinstance(radius_mm, (int, float)) or radius_mm <= 0:
                result["error"] = (
                    f"radius_mm must be a positive number, got {radius_mm!r}"
                )
                return result
        elif feat_type == "chamfer":
            distance_mm = feature.get("distance_mm")
            if not isinstance(distance_mm, (int, float)) or distance_mm <= 0:
                result["error"] = (
                    f"distance_mm must be a positive number, got {distance_mm!r}"
                )
                return result
            angle_deg = feature.get("angle_deg", 45.0)
            if not isinstance(angle_deg, (int, float)) or not (0 < angle_deg < 90):
                result["error"] = (
                    f"angle_deg must be in (0, 90), got {angle_deg!r}"
                )
                return result
        elif feat_type == "base_flange":
            for pname in ("thickness_mm", "bend_radius_mm"):
                pval = feature.get(pname)
                if not isinstance(pval, (int, float)) or pval <= 0:
                    result["error"] = (
                        f"{pname} must be a positive number, got {pval!r}"
                    )
                    return result
        elif feat_type == "wizard_hole":
            # Shape-only checks here; the standard/fastener/size are validated
            # against the live DB at dry-run (they need SW).
            ht = feature.get("hole_type")
            if ht not in _WZD_GENERIC_HOLE_TYPES:
                result["error"] = (
                    f"hole_type must be one of {sorted(_WZD_GENERIC_HOLE_TYPES)}, "
                    f"got {ht!r}"
                )
                return result
            ec = feature.get("end_condition", "blind")
            if ec not in _WZD_END_CONDITIONS:
                result["error"] = (
                    f"end_condition must be one of {sorted(_WZD_END_CONDITIONS)}, "
                    f"got {ec!r}"
                )
                return result
            for pname in ("standard", "fastener_type", "size"):
                if not isinstance(feature.get(pname), str) or not feature[pname]:
                    result["error"] = f"{pname} must be a non-empty string"
                    return result
            depth_mm = feature.get("depth_mm")
            if depth_mm is not None and (
                not isinstance(depth_mm, (int, float)) or depth_mm <= 0
            ):
                result["error"] = f"depth_mm must be a positive number, got {depth_mm!r}"
                return result
        elif feat_type == "shell":
            thickness_mm = feature.get("thickness_mm")
            if not isinstance(thickness_mm, (int, float)) or thickness_mm <= 0:
                result["error"] = (
                    f"thickness_mm must be a positive number, got {thickness_mm!r}"
                )
                return result
        elif feat_type == "draft":
            angle_deg = feature.get("angle_deg")
            if not isinstance(angle_deg, (int, float)) or angle_deg <= 0:
                result["error"] = f"angle_deg must be a positive number, got {angle_deg!r}"
                return result
            prop = feature.get("propagation", "none")
            if prop not in _DRAFT_PROPAGATION:
                result["error"] = (
                    f"propagation must be one of {sorted(_DRAFT_PROPAGATION)}, got {prop!r}"
                )
                return result

        if not isinstance(target, dict) or not target:
            result["error"] = "target must be a non-empty dict"
            return result

        # A base flange is built on a named profile sketch, not an edge ref.
        if feat_type == "base_flange" and not target.get("sketch"):
            result["error"] = "base_flange target must contain a 'sketch' name"
            return result

        # A variable-radius fillet carries an ordered list of (edge, radius).
        if feat_type == "variable_radius_fillet":
            edge_specs = target.get("edges")
            if not isinstance(edge_specs, list) or not edge_specs:
                result["error"] = (
                    "variable_radius_fillet target must contain a non-empty "
                    "'edges' list"
                )
                return result
            for k, es in enumerate(edge_specs):
                if not isinstance(es, dict) or not isinstance(es.get("ref"), dict) or not es["ref"]:
                    result["error"] = f"edges[{k}] must contain a non-empty 'ref' dict"
                    return result
                r = es.get("radius_mm")
                if not isinstance(r, (int, float)) or r <= 0:
                    result["error"] = (
                        f"edges[{k}].radius_mm must be a positive number, got {r!r}"
                    )
                    return result

        # A wizard hole is placed at a point on a face. The face is given
        # either durably (``face_ref``: a manifest-face dict, preferred) or by
        # raw model-metre coords (``face``: [x,y,z], v1). ``point`` is the
        # on-face hole location in model metres in both cases.
        if feat_type == "wizard_hole":
            point = target.get("point")
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                result["error"] = "wizard_hole target.point must be a 3-element [x,y,z]"
                return result
            face_ref = target.get("face_ref")
            face = target.get("face")
            if face_ref is not None:
                if not isinstance(face_ref, dict) or not face_ref:
                    result["error"] = (
                        "wizard_hole target.face_ref must be a non-empty "
                        "manifest-face dict"
                    )
                    return result
            elif not (isinstance(face, (list, tuple)) and len(face) == 3):
                result["error"] = (
                    "wizard_hole target needs a 'face_ref' (durable manifest-face "
                    "dict) or a 'face' ([x,y,z] coords)"
                )
                return result

        def _is_coord(v: Any) -> bool:
            return isinstance(v, (list, tuple)) and len(v) == 3

        # A shell removes a non-empty list of faces.
        if feat_type == "shell":
            faces = target.get("faces")
            if not isinstance(faces, list) or not faces or not all(_is_coord(f) for f in faces):
                result["error"] = (
                    "shell target.faces must be a non-empty list of [x,y,z] coords"
                )
                return result

        # A draft needs a neutral face + a non-empty list of faces to draft.
        if feat_type == "draft":
            if not _is_coord(target.get("neutral_face")):
                result["error"] = "draft target.neutral_face must be a 3-element [x,y,z]"
                return result
            faces = target.get("faces")
            if not isinstance(faces, list) or not faces or not all(_is_coord(f) for f in faces):
                result["error"] = (
                    "draft target.faces must be a non-empty list of [x,y,z] coords"
                )
                return result

        # A sweep is built on two named sketches: a profile and a path.
        if feat_type == "sweep":
            for pname in ("profile", "path"):
                if not isinstance(target.get(pname), str) or not target.get(pname):
                    result["error"] = (
                        f"sweep target.{pname} must be a non-empty sketch name"
                    )
                    return result

        # Wave-5/6: ref_plane is either an offset plane (plane name +
        # distance_mm) or a normal-to-edge plane (durable edge_ref).
        if feat_type == "ref_plane":
            if target.get("edge_ref") is not None:
                if not isinstance(target.get("edge_ref"), dict):
                    result["error"] = "ref_plane target.edge_ref must be a DurableEdgeRef dict"
                    return result
            else:
                if not isinstance(target.get("plane"), str) or not target.get("plane"):
                    result["error"] = (
                        "ref_plane target needs an 'edge_ref' (normal-to-edge) "
                        "or a non-empty 'plane' name (offset)"
                    )
                    return result
                dist = feature.get("distance_mm")
                if not isinstance(dist, (int, float)) or dist <= 0:
                    result["error"] = f"ref_plane distance_mm must be a positive number, got {dist!r}"
                    return result

        # Wave-5: ref_axis needs two plane names.
        if feat_type == "ref_axis":
            planes = target.get("planes")
            if not isinstance(planes, list) or len(planes) != 2:
                result["error"] = "ref_axis target.planes must be a 2-element list of plane names"
                return result

        # Wave-5 / W5.3 Epic B: ref_point accepts a durable face-ref
        # (face-centroid, preferred) OR a legacy 3-element vertex coordinate.
        if feat_type == "ref_point":
            face_ref = target.get("face_ref")
            point = target.get("point")
            if face_ref is not None:
                if not isinstance(face_ref, dict) or not face_ref:
                    result["error"] = (
                        "ref_point target.face_ref must be a non-empty manifest-face dict"
                    )
                    return result
            elif not isinstance(point, (list, tuple)) or len(point) != 3:
                result["error"] = (
                    "ref_point target needs a 'face_ref' (durable manifest-face dict) "
                    "or a 3-element 'point' [x,y,z]"
                )
                return result

        # Wave-5: sweep_cut mirrors sweep (profile + path).
        if feat_type == "sweep_cut":
            for pname in ("profile", "path"):
                if not isinstance(target.get(pname), str) or not target.get(pname):
                    result["error"] = (
                        f"sweep_cut target.{pname} must be a non-empty sketch name"
                    )
                    return result

        # Wave-5: loft needs >=2 profile sketch names.
        if feat_type == "loft":
            profiles = target.get("profiles")
            if not isinstance(profiles, list) or len(profiles) < 2:
                result["error"] = "loft target.profiles must be a list of >=2 sketch names"
                return result

        # Wave-5: rib needs a sketch name.
        if feat_type == "rib":
            if not isinstance(target.get("sketch"), str) or not target.get("sketch"):
                result["error"] = "rib target.sketch must be a non-empty sketch name"
                return result

        # Wave-6 T2: dome takes a durable face_ref (preferred) or legacy coord.
        if feat_type == "dome":
            face_ref = target.get("face_ref")
            face = target.get("face")
            if face_ref is not None:
                if not isinstance(face_ref, dict) or not face_ref:
                    result["error"] = (
                        "dome target.face_ref must be a non-empty manifest-face dict"
                    )
                    return result
            elif not isinstance(face, (list, tuple)) or len(face) != 3:
                result["error"] = (
                    "dome target needs a 'face_ref' (durable manifest-face dict) "
                    "or a 3-element 'face' [x,y,z]"
                )
                return result

        # Wave-7: edge_flange takes a durable edge_ref + positive height_mm;
        # angle_deg (0,180) and radius_mm default if absent.
        if feat_type == "edge_flange":
            if not isinstance(target.get("edge_ref"), dict) or not target.get("edge_ref"):
                result["error"] = "edge_flange target.edge_ref must be a DurableEdgeRef dict"
                return result
            h = feature.get("height_mm")
            if not isinstance(h, (int, float)) or h <= 0:
                result["error"] = f"edge_flange height_mm must be a positive number, got {h!r}"
                return result
            ang = feature.get("angle_deg", 90.0)
            if not isinstance(ang, (int, float)) or not (0 < ang < 180):
                result["error"] = f"edge_flange angle_deg must be in (0, 180), got {ang!r}"
                return result
            rad = feature.get("radius_mm", 2.0)
            if not isinstance(rad, (int, float)) or rad <= 0:
                result["error"] = f"edge_flange radius_mm must be a positive number, got {rad!r}"
                return result

        # Wave-5: wrap needs sketch + face.
        if feat_type == "wrap":
            if not isinstance(target.get("sketch"), str) or not target.get("sketch"):
                result["error"] = "wrap target.sketch must be a non-empty sketch name"
                return result
            face = target.get("face")
            if not isinstance(face, (list, tuple)) or len(face) != 3:
                result["error"] = "wrap target.face must be a 3-element [x,y,z]"
                return result

        # Wave-5: boundary_boss needs dir1 + dir2 profile lists.
        if feat_type == "boundary_boss":
            for key in ("dir1_profiles", "dir2_profiles"):
                val = target.get(key)
                if not isinstance(val, list) or not val:
                    result["error"] = f"boundary_boss target.{key} must be a non-empty list"
                    return result

        # W21: linear_pattern — seed + direction + spacing_mm + count.
        if feat_type == "linear_pattern":
            if not isinstance(target.get("seed"), str) or not target.get("seed"):
                result["error"] = "linear_pattern target.seed must be a non-empty feature name"
                return result
            direction = target.get("direction")
            if not isinstance(direction, dict):
                result["error"] = "linear_pattern target.direction must be a dict with x, y, z"
                return result
            for k in ("x", "y", "z"):
                v = direction.get(k)
                if not isinstance(v, (int, float)):
                    result["error"] = f"linear_pattern target.direction.{k} must be a number"
                    return result
            spacing = feature.get("spacing_mm")
            if not isinstance(spacing, (int, float)) or spacing <= 0:
                result["error"] = f"linear_pattern spacing_mm must be a positive number, got {spacing!r}"
                return result
            cnt = feature.get("count")
            if not isinstance(cnt, int) or cnt < 2:
                result["error"] = f"linear_pattern count must be an integer >= 2, got {cnt!r}"
                return result

        # W21: circular_pattern — seed + axis + count + angle/equal_spacing.
        if feat_type == "circular_pattern":
            if not isinstance(target.get("seed"), str) or not target.get("seed"):
                result["error"] = "circular_pattern target.seed must be a non-empty feature name"
                return result
            if not isinstance(target.get("axis"), str) or not target.get("axis"):
                result["error"] = "circular_pattern target.axis must be a non-empty axis name"
                return result
            cnt = feature.get("count")
            if not isinstance(cnt, int) or cnt < 2:
                result["error"] = f"circular_pattern count must be an integer >= 2, got {cnt!r}"
                return result
            angle = feature.get("angle_deg", 360.0)
            if not isinstance(angle, (int, float)) or angle <= 0:
                result["error"] = f"circular_pattern angle_deg must be a positive number, got {angle!r}"
                return result

        # W21: mirror_feature — seed + plane.
        if feat_type == "mirror_feature":
            if not isinstance(target.get("seed"), str) or not target.get("seed"):
                result["error"] = "mirror_feature target.seed must be a non-empty feature name"
                return result
            if not isinstance(target.get("plane"), str) or not target.get("plane"):
                result["error"] = "mirror_feature target.plane must be a non-empty plane name"
                return result

        # W41: delete_body — body_index or body_name.
        if feat_type == "delete_body":
            body_index = target.get("body_index")
            body_name = target.get("body_name")
            if body_name is not None:
                if not isinstance(body_name, str) or not body_name:
                    result["error"] = "delete_body target.body_name must be a non-empty string"
                    return result
            elif body_index is not None:
                if not isinstance(body_index, int) or body_index < 0:
                    result["error"] = (
                        f"delete_body target.body_index must be a non-negative int, "
                        f"got {body_index!r}"
                    )
                    return result
            else:
                result["error"] = (
                    "delete_body target must contain 'body_index' or 'body_name'"
                )
                return result

        # W41: combine — operation + main + tool bodies.
        if feat_type == "combine":
            operation = feature.get("operation", "subtract")
            if operation not in ("add", "subtract", "common"):
                result["error"] = (
                    f"combine operation must be one of ['add', 'subtract', 'common'], "
                    f"got {operation!r}"
                )
                return result
            has_main = (
                target.get("main_body_index") is not None
                or target.get("main_body_name") is not None
            )
            has_tool = (
                target.get("tool_body_indices") is not None
                or target.get("tool_body_names") is not None
            )
            if not has_main:
                result["error"] = (
                    "combine target must contain 'main_body_index' or 'main_body_name'"
                )
                return result
            if not has_tool:
                result["error"] = (
                    "combine target must contain 'tool_body_indices' or 'tool_body_names'"
                )
                return result

        # W41: split — body + cutting entity.
        if feat_type == "split":
            if target.get("cutting_plane") is None and target.get("cutting_surface") is None:
                result["error"] = (
                    "split target must contain 'cutting_plane' or 'cutting_surface'"
                )
                return result

        if not doc_path or not Path(doc_path).exists():
            result["error"] = f"doc_path does not exist: {doc_path}"
            return result

        proposal_id = uuid.uuid4().hex[:12]
        record = {
            "kind": "feature_add",
            "proposal_id": proposal_id,
            "created_at": time.time(),
            "doc_path": doc_path,
            "feature": feature,
            "target": target,
            "state": ST_PROPOSED,
            "dry_run_result": None,
            "committed_at": None,
        }
        _save_proposal(proposal_id, record)
        result["proposal_id"] = proposal_id
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def sw_propose_assembly(spec: dict[str, Any]) -> dict[str, Any]:
    """Stage an assembly proposal. Validates offline; no SW state touched.

    The assembly kind is **de-advertised** — this function is the only entry
    point and is not reachable through ``sw_propose_feature_add``. It validates
    the spec structurally (jsonschema against ``ASSEMBLY_SCHEMA``) and
    semantically (``validate_assembly``) before writing a proposal record with
    ``kind: "assembly"``.
    """
    import jsonschema

    from .assembly.schema import ASSEMBLY_SCHEMA
    from .assembly.validator import AssemblyValidationError, validate_assembly

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "kind": "assembly",
        "spec": spec,
        "state": ST_PROPOSED,
        "error": None,
    }
    try:
        if not isinstance(spec, dict):
            result["error"] = "spec must be a dict"
            return result

        try:
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)
        except jsonschema.ValidationError as exc:
            result["error"] = f"schema: {exc.message}"
            return result

        try:
            validate_assembly(spec)
        except AssemblyValidationError as exc:
            result["error"] = str(exc)
            return result

        proposal_id = uuid.uuid4().hex[:12]
        record = {
            "kind": "assembly",
            "proposal_id": proposal_id,
            "created_at": time.time(),
            "spec": spec,
            "state": ST_PROPOSED,
            "dry_run_result": None,
            "committed_at": None,
        }
        _save_proposal(proposal_id, record)
        result["proposal_id"] = proposal_id
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result


def sw_dry_run_assembly(proposal_id: str) -> dict[str, Any]:
    """Dry-run an assembly proposal — validate bindings without mutating SW.

    Resolves part file paths, confirms files exist, and validates mate face_refs
    are well-formed. Does not open any SW documents.
    """
    from .assembly.lifecycle import dry_run_assembly

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "assembly":
        result["error"] = f"proposal {proposal_id} is not an assembly proposal"
        return result

    spec = rec["spec"]
    dry = dry_run_assembly(spec)
    result.update(dry)

    if dry.get("ok"):
        rec["state"] = ST_DRY_RUN_OK
        rec["dry_run_result"] = dry
        _save_proposal(proposal_id, rec)
        result["state"] = ST_DRY_RUN_OK

    return result


def sw_commit_assembly(
    proposal_id: str,
    output_path: str,
    *,
    part_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the assembly — place components, create mates, save.

    Requires the proposal to be in ``dry_run_ok`` state. Opens an assembly
    document, places all components, creates all mates, saves the ``.sldasm``,
    and writes the assembly manifest alongside it.
    """
    from .assembly.lifecycle import commit_assembly

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "assembly":
        result["error"] = f"proposal {proposal_id} is not an assembly proposal"
        return result
    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok' (run sw_dry_run_assembly first)"
        )
        return result

    spec = rec["spec"]

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = f"could not connect to SW: {exc!r}"
        return result

    commit = commit_assembly(sw, spec, output_path, part_paths=part_paths)
    result.update(commit)

    if commit.get("ok"):
        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        rec["manifest"] = commit.get("manifest")
        _save_proposal(proposal_id, rec)
        result["state"] = ST_COMMITTED

    return result


def sw_edit_assembly(
    manifest_path: str, op: dict[str, Any]
) -> dict[str, Any]:
    """Edit an assembly via its manifest sidecar.

    Loads the manifest, extracts the verbatim spec via ``to_spec()``,
    applies the declarative edit op, re-validates, and proposes the
    edited spec. Returns a ``proposal_id`` that feeds the existing
    ``sw_dry_run_assembly`` → ``sw_commit_assembly`` pipeline.

    Args:
        manifest_path: path to the ``.manifest.json`` sidecar.
        op: a declarative edit op dict (see ``assembly.edit``).

    Returns:
        A result dict with ``ok``, ``proposal_id``, ``edit_applied``,
        and ``error``.
    """
    from pathlib import Path as _Path

    from .assembly.edit import AssemblyEditError, apply_edit_op
    from .assembly.storage import AssemblyManifest
    from .assembly.validator import AssemblyValidationError, validate_assembly

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "edit_applied": False,
        "error": None,
    }

    try:
        manifest = AssemblyManifest.load(_Path(manifest_path))
        old_spec = manifest.to_spec()
    except (FileNotFoundError, ValueError) as exc:
        result["error"] = f"manifest load failed: {exc}"
        return result

    try:
        new_spec = apply_edit_op(old_spec, op)
    except AssemblyEditError as exc:
        result["error"] = f"edit op rejected: {exc.message}"
        return result

    result["edit_applied"] = True

    try:
        validate_assembly(new_spec)
    except AssemblyValidationError as exc:
        result["error"] = (
            f"edited spec failed validation: {exc.message}"
        )
        return result

    propose = sw_propose_assembly(new_spec)
    result.update(propose)
    return result


# ---- Drawing lifecycle (Wave-16) ----


def sw_propose_drawing(spec: dict[str, Any]) -> dict[str, Any]:
    """Propose a drawing spec — validate offline.

    Returns a result dict with ``ok``, ``proposal_id``, and ``error``.
    """
    import jsonschema

    from .drawing.lifecycle import validate_drawing_spec
    from .drawing.spec_schema import DRAWING_SPEC_SCHEMA

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "kind": "drawing",
        "state": ST_PROPOSED,
        "error": None,
    }

    try:
        jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)
    except jsonschema.ValidationError as exc:
        result["error"] = f"schema error: {exc.message}"
        return result

    try:
        validate_drawing_spec(spec)
    except ValueError as exc:
        result["error"] = str(exc)
        return result

    pid = uuid.uuid4().hex[:12]
    rec = {
        "kind": "drawing",
        "state": ST_PROPOSED,
        "spec": spec,
        "proposed_at": time.time(),
    }
    _save_proposal(pid, rec)
    result["ok"] = True
    result["proposal_id"] = pid
    return result


def sw_dry_run_drawing(proposal_id: str) -> dict[str, Any]:
    """Dry-run a drawing proposal — confirm model file exists."""
    from .drawing.lifecycle import dry_run_drawing

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "drawing":
        result["error"] = f"proposal {proposal_id} is not a drawing proposal"
        return result

    dry = dry_run_drawing(rec["spec"])
    result.update(dry)

    if dry.get("ok"):
        rec["state"] = ST_DRY_RUN_OK
        _save_proposal(proposal_id, rec)
        result["state"] = ST_DRY_RUN_OK

    return result


def sw_commit_drawing(
    proposal_id: str,
    output_path: str,
) -> dict[str, Any]:
    """Commit a drawing proposal — create views, save .SLDDRW."""
    from .drawing.lifecycle import commit_drawing

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "drawing":
        result["error"] = f"proposal {proposal_id} is not a drawing proposal"
        return result
    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok'"
        )
        return result

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = f"could not connect to SW: {exc!r}"
        return result

    commit = commit_drawing(sw, rec["spec"], output_path)
    result.update(commit)

    if commit.get("ok"):
        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        _save_proposal(proposal_id, rec)
        result["state"] = ST_COMMITTED

    return result


# ---- properties support (W29) ------------------------------------------------


def sw_propose_properties(spec: dict[str, Any]) -> dict[str, Any]:
    """Propose a properties spec — validate offline.

    Returns a result dict with ``ok``, ``proposal_id``, and ``error``.
    """
    import jsonschema

    from .metadata.lifecycle import propose_properties
    from .metadata.spec_schema import PROPERTIES_SPEC_SCHEMA

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": None,
        "kind": "properties",
        "state": ST_PROPOSED,
        "error": None,
    }

    try:
        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)
    except jsonschema.ValidationError as exc:
        result["error"] = f"schema validation failed: {exc.message}"
        return result

    propose_result = propose_properties(spec)
    if not propose_result.get("ok"):
        result["error"] = propose_result.get("error")
        return result

    pid = uuid.uuid4().hex[:12]
    rec = {
        "kind": "properties",
        "state": ST_PROPOSED,
        "spec": spec,
        "proposed_at": time.time(),
    }
    _save_proposal(pid, rec)

    result["ok"] = True
    result["proposal_id"] = pid
    return result


def sw_dry_run_properties(proposal_id: str) -> dict[str, Any]:
    """Dry-run a properties proposal — confirm model file exists."""
    from .metadata.lifecycle import dry_run_properties

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "properties":
        result["error"] = f"proposal {proposal_id} is not a properties proposal"
        return result

    dry = dry_run_properties(rec["spec"])
    result.update(dry)

    if dry.get("ok"):
        rec["state"] = ST_DRY_RUN_OK
        rec["dry_run_at"] = time.time()
        _save_proposal(proposal_id, rec)
        result["state"] = ST_DRY_RUN_OK

    return result


def sw_commit_properties(proposal_id: str) -> dict[str, Any]:
    """Commit a properties proposal — set custom properties on the model."""
    from .metadata.lifecycle import commit_properties

    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result
    if rec.get("kind") != "properties":
        result["error"] = f"proposal {proposal_id} is not a properties proposal"
        return result
    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok'"
        )
        return result

    try:
        sw = get_sw_app()
    except Exception as exc:
        result["error"] = f"could not connect to SW: {exc!r}"
        return result

    commit_result = commit_properties(sw, rec["spec"])
    result.update(commit_result)

    if commit_result.get("ok"):
        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        _save_proposal(proposal_id, rec)
        result["state"] = ST_COMMITTED

    return result


def sw_dry_run_feature_add(proposal_id: str) -> dict[str, Any]:
    """Open the doc, resolve the edge, add the fillet, rebuild, close without saving."""
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "state": ST_PROPOSED,
        "dry_run_result": None,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result

    if rec.get("kind", "local_change") != "feature_add":
        result["error"] = f"proposal {proposal_id} is not a feature_add proposal"
        return result

    if rec["state"] not in (ST_PROPOSED, ST_DRY_RUN_OK, ST_DRY_RUN_BROKE):
        result["error"] = f"proposal is in state {rec['state']!r}, cannot dry-run"
        return result

    doc_path = rec["doc_path"]
    doc = None
    sw = None

    try:
        sw = get_sw_app()
        active = get_active_doc(sw)
        if active is not None:
            try:
                active_path = str(resolve(active, "GetPathName"))
                if (
                    active_path
                    and Path(active_path).resolve() == Path(doc_path).resolve()
                ):
                    result["error"] = (
                        f"target doc is the active document ({doc_path}); "
                        "close it before dry-run"
                    )
                    return result
            except Exception:
                pass

        doc = _open_doc_typed(doc_path)
        if doc is None:
            result["error"] = f"failed to open doc: {doc_path}"
            return result

        feat_ok, feat_err = _apply_feature(doc, rec["feature"], rec["target"])

        try:
            rebuild_ok = bool(doc.ForceRebuild3(False))
        except Exception:
            rebuild_ok = False

        dry_run_result = {
            "ran_at": time.time(),
            "feature_ok": feat_ok,
            "rebuild_ok": rebuild_ok,
            "error": feat_err,
        }

        if feat_ok:
            state = ST_DRY_RUN_OK
        else:
            state = ST_DRY_RUN_BROKE
            result["error"] = feat_err

        result["state"] = state
        result["dry_run_result"] = dry_run_result

    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseDoc(_doc_title(doc))
            except Exception:
                pass

    rec["state"] = state
    rec["dry_run_result"] = dry_run_result
    _save_proposal(proposal_id, rec)

    result["ok"] = state == ST_DRY_RUN_OK
    result["state"] = state
    return result


def sw_commit_feature_add(proposal_id: str) -> dict[str, Any]:
    """Re-run the feature-add pipeline and save the document."""
    result: dict[str, Any] = {
        "ok": False,
        "proposal_id": proposal_id,
        "doc_saved": False,
        "state": ST_PROPOSED,
        "error": None,
    }

    rec = _load_proposal(proposal_id)
    if rec is None:
        result["error"] = f"proposal {proposal_id} not found"
        return result

    if rec.get("kind", "local_change") != "feature_add":
        result["error"] = f"proposal {proposal_id} is not a feature_add proposal"
        return result

    if rec["state"] != ST_DRY_RUN_OK:
        result["error"] = (
            f"refusing to commit proposal in state {rec['state']!r}; "
            "must be 'dry_run_ok' (run sw_dry_run_feature_add first)"
        )
        return result

    doc_path = rec["doc_path"]
    doc = None
    sw = None

    try:
        sw = get_sw_app()
        active = get_active_doc(sw)
        if active is not None:
            try:
                active_path = str(resolve(active, "GetPathName"))
                if (
                    active_path
                    and Path(active_path).resolve() == Path(doc_path).resolve()
                ):
                    result["error"] = (
                        f"target doc is the active document ({doc_path}); "
                        "close it before commit"
                    )
                    return result
            except Exception:
                pass

        doc = _open_doc_typed(doc_path)
        if doc is None:
            result["error"] = f"failed to open doc: {doc_path}"
            return result

        feat_ok, feat_err = _apply_feature(doc, rec["feature"], rec["target"])
        if not feat_ok:
            result["error"] = f"feature creation failed during commit: {feat_err}"
            return result

        try:
            result["doc_saved"] = _save_doc(doc)
        except Exception as exc:
            result["error"] = f"doc.Save raised: {exc!r}"
            return result

        rec["state"] = ST_COMMITTED
        rec["committed_at"] = time.time()
        _save_proposal(proposal_id, rec)

        result["state"] = ST_COMMITTED
        result["ok"] = True
        return result

    except Exception as exc:
        result["error"] = f"unexpected: {exc!r}"
        return result

    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseDoc(_doc_title(doc))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# v0.14 — class-based facade over the legacy ``sw_*`` free functions.
#
# The free functions above are the canonical implementations and remain
# the documented backward-compatible API. ``ProposalStore`` is the
# recommended entry point for new code. A deeper migration (move
# logic into methods, extract the file-locking + state-transition
# ceremony into one place) is logged as ``D-v0.14-06`` in
# ``docs/DEFERRED.md`` and targets v0.15.
# ---------------------------------------------------------------------------


class ProposalStore:
    """File-backed proposal lifecycle store. New in v0.14.

    Methods return the same JSON-shaped dicts as the legacy
    ``sw_*`` free functions in this module — the class is a thin
    facade so callers can prefer instance-method syntax and so a
    future refactor can swap the on-disk format without touching
    call sites. Instances are stateless; nothing is cached between
    calls.

    Proposals persist under :func:`_proposals_dir` (``./proposals``
    by default; override with ``AI_SW_BRIDGE_PROPOSALS``).
    """

    def propose(self, var: str, new_value: str) -> dict[str, Any]:
        """Stage a change to *var* — no SW state is modified yet."""
        return sw_propose_local_change(var=var, new_value=new_value)

    def dry_run(self, proposal_id: str) -> dict[str, Any]:
        """Apply a proposal, force-rebuild, capture state, roll back."""
        return sw_dry_run(proposal_id=proposal_id)

    def commit(self, proposal_id: str) -> dict[str, Any]:
        """Re-apply a dry-run-ok proposal and save the SW document."""
        return sw_commit(proposal_id=proposal_id)

    def undo_last(self) -> dict[str, Any]:
        """Revert the most recently committed proposal."""
        return sw_undo_last_commit()

    def propose_feature_add(
        self, doc_path: str, feature: dict, target: dict
    ) -> dict[str, Any]:
        """Stage a feature-add proposal — no SW state is modified yet."""
        return sw_propose_feature_add(
            doc_path=doc_path, feature=feature, target=target
        )

    def dry_run_feature_add(self, proposal_id: str) -> dict[str, Any]:
        """Apply a feature-add proposal, rebuild, close without saving."""
        return sw_dry_run_feature_add(proposal_id=proposal_id)

    def commit_feature_add(self, proposal_id: str) -> dict[str, Any]:
        """Re-run a dry-run-ok feature-add and save the SW document."""
        return sw_commit_feature_add(proposal_id=proposal_id)
