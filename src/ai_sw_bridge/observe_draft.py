"""Draft analysis observation helper — W37 (perception axis).

Read-only DFM draft analysis: for a part + a pull direction, classify
every face as **positive draft / negative draft / vertical (needs draft)**
and report the minimum draft angle plus the count of faces below a
configurable threshold.

Seat-proven first-principles route (no add-in dependency):
  ``IPartDoc.GetBodies2(swSolidBody=0, True)`` → ``IBody2.GetFaces`` →
  ``IFace2.Normal`` (property-get under pywin32 late binding, per the
  E2.1 spike finding baked into ``brep/interrogator.py``).

Draft angle derivation:
  ``angle = arccos(dot(normal, pull))``
  ``draft_deg = 90° − angle``
  - Positive draft → face tilts outward (moldable).
  - Zero draft → vertical wall (needs draft added).
  - Negative draft → undercut (cannot eject).

v1 scope: single-body or multi-body part, one pull direction.
DEFER: undercut shadow detection, min-wall-thickness, parting-line
suggestion, multi-body per-body report, per-config draft, straddle
faces, DFM cost aggregation.
"""

from __future__ import annotations

import math
from typing import Any

from .sw_com import SW_DOC_PART, resolve


PULL_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "front": (0.0, 0.0, 1.0),
    "back": (0.0, 0.0, -1.0),
    "top": (0.0, 1.0, 0.0),
    "bottom": (0.0, -1.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "+x": (1.0, 0.0, 0.0),
    "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 1.0, 0.0),
    "-y": (0.0, -1.0, 0.0),
    "+z": (0.0, 0.0, 1.0),
    "-z": (0.0, 0.0, -1.0),
}


def parse_pull_direction(direction_str: str) -> tuple[float, float, float] | None:
    """Resolve a pull-direction string to a unit vector.

    Accepts named directions (``front``, ``back``, ``top``, ``bottom``,
    ``right``, ``left``) and axis shorthand (``+x``, ``-x``, ``+y``,
    ``-y``, ``+z``, ``-z``).  Case-insensitive.

    Returns ``None`` when the string is not recognised.
    """
    return PULL_DIRECTIONS.get(direction_str.strip().lower())


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _read_normal(face: Any) -> tuple[float, float, float] | None:
    """Read ``IFace2.Normal`` — proven pattern from ``brep/interrogator.py``.

    Under pywin32 late binding, zero-arg IFace2 methods auto-invoke on
    attribute access; calling with parens raises ``TypeError``.
    """
    try:
        result = face.Normal
        if callable(result):
            result = result()
    except Exception:
        return None
    if not isinstance(result, (tuple, list)) or len(result) != 3:
        return None
    try:
        return (float(result[0]), float(result[1]), float(result[2]))
    except (TypeError, ValueError):
        return None


def _classify_draft(draft_deg: float, min_angle_deg: float) -> str:
    """Classify a draft angle as positive, negative, or vertical."""
    if abs(draft_deg) <= min_angle_deg:
        return "vertical"
    return "positive" if draft_deg > 0.0 else "negative"


def _compute_draft_deg(
    normal: tuple[float, float, float],
    pull: tuple[float, float, float],
) -> float:
    """Compute draft angle in degrees from a face normal and pull vector.

    ``draft_deg = 90 − degrees(arccos(dot(normal, pull)))``

    Positive when the face normal tilts toward the pull direction
    (outward draft), negative when it tilts away (undercut), zero when
    the face is parallel to the pull (vertical wall).
    """
    d = _dot(normal, pull)
    d = max(-1.0, min(1.0, d))
    angle_rad = math.acos(d)
    return 90.0 - math.degrees(angle_rad)


