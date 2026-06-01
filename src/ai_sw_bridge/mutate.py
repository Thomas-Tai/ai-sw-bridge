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

from .com.earlybind import typed, typed_qi
from .com.sw_type_info import wrapper_module
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
    "base_flange",
    "variable_radius_fillet",
    "wizard_hole",
    "shell",
    "draft",
    "sweep",
    # ---- Wave-5 F0 ref-geom: handlers wired below, but NOT advertised yet ----
    # The recipe is seat-proven at the spike level (spike_refgeom, W3 S-REFGEOM PASS),
    # but per the W0 directive these kinds are gated on a fresh gold-standard PAE of
    # the production handlers (propose→dry_run→commit on a live seat) before they
    # enter the advertised surface. Re-add ref_plane / ref_axis / coordinate_system /
    # ref_point here once that PAE is GREEN.
    # ---- Wave-5 F1–F6 kinds REMOVED from the advertised surface (W0 handback) ----
    # The handlers + dispatch entries remain below as characterized code; propose
    # must fail-close with "unsupported feature type" for any of these kinds
    # until a seat-run materializes them. Removing them here enforces the
    # edge-flange precedent: never advertise a non-materializing kind.
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
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_SWEEP)
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
    """Create an offset reference plane.

    Seat-proven recipe (spike_refgeom, W3):
      doc.SelectByID(plane, "PLANE", 0,0,0)
      fm.InsertRefPlane(8, distance_m, 0,0,0,0)
    where 8 = swRefPlaneReferenceConstraint_Distance (bit-flag).
    """
    plane_name = target.get("plane") if isinstance(target, dict) else None
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
        doc.SelectByID(planes[0], "PLANE", 0, 0, 0)
        doc.SelectByID(planes[1], "PLANE", 0, 0, 0)
        feat = doc.InsertAxis2(True)
        if feat is not None and not isinstance(feat, (int, bool)):
            return True, None
        return False, "InsertAxis2 did not materialize"
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
    """Create a reference point at a vertex or coordinate.

    Seat-proven recipe (spike_refgeom, W3):
      Select vertex at coords, then fm.InsertReferencePoint(5, 0, 0.0, 1).
    """
    point = target.get("point") if isinstance(target, dict) else None
    if not isinstance(point, (list, tuple)) or len(point) != 3:
        return False, "target.point must be a 3-element [x,y,z] in model metres"
    try:
        doc.ClearSelection2(True)
        doc.SelectByID("", "VERTEX", float(point[0]), float(point[1]), float(point[2]))
        fm = doc.FeatureManager
        feat = fm.InsertReferencePoint(5, 0, 0.0, 1)
        if _materialized(feat):
            return True, None
        return False, "InsertReferencePoint did not materialize"
    except Exception as exc:
        return False, f"ref-point pipeline failed: {exc!r}"


# ---- Wave-5: F1 sweep-cut (mirror _create_sweep, swFmSweepCut=18) ----


def _create_sweep_cut(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a sweep-cut feature — mirror of _create_sweep with swFmSweepCut=18.

    Same ISweepFeatureData interface; same marked select pipeline
    (profile=mark 1, path=mark 4). SEAT-PENDING (W0): confirm const=18 from
    swconst.tlb and that ISweepFeatureData is the right interface for cuts.
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
        # SEAT-PENDING (W0): confirm CreateFeature materializes a sweep cut.
        feat = fm.CreateFeature(fd)
        if _materialized(feat):
            return True, None
        return False, (
            "CreateFeature did not materialize "
            "(the path sketch must leave the profile plane)"
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
    """Create a dome feature on a selected face.

    Seat-validated (SW 2024 SP1): no ``swFmDome`` in ``swconst.tlb``.
    Legacy ``IModelDoc2.InsertDome`` takes **3 args**:
    ``(distance, flipDir, elipticalDome)``.

    SEAT-PENDING (W0): InsertDome materialization needs seat confirmation
    with correct face selection and arg values.
    """
    face = target.get("face") if isinstance(target, dict) else None
    if not isinstance(face, (list, tuple)) or len(face) != 3:
        return False, "target.face must be a 3-element [x,y,z]"
    distance_mm = feature.get("distance_mm", 5.0) if isinstance(feature, dict) else 5.0
    distance_m = float(distance_mm) / 1000.0
    try:
        mod = wrapper_module()
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        if not ext.SelectByID2("", "FACE", float(face[0]), float(face[1]), float(face[2]), False, 0, None, 0):
            return False, "could not select face for dome"
        # SEAT-PENDING (W0): confirm InsertDome(3) materializes a dome.
        feat = doc.InsertDome(distance_m, False, False)
        if _materialized(feat):
            return True, None
        return False, "InsertDome did not materialize"
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
    InsertFeatureShell returns void, so success is confirmed via the feature
    count (``IModelDoc2.GetFeatureCount`` — works on the typed reopened doc,
    unlike ``GetBodies2`` which lives on ``IPartDoc``). ``target`` = ``{"faces":
    [[x,y,z], ...]}`` (model-metre coords; v1 coordinate placement). Returns
    (ok, error).
    """
    thickness_mm = feature["thickness_mm"]
    outward = bool(feature.get("outward", False))
    face_coords = target["faces"]
    doc.ForceRebuild3(False)
    try:
        before = int(doc.GetFeatureCount())
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
        after = int(doc.GetFeatureCount())
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
        feat = fm.InsertMultiFaceDraft(
            math.radians(angle_deg), flip, edge_draft, prop, False, False
        )
        if _materialized(feat):
            return True, None
        return False, "InsertMultiFaceDraft did not materialize"
    except Exception as exc:
        return False, f"draft pipeline failed: {exc!r}"


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
        if feat_type not in _SUPPORTED_FEATURE_TYPES:
            result["error"] = (
                f"unsupported feature type {feat_type!r}; "
                f"supported: {', '.join(_SUPPORTED_FEATURE_TYPES)}"
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

        # Wave-5: ref_plane needs plane name + distance_mm.
        if feat_type == "ref_plane":
            if not isinstance(target.get("plane"), str) or not target.get("plane"):
                result["error"] = "ref_plane target.plane must be a non-empty plane name"
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

        # Wave-5: ref_point needs a 3-element vertex coordinate.
        if feat_type == "ref_point":
            point = target.get("point")
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                result["error"] = "ref_point target.point must be a 3-element [x,y,z]"
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

        # Wave-5: dome needs a face coordinate.
        if feat_type == "dome":
            face = target.get("face")
            if not isinstance(face, (list, tuple)) or len(face) != 3:
                result["error"] = "dome target.face must be a 3-element [x,y,z]"
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
