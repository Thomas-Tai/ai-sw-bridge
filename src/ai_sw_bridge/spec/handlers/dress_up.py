"""Dress-up family handlers, relocated from builder.py (Phase 3 Move 4).

`_build_fillet_constant_radius` / `_build_chamfer_edge` and the shared
edge-selection block (`_edge_fingerprint`, `_all_solid_edges`,
`_select_edges`, `_EDGE_FP_REFS`) plus the two fillet enum constants
(`SW_FM_FILLET`, `SW_CONST_RADIUS_FILLET`), whose only consumers are these
two handlers. Leaf module: imports only `.._build_context`,
`.._edge_selectors`, `.._face_geometry`, `.._sketch_primitives`, and
`...sw_types` -- never builder.py or a sibling handler module.
"""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext, BuiltFeature
from .._edge_selectors import (
    EdgeSelectorError,
    LiteralPoint,
    faces_referenced,
    parse_edge_selectors,
    resolve_edge_selectors,
)
from .._face_geometry import _face_edge_objects, _resolve_face_object
from .._sketch_primitives import _literal_or_default
from ...sw_types import (
    SW_CHAMFER_ANGLE_DISTANCE,
    SW_CHAMFER_DISTANCE_DISTANCE,
    SW_FEATURE_CHAMFER_TANGENT_PROPAGATION,
    assert_args,
)

# swFeatureNameID_e.swFmFillet -- numeric value not exposed in the
# decompiled CHM enum table (text-only). Found empirically in Spike P
# (spikes/phase0/spike_p_fillet_pipeline.py) by probing CreateDefinition
# with ints 0..59 and checking which return object accepts
# .Initialize(swConstRadiusFillet). swFmFillet = 1 on SW 2024 SP1.
SW_FM_FILLET = 1

# swSimpleFilletType_e.swConstRadiusFillet -- value IS in the CHM enum
# table (constant radius == 0). The other useful values: swFaceFillet=2,
# swFullRoundFillet=3. v1 of the bridge supports only constant-radius.
SW_CONST_RADIUS_FILLET = 0


# Two fixed, well-separated reference points (meters) for the geometric edge
# fingerprint. An edge's closest point to each reference, rounded to microns, is
# its identity key. The key is GEOMETRIC (not COM identity), so the SAME
# physical edge -- enumerated from a body, from a face, or found by literal
# closest-match -- hashes equal. That is what lets between_faces intersect two
# faces' edge sets and lets a corner edge reached two ways de-duplicate. Two
# well-separated references make a collision between two distinct edges
# effectively impossible on the orthogonal solids this addresses.
_EDGE_FP_REFS = ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))


def _edge_fingerprint(edge: Any) -> tuple:
    """A stable geometric identity key for an ``IEdge`` (see ``_EDGE_FP_REFS``)."""
    pts: list = []
    for rx, ry, rz in _EDGE_FP_REFS:
        cp = edge.GetClosestPointOn(rx, ry, rz)
        if cp is None:
            raise RuntimeError(
                "edge fingerprint failed: GetClosestPointOn returned None"
            )
        pts.append((round(cp[0], 6), round(cp[1], 6), round(cp[2], 6)))
    return tuple(pts)


def _all_solid_edges(ctx: BuildContext) -> list:
    """Every ``IEdge`` of every solid body, for literal closest-point matching.

    ``IPartDoc.GetBodies2(swSolidBody=0, bVisibleOnly=True)`` -> bodies, then
    ``body.GetEdges`` (callable-or-property guarded). The caller keeps the edges
    alive across selection (W67 IEdge lifetime trap).
    """
    try:
        bodies = ctx.doc.GetBodies2(0, True)  # swBodyType_e.swSolidBody=0
    except Exception as e:
        raise RuntimeError(f"GetBodies2 failed: {e!r}")
    if bodies is None or len(bodies) == 0:
        raise RuntimeError("part has no solid bodies; cannot select edges")
    all_edges: list = []
    for body in bodies:
        edges = body.GetEdges
        if callable(edges):
            edges = edges()
        if edges is None:
            continue
        all_edges.extend(edges)
    if not all_edges:
        raise RuntimeError("no edges on any body; cannot select")
    return all_edges


