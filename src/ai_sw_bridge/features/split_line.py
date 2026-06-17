"""W62 — ``split_line`` feature-add handler (registry seam).

Projects a sketch onto a solid-body face, splitting the face topologically
without removing material.  The dual-mode doctrine is applied:

  Mode-A:  CreateDefinition → typed_qi(data, "ISplitLineFeatureData")
           → AccessSelections(doc, None) → set Sketch, SplitType, ISetFaces
           → ReleaseSelectionAccess() → CreateFeature(data)
  Mode-B:  select sketch + face, then
           doc.InsertSplitLineProject(Reverse:bool, SingleDirection:bool)

Verify-the-EFFECT (DIFFERENT from hem): success = ΔFace > 0 AND ΔVol == 0.
A split line adds topological faces (the projected curve partitions the
target face) but does NOT change solid volume.  A volume delta means
something else happened (a cut or boss); no face delta means the split
was a silent no-op (the W21/W42 ghost trap).
"""

from __future__ import annotations

from typing import Any

from ..com.earlybind import EarlyBindError, typed, typed_qi
from ..com.sw_type_info import wrapper_module
from ..selection.live import select_entity

# Flipped to "GREEN" by W0 after the spike fires on the live seat and
# one of the two modes is proven generative.
SPIKE_STATUS = "UNRUN"

_SW_SOLID_BODY = 0

# swSplitLineType_e — projection is the lead variant.
_SPLIT_TYPES: dict[str, int] = {"projection": 0, "silhouette": 1}

# FP-noise threshold for volume comparison (mm³).
_VOL_EPS_MM3 = 1e-6


def _solid_bodies(doc: Any) -> list[Any] | None:
    """Solid bodies of *doc*; ``None`` on COM failure, ``[]`` when there are none."""
    try:
        src = (
            doc if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        bodies = src.GetBodies2(_SW_SOLID_BODY, True)
    except Exception:
        return None
    if not bodies:
        return []
    return list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]


def _metrics(doc: Any) -> tuple[int, float]:
    """(face_count, volume_mm³) over the doc's solid bodies; (0, 0.0) on failure."""
    bodies = _solid_bodies(doc)
    if not bodies:
        return 0, 0.0
    faces = 0
    vol_mm3 = 0.0
    for b in bodies:
        try:
            f = b.GetFaces()
            faces += len(f) if f else 0
        except Exception:
            pass
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                vol_mm3 += float(mp[3]) * 1e9
        except Exception:
            pass
    return faces, vol_mm3


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
    if d_faces > 0 and abs(d_vol) < _VOL_EPS_MM3:
        return True, f"split_line projected ({d_faces} new faces, mode-{mode})"

    return False, (
        f"split_line did not split topologically "
        f"(delta_face={d_faces}, delta_vol_mm3={d_vol:.6f}); "
        f"mode-{mode} returned but verify-the-effect failed"
    )


def _try_mode_a(
    doc: Any, sketch_name: str, face_entity: Any, split_type: int,
) -> Any | None:
    """Mode-A: CreateDefinition → ISplitLineFeatureData → CreateFeature.

    Returns the created feature node, or None on any failure (E_NOINTERFACE,
    None data, silent drop).
    """
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(65)
        if data is None:
            return None
        sd = typed_qi(data, "ISplitLineFeatureData")
        sd.AccessSelections(doc, None)
        try:
            sketch_feat = doc.FeatureByName(sketch_name)
            if sketch_feat is None:
                return None
            sd.Sketch = sketch_feat
        except Exception:
            return None
        sd.SplitType = split_type
        try:
            sd.ISetFaces(1, (face_entity,))
        except Exception:
            try:
                sd.ISetFaces((face_entity,))
            except Exception:
                return None
        sd.ReleaseSelectionAccess()
        return fm.CreateFeature(data)
    except (EarlyBindError, Exception):
        return None


def _try_mode_b(
    doc: Any, sketch_name: str, face_entity: Any,
    reverse: bool, single_direction: bool,
) -> Any | None:
    """Mode-B: select sketch + face, then InsertSplitLineProject.

    Returns a sentinel on call success (verify-the-effect decides real success).
    Returns None if selection or the insert call fails.
    """
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    try:
        sketch_feat = doc.FeatureByName(sketch_name)
        if sketch_feat is None:
            return None
        if not select_entity(sketch_feat, mark=0):
            return None
        if not select_entity(face_entity, append=True, mark=0):
            return None
    except Exception:
        return None
    try:
        doc.InsertSplitLineProject(reverse, single_direction)
    except Exception:
        return None
    return object()
