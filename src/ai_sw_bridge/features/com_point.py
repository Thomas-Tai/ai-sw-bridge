"""Center-of-Mass reference-point handler (W63 lane 3 — ``com_point``).

Inserts a Center-of-Mass reference point via ``IModelDoc2.InsertCenterOfMass``.
No pre-selection required — CoM is auto-computed from the body's mass
properties.

Mode-A status: SKIPPED BY DESIGN
---------------------------------
``InsertCenterOfMass`` is a no-arg legacy method with no ``FeatureData``
interface and no creation enum in ``swFeatureNameID_e``. There is nothing to
probe via ``CreateDefinition`` — the W62 quarantine doctrine applies
asymmetrically here: quarantining requires a candidate enum, but ``com_point``
has none. Only ``_try_mode_b`` is authored.

Mode-B: legacy ``IModelDoc2.InsertCenterOfMass()``
---------------------------------------------------
No-arg call; returns void or Boolean. The callable-or-property guard is
mandatory: win32com late-binding may resolve ``InsertCenterOfMass`` as a
property and auto-invoke on attribute access, so calling ``()`` on the result
raises ``TypeError``.

Verify-the-EFFECT
-----------------
``_count_feature_nodes(doc)`` delta = +1 AND a node whose ``GetTypeName2``
returns ``"CenterOfMass"`` or ``"CenterOfMassFolder"`` materializes.
"""

from __future__ import annotations

import logging
from typing import Any

from ..com.earlybind import EarlyBindError, typed_qi
from ..com.sw_type_info import wrapper_module
from . import verify

logger = logging.getLogger(__name__)

SPIKE_STATUS = "GREEN"

# Verify class (W67): REF_NODE — node count delta + type-name corroboration.
VERIFY_CLASS = verify.FeatureClass.REF_NODE


def _count_feature_nodes(doc: Any) -> int:
    """Flat feature-node count via ``GetFeatures(False)``. Delegates to the W67
    verify substrate (the W62-canonical substrate — not ``GetFeatures(True)``
    or ``GetFeatureCount()``)."""
    return verify.feature_node_count(doc)


def _get_type_name(node: Any) -> str | None:
    """Callable-or-property-guarded ``GetTypeName2`` / ``GetTypeName`` access.
    Delegates to the W67 verify substrate."""
    return verify.type_name(node)


def _find_com_node(doc: Any) -> Any | None:
    """Walk feature nodes looking for a CenterOfMass-typed node.

    W63 round-2 doctrine update (mirrors [[project_w63_bbox_lane]]):
    CHM/UI type names ('CenterOfMass', 'CenterOfMassFolder', 'CoMRefPoint')
    are not authoritative — the v32.1 kernel may return a different
    GetTypeName2 string. Match via case-insensitive substring on
    'centerofmass', 'com', or 'massref' to survive naming drift.
    """
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception as exc:
        logger.warning("[com_point] find_com_node GetFeatures failed: %r", exc)
        return None
    if not feats:
        return None
    for node in feats:
        tname = _get_type_name(node)
        if not tname:
            continue
        lower = tname.lower()
        # 'com' is short but the SW2024 PartCom node uses "com" as a token in
        # several legitimate type names. We accept that and the more specific
        # 'centerofmass' / 'massref' tokens to catch reference-point variants.
        if "centerofmass" in lower or "massref" in lower or "compoint" in lower:
            return node
        # Looser fallback: bare 'com' surrounded by non-alphabetic boundaries
        # (so we don't false-match 'Combine' / 'Comment' / 'CompositeCurve').
        if (
            lower == "com"
            or lower.startswith("com_")
            or lower.endswith("_com")
            or "_com_" in lower
            or lower.startswith("compoint")
            or lower.startswith("comref")
        ):
            return node
    return None