def _select_edges(ctx: BuildContext, edge_items: "list[dict[str, Any]]") -> int:
    """Resolve a fillet/chamfer ``edges[]`` array and add the edges to the
    selection set, returning the count selected.

    Each item is one of three forms (see ``spec/_edge_selectors.py``):
      - literal point  ``{x, y, z}``                       -- nearest edge / 1um
      - of_face        ``{of_feature, face}``              -- all edges of a face
      - between_faces  ``{of_feature, between_faces:[A,B]}``-- the shared edge

    TWO-PHASE by design (the load-bearing correctness rule): RESOLVE everything
    into a Python ``edge key -> IEdge`` map FIRST -- because
    ``_resolve_face_object`` clears the selection internally, interleaving
    face-picking with edge accumulation would wipe earlier selections -- THEN
    ``ClearSelection2`` once and ``IEntity.Select2(Append, Mark)`` each unique
    edge. The set algebra (ordering, de-dup, between_faces intersection) is the
    pure ``resolve_edge_selectors``; only fingerprinting, ``IFace2.GetEdges``,
    and ``Select2`` touch COM here.

    The naive 5-arg ``SelectByID("", "EDGE", x, y, z)`` loop does NOT accumulate
    (each call replaces the prior selection; Spike Q3, 2026-05-17), and
    ``SelectByID2(...Callout=None...)`` / ``IEntity.Select4`` fail to marshal the
    Callout OUT-param under pywin32 late binding -- hence the
    ``GetClosestPointOn`` + ``IEntity.Select2`` working path (Spike Q4 GREEN).

    Legacy literal-only specs take a byte-identical closest-edge path and the
    same "matches no edge within 1um" RuntimeError. Raises RuntimeError on any
    malformed or unresolvable selector.
    """
    try:
        parsed = parse_edge_selectors(edge_items)
    except EdgeSelectorError as e:
        raise RuntimeError(f"edge selector error: {e}")

    edge_objects: dict = {}  # EdgeKey -> IEdge (doubles as the keepalive)
    keepalive: list = []  # parent IFace2/IBody2/IEdge proxies (W67 trap)
    all_edges_cache: list = []  # lazily filled; a semantic-only spec skips it

    def literal_to_edge(p: LiteralPoint, index: int) -> tuple:
        if not all_edges_cache:
            all_edges_cache.extend(_all_solid_edges(ctx))
        x_m, y_m, z_m = p.x / 1000.0, p.y / 1000.0, p.z / 1000.0
        best_edge, best_d2 = None, 1e18
        for edge in all_edges_cache:
            try:
                cp = edge.GetClosestPointOn(x_m, y_m, z_m)
            except Exception:
                continue
            if cp is None:
                continue
            d2 = (cp[0] - x_m) ** 2 + (cp[1] - y_m) ** 2 + (cp[2] - z_m) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_edge = edge
        if best_edge is None or best_d2 > 1e-12:
            raise RuntimeError(
                f"edge #{index} at part ({p.x}, {p.y}, {p.z}) mm "
                f"matches no edge within 1um (best squared distance "
                f"{best_d2:.3e} m^2)"
            )
        key = _edge_fingerprint(best_edge)
        edge_objects.setdefault(key, best_edge)
        return key

    # Build the (of_feature, face) -> frozenset[edge key] incidence map for
    # every semantic face referenced, resolving each face object IMMEDIATELY
    # (before any edge selection -- see the two-phase note above).
    needed_faces = {
        (sel.of_feature, face)
        for sel in parsed
        if not isinstance(sel, LiteralPoint)
        for face in faces_referenced(sel)
    }
    face_edges: dict = {}
    for of_feature, face in needed_faces:
        parent = ctx.features_by_name.get(of_feature)
        if parent is None or parent.extrude_axis is None:
            # The validator enforces this; belt-and-suspenders for a direct
            # build path that bypasses validation.
            raise RuntimeError(
                f"edge selector references '{of_feature}', which is not a "
                f"built extrusion with resolvable faces"
            )
        face_obj = _resolve_face_object(ctx, parent, face)
        keepalive.append(face_obj)
        keys: set = set()
        for edge in _face_edge_objects(face_obj):
            key = _edge_fingerprint(edge)
            edge_objects.setdefault(key, edge)
            keepalive.append(edge)
            keys.add(key)
        if not keys:
            raise RuntimeError(
                f"{face} face of '{of_feature}' has no bounding edges "
                f"(IFace2.GetEdges returned empty)"
            )
        face_edges[(of_feature, face)] = frozenset(keys)

    try:
        resolved_keys = resolve_edge_selectors(
            parsed, literal_to_edge=literal_to_edge, face_edges=face_edges
        )
    except EdgeSelectorError as e:
        raise RuntimeError(f"edge selector error: {e}")

    # Phase 2: select. ClearSelection2 once, then append each unique edge.
    ctx.doc.ClearSelection2(True)
    for index, edge_key in enumerate(resolved_keys):
        if not edge_objects[edge_key].Select2(True, 0):
            raise RuntimeError(
                f"IEntity.Select2(append=True, mark=0) returned False on "
                f"resolved edge #{index}"
            )
    return len(resolved_keys)


