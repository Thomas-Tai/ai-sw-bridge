"""B-rep resolver — symbolic face_role → face-id (spec.md §2.6).

Resolves a symbolic ``face_role`` (e.g. ``"top"``, ``"+z_outboard"``)
on a face-referencing feature (sketch_*_on_face, simple_hole) to the
concrete face fingerprint from the parent feature's brep block in
the manifest.

The validator (``spec.validator``) runs at spec-ingest time, before
any COM call. At that point the parent feature hasn't been built
yet, so the manifest doesn't exist. The validator's job is to
confirm *shape* — that the referencing feature uses ``face_role``
correctly. The resolver's job is to do the *runtime* lookup against
the built manifest after the parent feature's brep block exists.

Case-insensitive role matching: ``"top"`` matches a face whose
``role_hint`` is ``"TOP"``, ``"+Z_OUTBOARD"``, or any casing variant.

Layering (OI-3): this resolver is *data-level* — it picks **which manifest
face dict** a symbolic role or normal refers to, and is intentionally
persist-agnostic. Resolving that face dict to a **live COM entity** (with the
persist-id → fingerprint tier hierarchy) is the job of
``selection.live.resolve_manifest_face`` / ``resolve_ref``. Do not add a
persist-token tier here; the token captured into the manifest face is consumed
at the live layer via ``DurableRef.from_manifest_face``.
"""

from __future__ import annotations

from typing import Any


class FaceResolutionError(Exception):
    """No face in the parent brep block matches the requested role."""

    def __init__(
        self,
        feature_name: str,
        face_role: str,
        available_roles: list[str],
    ) -> None:
        self.feature_name = feature_name
        self.face_role = face_role
        self.available_roles = available_roles
        super().__init__(
            f"feature '{feature_name}' requests face_role={face_role!r} "
            f"but no face in the parent brep block matches. "
            f"Available roles: {available_roles!r}"
        )


class FaceAmbiguityError(Exception):
    """Multiple faces in the parent brep block match the requested role."""

    def __init__(
        self,
        feature_name: str,
        face_role: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        self.feature_name = feature_name
        self.face_role = face_role
        self.candidates = candidates
        fingerprints = [c.get("fingerprint", "?") for c in candidates]
        super().__init__(
            f"feature '{feature_name}' requests face_role={face_role!r} "
            f"but {len(candidates)} faces match. Candidates: {fingerprints!r}. "
            f"Disambiguate by adding a face_centroid_hint to the spec."
        )


def resolve_face_role(
    *,
    feature_name: str,
    face_role: str,
    parent_brep_block: dict[str, Any],
) -> dict[str, Any]:
    """Resolve ``face_role`` against the parent feature's brep block.

    Args:
        feature_name: The name of the referencing feature (used in
            error messages).
        face_role: The symbolic role to resolve (e.g. ``"top"``).
        parent_brep_block: The brep block of the parent feature, as
            produced by :meth:`brep.manifest.Manifest.lookup`.

    Returns:
        The face dict (including fingerprint) that matches the role.

    Raises:
        FaceResolutionError: no face matches.
        FaceAmbiguityError: more than one face matches.
    """
    if not isinstance(face_role, str) or not face_role:
        raise FaceResolutionError(
            feature_name=feature_name,
            face_role=str(face_role),
            available_roles=_available_roles(parent_brep_block),
        )

    target = face_role.lower()
    matches: list[dict[str, Any]] = []
    for face in parent_brep_block.get("faces", []):
        role_hint = face.get("role_hint")
        if not isinstance(role_hint, str):
            continue
        if role_hint.lower() == target:
            matches.append(face)

    available = _available_roles(parent_brep_block)
    if not matches:
        raise FaceResolutionError(feature_name, face_role, available)
    if len(matches) > 1:
        raise FaceAmbiguityError(feature_name, face_role, matches)
    return matches[0]


def _available_roles(parent_brep_block: dict[str, Any]) -> list[str]:
    return [
        face["role_hint"]
        for face in parent_brep_block.get("faces", [])
        if isinstance(face.get("role_hint"), str)
    ]


def find_face_by_normal(
    parent_brep_block: dict[str, Any],
    normal_vec: tuple[float, float, float],
    *,
    tolerance: float = 0.01,
) -> dict[str, Any] | None:
    """Find the face whose unit normal is closest to *normal_vec*.

    Direct-normal lookup canonicalized in requirements.md
    FR-v0.11-L1-02. Complements :func:`resolve_face_role` (symbolic
    role lookup, FR-v0.11-L1-03) — same underlying brep block, two
    different access patterns.

    Args:
        parent_brep_block: The brep block of the parent feature
            (the dict from ``manifest.features[feature_name]``).
        normal_vec: The query normal as a unit-length 3-tuple
            ``(nx, ny, nz)``. Caller is responsible for
            normalization; the comparison uses dot-product so a
            non-unit input degrades to a magnitude-scaled similarity.
        tolerance: Angular tolerance expressed as
            ``1 - dot_product``. Default 0.01 ≈ 8° of angular slop;
            tighten for parts with closely-aligned faces.

    Returns:
        The face dict whose normal has the highest dot product with
        *normal_vec*, or ``None`` if no face satisfies the tolerance
        (i.e. every candidate's ``1 - dot`` exceeds ``tolerance``).

    Notes:
        Face fingerprinting (E2.3) hashes ``normal + centroid +
        area`` together; this lookup is normal-only and intentionally
        ignores centroid/area. For geometry-disambiguated lookup
        when multiple faces share a normal direction (e.g. the +Z
        face of two parallel bodies in a multi-body part), filter
        the result downstream by centroid or use a fingerprint
        match instead.
    """
    best: dict[str, Any] | None = None
    best_dot = -2.0  # below the [-1, 1] domain of dot for unit vectors
    for face in parent_brep_block.get("faces", []):
        face_normal = face.get("normal")
        if not isinstance(face_normal, (list, tuple)) or len(face_normal) != 3:
            continue
        try:
            dot = (
                float(face_normal[0]) * normal_vec[0]
                + float(face_normal[1]) * normal_vec[1]
                + float(face_normal[2]) * normal_vec[2]
            )
        except (TypeError, ValueError):
            continue
        if dot > best_dot:
            best_dot = dot
            best = face
    if best is None or (1.0 - best_dot) > tolerance:
        return None
    return best


__all__ = [
    "FaceAmbiguityError",
    "FaceResolutionError",
    "find_face_by_normal",
    "resolve_face_role",
]
