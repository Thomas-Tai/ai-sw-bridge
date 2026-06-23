"""Recipe-C cut #4 — sheet-metal flange family (base_flange / edge_flange).

base_flange = W7 GREEN (seat-proven CreateDefinition pipeline).
edge_flange  = DORMANT ghost (quarantined W42 — handler + tests stay, but the
kind is NEVER advertised; a ΔVol>0 seat proof is required before re-advertising).

The ``_feature_names`` / ``_build_edge_normal_plane_sketch`` private helpers
and the ``_SW_REFPLANE_PERPENDICULAR`` / ``_SW_REFPLANE_COINCIDENT`` consts
(previously in mutate.py at lines 127-128) are moved here; they were only
used by the edge_flange island and go dead in mutate after this relocation.

``BASE_FLANGE_STATUS = "GREEN"``
``EDGE_FLANGE_STATUS = "DORMANT"``
"""

from __future__ import annotations

import math
from typing import Any

import pythoncom
from win32com.client import VARIANT

from ..com.earlybind import typed, typed_qi, read_persist_reference
from ..com.sw_type_info import wrapper_module
from ..selection import (
    DurableEdgeRef,
    resolve_edge_ref,
    select_entity,
)
from .verify import materialized as _materialized

BASE_FLANGE_STATUS = "GREEN"
EDGE_FLANGE_STATUS = "DORMANT"

# swFmBaseFlange — CreateDefinition id for a sheet-metal base flange (seat-proven).
_SW_FM_BASEFLANGE = 34

# swRefPlaneReferenceConstraints_e — used by _build_edge_normal_plane_sketch.
# Moved here from mutate.py (lines 127-128) where they were only used by the
# edge_flange island; they go dead in mutate after this relocation.
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
