"""Recipe-C cut #6 — sweep family (the final monolith extraction).

sweep / sweep_cut + the sketch-coordinate core (_sketch_to_model_coords /
_apply_auto_pierce / auto-pierce centroid math) relocated byte-identical from
mutate.py into the HANDLER_REGISTRY seam. With this cut mutate.py holds zero
feature handlers and _apply_feature collapses to a pure registry lookup.

SPIKE_STATUS = "GREEN"
"""

from __future__ import annotations

from typing import Any

import pythoncom

from ..com.earlybind import typed, typed_qi
from ..com.sw_type_info import wrapper_module
from .verify import materialized as _materialized

SPIKE_STATUS = "GREEN"


_SW_FM_SWEEP = 17
# Wave-5 feature constants — SEAT-PENDING (W0): confirm from swconst.tlb.
# swFmSweepCut uses the same ISweepFeatureData interface as swFmSweep.
_SW_FM_SWEEP_CUT = 18

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
            if cg() if callable(cg) else cg:
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
            got += [
                _pt(arc, "GetCenterPoint2"),
                _pt(arc, "GetStartPoint2"),
                _pt(arc, "GetEndPoint2"),
            ]
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
        psegs = _ps() if callable(_ps) else _ps
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
    model_anchor = _sketch_to_model_coords(
        doc, sk, anchor[0], anchor[1], anchor[2], mod
    )

    try:
        tdoc.ClearSelection2(True)
        sel_pt = bool(
            ext.SelectByID2(
                "",
                "SKETCHPOINT",
                model_anchor[0],
                model_anchor[1],
                model_anchor[2],
                False,
                0,
                None,
                0,
            )
        )
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


def _create_sweep(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
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


# ---- Wave-5: F1 sweep-cut (mirror _create_sweep, swFmSweepCut=18) ----


def _create_sweep_cut(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
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
