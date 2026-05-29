"""Typed B-rep fingerprint — hash + the geometry that produced it.

Wraps the 16-hex-char stable identity hash from
``brep.fingerprint.fingerprint`` together with the three face
properties that feed it (unit normal, centroid, area). Carrying the
source geometry alongside the hash lets downstream resolvers re-match
against a fresh brep block by quantized value equality, not just
string equality on the hash — which matters when a rebuild perturbs
a face past the quantization step and the hash changes.

The hash itself is derived deterministically by re-running
``brep.fingerprint.fingerprint`` on ``to_face_dict()``; a caller that
hands in a ``hash_hex`` that disagrees with the geometry gets a
``ValueError`` at construction. That invariant keeps the typed wrapper
faithful to the canonical hash function in ``brep/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..brep.fingerprint import fingerprint as _compute_hash


@dataclass(frozen=True)
class BrepFingerprint:
    """A stable B-rep identity hash plus the geometry that produced it.

    Fields:

    * ``hash_hex`` — the 16-hex-char digest from
      ``brep.fingerprint.fingerprint``.
    * ``normal`` — unit normal as a 3-tuple (dimensionless).
    * ``centroid`` — face centroid as a 3-tuple (meters, part frame).
    * ``area_mm2`` — face area in square millimeters.
    """

    hash_hex: str
    normal: tuple[float, float, float]
    centroid: tuple[float, float, float]
    area_mm2: float

    def __post_init__(self) -> None:
        if not isinstance(self.hash_hex, str) or len(self.hash_hex) != 16:
            raise ValueError(
                f"hash_hex must be a 16-char hex string, got {self.hash_hex!r}"
            )
        if len(self.normal) != 3 or len(self.centroid) != 3:
            raise ValueError("normal and centroid must be 3-tuples")

        expected = _compute_hash(self.to_face_dict())
        if expected != self.hash_hex:
            raise ValueError(
                f"hash_hex {self.hash_hex!r} does not match geometry "
                f"(expected {expected!r})"
            )

    def to_face_dict(self) -> dict[str, Any]:
        """Return the face-dict shape consumed by ``brep.fingerprint``.

        The key names (``normal`` / ``centroid`` / ``area_mm2``) match
        ``brep.interrogator.BrepFace.to_dict`` so the same dict feeds
        both the canonical hash and downstream manifest assembly.
        """
        return {
            "normal": list(self.normal),
            "centroid": list(self.centroid),
            "area_mm2": float(self.area_mm2),
        }

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form for the manifest / wire format."""
        return {
            "hash": self.hash_hex,
            "normal": list(self.normal),
            "centroid": list(self.centroid),
            "area_mm2": float(self.area_mm2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrepFingerprint:
        """Inverse of :meth:`to_dict`.

        The hash is recomputed on the geometry and checked against the
        stored ``hash``; a mismatch raises ``ValueError`` so a
        corrupted or hand-edited manifest can't silently land.
        """
        if not isinstance(data, dict):
            raise TypeError("BrepFingerprint data must be a dict")
        hash_hex = data.get("hash")
        if not isinstance(hash_hex, str):
            raise ValueError("BrepFingerprint data missing 'hash' string")
        normal = data.get("normal")
        centroid = data.get("centroid")
        area_mm2 = data.get("area_mm2")
        if (
            not isinstance(normal, (list, tuple))
            or not isinstance(centroid, (list, tuple))
            or area_mm2 is None
        ):
            raise ValueError(
                "BrepFingerprint data must include normal, centroid, area_mm2"
            )
        return cls(
            hash_hex=hash_hex,
            normal=tuple(float(v) for v in normal),  # type: ignore[arg-type]
            centroid=tuple(float(v) for v in centroid),  # type: ignore[arg-type]
            area_mm2=float(area_mm2),
        )

    @classmethod
    def from_face_dict(cls, face_dict: dict[str, Any]) -> BrepFingerprint:
        """Construct from a brep interrogator face dict, computing the hash.

        Canonical construction path: the caller has a face dict from
        ``brep.interrogator.interrogate`` (or ``BrepFace.to_dict``)
        and wants a typed fingerprint without hand-computing the hash.
        """
        hash_hex = _compute_hash(face_dict)
        return cls(
            hash_hex=hash_hex,
            normal=tuple(float(v) for v in face_dict["normal"]),  # type: ignore[arg-type]
            centroid=tuple(float(v) for v in face_dict["centroid"]),  # type: ignore[arg-type]
            area_mm2=float(face_dict["area_mm2"]),
        )


__all__ = ["BrepFingerprint"]
