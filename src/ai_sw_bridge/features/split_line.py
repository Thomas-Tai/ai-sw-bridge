"""W62 — ``split_line`` feature-add handler (registry seam).

Projects a sketch onto a solid-body face, splitting the face topologically
without removing material.

  **Mode-A (QUARANTINED — documented unreachable for CREATION)**: the SW2024
  swconst harvest (DLL reflection 2026-06-17) exposes NO swFeatureNameID
  for split-line — same class as composite (W62 2a04542) and helix
  (W62 057789a). The worker probe id=65 (``swFmReferenceCurve``) returned
  None from CreateDefinition on the live seat. ``ISplitLineFeatureData``
  is in the typelib but is edit-only via ``IFeature.GetDefinition()`` on
  an existing split-line node; no creation route exists. Mode-A is a
  no-op stub. Historical CreateDefinition+ISetSplitTools+ISetFaces+
  CreateFeature wiring can be reconstructed from git history if a future
  SW version exposes a creation enum.

  **Mode-B (legacy, operative path)**: select sketch + face (mark=0 for
  both — macro-recorder default), then ``doc.InsertSplitLineProject(
  Reverse:bool, SingleDirection:bool)`` (2-arg method, void return).
  Verify-the-EFFECT must drive (the call never raises and never returns a
  truthy success — only ΔFace>0 ∧ ΔVol==0 proves a split happened).

Verify-the-EFFECT (DIFFERENT from hem): success = ΔFace > 0 AND ΔVol == 0.
A split line adds topological faces (the projected curve partitions the
target face) but does NOT change solid volume.  A volume delta means
something else happened (a cut or boss); no face delta means the split
was a silent no-op (the W21/W42 ghost trap).
"""

from __future__ import annotations

import logging
from typing import Any

import pythoncom
from win32com.client import VARIANT

from ..com.earlybind import EarlyBindError, typed_qi  # noqa: F401 — module surface; test_split_line patches sl.typed_qi (historical Mode-A fixture)
from ..selection.live import select_entity
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.split_line")

# Flipped to "GREEN" by W0 after the spike fires on the live seat and
# one of the two modes is proven generative.
SPIKE_STATUS = "UNRUN"

# Verify class (W67): volume-preserving fold — a split adds faces (the
# projected curve partitions the target face) but conserves solid volume.
VERIFY_CLASS = verify.FeatureClass.FOLD_VOL_PRESERVING

# swSplitLineType_e — projection is the lead variant.
_SPLIT_TYPES: dict[str, int] = {"projection": 0, "silhouette": 1}

# PropertyManager selection marks for split-line "Sketch to project" and
# "Faces to split" list boxes. The macro-recorder default is mark=0 for
# both (SW infers list-box routing from entity type); some sources
# document mark=1/2 differentiation. The handler tries mark=0/0 first
# (recorder-default) — the first seat fire 2026-06-17 showed marks=1/2
# accepted the selection but the macro returned no-op.
_MARK_SKETCH = 0
_MARK_FACE = 0


def _metrics(doc: Any) -> tuple[int, float]:
    """(face_count, volume_mm³) over solid bodies. Delegates to the W67 verify
    substrate (``visible_only=False`` — Phase-3 normalized to count all bodies)."""
    return verify.solid_metrics(doc)


