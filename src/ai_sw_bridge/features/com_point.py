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

logger = logging.getLogger(__name__)

SPIKE_STATUS = "UNFIRED"


def _count_feature_nodes(doc: Any) -> int:
    """Flat feature-node count via ``GetFeatures(False)`` (W62 substrate).

    ``GetFeatures(False)`` returns individual nodes (not folders); this is the
    W62-canonical verify substrate — do NOT substitute ``GetFeatures(True)``
    or ``GetFeatureCount()``.
    """
    try:
        feats = doc.FeatureManager.GetFeatures(False)
        return len(feats) if feats else 0
    except Exception as exc:
        logger.warning("[com_point] count_feature_nodes failed: %r", exc)
        return 0


def _get_type_name(node: Any) -> str | None:
    """Callable-or-property-guarded ``GetTypeName2`` access."""
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(node, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _find_com_node(doc: Any) -> Any | None:
    """Walk feature nodes looking for a CenterOfMass-typed node."""
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception as exc:
        logger.warning("[com_point] find_com_node GetFeatures failed: %r", exc)
        return None
    if not feats:
        return None
    for node in feats:
        tname = _get_type_name(node)
        if tname in ("CenterOfMass", "CenterOfMassFolder"):
            return node
    return None


def _try_mode_b(doc: Any) -> tuple[bool, str | None]:
    """Mode-B: ``IModelDoc2.InsertCenterOfMass()`` — no selection needed."""
    logger.warning("[com_point] mode_b: attempting InsertCenterOfMass")
    before = _count_feature_nodes(doc)

    try:
        _icom = getattr(doc, "InsertCenterOfMass")
        _result = _icom() if callable(_icom) else _icom
    except Exception as exc:
        logger.warning("[com_point] mode_b InsertCenterOfMass raised: %r", exc)
        return False, f"InsertCenterOfMass raised: {exc!r}"

    try:
        doc.ForceRebuild3(False)
    except Exception as exc:
        logger.warning("[com_point] mode_b ForceRebuild3 failed: %r", exc)

    after = _count_feature_nodes(doc)
    delta = after - before
    logger.warning("[com_point] mode_b: node count %d -> %d (delta %d)", before, after, delta)

    if delta < 1:
        logger.warning("[com_point] mode_b: no feature node added (ghost)")
        return False, f"com_point did not add a feature node (count {before} -> {after})"

    com_node = _find_com_node(doc)
    if com_node is None:
        logger.warning("[com_point] mode_b: node added but no CenterOfMass-typed node found")
        return False, "feature node added but no CenterOfMass/CenterOfMassFolder node found"

    logger.warning("[com_point] mode_b: CenterOfMass node materialized")
    return True, "mode_b"


def create_com_point(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
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
