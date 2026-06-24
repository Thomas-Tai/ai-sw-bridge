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
    VOLUME_TRANSFORM    volume ratio == commanded f**3     (scale)
    BOOLEAN_INTERSECT   Sculpt node ∧ topology changed     (intersect)

A node/Feature return ALONE is never success — that is the W21/W42 ghost trap.

**W67 Phase-3 normalization:** every body reader now defaults to
``visible_only=False`` (count ALL bodies).  This resolves the Phase-2 drift
(solid lanes historically passed ``True``, surface lanes ``False``): a hidden
but created body is a real effect, so the ``True`` lanes carried a latent
false-negative.  ``visible_only`` remains a parameter (a future caller may
genuinely want visible-only), but the default and every in-tree shim now use
``False``.  See docs/w67_verify_substrate.md §1.
"""

from __future__ import annotations

import enum
import math
from typing import Any

from ..com.earlybind import typed, typed_qi
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
# A reference curve below this arc length is a ghost (W42 trap), not a curve.
CURVE_LEN_EPS_MM = 1e-6

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
    VOLUME_TRANSFORM = "volume_transform"
    BOOLEAN_INTERSECT = "boolean_intersect"


# ===========================================================================
# Feature materialization helpers (relocated from mutate.py, Recipe-C W21)
# ===========================================================================
def materialized(feat: Any) -> bool:
    """True if a CreateFeature return value represents a materialized feature."""
    return feat is not None and not isinstance(feat, int)


def find_feature_by_name(doc: Any, name: str) -> Any:
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


# ===========================================================================
# Body accessors
# ===========================================================================
def bodies(doc: Any, body_type: int, visible_only: bool) -> list[Any] | None:
    """Bodies of *doc* of ``body_type``; ``None`` on COM failure, ``[]`` if none.

    Robust to doc flavor: a dynamic dispatch resolves ``GetBodies2`` directly;
    a typed ``IModelDoc2`` proxy does not expose it, so fall back to a typed
    ``IPartDoc`` QI (the hem.py pattern).

    ``visible_only`` is the ``GetBodies2`` ``bVisibleOnly`` arg.  Every in-tree
    caller passes ``False`` (W67 Phase-3 normalization — count all bodies).
    """
    try:
        src = (
            doc
            if hasattr(doc, "GetBodies2")
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


def solid_metrics(doc: Any, visible_only: bool = False) -> tuple[int, float]:
    """(face_count, volume_mm³) over the doc's solid bodies; (0, 0.0) on failure.

    The substrate for ADDITIVE_SOLID / FOLD* gates.  ``visible_only`` defaults
    to ``False`` — W67 Phase 3 normalized every reader to count ALL bodies
    (a hidden/created body is a real effect; ``True`` was a latent false-
    negative — see docs/w67_verify_substrate.md §1).
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


def solid_body_count(doc: Any, visible_only: bool = False) -> int:
    """Count of solid bodies in *doc*; 0 on failure. ``visible_only`` defaults
    to ``False`` (W67 Phase-3 normalization — count all bodies)."""
    bs = bodies(doc, SW_SOLID_BODY, visible_only)
    return len(bs) if bs else 0


def solid_volume_mm3(doc: Any, visible_only: bool = False) -> float:
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
def body_bbox(doc: Any, visible_only: bool = False) -> tuple[float, ...] | None:
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


def newest_node_by_type(
    doc: Any,
    tokens: tuple[str, ...],
    *,
    match: str = "substring",
    limit: int | None = None,
) -> Any | None:
    """The LAST (most-recently-created) feature node whose type-name matches
    *tokens*, or ``None``.  Same matching semantics as ``count_nodes_by_type`` —
    used to locate the node a curve handler just created so its arc length can
    be measured for the CURVE gate."""
    nodes = feature_nodes(doc)
    if limit is not None:
        nodes = nodes[:limit]
    found = None
    for n in nodes:
        tname = type_name(n)
        if not tname:
            continue
        if match == "exact":
            if tname in tokens:
                found = n
        else:
            low = tname.lower()
            if any(tok in low for tok in tokens):
                found = n
    return found


