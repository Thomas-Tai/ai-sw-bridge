"""B-rep interrogator — per-feature topology extraction (spec.md §2.2).

After a feature handler returns an ``IFeature`` handle, ``interrogate``
walks the resulting bodies/faces and produces a structured dict
describing the feature's topology: per-face bounding box, unit normal,
centroid, area, body-id, and a role hint derived from the normal.

E2.1 spike load-bearing findings baked in:

* Under pywin32 late binding, zero-arg IFace2 methods (``GetBox``,
  ``Normal``, ``GetArea``) are already invoked on attribute access —
  calling them with parens raises ``TypeError: 'tuple' object is not
  callable``. All reads below use property access.
* ``IEntity.GetSelectByIDString()`` is unreachable on the IFace2
  dispatch proxy returned via ``IFeature.GetFaces()`` (out-of-process
  marshaler limitation). Workaround: synthesize a session-scoped
  ``temp_id`` from ``"body{body_id}_face{face_idx}"``; downstream
  face_role resolution uses the role_hint + fingerprint instead.

Gated by ``flags.brep_interrogation`` (default OFF). When the flag is
OFF, ``interrogate`` returns ``None`` without touching COM.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..flags import resolve as resolve_flags
from ..telemetry import histogram as telemetry_histogram

logger = logging.getLogger("ai_sw_bridge.brep.interrogator")

# Alignment tolerance for axis-aligned role-hint heuristic (spec §2.3).
_AXIS_TOLERANCE = 1e-6


@dataclass(frozen=True)
class BrepFace:
    """One face's topological fingerprint payload.

    ``temp_id`` is session-scoped only — never written to the manifest.
    ``fingerprint`` is assigned by the fingerprint module (E2.3), not
    the interrogator; it's left empty here and populated in the
    manifest serializer.
    """

    face_idx: int
    body_id: int
    temp_id: str
    normal_vec: tuple[float, float, float]
    centroid: tuple[float, float, float]
    bbox: tuple[tuple[float, float, float], tuple[float, float, float]]
    area_mm2: float
    role_hint: str
    fingerprint: str = ""
    is_surface: bool = False
    is_hidden: bool = False

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form for the manifest brep block."""
        return {
            "face_idx": self.face_idx,
            "body_id": self.body_id,
            "temp_id": self.temp_id,
            "normal": list(self.normal_vec),
            "centroid": list(self.centroid),
            "bbox": [list(self.bbox[0]), list(self.bbox[1])],
            "area_mm2": self.area_mm2,
            "role_hint": self.role_hint,
            "fingerprint": self.fingerprint,
            "is_surface": self.is_surface,
            "is_hidden": self.is_hidden,
        }


def interrogate(feature: Any, ctx: Any = None) -> Optional[dict[str, Any]]:
    """Run the L1 interrogation algorithm on a built feature.

    Returns a dict shaped ``{"feature": str, "faces": [BrepFace.to_dict()]}``
    or ``None`` when the ``brep_interrogation`` flag is OFF.

    Edge cases per spec.md §2.8:

    * Suppressed features (``IFeature.IsSuppressed()`` truthy) skip face
      walking entirely and return ``{"faces": [], "status": "suppressed"}``
      so downstream resolvers see a well-formed brep block instead of
      stale data from before suppression.
    * Hidden faces (``IFace2.IsHidden`` truthy) are still included but
      flagged with ``is_hidden=true`` so the resolver can deprioritize
      them when scoring ``face_role`` candidates.
    * Imported features (``IFeature.GetTypeName2() == "ImportFeature"``)
      have no native face topology accessible via the feature handle;
      the walker falls back to body-level enumeration via
      ``IFeature.GetBody`` if reachable, else returns
      ``{"faces": [], "status": "imported"}``.

    Lazy mode (spec.md §2.11): when ``ctx.referenced_face_roles`` is a
    non-None set, features not referenced by any downstream feature skip
    face walking entirely (``status: "no_downstream_refs"``). Features
    that are referenced have their faces walked normally but only faces
    whose ``role_hint`` matches an entry in the set are included.

    The ``ctx`` parameter carries build state (BuildContext). When it
    exposes a ``referenced_face_roles`` attribute, lazy mode activates.
    """
    flags = resolve_flags()
    if not flags.get("brep_interrogation", False):
        return None

    if _is_suppressed(feature):
        return {
            "feature": _feature_name(feature),
            "faces": [],
            "status": "suppressed",
        }

    is_import = _is_import_feature(feature)

    # Lazy mode (spec.md §2.11): extract the referenced-face set from ctx.
    referenced_face_roles: Optional[set] = None
    if ctx is not None:
        referenced_face_roles = getattr(ctx, "referenced_face_roles", None)

    feat_name = _feature_name(feature)
    mode_label = "eager"

    if referenced_face_roles is not None:
        mode_label = "lazy"
        roles_for_feature = {
            role for (name, role) in referenced_face_roles if name == feat_name
        }
        if not roles_for_feature:
            t0 = time.perf_counter()
            elapsed = time.perf_counter() - t0
            try:
                telemetry_histogram("brep_interrogation_seconds", elapsed, mode="lazy")
            except Exception:
                pass
            return {
                "feature": feat_name,
                "faces": [],
                "status": "no_downstream_refs",
            }

    t0 = time.perf_counter()
    try:
        faces = _walk_faces(feature, force_body_walk=is_import)
    except Exception as e:
        logger.warning("brep interrogation failed: %s", e)
        return {"feature": feat_name, "faces": [], "error": str(e)}
    elapsed = time.perf_counter() - t0
    try:
        telemetry_histogram("brep_interrogation_seconds", elapsed, mode=mode_label)
    except Exception:
        pass

    if referenced_face_roles is not None:
        roles_for_feature = {
            role for (name, role) in referenced_face_roles if name == feat_name
        }
        faces = [f for f in faces if f.role_hint in roles_for_feature]

    payload: dict[str, Any] = {
        "feature": feat_name,
        "faces": [f.to_dict() for f in faces],
    }
    if is_import and not faces:
        payload["status"] = "imported"
    return payload


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _feature_name(feature: Any) -> str:
    try:
        return feature.Name or "unknown"
    except Exception:
        return "unknown"


