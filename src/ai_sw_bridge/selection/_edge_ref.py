"""DurableEdgeRef — a durable reference to a B-rep *edge* (spec.md §5, Phase 0).

The face-shaped :class:`DurableRef` carries a `BrepFingerprint` (normal /
centroid / area) — meaningless for an edge. ``DurableEdgeRef`` is the edge
analog: it anchors an edge across a rebuild by its durable
``GetPersistReference3`` token (tier 1), carrying the edge endpoints alongside
for human readability and a future edge-fingerprint fallback.

v1 resolves by the **persist token only** — proven robust through both rebuild
and save→close→reopen (``spike_edge_persist`` = PASS). The endpoint geometry is
stored but not yet used for resolution (an edge fingerprint-fallback, analogous
to the face one, is deferred). When ``persist_id`` is ``None`` the edge is not
durably resolvable yet and the ref degrades to "unresolved".

Geometry comes from ``IEdge.GetCurveParams2`` upstream (``brep.interrogator``);
``start`` / ``end`` are the curve endpoints in metres, part frame.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any


def _b64_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _vec3(seq: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(seq, (list, tuple)) or len(seq) != 3:
        raise ValueError(f"{name} must be a 3-element sequence, got {seq!r}")
    return (float(seq[0]), float(seq[1]), float(seq[2]))


@dataclass(frozen=True)
class DurableEdgeRef:
    """Durable reference to a B-rep edge (persist token + endpoint geometry).

    Fields:

    * ``persist_id`` — raw bytes from ``GetPersistReference3``; ``None`` when no
      token was captured (then the ref is not durably resolvable in v1).
    * ``start`` / ``end`` — edge endpoints (metres, part frame).
    * ``length`` — arc length when the interrogator's curve read succeeded,
      chord length otherwise (see ``BrepEdge.curve_mid_source``).
    * ``midpoint`` — curve midpoint (parametric midpoint) when captured;
      ``None`` when the manifest edge predates the curve-mid upgrade. The
      edge-fingerprint resolver forwards this into the match predicate's
      midpoint gate so a captured true curve midpoint auto-discriminates
      straight-from-curved edges (no predicate change required).
    * ``role_hint`` — free-form label (default ``"edge"``).
    """

    persist_id: bytes | None
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    length: float
    role_hint: str = "edge"
    midpoint: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        if self.persist_id is not None and not isinstance(self.persist_id, bytes):
            raise TypeError(
                f"persist_id must be bytes or None, got {type(self.persist_id).__name__}"
            )
        if len(self.start) != 3 or len(self.end) != 3:
            raise ValueError("start and end must be 3-tuples")
        if not isinstance(self.role_hint, str) or not self.role_hint:
            raise ValueError("role_hint must be a non-empty string")
        if self.midpoint is not None and len(self.midpoint) != 3:
            raise ValueError("midpoint must be a 3-tuple or None")

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form. ``persist_id`` is base64url (no padding) when
        present and omitted entirely when ``None`` — never serialized as null.
        ``midpoint`` is likewise omitted when ``None`` (legacy refs)."""
        out: dict[str, Any] = {
            "start": list(self.start),
            "end": list(self.end),
            "length": self.length,
            "role_hint": self.role_hint,
        }
        if self.persist_id is not None:
            out["persist_id"] = (
                base64.urlsafe_b64encode(self.persist_id).decode("ascii").rstrip("=")
            )
        if self.midpoint is not None:
            out["midpoint"] = list(self.midpoint)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableEdgeRef:
        """Inverse of :meth:`to_dict`. Missing ``persist_id`` -> ``None``.
        Missing ``midpoint`` -> ``None`` (legacy refs)."""
        if not isinstance(data, dict):
            raise TypeError("DurableEdgeRef data must be a dict")
        start = _vec3(data.get("start"), "start")
        end = _vec3(data.get("end"), "end")
        length = data.get("length")
        if length is None:
            raise ValueError("DurableEdgeRef data missing 'length'")
        role_hint = data.get("role_hint") or "edge"

        persist_b64 = data.get("persist_id")
        persist_id: bytes | None
        if persist_b64 is None:
            persist_id = None
        elif isinstance(persist_b64, str):
            persist_id = _b64_decode(persist_b64)
        else:
            raise TypeError(
                f"persist_id must be a base64url string, got {type(persist_b64).__name__}"
            )

        midpoint_raw = data.get("midpoint")
        midpoint: tuple[float, float, float] | None
        if midpoint_raw is None:
            midpoint = None
        else:
            midpoint = _vec3(midpoint_raw, "midpoint")

        return cls(
            persist_id=persist_id,
            start=start,
            end=end,
            length=float(length),
            role_hint=role_hint,
            midpoint=midpoint,
        )

    @classmethod
    def from_manifest_edge(cls, edge: dict[str, Any]) -> DurableEdgeRef:
        """Build from one serialized brep-manifest edge (``Manifest._serialize_edge``).

        The manifest edge shape carries ``start`` / ``end`` / ``length`` /
        ``midpoint`` plus an optional base64url ``persist_id`` (present when
        ``persist_capture`` was on at build time). ``midpoint`` is optional so
        older manifests without it still round-trip.
        """
        if not isinstance(edge, dict):
            raise TypeError("manifest edge must be a dict")
        start = _vec3(edge.get("start"), "start")
        end = _vec3(edge.get("end"), "end")
        length = edge.get("length")
        if length is None:
            raise ValueError("manifest edge missing 'length'")

        persist_b64 = edge.get("persist_id")
        persist_id: bytes | None
        if persist_b64 is None:
            persist_id = None
        elif isinstance(persist_b64, str):
            persist_id = _b64_decode(persist_b64)
        else:
            raise TypeError(
                f"persist_id must be a base64url string, got {type(persist_b64).__name__}"
            )

        midpoint_raw = edge.get("midpoint")
        midpoint: tuple[float, float, float] | None
        if midpoint_raw is None:
            midpoint = None
        else:
            midpoint = _vec3(midpoint_raw, "midpoint")

        return cls(
            persist_id=persist_id,
            start=start,
            end=end,
            length=float(length),
            role_hint=str(edge.get("role_hint") or "edge"),
            midpoint=midpoint,
        )


__all__ = ["DurableEdgeRef"]