def read_draft(
    part_doc: Any,
    pull_direction: str,
    min_angle_deg: float = 1.0,
    mod: Any = None,
) -> dict[str, Any]:
    """Analyse draft for every face of every solid body in *part_doc*.

    Pipeline:
      1. Parse *pull_direction* → unit vector.
      2. ``IPartDoc.GetBodies2(0, True)`` (``swSolidBody=0``).
      3. Per body → ``IBody2.GetFaces``.
      4. Per face → ``IFace2.Normal``, compute draft vs pull vector.
      5. Classify each face, accumulate stats.

    Returns dict with:
      - pull_direction (str)
      - pull_vector (list[float])
      - faces_total (int)
      - faces_positive (int)
      - faces_negative (int)
      - faces_vertical (int)
      - min_draft_deg (float | None) — min |draft_deg| across all faces
      - faces_below_threshold (list[dict]) — faces with |draft_deg| <= min_angle_deg
      - errors (list[str])
    """
    pull_vec = parse_pull_direction(pull_direction)
    result: dict[str, Any] = {
        "pull_direction": pull_direction,
        "pull_vector": list(pull_vec) if pull_vec else None,
        "faces_total": 0,
        "faces_positive": 0,
        "faces_negative": 0,
        "faces_vertical": 0,
        "min_draft_deg": None,
        "faces_below_threshold": [],
        "errors": [],
    }

    if pull_vec is None:
        result["errors"].append(
            f"unrecognised pull direction: {pull_direction!r}; "
            f"valid: {sorted(PULL_DIRECTIONS)}"
        )
        return result

    # ── Acquire IPartDoc ──────────────────────────────────────────────
    # GetBodies2 is an IPartDoc member; sw_get_draft_analysis may hand us a
    # typed IModelDoc2 (which lacks it). QI to IPartDoc, accepting either
    # binding — mirrors the shipped observe_bbox.read_bbox (W30) pattern.
    try:
        if hasattr(part_doc, "GetBodies2"):
            pdoc = part_doc
        else:
            from .com.earlybind import typed

            pdoc = typed(part_doc, "IPartDoc", module=mod)
    except Exception as exc:
        result["errors"].append(f"IPartDoc acquisition failed: {exc!r}")
        return result

    # ── Get solid bodies ───────────────────────────────────────────────
    try:
        bodies = pdoc.GetBodies2(0, True)
    except Exception as exc:
        result["errors"].append(f"GetBodies2 failed: {exc!r}")
        return result

    if bodies is None or (isinstance(bodies, (list, tuple)) and len(bodies) == 0):
        result["errors"].append("no solid bodies found in part")
        return result

    if not isinstance(bodies, (list, tuple)):
        bodies = (bodies,)

    min_abs_draft: float | None = None
    face_global_idx = 0

    for body_id, body in enumerate(bodies):
        try:
            raw_faces = body.GetFaces
            if callable(raw_faces):
                raw_faces = raw_faces()
        except Exception:
            continue
        if not isinstance(raw_faces, (tuple, list)):
            continue

        for face in raw_faces:
            normal = _read_normal(face)
            if normal is None:
                face_global_idx += 1
                continue

            draft_deg = _compute_draft_deg(normal, pull_vec)
            classification = _classify_draft(draft_deg, min_angle_deg)

            result["faces_total"] += 1
            if classification == "positive":
                result["faces_positive"] += 1
            elif classification == "negative":
                result["faces_negative"] += 1
            else:
                result["faces_vertical"] += 1

            abs_draft = abs(draft_deg)
            if min_abs_draft is None or abs_draft < min_abs_draft:
                min_abs_draft = abs_draft

            if abs_draft <= min_angle_deg:
                result["faces_below_threshold"].append(
                    {
                        "face_id": f"body{body_id}_face{face_global_idx}",
                        "draft_deg": round(draft_deg, 4),
                        "classification": classification,
                    }
                )

            face_global_idx += 1

    result["min_draft_deg"] = (
        round(min_abs_draft, 4) if min_abs_draft is not None else None
    )
    return result


def _sw_get_draft_analysis_impl(
    doc: Any,
    pull_direction: str,
    min_angle_deg: float = 1.0,
    mod: Any = None,
) -> dict[str, Any]:
    """Core: DFM draft analysis of the active part (v0.18 implementation).

    Validates *doc* is a part document, then delegates to
    :func:`read_draft`.  Returns structured report:
    ``{"ok": bool, "draft_analysis": {...}, "error": str|None}``.
    Internal callers (the ``SolidWorksClient.observe`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_get_draft_analysis` free function routes here behind a
    ``PendingDeprecationWarning``.

    Fail-closed:
      - Not a part → ``ok=False``, typed error.
      - No solid bodies → ``ok=False``, error.
      - Unrecognised pull direction → ``ok=False``, error.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "draft_analysis": None,
    }

    try:
        doc_type = resolve(doc, "GetType")
        if callable(doc_type):
            doc_type = doc_type()
    except Exception as exc:
        result["error"] = f"doc.GetType failed: {exc!r}"
        return result

    if doc_type != SW_DOC_PART:
        result["error"] = f"draft analysis requires part document (got type {doc_type})"
        return result

    draft = read_draft(doc, pull_direction, min_angle_deg, mod=mod)

    if draft["errors"]:
        result["error"] = "; ".join(draft["errors"])
        result["draft_analysis"] = {k: v for k, v in draft.items() if k != "errors"}
    else:
        result["draft_analysis"] = {k: v for k, v in draft.items() if k != "errors"}
        result["ok"] = True

    return result