def _walk_faces(feature: Any, *, force_body_walk: bool = False) -> list[BrepFace]:
    """Walk bodies → faces. Falls back to feature.GetFaces when bodies
    aren't reachable on the dispatch proxy.

    ``force_body_walk`` skips ``IFeature.GetFaces`` entirely — used for
    ImportFeature where the feature handle doesn't carry native face
    topology and the only path is via ``IFeature.GetBody``.
    """
    faces: list[BrepFace] = []

    if not force_body_walk:
        # Preferred path: IFeature.GetFaces() returns a SAFEARRAY
        # marshaled as a tuple under late binding. Treat it as the fast
        # path; if it raises or returns empty, fall back to body walk.
        direct = _try_feature_getfaces(feature)
        if direct:
            for idx, face in enumerate(direct):
                bf = _probe_face(face, body_id=0, face_idx=idx)
                if bf is not None:
                    faces.append(bf)
            return faces

    # Fallback: walk bodies via the parent IPartDoc. ctx is not
    # plumbed through the current interrogate() signature, so this
    # path is only taken when the caller supplies a feature that
    # exposes a parent body chain via IFeature.GetBody (rare).
    body_id = 0
    body = _try_get_body(feature)
    while body is not None:
        raw = _try_get_faces(body)
        for idx, face in enumerate(raw):
            bf = _probe_face(face, body_id=body_id, face_idx=idx)
            if bf is not None:
                faces.append(bf)
        body = _next_body(body)
        body_id += 1
    return faces


def _try_feature_getfaces(feature: Any) -> list[Any]:
    try:
        result = feature.GetFaces
        if callable(result):
            result = result()
    except Exception:
        return []
    if result is None:
        return []
    if isinstance(result, (tuple, list)):
        return list(result)
    return []


def _try_get_body(feature: Any) -> Optional[Any]:
    try:
        body = feature.GetBody
        if callable(body):
            body = body()
        return body
    except Exception:
        return None


def _next_body(body: Any) -> Optional[Any]:
    try:
        nxt = body.GetNext
        if callable(nxt):
            nxt = nxt()
        return nxt
    except Exception:
        return None


def _try_get_faces(body: Any) -> list[Any]:
    try:
        result = body.GetFaces
        if callable(result):
            result = result()
    except Exception:
        return []
    if result is None:
        return []
    if isinstance(result, (tuple, list)):
        return list(result)
    return []


def _probe_face(face: Any, *, body_id: int, face_idx: int) -> Optional[BrepFace]:
    """Extract the six load-bearing attributes from one IFace2 proxy."""
    box = _read_box(face)
    normal = _read_normal(face)
    area_mm2 = _read_area(face)
    if box is None or normal is None:
        return None

    centroid = _centroid_from_box(box)
    temp_id = _synthetic_temp_id(body_id, face_idx)
    role = _role_hint(normal, centroid, box)
    is_surface = _read_is_surface(face)
    is_hidden = _read_is_hidden(face)

    return BrepFace(
        face_idx=face_idx,
        body_id=body_id,
        temp_id=temp_id,
        normal_vec=normal,
        centroid=centroid,
        bbox=(box[:3], box[3:]),
        area_mm2=area_mm2 if area_mm2 is not None else 0.0,
        role_hint=role,
        is_surface=is_surface,
        is_hidden=is_hidden,
    )


