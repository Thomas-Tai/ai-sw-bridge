"""W67 — unified verify substrate for the feature-add HANDLER_REGISTRY.

Before W67, every feature handler hand-copied its own ``_solid_bodies`` /
``_metrics`` / ``_sheet_bodies`` / ``_count_feature_nodes`` / ``_body_bbox``
helpers (28 defs across 13 modules) plus the body-type and FP-epsilon
constants.  A fix to the ``GetBodies2`` + typed-``IPartDoc`` QI fallback, or a
swconst constant drifting in a future SW version, had to be applied in N
places — and the next handler author copied whichever stale variant they
happened to open.  This module is the single source.

**Verify-the-EFFECT taxonomy (the W65/W66 doctrine, now declarable):**
the conserved/measurable witness is feature-class-specific —

    ADDITIVE_SOLID      ΔFaces > 0  ∧  |ΔVol| > eps      (hem)
    FOLD                ΔFaces > 0  ∧  bbox moved         (sketched_bend, jog)
    FOLD_VOL_PRESERVING ΔFaces > 0  ∧  |ΔVol| < eps       (split_line)
    SURFACE_CREATE      ΔSheetBodies ≥ +1 ∧ ΔArea > eps   (planar, offset)
    SURFACE_AGGREGATE   ΔSheetBodies < 0  ∧ area conserved (knit)
    SURFACE_TO_SOLID    ΔVol > eps ∧ ΔSolidBodies ≥ +1    (thicken — DEFERRED OOP)
    CURVE               feature-node delta                (composite/helix/proj)
    REF_NODE            feature-node delta + type-name     (bbox/com_point/materef)
    BODY_MOVE           centroid delta                     (move_copy_body)

A node/Feature return ALONE is never success — that is the W21/W42 ghost trap.

**Behavior-preservation contract (W67 Phase 2):** this is a pure refactor.
The readers reproduce the prior per-handler behavior exactly; in particular
``visible_only`` (the ``GetBodies2`` 2nd arg) is a parameter that each caller
passes with its historical value.  A known inconsistency — the solid lanes
historically passed ``True`` while the surface lanes passed ``False`` — is
preserved here, NOT silently normalized, and is tracked as a W67 Phase-3
finding (a hidden solid body is invisible to the additive gate; the surface
lanes' ``False`` is the safer choice).
"""

from __future__ import annotations

import enum
from typing import Any

from ..com.earlybind import typed
from ..com.sw_type_info import wrapper_module

# --- swconst (SW2024 v32.1.0.123 harvest) ---------------------------------
SW_SOLID_BODY = 0  # swBodyType_e.swSolidBody
SW_SHEET_BODY = 1  # swBodyType_e.swSheetBody

# --- FP-noise thresholds ---------------------------------------------------
# Below VOL_EPS, a volume delta is FP jitter (the hem v5 NO_OP showed ~1e-21
# mm³; the real fold was +1103.84 mm³).  AREA_EPS is the surface analogue.
VOL_EPS_MM3 = 1e-6
AREA_EPS_MM2 = 1e-6
BBOX_EPS_M = 1e-6

# GetFeatures(False) returns a flat node tuple; bound the walk on pathological
# trees (project_curve's historical limit).
FEATURE_TREE_WALK_LIMIT = 500


class FeatureClass(enum.Enum):
    """The verify class a handler declares (its ``VERIFY_CLASS`` attribute).

    Drives which gate witnesses success — see the module docstring taxonomy.
    """

    ADDITIVE_SOLID = "additive_solid"
    FOLD = "fold"
    FOLD_VOL_PRESERVING = "fold_volume_preserving"
    SURFACE_CREATE = "surface_create"
    SURFACE_AGGREGATE = "surface_aggregate"
    SURFACE_TO_SOLID = "surface_to_solid"
    CURVE = "curve"
    REF_NODE = "ref_node"
    BODY_MOVE = "body_move"