def create_split_line(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Project a sketch onto a face, splitting it. Fail-closed, dual-mode.

    Tries Mode-A (CreateDefinition → ISplitLineFeatureData → CreateFeature)
    first; on E_NOINTERFACE / None / silent-drop falls back to Mode-B
    (InsertSplitLineProject) in the same call.

    ``feature`` keys
        reverse         : bool  — reverse projection direction (default False)
        single_direction : bool  — single-direction projection (default False)
        split_type      : str|int — "projection" (default) | "silhouette"

    ``target`` keys
        sketch_name  : str  — name of the sketch to project (e.g. "Sketch2")
        face_entity  : Any  — the live COM face entity (IFace2) to split
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    sketch_name = target.get("sketch_name")
    if not sketch_name:
        return False, "target must include 'sketch_name'"
    face_entity = target.get("face_entity")
    if face_entity is None:
        return False, "target must include 'face_entity'"

    reverse = bool(feature.get("reverse", False))
    single_direction = bool(feature.get("single_direction", False))
    split_type_val = feature.get("split_type", "projection")
    if isinstance(split_type_val, str):
        st = _SPLIT_TYPES.get(split_type_val.strip().lower())
        if st is None:
            return False, (
                f"split_type {split_type_val!r} not one of {sorted(_SPLIT_TYPES)}"
            )
    elif isinstance(split_type_val, int):
        st = split_type_val
    else:
        return False, f"split_type must be str or int, got {type(split_type_val).__name__}"

    faces_before, vol_before = _metrics(doc)
    if faces_before == 0:
        return False, "document has no solid bodies"

    feat = _try_mode_a(doc, sketch_name, face_entity, st)
    mode = "A"
    if feat is None:
        feat = _try_mode_b(doc, sketch_name, face_entity, reverse, single_direction)
        mode = "B"
    if feat is None:
        return False, (
            "split_line failed: both Mode-A (CreateDefinition/QI) and "
            "Mode-B (InsertSplitLineProject) produced no feature"
        )

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    faces_after, vol_after = _metrics(doc)
    d_faces = faces_after - faces_before
    d_vol = vol_after - vol_before
    if verify.gate_fold_volume_preserving(d_faces, d_vol):
        return True, f"split_line projected ({d_faces} new faces, mode-{mode})"

    return False, (
        f"split_line did not split topologically "
        f"(delta_face={d_faces}, delta_vol_mm3={d_vol:.6f}); "
        f"mode-{mode} returned but verify-the-effect failed"
    )


def _try_mode_a(
    doc: Any, sketch_name: str, face_entity: Any, split_type: int,
) -> Any | None:
    """Mode-A: QUARANTINED — documented unreachable for CREATION.

    The SW2024 swconst harvest exposes NO swFeatureNameID for split-line:
    the worker probe id=65 (swFmReferenceCurve) returned None from
    CreateDefinition on the live seat 2026-06-17. Same class as composite
    (W62 2a04542) and helix (W62 057789a). ISplitLineFeatureData is
    edit-only via IFeature.GetDefinition() on an existing split-line
    feature; no creation route exists. Returning None routes the handler
    to Mode-B without spending a CreateDefinition call every invocation.

    Historical implementation (CreateDefinition(65) +
    typed_qi(ISplitLineFeatureData) + AccessSelections(doc,
    VARIANT(VT_DISPATCH,None)) + ISetSplitTools(sketch) + ISetFaces(face)
    + ReleaseSelectionAccess + CreateFeature) can be reconstructed from
    git history if a future SW version exposes a creation enum.
    """
    return None


def _try_mode_b(
    doc: Any, sketch_name: str, face_entity: Any,
    reverse: bool, single_direction: bool,
) -> Any | None:
    """Mode-B: select sketch (mark=1) + face (mark=2) + InsertSplitLineProject.

    The split-line PropertyManager uses distinct marks for the "Sketch to
    project" (mark=1) and "Faces to split" (mark=2) list boxes — the
    macro-recorder corpus is consistent. Selecting both with mark=0 is the
    classic silent no-op trap (selection enters preselection, never routes
    to either list box).

    InsertSplitLineProject is a 2-arg method (Reverse, SingleDirection)
    returning void — verify-the-effect decides real success.
    """
    try:
        doc.ClearSelection2(True)
    except Exception as e:
        logger.warning("[B] ClearSelection2 RAISED: %r", e)
        return None

    try:
        sketch_feat = doc.FeatureByName(sketch_name)
    except Exception as e:
        logger.warning("[B] FeatureByName RAISED: %r", e)
        return None
    if sketch_feat is None:
        logger.warning("[B] FeatureByName(%r) -> None", sketch_name)
        return None

    try:
        sk_ok = select_entity(sketch_feat, mark=_MARK_SKETCH)
    except Exception as e:
        logger.warning("[B] select_entity(sketch) RAISED: %r", e)
        return None
    logger.warning(
        "[B] select_entity(sketch, mark=%d) -> %r", _MARK_SKETCH, sk_ok
    )
    if not sk_ok:
        return None

    try:
        fc_ok = select_entity(face_entity, append=True, mark=_MARK_FACE)
    except Exception as e:
        logger.warning("[B] select_entity(face) RAISED: %r", e)
        return None
    logger.warning(
        "[B] select_entity(face, append=True, mark=%d) -> %r", _MARK_FACE, fc_ok
    )
    if not fc_ok:
        return None

    try:
        isp = doc.InsertSplitLineProject
        result = (
            isp(reverse, single_direction) if callable(isp)
            else None  # property-bool resolution would already have been auto-invoked
        )
        logger.warning(
            "[B] InsertSplitLineProject(reverse=%r, single=%r) callable=%s -> %r",
            reverse, single_direction, callable(isp), result,
        )
    except Exception as e:
        logger.warning("[B] InsertSplitLineProject RAISED: %r", e)
        return None
    return object()