def _try_mode_b(doc: Any) -> tuple[bool, str | None]:
    """Mode-B: ``IFeatureManager.InsertCenterOfMassReferencePoint()`` — no
    selection needed; creates a queryable CoM reference-point IFeature.

    W63 round-2 seat-fire correction: the W63 worker brief named
    ``IModelDoc2.InsertCenterOfMass`` — wrong on both axes. DLL reflection
    (``SolidWorks.Interop.sldworks.dll`` over the v32.1 interop) shows
    the method lives on ``IFeatureManager``, not ``IModelDoc2``; and the
    lane's intent (a queryable IFeature node, lane name ``com_point``)
    matches ``InsertCenterOfMassReferencePoint`` (creates a Reference
    Point), NOT ``InsertCenterOfMass`` (toggles the visual CoM marker —
    a document property, not a feature node).
    """
    logger.warning("[com_point] mode_b: attempting InsertCenterOfMassReferencePoint")
    before = _count_feature_nodes(doc)

    try:
        fm = doc.FeatureManager
    except Exception as exc:
        logger.warning("[com_point] mode_b: FeatureManager access failed: %r", exc)
        return False, f"FeatureManager unavailable: {exc!r}"

    # A3-style reflection probe — log what attrs the live FM proxy actually
    # exposes so we can compare against DLL reflection (the makepy gen_py
    # may be stale; per [[reference_gen_server_version_skew]] the live
    # dispid table can differ from the pinned tlb).
    try:
        logger.warning("[com_point] mode_b A3 probe — type(fm) = %r", type(fm).__name__)
        _fm_all = sorted([a for a in dir(fm) if not a.startswith("_")])
        logger.warning(
            "[com_point] mode_b A3 probe — fm all attrs (%d): %r",
            len(_fm_all),
            _fm_all[:60],
        )
    except Exception as exc:
        logger.warning("[com_point] mode_b A3 probe failed: %r", exc)

    # Late-bound-first / typed-fallback (W52-B lesson from
    # [[project_observe_measure_bbox]]): RAW CDispatch can't dispatch via
    # GetIDsOfNames on every method; the typed early-bound proxy uses
    # InvokeTypes with the pinned tlb's dispid table. We try the typed
    # path FIRST here because the round-3 fire proved bare CDispatch
    # walls with DISP_E_UNKNOWNNAME on both DLL-listed CoM methods.
    fm_typed = None
    try:
        fm_typed = typed_qi(fm, "IFeatureManager", module=wrapper_module())
        logger.warning(
            "[com_point] mode_b typed_qi(IFeatureManager) OK; type=%r",
            type(fm_typed).__name__,
        )
        try:
            _typed_attrs = sorted(
                [
                    a
                    for a in dir(fm_typed)
                    if "insert" in a.lower()
                    and (
                        "com" in a.lower()
                        or "mass" in a.lower()
                        or "center" in a.lower()
                    )
                ]
            )
            logger.warning(
                "[com_point] mode_b typed-fm CoM-related Insert* attrs: %r",
                _typed_attrs,
            )
        except Exception as exc:
            logger.warning("[com_point] mode_b typed-fm dir probe failed: %r", exc)
    except EarlyBindError as exc:
        logger.warning(
            "[com_point] mode_b typed_qi(IFeatureManager) E_NOINTERFACE: %r", exc
        )
    except Exception as exc:
        logger.warning("[com_point] mode_b typed_qi(IFeatureManager) failed: %r", exc)

    # Try-chain across the two DLL-listed IFeatureManager candidates: the
    # primary (creates a queryable ReferencePoint IFeature) and the legacy
    # (toggles the CoM marker — may still produce a node). DLL reflection
    # (SolidWorks.Interop.sldworks.dll v32.1) lists both as 0-arg on
    # IFeatureManager; the live IDispatch may only expose one (or neither).
    _call_attempts = ["InsertCenterOfMassReferencePoint", "InsertCenterOfMass"]
    _errors: list[str] = []
    _called_via: str | None = None
    # Prefer the typed proxy; the bare CDispatch is the fallback.
    _target = fm_typed if fm_typed is not None else fm
    _target_label = "typed-fm" if fm_typed is not None else "raw-fm"
    for _name in _call_attempts:
        try:
            _icom = getattr(_target, _name)
        except AttributeError as exc:
            logger.warning(
                "[com_point] mode_b: %s not on %s typelib (%r)",
                _name,
                _target_label,
                exc,
            )
            _errors.append(f"{_name} not on {_target_label} typelib")
            continue
        try:
            _result = _icom() if callable(_icom) else _icom
            logger.warning(
                "[com_point] mode_b %s via %s returned %r",
                _name,
                _target_label,
                _result,
            )
            _called_via = f"{_name} ({_target_label})"
            break
        except Exception as exc:
            logger.warning(
                "[com_point] mode_b %s via %s raised: %r", _name, _target_label, exc
            )
            _errors.append(f"{_name} via {_target_label} raised: {exc!r}")
            continue

    if _called_via is None:
        return False, (
            "; ".join(_errors) if _errors else "no CoM insertion method dispatched"
        )

    try:
        doc.ForceRebuild3(False)
    except Exception as exc:
        logger.warning("[com_point] mode_b ForceRebuild3 failed: %r", exc)

    after = _count_feature_nodes(doc)
    delta = after - before
    logger.warning(
        "[com_point] mode_b: node count %d -> %d (delta %d)", before, after, delta
    )

    if delta < 1:
        logger.warning("[com_point] mode_b: no feature node added (ghost)")
        return (
            False,
            f"com_point did not add a feature node (count {before} -> {after})",
        )

    # A7-style probe (W63 doctrine — CHM/UI type names are not authoritative,
    # the kernel's own GetTypeName2 is). Log new top-level node identifiers
    # for telemetry and broaden the verifier match accordingly.
    try:
        _all = doc.FeatureManager.GetFeatures(False) or []
        _new_tnames = [_get_type_name(f) for f in _all[before:]]
        logger.warning(
            "[com_point] mode_b A7 probe — new top-level node type names: %r",
            _new_tnames,
        )
    except Exception as exc:
        logger.warning("[com_point] mode_b A7 probe (GetFeatures) raised: %r", exc)

    com_node = _find_com_node(doc)
    if com_node is None:
        logger.warning("[com_point] mode_b: node added but no CoM-typed node found")
        return False, "feature node added but no CenterOfMass-typed node found in tree"

    logger.warning(
        "[com_point] mode_b: CoM node materialized (type=%r)", _get_type_name(com_node)
    )
    return True, "mode_b"


def create_com_point(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Insert a Center-of-Mass reference point on the part.

    ``feature`` spec shape::

        {"kind": "com_point", "name": "CoM-1"}

    ``target`` is unused (CoM is computed from mass properties).

    Returns ``(True, "<mode>")`` on verified materialization, or
    ``(False, "<reason>")`` on any failure — never raises.
    """
    try:
        return _try_mode_b(doc)
    except Exception as exc:
        logger.warning("[com_point] handler unexpected exception: %r", exc)
        return False, f"com_point handler failed: {exc!r}"