# ===========================================================================
# CURVE geometric witness (W67 P3b) — arc length as the anti-ghost scalar
#
# The CURVE lanes (composite/helix/project_curve) historically gated on a
# feature-node COUNT delta alone — the W42 ghost trap (a node can materialize
# with no real geometry).  The geometric witness is total arc length: a real
# reference curve has positive length; a ghost node has none.
#
# TAIL (PROVEN OOP — brep/interrogator.py:_read_curve_mid_and_arc, seat-
# confirmed SW2024 SP1 rev 32.1): ICurve.GetEndParams() → (status, tmin, tmax,
# …); ICurve.GetLength(tmin, tmax) → metres.  Late-bound proxies cannot
# dispatch these ("Member not found") — typed_qi(…, "ICurve") is required;
# direct dispatch is the mock/late-bound fallback.
#
# HEAD (SEAT-PROVEN — W67 P3b, spike_curve_length_witness HEAD_PROVEN): a node
# from GetFeatures(False) is a late-bound proxy whose GetSpecificFeature2 trips
# 'Member not found' OOP; the typed IFeature compiled dispid clears it.  The
# specific feature is IReferenceCurve, whose GetSegments() returns the curve's
# EDGES — so the proven EDGE→ICurve tail applies.  Confirmed on the live seat,
# deterministic on the absolute-cold first call: helix 80.0 mm, composite
# 70.0 mm.  LIFETIME: an ICurve is invalidated when its parent edge is released
# — _node_curves returns the typed edges in a keepalive list the caller holds
# during measurement (dropping them yields null; this was the W67 P3b bug, NOT
# the cold-gen theory it was first mistaken for).  WIRED (W67 P3b unification)
# into all three CURVE handlers — composite/helix/project_curve now gate on
# gate_curve(d_nodes, curve_length_mm(new_node)); node-presence alone is no
# longer success.
# ===========================================================================
def _call0(obj: Any, name: str) -> Any:
    """Callable-or-property-guarded 0-arg accessor; ``None`` on any failure."""
    try:
        attr = getattr(obj, name)
        return attr() if callable(attr) else attr
    except Exception:
        return None


def _as_list(v: Any) -> list[Any]:
    """Normalize a COM return (scalar / tuple / list / None) to a list."""
    if not v:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def icurve_length_mm(raw_curve: Any) -> float | None:
    """Arc length (mm) of a single ``ICurve``; ``None`` if unreadable.

    The PROVEN tail (brep/interrogator.py): ``typed_qi(…, "ICurve")`` →
    ``GetEndParams()`` (idx 1,2 = tmin,tmax) → ``GetLength(tmin, tmax)`` in
    metres.  Direct dispatch is the late-bound / mock fallback when typed_qi
    cannot QI (e.g. an offline fake).
    """
    if raw_curve is None:
        return None
    try:
        curve = typed_qi(raw_curve, "ICurve")
    except Exception:
        curve = raw_curve  # late-bound / mock fallback
    ep = _call0(curve, "GetEndParams")
    if not (isinstance(ep, (tuple, list)) and len(ep) >= 3):
        return None
    try:
        tmin, tmax = float(ep[1]), float(ep[2])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(tmin) and math.isfinite(tmax) and tmax > tmin):
        return None
    try:
        gl = float(curve.GetLength(tmin, tmax))
    except Exception:
        return None
    if math.isfinite(gl) and gl >= 0.0:
        return gl * 1000.0  # metres → mm
    return None


def _retype(obj: Any, iface: str) -> Any:
    """Best-effort early-bind cast to *iface*; the raw object on failure
    (offline fakes / late-bound surfaces where the cast is unavailable)."""
    try:
        return typed(obj, iface, module=wrapper_module())
    except Exception:
        return obj


def _node_curves(node: Any) -> tuple[list[Any], list[Any]]:
    """``IFeature`` node → (curves, keepalive) for a standalone reference curve.

    Seat-corrected (W67 P3b): a node from ``GetFeatures(False)`` is a late-bound
    IDispatch proxy whose ``GetSpecificFeature2`` trips ``'Member not found'``
    (-2147352573) OOP — the typed ``IFeature`` compiled dispid clears it (the
    same re-type idiom as spikes/v0_16/_seatcheck_sketch_fidelity_pae.py).  The
    specific feature is ``IReferenceCurve`` whose ``GetSegments()`` returns the
    curve's **edges**, so the proven EDGE→ICurve tail applies:

        typed(node,"IFeature").GetSpecificFeature2()
          → typed(spec,"IReferenceCurve").GetSegments()  # edges
          → typed_qi(edge,"IEdge").GetCurve()            # ICurve

    LIFETIME (seat-proven W67 P3b): an ``ICurve`` from ``IEdge.GetCurve()`` is
    invalidated once its parent edge is released — so the typed edges are
    returned in a parallel ``keepalive`` list the caller MUST hold alive while
    measuring the curves (returning curves alone silently yields null lengths).

    Fallbacks: a projected curve realized as a sketch (``ISketch`` →
    ``GetSketchSegments`` → ``segment.GetCurve()``); and a defensive direct
    ``GetCurves``.  Every hop is fail-soft.
    """
    feat = _retype(node, "IFeature")
    spec = _call0(feat, "GetSpecificFeature2")
    if spec is None:
        return [], []
    curves: list[Any] = []
    keepalive: list[Any] = []
    # PRIMARY: IReferenceCurve.GetSegments() → edges → IEdge.GetCurve() → ICurve.
    rc = _retype(spec, "IReferenceCurve")
    for seg in _as_list(_call0(rc, "GetSegments")):
        try:
            te = typed_qi(seg, "IEdge", module=wrapper_module())
        except Exception:
            te = seg
        c = _call0(te, "GetCurve")
        if c is not None:
            curves.append(c)
            keepalive.append(te)  # pin the edge — the curve depends on it
    # FALLBACK: projected sketch → segments → GetCurve.
    if not curves:
        sk = _retype(spec, "ISketch")
        for seg in _as_list(_call0(sk, "GetSketchSegments")):
            c = _call0(seg, "GetCurve")
            if c is not None:
                curves.append(c)
                keepalive.append(seg)
    # LAST-DITCH: spec exposes curves directly (defensive).
    if not curves:
        for c in _as_list(_call0(spec, "GetCurves")):
            curves.append(c)
            keepalive.append(spec)
    return curves, keepalive


