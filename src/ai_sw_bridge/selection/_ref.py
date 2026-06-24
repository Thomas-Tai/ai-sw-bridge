"""DurableRef — durable topological reference (spec.md §5.1).

A ``DurableRef`` points at a face/edge/plane across a rebuild. The
resolve fallback hierarchy (codified, deterministic — spec §5.1) is:

1. ``persist_id`` via ``GetObjectByPersistReference3`` (S-PERSIST GREEN).
2. ``fingerprint`` re-match against the current body's brep block
   (the shipped ``brep/`` resolver path; lossy across large edits).
3. Client-side hand-off (Pointer-CAD / CADialogue; out of bridge core).

The wire/manifest form carries ``persist_id`` as base64url (no
padding) so it's JSON-safe and URL-safe; the in-memory form keeps
raw ``bytes`` so the byte-equality check in spec §5.3 is direct.
When S-PERSIST is RED or unrun, ``persist_id`` is ``None`` and the
``persist_id`` key is omitted from the serialized dict (no null
sentinels in the manifest).

``role_hint`` is a free-form string (e.g. ``"+z_outboard"``) mirroring
``brep.interrogator.BrepFace.role_hint``. It disambiguates when two
faces share a fingerprint-preimage geometry (rare — would require
identical normal + centroid + area), and is the last-chance tiebreak
before client-side hand-off.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from ._fingerprint import BrepFingerprint


@dataclass(frozen=True)
class DurableRef:
    """Durable reference to a topological entity (face / edge / plane).

    Fields:

    * ``persist_id`` — raw bytes from ``GetPersistReference3``; ``None``
      when S-PERSIST is RED or the ref was constructed pre-GREEN.
    * ``fingerprint`` — the B-rep identity hash + source geometry.
    * ``role_hint`` — symbolic role (e.g. ``"+z_outboard"``) matching
      ``brep`` role hints; aids disambiguation and human readability.
    """

    persist_id: bytes | None
    fingerprint: BrepFingerprint
    role_hint: str

    def __post_init__(self) -> None:
        if self.persist_id is not None and not isinstance(self.persist_id, bytes):
            raise TypeError(
                f"persist_id must be bytes or None, got {type(self.persist_id).__name__}"
            )
        if not isinstance(self.role_hint, str) or not self.role_hint:
            raise ValueError("role_hint must be a non-empty string")

    # ------------------------------------------------------------------
    # Serialization (manifest / wire format)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form for the manifest.

        ``persist_id`` is base64url-encoded (no padding) when present
        and omitted entirely when ``None`` — never serialized as
        ``null``. That keeps the RED-spike manifest byte-identical to
        today's brep-only references.
        """
        out: dict[str, Any] = {
            "fingerprint": self.fingerprint.to_dict(),
            "role_hint": self.role_hint,
        }
        if self.persist_id is not None:
            out["persist_id"] = (
                base64.urlsafe_b64encode(self.persist_id).decode("ascii").rstrip("=")
            )
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableRef:
        """Inverse of :meth:`to_dict`.

        Accepts both the padded and unpadded base64url forms for
        ``persist_id`` (the writer strips padding; older writers may
        not). Missing ``persist_id`` round-trips to ``None`` — the
        first-class S-PERSIST RED state.
        """
        if not isinstance(data, dict):
            raise TypeError("DurableRef data must be a dict")
        fp_data = data.get("fingerprint")
        if fp_data is None:
            raise ValueError("DurableRef data missing 'fingerprint'")
        fingerprint = BrepFingerprint.from_dict(fp_data)

        role_hint = data.get("role_hint")
        if not isinstance(role_hint, str) or not role_hint:
            raise ValueError("DurableRef data missing or empty 'role_hint'")

        persist_b64 = data.get("persist_id")
        persist_id: bytes | None
        if persist_b64 is None:
            persist_id = None
        elif isinstance(persist_b64, str):
            # Restore padding before decode; base64.urlsafe_b64decode is
            # lenient but explicit padding is safer across Py versions.
            pad = "=" * (-len(persist_b64) % 4)
            persist_id = base64.urlsafe_b64decode(persist_b64 + pad)
        else:
            raise TypeError(
                f"persist_id must be a base64url string, got {type(persist_b64).__name__}"
            )

        return cls(
            persist_id=persist_id,
            fingerprint=fingerprint,
            role_hint=role_hint,
        )

    @classmethod
    def from_manifest_face(cls, face: dict[str, Any]) -> DurableRef:
        """Build a ``DurableRef`` from one serialized brep-manifest face.

        The manifest face shape (``brep.manifest.Manifest._serialize_face``)
        differs from :meth:`to_dict`: the fingerprint is stored flat — a
        ``fingerprint`` hash string plus top-level ``normal`` / ``centroid`` /
        ``area_mm2`` — rather than nested under a ``fingerprint`` object. This
        adapter bridges that shape so a captured manifest face round-trips
        straight into the resolver without hand-assembling a fingerprint.

        ``persist_id`` (base64url, no padding) is decoded to raw bytes when the
        face carries one (``persist_capture`` was on at build time) and is
        ``None`` otherwise — the first-class fingerprint-only state.
        """
        if not isinstance(face, dict):
            raise TypeError("manifest face must be a dict")

        normal = face.get("normal")
        centroid = face.get("centroid")
        area_mm2 = face.get("area_mm2")
        if (
            not isinstance(normal, (list, tuple))
            or not isinstance(centroid, (list, tuple))
            or area_mm2 is None
        ):
            raise ValueError("manifest face must include normal, centroid, area_mm2")
        fingerprint = BrepFingerprint.from_face_dict(
            {"normal": normal, "centroid": centroid, "area_mm2": area_mm2}
        )

        role_hint = face.get("role_hint")
        if not isinstance(role_hint, str) or not role_hint:
            role_hint = "unknown"

        persist_b64 = face.get("persist_id")
        persist_id: bytes | None
        if persist_b64 is None:
            persist_id = None
        elif isinstance(persist_b64, str):
            pad = "=" * (-len(persist_b64) % 4)
            persist_id = base64.urlsafe_b64decode(persist_b64 + pad)
        else:
            raise TypeError(
                f"persist_id must be a base64url string, got {type(persist_b64).__name__}"
            )

        return cls(
            persist_id=persist_id,
            fingerprint=fingerprint,
            role_hint=role_hint,
        )


__all__ = ["DurableRef"]
