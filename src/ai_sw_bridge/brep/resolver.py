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


__all__ = [
    "FaceAmbiguityError",
    "FaceResolutionError",
    "resolve_face_role",
]
