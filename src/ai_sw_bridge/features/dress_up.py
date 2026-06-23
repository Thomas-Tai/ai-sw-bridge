"""Recipe-C cut #4 — dress-up family (fillet/chamfer/variable_fillet/shell/draft).

All five handlers are GREEN (seat-proven); relocated byte-identical from mutate.py
into the HANDLER_REGISTRY seam.  The ``_get_face_entity`` helper is shared by
shell and draft and is moved here once.

``SPIKE_STATUS = "GREEN"``
"""

from __future__ import annotations

import math
from typing import Any

from ..com.earlybind import typed, typed_qi
from ..com.sw_type_info import wrapper_module
from ..selection import (
    DurableEdgeRef,
    resolve_edge_ref,
    select_entity,
)
from .verify import materialized as _materialized

SPIKE_STATUS = "GREEN"

# swFmFillet — CreateDefinition id for constant-radius fillet (seat-proven).
_SW_FM_FILLET = 1
_SW_CONST_RADIUS_FILLET = 0  # swFilletType_e.swConstantRadiusFillet

# swChamferType_e — duplicated from mutate (the original stays for the
# propose-time validator; this copy serves the handler only).
_SW_CHAMFER_ANGLE_DISTANCE = 1     # swChamferType_e.swChamferAngleDistance
_SW_CHAMFER_DISTANCE_DISTANCE = 2  # swChamferType_e.swChamferDistanceDistance
_SW_CHAMFER_VERTEX = 3             # swChamferType_e.swChamferVertex
_CHAMFER_TYPES = ("angle_distance", "distance_distance", "vertex")

# swDraftFacePropagationType_e — draft face propagation (duplicated for handler).
_DRAFT_PROPAGATION = {
    "none": 0,
    "tangent": 1,
    "all_loops": 2,
    "inner_loops": 3,
    "outer_loops": 4,
}


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


def _create_chamfer(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Run the chamfer pipeline on a durable edge or vertex — fillet sibling.

    Three closed-form modes via ``feature['chamfer_type']`` (default
    ``'angle_distance'`` — the W24 shipped behaviour, so existing specs are
    unaffected):

      * ``angle_distance``    — EDGE target; ``distance_mm`` + ``angle_deg``.
      * ``distance_distance`` — EDGE target; ``distance_mm`` (face-set 1) +
        ``distance2_mm`` (face-set 2).
      * ``vertex``            — VERTEX target ``{'point':[x,y,z]}`` (mm); three
        back-set distances ``distance_mm``/``distance2_mm``/``distance3_mm``.

    Uses ``InsertFeatureChamfer`` (8-arg, seat-proven W24):
    ``(Options, ChamferType, Width, Angle, OtherDist, VCDist1, VCDist2,
    VCDist3)``.  swChamferType_e: AngleDistance=1, DistanceDistance=2,
    Vertex=3.  ``CreateDefinition(swFmChamfer)`` returns ``None`` on SW 2024
    SP1 — the CreateDefinition pipeline is fillet-only.  Returns (ok, error);
    fail-closed.
    """
    chamfer_type = (
        feature.get("chamfer_type", "angle_distance")
        if isinstance(feature, dict) else "angle_distance"
    )
    if chamfer_type not in _CHAMFER_TYPES:
        return False, (
            f"chamfer_type must be one of {list(_CHAMFER_TYPES)}, got {chamfer_type!r}"
        )

    def _dist_m(key: str) -> float | None:
        val = feature.get(key)
        if not isinstance(val, (int, float)) or val <= 0:
            return None
        return float(val) / 1000.0

    options = 4  # swFeatureChamferTangentPropagation
    doc.ForceRebuild3(False)

    # --- VERTEX chamfer: select a vertex by point, three back-set distances ---
    if chamfer_type == "vertex":
        point = target.get("point") if isinstance(target, dict) else None
        if not (isinstance(point, (list, tuple)) and len(point) == 3):
            return False, "vertex chamfer target.point must be [x, y, z] mm"
        d1, d2, d3 = (_dist_m("distance_mm"), _dist_m("distance2_mm"), _dist_m("distance3_mm"))
        if None in (d1, d2, d3):
            return False, (
                "vertex chamfer requires positive distance_mm, distance2_mm, distance3_mm"
            )
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        if not doc.SelectByID(
            "", "VERTEX",
            float(point[0]) / 1000.0, float(point[1]) / 1000.0, float(point[2]) / 1000.0,
        ):
            return False, f"SelectByID(VERTEX at {list(point)} mm) failed"
        try:
            feat = doc.FeatureManager.InsertFeatureChamfer(
                options, _SW_CHAMFER_VERTEX, 0.0, 0.0, 0.0, d1, d2, d3,
            )
            if _materialized(feat):
                return True, None
            return False, "InsertFeatureChamfer(vertex) did not materialize"
        except Exception as exc:
            return False, f"vertex chamfer pipeline failed: {exc!r}"

    # --- EDGE chamfer (angle_distance | distance_distance) -------------------
    edge_ref = DurableEdgeRef.from_dict(target)
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
        if chamfer_type == "distance_distance":
            d1, d2 = _dist_m("distance_mm"), _dist_m("distance2_mm")
            if None in (d1, d2):
                return False, (
                    "distance_distance chamfer requires positive distance_mm and distance2_mm"
                )
            feat = fm.InsertFeatureChamfer(
                options, _SW_CHAMFER_DISTANCE_DISTANCE,
                d1, 0.0, d2, 0.0, 0.0, 0.0,
            )
        else:  # angle_distance (default / W24)
            d1 = _dist_m("distance_mm")
            if d1 is None:
                return False, "angle_distance chamfer requires positive distance_mm"
            angle_rad = float(feature.get("angle_deg", 45.0)) * math.pi / 180.0
            feat = fm.InsertFeatureChamfer(
                options, _SW_CHAMFER_ANGLE_DISTANCE,
                d1, angle_rad, 0.0, 0.0, 0.0, 0.0,
            )
        if _materialized(feat):
            return True, None
        return False, f"InsertFeatureChamfer({chamfer_type}) did not materialize"
    except Exception as exc:
        return False, f"chamfer pipeline failed: {exc!r}"


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
