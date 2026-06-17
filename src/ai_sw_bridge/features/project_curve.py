"""W62 — ``project_curve`` feature-add handler (registry seam, boss fight).

Projects a sketch curve onto a solid-body face (sketch-on-face projection)
or intersects two sketches to produce a 3D reference curve.  The creation
entry point is **UNKNOWN** — reflection found no dedicated project-curve
FeatureData interface and no ``InsertProjectCurve*`` method on any of
``IModelDoc2``, ``IModelDocExtension``, or ``IFeatureManager``.

METHOD DISCOVERY (authored offline; the seat spike exhausts every probe)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Interfaces probed at author time by reflecting the SW2024 v32 typelib:

  ``IModelDoc2`` / ``IModelDocExtension`` Insert* with "Project" token:
    InsertSplitLineProject(bool, bool)  — split-line projection, NOT curve
    (no InsertProjectCurve / InsertProjectedCurve found on either iface)

  ``IFeatureManager`` Insert* / Create* with "Project" / "Curve" tokens:
    InsertCompositeCurve()              — composite of edges, NOT projection
    InsertSplitLineProject(bool, bool)  — split-line, NOT curve projection
    CreateDefinition(int)               — generic factory (Mode-A entry)
    (no InsertProjectCurve / InsertProjectedCurve / InsertRefCurve found)

  FeatureData interfaces (QI targets for CreateDefinition return):
    IReferenceCurveFeatureData          — candidate if swFmRefCurve yields it
    IProjectedCurveFeatureData          — hypothetical (DLL probe needed)
    IRefCurveFeatureData                — alternate spelling candidate
    ICompositeCurveFeatureData          — composite, NOT projection

  swFeatureNameID_e values of interest:
    swFmRefCurve = 14                   — generic ref-curve factory
    swFmReferenceCurve = 61             — alternate ref-curve ID
    (no swFmProjectedCurve in the enum dump)

  Convert-on-face fallback (W60 convert recipe):
    SketchManager.SketchUseEdge3(bool, bool, double) — project/convert
    selected model edges or sketch entities into the active sketch

**Verdict:** NO dedicated project-curve creator surfaced.  Both Mode-A
(``CreateDefinition`` → QI ref-curve data) and Mode-B (Insert* probe +
convert-on-face fallback) candidates are authored below for the seat to
exhaust.  The handler returns ``(False, reason)`` when neither fires;
declaring WALLED is W0's call after the seat proves both modes.

HANDLER STRATEGY (dual-mode doctrine)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Mode-A  CreateDefinition(swFmRefCurve=14)
        → typed_qi(data, <ref-curve ifaces>)
        → set projection inputs via AccessSelections
        → CreateFeature(data)
        → fails by E_NOINTERFACE on QI or CreateDefinition returning None

Mode-B  (a) dynamic-dispatch probe for Insert* methods with "Project"
        (b) convert-on-face fallback:
            open a sketch on the target face
            select the source sketch entities
            SketchUseEdge3 to project them into the face sketch
            close the sketch
        → fails by method-not-found + convert silent no-op

Verify: new reference-curve feature node via FirstFeature walk
        (type name contains "RefCurve" or "ProjectedCurve"), no ΔVol.
"""

from __future__ import annotations

from typing import Any

from ..com.earlybind import typed_qi

# Flipped to "GREEN" by W0 after the seat spike fires and a mode produces
# a reference-curve node surviving save→reopen.  While "UNRUN", the
# handler exists but is NOT registered in HANDLER_REGISTRY.
SPIKE_STATUS = "UNRUN"

_SW_FM_REF_CURVE = 14

_REF_CURVE_QI_IFACES = (
    "IReferenceCurveFeatureData",
    "IProjectedCurveFeatureData",
    "IRefCurveFeatureData",
)

_FEATURE_TREE_WALK_LIMIT = 500

_NODE_TYPE_TOKENS = ("refcurve", "projectedcurve", "ref_curve")


def _count_feature_nodes(doc: Any) -> int:
    """Count feature-tree nodes whose type matches a ref-curve token.

    Walks ``FirstFeature()`` → ``GetNextFeature()`` (re-typing each node
    per step — the W59 thread-annotation lesson).  Returns the count of
    nodes whose ``GetTypeName2()`` matches a ref-curve token.
    """
    count = 0
    try:
        feat = doc.FirstFeature()
    except Exception:
        return 0
    seen = 0
    while feat is not None and seen < _FEATURE_TREE_WALK_LIMIT:
        seen += 1
        try:
            tname = str(feat.GetTypeName2() or "").lower()
            if any(tok in tname for tok in _NODE_TYPE_TOKENS):
                count += 1
        except Exception:
            pass
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    return count


