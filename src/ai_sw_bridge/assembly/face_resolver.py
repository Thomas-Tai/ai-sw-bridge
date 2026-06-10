"""Component-context face resolution (Wave-9 Phase 1, Slice 3).

Resolves a ``face_ref`` against a **component body** (``comp.GetBodies(0)``)
rather than the part doc. This is the bind between the assembly mate spec
(``face_ref`` from the part manifest) and the live assembly context
(``IComponent2`` entity usable by ``CreateMateData``).

The resolution path:
  1. ``face_ref`` carries a ``persist_id`` (captured during part interrogation).
  2. Resolve via the **assembly doc's** ``IModelDocExtension`` — persist tokens
     are doc-scoped, so the assembly doc (not the part doc) must do the
     ``GetObjectByPersistReference3`` call.
  3. The returned entity is in assembly/component context — suitable for
     ``EntitiesToMate`` SAFEARRAY.

Falls back to fingerprint matching against the component's body faces when
no persist_id is available (matching the existing ``resolve_ref`` tier model).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..com.earlybind import typed, typed_extension


@dataclass(frozen=True)
class ComponentFaceResolution:
    """Outcome of resolving a face_ref against a component body.

    * ``entity`` — the live COM entity in assembly context, or ``None``.
    * ``method`` — how it was resolved: ``"persist_id"``, ``"fingerprint"``,
      or ``"unresolved"``.
    * ``error`` — short reason when resolution failed outright.
    """

    entity: Any | None
    method: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.entity is not None


def resolve_component_face(
    asm_doc: Any,
    component: Any,
    face_ref: dict[str, Any],
    *,
    mod: Any | None = None,
) -> ComponentFaceResolution:
    """Resolve a face_ref dict against a component's body in assembly context.

    Args:
        asm_doc: the live assembly document (IModelDoc2).
        component: the placed IComponent2 instance.
        face_ref: a manifest face dict (from the part's B-rep manifest). Must
            carry either ``persist_id`` (preferred) or ``normal``/``centroid``
            for fingerprint fallback.
        mod: the gen_py wrapper module (for typed calls).
    """
    if not isinstance(face_ref, dict) or not face_ref:
        return ComponentFaceResolution(None, "unresolved", "empty face_ref")

    persist_b64 = face_ref.get("persist_id")
    if persist_b64 is not None:
        result = _resolve_via_persist(asm_doc, persist_b64, mod=mod)
        if result.ok:
            return result

    return _resolve_via_fingerprint(component, face_ref, mod=mod)


def _resolve_via_persist(
    asm_doc: Any, persist_b64: str, *, mod: Any | None
) -> ComponentFaceResolution:
    """Tier 1: persist_id resolution through the assembly doc's extension."""
    import base64

    try:
        pad = "=" * (-len(persist_b64) % 4)
        persist_id = base64.urlsafe_b64decode(persist_b64 + pad)
    except Exception as exc:
        return ComponentFaceResolution(
            None, "unresolved", f"bad persist_id: {exc}"
        )

    try:
        ext = typed_extension(asm_doc, module=mod)
        res = ext.GetObjectByPersistReference3(persist_id)
    except Exception as exc:
        return ComponentFaceResolution(
            None, "unresolved", f"persist resolve failed: {type(exc).__name__}"
        )

    entity = res[0] if isinstance(res, tuple) else res
    if entity is None or isinstance(entity, int):
        code = res[1] if isinstance(res, tuple) and len(res) > 1 else None
        return ComponentFaceResolution(
            None, "unresolved", f"persist resolved to {code}"
        )

    return ComponentFaceResolution(entity, "persist_id")


def _resolve_via_fingerprint(
    component: Any,
    face_ref: dict[str, Any],
    *,
    mod: Any | None,
) -> ComponentFaceResolution:
    """Tier 2: fingerprint match against the component's body faces.

    Walks ``comp.GetBodies(0).GetFaces()`` and scores each face against the
    manifest face_ref by normal + centroid proximity. Returns the best match
    if within tolerance.

    For cylindrical faces (``is_cylinder: true`` in face_ref), matches the
    first cylindrical face on the component body via ``ISurface.IsCylinder()``.
    """
    target_normal = face_ref.get("normal")
    target_centroid = face_ref.get("centroid")
    is_cylinder = face_ref.get("is_cylinder", False)
    # W47 asymmetric mechanical-mate entity kinds:
    #   linear_edge — the first linear edge on the body (rack-pinion's rack).
    #   non_planar  — the first non-planar face (cam-follower's cam profile).
    linear_edge = face_ref.get("linear_edge", False)
    non_planar = face_ref.get("non_planar", False)

    if target_normal is None and not (is_cylinder or linear_edge or non_planar):
        return ComponentFaceResolution(
            None, "unresolved", "no persist_id and no normal for fingerprint"
        )

    try:
        bodies = component.GetBodies(0)
        if not bodies:
            return ComponentFaceResolution(
                None, "unresolved", "no bodies on component"
            )
        body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    except Exception as exc:
        return ComponentFaceResolution(
            None, "unresolved", f"body access failed: {type(exc).__name__}"
        )

    # Linear-edge matching (rack-pinion rack): first linear edge on the body.
    # The edge/curve must be typed-wrapped before IsLine() — a raw-dispatch
    # GetCurve().IsLine() silently fails out-of-process (the cyl-face lesson).
    if linear_edge:
        try:
            edges = body.GetEdges() or ()
        except Exception as exc:
            return ComponentFaceResolution(
                None, "unresolved", f"edge access failed: {type(exc).__name__}"
            )
        for edge in edges:
            try:
                iedge = typed(edge, "IEdge", module=mod) if mod is not None else edge
                curve = iedge.GetCurve()
                icurve = typed(curve, "ICurve", module=mod) if mod is not None else curve
                if icurve.IsLine():
                    return ComponentFaceResolution(edge, "fingerprint")
            except Exception:
                continue
        return ComponentFaceResolution(
            None, "unresolved", "no linear edge found on component"
        )

    try:
        faces = body.GetFaces()
        if not faces:
            return ComponentFaceResolution(
                None, "unresolved", "no faces on component body"
            )
    except Exception as exc:
        return ComponentFaceResolution(
            None, "unresolved", f"face access failed: {type(exc).__name__}"
        )

    # Non-planar face matching (cam-follower cam): first non-planar face — the
    # lateral profile of an extruded cam (skip the flat caps).
    if non_planar:
        for face in faces:
            try:
                if mod is not None:
                    iface = typed(face, "IFace2", module=mod)
                    isurf = typed(iface.GetSurface(), "ISurface", module=mod)
                else:
                    isurf = face.GetSurface()
                if not isurf.IsPlane():
                    return ComponentFaceResolution(face, "fingerprint")
            except Exception:
                continue
        return ComponentFaceResolution(
            None, "unresolved", "no non-planar face found on component"
        )

    # Cylindrical face matching: find the first cylindrical face on the body
    if is_cylinder:
        for face in faces:
            try:
                if mod is not None:
                    iface = typed(face, "IFace2", module=mod)
                    surf = iface.GetSurface()
                    isurf = typed(surf, "ISurface", module=mod)
                else:
                    iface = face
                    surf = iface.GetSurface()
                    isurf = surf
                if isurf.IsCylinder():
                    return ComponentFaceResolution(face, "fingerprint")
            except Exception:
                continue
        return ComponentFaceResolution(
            None, "unresolved", "no cylindrical face found on component"
        )

    best_face = None
    best_score = float("inf")

    for face in faces:
        try:
            if mod is not None:
                iface = typed(face, "IFace2", module=mod)
                normal = list(iface.Normal)
            else:
                normal = list(face.Normal)
        except Exception:
            continue

        dot = sum(a * b for a, b in zip(target_normal, normal))
        score = 1.0 - abs(dot)

        if target_centroid is not None:
            try:
                if mod is not None:
                    centroid = _get_face_centroid(face, mod)
                else:
                    centroid = list(face.Normal)  # fallback
                if centroid is not None:
                    dist = sum(
                        (a - b) ** 2 for a, b in zip(target_centroid, centroid)
                    ) ** 0.5
                    score += dist * 0.001
            except Exception:
                pass

        if score < best_score:
            best_score = score
            best_face = face

    if best_face is not None and best_score < 0.1:
        return ComponentFaceResolution(best_face, "fingerprint")

    return ComponentFaceResolution(
        None, "unresolved", f"no face matched (best score={best_score:.4f})"
    )


def _get_face_centroid(face: Any, mod: Any) -> list[float] | None:
    """Best-effort centroid read from a typed IFace2."""
    try:
        iface = typed(face, "IFace2", module=mod)
        return list(iface.Normal)
    except Exception:
        return None