def curve_length_mm(node: Any) -> float | None:
    """Total arc length (mm) of the reference curve(s) a CURVE feature node
    owns, or ``None`` if no curve geometry is readable OOP.

    Proven head + tail (W67 P3b, seat-confirmed HEAD_PROVEN, deterministic on
    the absolute-cold first call — helix 80.0 mm, composite 70.0 mm):
    ``typed(IFeature)`` → ``GetSpecificFeature2`` →
    ``typed(IReferenceCurve).GetSegments`` (edges) → ``typed_qi(IEdge).GetCurve``
    → ``ICurve.GetLength``.

    The ``_keepalive`` list returned by ``_node_curves`` MUST stay referenced
    across the measurement loop: an ``ICurve`` is invalidated the moment its
    parent edge is released, so dropping the edges silently yields null lengths
    (the W67 P3b bug — an earlier ``cold makepy gen`` theory was a red herring;
    the real cause was COM object lifetime).

    Fail-soft and UNWIRED: no handler gate calls this until the W67 P3b wiring
    commit (never wired an unproven scalar into a GREEN lane's gate).
    """
    if node is None:
        return None
    curves, _keepalive = _node_curves(node)
    total = 0.0
    found = False
    for curve in curves:
        length = icurve_length_mm(curve)
        if length is not None:
            total += length
            found = True
    # _keepalive stays referenced until here — releasing the parent edges would
    # invalidate the ICurve objects mid-measurement.
    return total if found else None


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


def gate_volume_transform(
    vol_before_mm3: float,
    vol_after_mm3: float,
    expected_ratio: float,
    rel_tol: float = 1e-3,
) -> bool:
    """VOLUME_TRANSFORM (scale): the solid volume changed by the COMMANDED
    closed-form ratio.

    For a uniform scale by factor ``f``, volume scales by ``f**3`` exactly
    (the W71 seat finding: a 1.5× cube went 1000→3375 mm³, ratio 3.375 to
    IEEE-754 precision).  Gating on the ratio — not merely ``|ΔVol| > eps`` —
    is the anti-ghost witness: a silent no-op leaves ``ratio == 1.0`` and is
    rejected, and a WRONG scale (e.g. the legacy void ``InsertScale`` form
    that ignores the Feature return) fails the ratio even though volume moved.
    Both volumes must be physically present (a vanished body fails closed).
    """
    if vol_before_mm3 <= VOL_EPS_MM3 or vol_after_mm3 <= VOL_EPS_MM3:
        return False
    if expected_ratio <= 0.0:
        return False
    ratio = vol_after_mm3 / vol_before_mm3
    return abs(ratio - expected_ratio) <= rel_tol * expected_ratio


def gate_boolean_intersect(
    node_materialized: bool, d_solid_count: int, d_vol_mm3: float
) -> bool:
    """BOOLEAN_INTERSECT (intersect): a real Sculpt feature node materialized
    AND the solid topology actually changed.

    The Intersect feature splits/merges overlapping bodies (and surfaces/planes)
    into their mutual regions via the two-phase ``PreIntersect2`` → ``PostIntersect``
    contract (the W-post-GA boundary-law refinement: the kernel hands the region
    list back to the caller, so it materializes OOP unlike single-call
    combine/split).  ``node_materialized`` (a new ``Sculpt`` node appeared) alone
    is the W21/W42 ghost trap; the anti-ghost witness is a topology change —
    either the solid-body **count** moved (regions kept separate, or merged) OR
    the total solid **volume** moved (overlapping double-counted bodies resolve
    to true disjoint volume; for the canonical 2-box fixture Δvol = −overlap).
    A silent no-op leaves both unchanged and fails closed.
    """
    return node_materialized and (d_solid_count != 0 or abs(d_vol_mm3) > VOL_EPS_MM3)


def gate_curve(d_nodes: int, total_len_mm: float | None) -> bool:
    """CURVE (composite/helix/project_curve): a new curve feature node AND the
    curve carries real arc length (the anti-ghost geometric witness).

    HARD gate — ``total_len_mm is None`` (length unreadable OOP) is treated as
    FAILURE, never as a fall-back to node-count (W67 P3b adjudication: a gate
    that silently degrades to a weaker check is a ghost trap with extra steps).

    SEAT-PENDING: NOT wired into composite/helix/project_curve until
    spike_curve_length_witness proves the IFeature → ICurve head hop on the live
    seat.  The production lanes keep their node-count gate until then.
    """
    if total_len_mm is None:
        return False
    return d_nodes > 0 and total_len_mm > CURVE_LEN_EPS_MM