def _read_box(face: Any) -> Optional[tuple[float, float, float, float, float, float]]:
    try:
        result = face.GetBox
        if callable(result):
            result = result()
    except Exception:
        return None
    if not isinstance(result, (tuple, list)) or len(result) != 6:
        return None
    try:
        return tuple(float(v) for v in result)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _read_normal(face: Any) -> Optional[tuple[float, float, float]]:
    try:
        result = face.Normal
        if callable(result):
            result = result()
    except Exception:
        return None
    if not isinstance(result, (tuple, list)) or len(result) != 3:
        return None
    try:
        return tuple(float(v) for v in result)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _read_area(face: Any) -> Optional[float]:
    try:
        result = face.GetArea
        if callable(result):
            result = result()
    except Exception:
        return None
    try:
        # SW returns m²; convert to mm².
        return float(result) * 1e6
    except (TypeError, ValueError):
        return None


def _read_is_surface(face: Any) -> bool:
    try:
        result = face.IsSurface
        if callable(result):
            result = result()
        return bool(result)
    except Exception:
        return False


def _read_is_hidden(face: Any) -> bool:
    """Read IFace2.IsHidden — true when the face is hidden from view.

    Some SW builds expose ``Visible`` as the inverse instead; fall back
    to that when ``IsHidden`` isn't reachable.
    """
    try:
        result = face.IsHidden
        if callable(result):
            result = result()
        return bool(result)
    except Exception:
        pass
    try:
        visible = face.Visible
        if callable(visible):
            visible = visible()
        return not bool(visible)
    except Exception:
        return False


def _is_suppressed(feature: Any) -> bool:
    """Check IFeature.IsSuppressed() — true when the feature is suppressed
    in the active configuration. Suppressed features have stale or
    absent geometry; interrogation must skip them entirely.
    """
    try:
        result = feature.IsSuppressed
        if callable(result):
            result = result()
        return bool(result)
    except Exception:
        return False


def _is_import_feature(feature: Any) -> bool:
    """Check IFeature.GetTypeName2() == "ImportFeature".

    Imported features (from STEP, IGES, Parasolid, etc.) have no
    native face topology accessible via ``IFeature.GetFaces`` — the
    walker has to fall back to body-level enumeration.
    """
    try:
        result = feature.GetTypeName2
        if callable(result):
            result = result()
        return str(result) == "ImportFeature"
    except Exception:
        pass
    # Older SW builds only expose GetTypeName.
    try:
        result = feature.GetTypeName
        if callable(result):
            result = result()
        return str(result) == "ImportFeature"
    except Exception:
        return False


def _centroid_from_box(
    box: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float]:
    """Midpoint of the bbox — cheap, avoids GetCenterOfMass (spec §2.2)."""
    return (
        (box[0] + box[3]) / 2.0,
        (box[1] + box[4]) / 2.0,
        (box[2] + box[5]) / 2.0,
    )


def _synthetic_temp_id(body_id: int, face_idx: int) -> str:
    """Session-scoped placeholder for GetSelectByIDString.

    The E2.1 spike found IEntity.GetSelectByIDString unreachable on the
    IFace2 dispatch proxy returned via IFeature.GetFaces(); the
    out-of-process marshaler does not expose the full vtable. We use a
    body-local index as the stable-in-session identifier. Downstream
    face_role resolution uses role_hint + fingerprint, NOT temp_id.
    """
    return f"body{body_id}_face{face_idx}"


def _role_hint(
    normal: tuple[float, float, float],
    centroid: tuple[float, float, float],
    box: tuple[float, float, float, float, float, float],
) -> str:
    """Axis-aligned role hint per spec.md §2.3.

    Returns one of ``"+x_outboard"``, ``"-x_inboard"``, ``"+y_outboard"``,
    ... ``"oblique"``. "Outboard" vs "inboard" is decided by comparing
    the centroid's signed projection along the normal against the bbox
    midpoint along the dominant axis.
    """
    axes = ("x", "y", "z")
    for i, axis in enumerate(axes):
        n = normal[i]
        if abs(abs(n) - 1.0) > _AXIS_TOLERANCE:
            # other components must be ~0 for an axis-aligned normal
            other = [abs(normal[j]) for j in range(3) if j != i]
            if any(v > _AXIS_TOLERANCE for v in other):
                continue
            continue
        other = [abs(normal[j]) for j in range(3) if j != i]
        if any(v > _AXIS_TOLERANCE for v in other):
            continue
        sign = "+" if n > 0 else "-"
        # Outboard if centroid projection >= bbox midpoint along axis.
        midpoint = (box[i] + box[i + 3]) / 2.0
        projection = centroid[i]
        side = "outboard" if projection >= midpoint else "inboard"
        return f"{sign}{axis}_{side}"
    return "oblique"


__all__ = [
    "BrepFace",
    "interrogate",
]