# ===========================================================================
# Body accessors
# ===========================================================================
def bodies(doc: Any, body_type: int, visible_only: bool) -> list[Any] | None:
    """Bodies of *doc* of ``body_type``; ``None`` on COM failure, ``[]`` if none.

    Robust to doc flavor: a dynamic dispatch resolves ``GetBodies2`` directly;
    a typed ``IModelDoc2`` proxy does not expose it, so fall back to a typed
    ``IPartDoc`` QI (the hem.py pattern).

    ``visible_only`` is the ``GetBodies2`` ``bVisibleOnly`` arg — passed by the
    caller with its historical value (see the module behavior-preservation
    contract; the solid/sheet drift is intentional-for-now, tracked Phase 3).
    """
    try:
        src = (
            doc if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        result = src.GetBodies2(body_type, visible_only)
    except Exception:
        return None
    if not result:
        return []
    return list(result) if isinstance(result, (list, tuple)) else [result]


def _faces_of(body: Any) -> list[Any]:
    """Faces of a body, with the callable-or-property guard (win32com may
    auto-invoke ``GetFaces`` as a property on attribute access)."""
    f = body.GetFaces
    f = f() if callable(f) else f
    return list(f) if f else []


def solid_metrics(doc: Any, visible_only: bool = True) -> tuple[int, float]:
    """(face_count, volume_mm³) over the doc's solid bodies; (0, 0.0) on failure.

    The substrate for ADDITIVE_SOLID / FOLD* gates.  ``visible_only`` defaults
    to ``True`` to match the historical solid-lane behavior (hem/sketched_bend/
    split_line all called ``GetBodies2(SOLID, True)``).
    """
    bs = bodies(doc, SW_SOLID_BODY, visible_only)
    if not bs:
        return 0, 0.0
    faces = 0
    vol_mm3 = 0.0
    for b in bs:
        try:
            faces += len(_faces_of(b))
        except Exception:
            pass
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                vol_mm3 += float(mp[3]) * 1e9
        except Exception:
            pass
    return faces, vol_mm3


def solid_body_count(doc: Any, visible_only: bool = True) -> int:
    """Count of solid bodies in *doc*; 0 on failure."""
    bs = bodies(doc, SW_SOLID_BODY, visible_only)
    return len(bs) if bs else 0


def solid_volume_mm3(doc: Any, visible_only: bool = True) -> float:
    """Total solid volume (mm³); 0.0 on failure."""
    return solid_metrics(doc, visible_only)[1]


def sheet_bodies(doc: Any, visible_only: bool = False) -> list[Any] | None:
    """Sheet bodies of *doc*; ``None`` on COM failure, ``[]`` if none.

    ``visible_only`` defaults to ``False`` to match the historical surface-lane
    behavior (knit/planar/offset all called ``GetBodies2(SHEET, False)``).
    """
    return bodies(doc, SW_SHEET_BODY, visible_only)


def sheet_body_count(doc: Any, visible_only: bool = False) -> int:
    """Count of sheet bodies in *doc*; 0 on failure/none."""
    bs = sheet_bodies(doc, visible_only)
    return len(bs) if bs else 0


def sheet_area_mm2(doc: Any, visible_only: bool = False) -> float:
    """Sum of face areas over all sheet bodies (mm²); 0.0 on failure.

    AREA is to surfaces what VOLUME is to solids (the W66 doctrine) — the
    anti-ghost witness for SURFACE_CREATE.  SW returns m² per face; ×1e6 → mm².
    """
    bs = sheet_bodies(doc, visible_only)
    if not bs:
        return 0.0
    total = 0.0
    for b in bs:
        try:
            for f in _faces_of(b):
                try:
                    a = f.GetArea
                    a = a() if callable(a) else a
                    total += float(a) * 1e6
                except Exception:
                    pass
        except Exception:
            pass
    return total


# ===========================================================================
# Bounding box (FOLD substrate — a bend is volume-preserving; the EFFECT is a
# bbox change as material rotates out of the original plane)
# ===========================================================================
def body_bbox(doc: Any, visible_only: bool = True) -> tuple[float, ...] | None:
    """Aggregate solid-body bounding box [xmin,ymin,zmin,xmax,ymax,zmax] in
    metres, or ``None`` on failure.  W65 seat finding: InsertSheetMetal3dBend
    returned +8 faces with ΔVol=0 — a real bend the old ΔVol>0 gate falsely
    rejected; the witness is the bbox moving."""
    bs = bodies(doc, SW_SOLID_BODY, visible_only)
    if not bs:
        return None
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    found = False
    for b in bs:
        try:
            box = b.GetBodyBox()
        except Exception:
            continue
        if not box or len(box) < 6:
            continue
        found = True
        for i in range(3):
            lo[i] = min(lo[i], float(box[i]))
            hi[i] = max(hi[i], float(box[i + 3]))
    if not found:
        return None
    return (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])


def bbox_changed(
    before: tuple | None, after: tuple | None, eps_m: float = BBOX_EPS_M
) -> bool:
    """True if the bounding box moved by more than eps in any coordinate."""
    if before is None or after is None or len(before) != 6 or len(after) != 6:
        return False
    return any(abs(a - b) > eps_m for a, b in zip(before, after))


