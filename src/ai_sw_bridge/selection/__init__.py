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
from ._ref import DurableRef

__all__ = [
    "BrepFingerprint",
    "DurableRef",
]