def _qi_ref_curve(data: Any) -> Any | None:
    """QI *data* for a ref-curve / projection FeatureData iface.

    Returns the first successfully QI'd typed wrapper, or ``None`` if
    every probe raises (E_NOINTERFACE / EarlyBindError / other).
    """
    for iface in _REF_CURVE_QI_IFACES:
        try:
            return typed_qi(data, iface)
        except Exception:
            continue
    return None


def _try_mode_a(doc: Any, feature: dict) -> Any | None:
    """Mode-A: CreateDefinition(swFmRefCurve=14) → QI → CreateFeature.

    Returns the created feature node on success, ``None`` on any failure
    (CreateDefinition None, QI E_NOINTERFACE, CreateFeature None/0).
    """
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_REF_CURVE)
    except Exception:
        return None
    if data is None:
        return None
    _qi_ref_curve(data)
    try:
        feat = fm.CreateFeature(data)
    except Exception:
        return None
    if feat and not isinstance(feat, int):
        return feat
    if isinstance(feat, int) and feat != 0:
        return feat
    return None


def _try_mode_b_insert(doc: Any, feature: dict) -> Any | None:
    """Mode-B(a): probe Insert* methods with "Project" on doc and FM.

    Returns the created feature (truthy) on success, ``None`` when no
    candidate method exists or every call fails.
    """
    candidates = (
        "InsertProjectCurve",
        "InsertProjectedCurve",
        "InsertRefCurve",
    )
    for name in candidates:
        for obj in (doc, getattr(doc, "FeatureManager", None)):
            if obj is None:
                continue
            fn = getattr(obj, name, None)
            if fn is None or not callable(fn):
                continue
            try:
                result = fn()
                if result:
                    return result
            except Exception:
                continue
    return None


def _try_mode_b_convert(doc: Any, feature: dict) -> bool:
    """Mode-B(b): convert-on-face fallback (W60 convert recipe).

    Opens a sketch on the target face, selects the source sketch, and
    calls ``SketchUseEdge3`` to project the source entities into the
    face sketch.  Returns ``True`` if the convert pipeline ran without
    error (the verify gate decides final success).
    """
    sketch_name = feature.get("sketch_name")
    if not sketch_name:
        return False
    try:
        source_feat = doc.FeatureByName(sketch_name)
        if source_feat is None:
            return False
        doc.ClearSelection2(True)
        source_feat.Select2(False, 0)

        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.SketchUseEdge3(False, False, 0.0)
        doc.SketchManager.InsertSketch(True)
        doc.ClearSelection2(True)
        doc.ForceRebuild3(False)
    except Exception:
        return False
    return True


def create_project_curve(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Project a sketch curve onto a face → 3D reference curve. Fail-closed.

    ``feature`` keys
        sketch_name : str  — name of the source sketch to project
            (e.g. ``"Sketch2"`` from ``fx.seed_line_over_top``)

    ``target`` keys
        face : Any  — a live ``IFace2`` entity for the projection target
            (from ``fx.seed_line_over_top`` or an observe call)
    """
    if SPIKE_STATUS != "GREEN":
        return False, (
            "project_curve: SEAT-PENDING — both Mode-A "
            "(CreateDefinition(swFmRefCurve=14) → QI ref-curve data) and "
            "Mode-B (Insert* probe + convert-on-face fallback) are awaiting "
            "live-seat proof (spike_project_curve)"
        )

    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    sketch_name = feature.get("sketch_name")
    if not sketch_name or not isinstance(sketch_name, str):
        return False, "feature must include a non-empty 'sketch_name' string"

    count_before = _count_feature_nodes(doc)

    feat, mode = _try_mode_a(doc, feature), "A"
    if feat is None:
        feat = _try_mode_b_insert(doc, feature)
        mode = "B"
    if feat is None:
        converted = _try_mode_b_convert(doc, feature)
        mode = "B-convert" if converted else "none"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    count_after = _count_feature_nodes(doc)
    d_nodes = count_after - count_before

    if d_nodes > 0:
        return True, f"project_curve created via mode-{mode} (+{d_nodes} node)"

    if mode == "none":
        return False, (
            "project_curve: both Mode-A (CreateDefinition/QI) and Mode-B "
            "(Insert* probe + convert-on-face fallback) failed — "
            "no ref-curve feature node materialized"
        )
    return False, (
        f"project_curve: mode-{mode} ran but no ref-curve feature node "
        f"materialized (delta_nodes={d_nodes})"
    )


# ---------------------------------------------------------------------------
# Gated self-registration (W0 flips SPIKE_STATUS + adds import in __init__)
# ---------------------------------------------------------------------------

if SPIKE_STATUS == "GREEN":
    from . import HANDLER_REGISTRY

    HANDLER_REGISTRY["project_curve"] = create_project_curve