def _build_fillet_constant_radius(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Constant-radius edge fillet via the SW 2020+ canonical pipeline.

    FeatureFillet3 (single-call) is marked obsolete for constant-radius
    fillets per the decompiled CHM. The recommended path is:
        data = fm.CreateDefinition(swFmFillet)
        data.Initialize(swConstRadiusFillet)
        data.DefaultRadius = radius_m
        <select edges>
        fm.CreateFeature(data)

    Spike P (spikes/phase0/spike_p_fillet_pipeline.py) verified the
    full pipeline works via pywin32 late binding -- the data-object
    arg to CreateFeature DOES marshal correctly (unlike Callout/OUT
    params that have failed on this build).

    v1 supports constant-radius only and selects edges by part-coord
    points (one per edge). No "all edges of face" sugar yet; the spec
    enumerates each edge midpoint explicitly.
    """
    radius_m = _literal_or_default(feat["radius"], 1.0)  # 1mm placeholder

    fm = ctx.doc.FeatureManager
    data = fm.CreateDefinition(SW_FM_FILLET)
    if data is None:
        raise RuntimeError("CreateDefinition(swFmFillet) returned None")
    ok = data.Initialize(SW_CONST_RADIUS_FILLET)
    if not ok:
        raise RuntimeError("ISimpleFilletFeatureData2.Initialize(0) returned False")

    # Set the default radius. Property assignment on the CDispatch worked
    # in Spike P; readback confirmed value round-trips.
    data.DefaultRadius = radius_m

    # Accumulate edges via the shared helper (literal points and/or semantic
    # of_face / between_faces selectors). See _select_edges docstring.
    n_selected = _select_edges(ctx, feat["edges"])
    if n_selected == 0:
        raise RuntimeError("no edges selected; fillet would no-op")

    # CreateFeature picks up the current selection set.
    f = fm.CreateFeature(data)
    if f is None:
        raise RuntimeError(
            f"CreateFeature returned None for fillet on {n_selected} edges "
            f"with radius {radius_m*1000:.2f}mm"
        )
    f.Name = feat["name"]

    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _build_chamfer_edge(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Edge chamfer via IFeatureManager::InsertFeatureChamfer (8-arg call).

    Modes and the args that actually commit geometry on SW 2024 SP1
    (confirmed GREEN in Spike Q11/Q12, 2026-05-17):

      equal_distance -> ChamferType=swChamferDistanceDistance=2,
                        Width=OtherDist=distance_m.
                        swChamferEqualDistance=16 is listed in the CHM enum
                        but never commits geometry on this build -- the
                        feature appears in the tree with GetEdgeCount=4 but
                        body topology stays 6F/12E (plain box). DistDist with
                        equal distances is geometrically identical.

      distance_angle -> ChamferType=swChamferAngleDistance=1,
                        Width=distance_m, Angle=angle in RADIANS.
                        The CHM says "degrees" but empirically both degrees
                        and radians produce the same geometry for 45deg;
                        using radians matches the broader SW API convention.

    Options: tangent-propagation flag (4) is always set; flip adds bit 1.
    """
    import math

    mode = feat["mode"]
    distance_m = _literal_or_default(feat["distance"], 1.0)  # 1mm placeholder

    options = SW_FEATURE_CHAMFER_TANGENT_PROPAGATION
    if feat.get("flip", False):
        options |= 1  # swFeatureChamferFlipDirection

    if mode == "equal_distance":
        # Use DistanceDistance with both sides equal -- swChamferEqualDistance=16
        # never commits geometry on SW 2024 SP1 (Spike Q12).
        chamfer_type = SW_CHAMFER_DISTANCE_DISTANCE
        width = distance_m
        angle_rad = 0.0
        other_dist = distance_m
    elif mode == "distance_angle":
        chamfer_type = SW_CHAMFER_ANGLE_DISTANCE
        width = distance_m
        angle_value = feat["angle"]
        if isinstance(angle_value, dict) and "rhs" in angle_value:
            angle_deg = 45.0  # placeholder; rebound on next ctx rebuild
        else:
            angle_deg = float(angle_value)
        angle_rad = angle_deg * math.pi / 180.0
        other_dist = 0.0
    else:
        raise RuntimeError(f"chamfer_edge: unknown mode {mode!r}")

    n_selected = _select_edges(ctx, feat["edges"])
    if n_selected == 0:
        raise RuntimeError("no edges selected; chamfer would no-op")

    fm = ctx.doc.FeatureManager
    args = (options, chamfer_type, width, angle_rad, other_dist, 0.0, 0.0, 0.0)
    assert_args("IFeatureManager.InsertFeatureChamfer", args)
    f = fm.InsertFeatureChamfer(*args)
    if f is None:
        raise RuntimeError(
            f"InsertFeatureChamfer returned None for chamfer on {n_selected} "
            f"edges, mode={mode}, distance={distance_m * 1000:.2f}mm"
        )
    f.Name = feat["name"]
    ctx.doc.ForceRebuild3(False)

    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)