# ===========================================================================
# Feature-tree nodes (CURVE / REF_NODE substrate)
# ===========================================================================
def feature_nodes(doc: Any) -> list[Any]:
    """All feature nodes via ``IFeatureManager.GetFeatures(False)``; ``[]`` on
    failure.  ``GetFeatures(False)`` (NOT ``FirstFeature``, which is unreachable
    on the raw late-bound doc out-of-process — W62) returns a flat tuple."""
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return []
    if not feats:
        return []
    return list(feats)


def feature_node_count(doc: Any) -> int:
    """Flat feature-node count via ``GetFeatures(False)``; 0 on failure."""
    return len(feature_nodes(doc))


def type_name(node: Any) -> str | None:
    """Callable-or-property-guarded ``GetTypeName2`` / ``GetTypeName`` access;
    ``None`` if neither resolves.  win32com IDispatch may resolve ``GetTypeName*``
    as a property and auto-invoke it on attribute access."""
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            v = getattr(node, attr)
            return str(v() if callable(v) else v)
        except Exception:
            continue
    return None


def count_nodes_by_type(
    doc: Any,
    tokens: tuple[str, ...],
    *,
    match: str = "substring",
    limit: int | None = None,
) -> int:
    """Count feature-tree nodes whose type-name matches *tokens*.

    ``match="exact"``     — node type-name is in *tokens* verbatim (helix → "Helix").
    ``match="substring"`` — a (lowercased) token is a substring of the (lowercased)
                            type-name (project_curve → ref-curve token family).
    ``limit`` bounds the walk (project_curve historically capped at 500).
    """
    nodes = feature_nodes(doc)
    if limit is not None:
        nodes = nodes[:limit]
    count = 0
    for n in nodes:
        tname = type_name(n)
        if not tname:
            continue
        if match == "exact":
            if tname in tokens:
                count += 1
        else:
            low = tname.lower()
            if any(tok in low for tok in tokens):
                count += 1
    return count


# ===========================================================================
# Centroid (BODY_MOVE substrate)
# ===========================================================================
def body_centroid_m(doc: Any) -> tuple[float, float, float] | None:
    """Part-level centre of mass (metres) via ``Extension.CreateMassProperty``;
    ``None`` on failure."""
    try:
        ext = doc.Extension
        mp = ext.CreateMassProperty()
        if mp is None:
            return None
        cog = mp.CenterOfMass
        if cog is None:
            return None
        if callable(cog):
            cog = cog()
        if cog is None:
            return None
        c = list(cog) if isinstance(cog, (tuple, list)) else [cog]
        if len(c) < 3:
            return None
        return (float(c[0]), float(c[1]), float(c[2]))
    except Exception:
        return None


# ===========================================================================
# Class gates — each reproduces the historical per-handler acceptance
# expression verbatim (thresholds unchanged; W67 Phase-2 contract).
# ===========================================================================
def gate_additive_solid(d_faces: int, d_vol_mm3: float) -> bool:
    """ADDITIVE_SOLID (hem): new faces AND a non-trivial volume change."""
    return d_faces > 0 and abs(d_vol_mm3) > VOL_EPS_MM3


def gate_fold(
    d_faces: int, bbox_before: tuple | None, bbox_after: tuple | None
) -> bool:
    """FOLD (sketched_bend/jog): new faces AND the bounding box moved
    (volume-preserving bend)."""
    return d_faces > 0 and bbox_changed(bbox_before, bbox_after)


def gate_fold_volume_preserving(d_faces: int, d_vol_mm3: float) -> bool:
    """FOLD_VOL_PRESERVING (split_line): new faces AND volume conserved."""
    return d_faces > 0 and abs(d_vol_mm3) < VOL_EPS_MM3


def gate_surface_create(d_sheet_count: int, d_area_mm2: float) -> bool:
    """SURFACE_CREATE (planar/offset): a new sheet body AND real area."""
    return d_sheet_count >= 1 and d_area_mm2 > AREA_EPS_MM2


def gate_surface_aggregate(d_sheets: int, area_after_mm2: float) -> bool:
    """SURFACE_AGGREGATE (knit, sheet→sheet): sheet-body count DECREASED
    (N→fewer) AND area survives (INVERTED gate — a ≥1-new-body test false-fails
    aggregation)."""
    return d_sheets < 0 and area_after_mm2 > AREA_EPS_MM2


def gate_surface_to_solid(d_vol_mm3: float, d_solids: int) -> bool:
    """SURFACE_TO_SOLID (thicken / knit→solid): volume appeared AND a solid
    body materialized.  WALLED OOP for thicken — see docs/DEFERRED.md."""
    return d_vol_mm3 > VOL_EPS_MM3 and d_solids >= 1
