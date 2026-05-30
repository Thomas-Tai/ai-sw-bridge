"""Selection package — durable topological references (spec.md §5, Phase 0).

Public API:

- :class:`DurableRef` — a durable reference to a face/edge/plane that
  survives a rebuild. Resolves through a deterministic fallback
  hierarchy: persist-id → fingerprint re-match → client-side hand-off.
- :class:`BrepFingerprint` — typed wrapper around a brep face's stable
  16-hex identity hash plus the geometry that produced it.

The ``persist_id`` field is gated on **S-PERSIST**. When the spike is
RED or has not yet run, ``persist_id`` stays ``None`` and the reference
degrades gracefully to fingerprint-only resolution (no regression vs.
today's literal-coordinate selection).
"""

from __future__ import annotations

from ._fingerprint import BrepFingerprint
from ._edge_ref import DurableEdgeRef
from ._ref import DurableRef
from .live import (
    PersistResolution,
    RefResolution,
    capture_persist_id,
    resolve_by_fingerprint,
    resolve_edge_ref,
    resolve_manifest_face,
    resolve_persist_id,
    resolve_ref,
    select_entity,
)

__all__ = [
    "BrepFingerprint",
    "DurableEdgeRef",
    "DurableRef",
    "PersistResolution",
    "RefResolution",
    "capture_persist_id",
    "resolve_by_fingerprint",
    "resolve_edge_ref",
    "resolve_manifest_face",
    "resolve_persist_id",
    "resolve_ref",
    "select_entity",
]
