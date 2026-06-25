"""Durable journal for SupervisedSession — binds the resilience ``Journal``
protocol to the SQLite :class:`~ai_sw_bridge.checkpoint.TransactionStore`.

The default :class:`~ai_sw_bridge.resilience.session.InMemoryJournal` only
survives within a process. This adapter makes the PENDING|COMMITTED boundary
DURABLE: a host crash mid-recovery leaves a ``pending`` row on disk that a next
process reads (``store.get_pending_transactions()``) to resume or roll back —
the foundation that makes Tier-2 resilience absolute.

Granularity: ONE transaction row per supervised ``execute()`` (the v1.x batch
is one atomic terminal-save transaction, not a per-feature progression). The
intent payload is the declarative proposal list verbatim — the only field a
resume actually needs to replay.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..checkpoint import TransactionStore


def _canonical(proposals: Any) -> str:
    """Stable JSON of the proposal list (the resume intent payload)."""
    return json.dumps(proposals, sort_keys=True, default=str)


class TransactionStoreJournal:
    """Resilience ``Journal`` backed by the durable SQLite transaction ledger.

    Implements ``insert_pending(doc_path, proposals) -> str`` and
    ``commit(row_id) -> None`` by delegating to :class:`TransactionStore`.
    The returned id is an opaque UUID string (the session treats it opaquely).
    """

    def __init__(self, store: TransactionStore) -> None:
        self._store = store

    @property
    def store(self) -> TransactionStore:
        return self._store

    def insert_pending(self, doc_path: str, proposals: list) -> str:
        payload = _canonical(proposals)
        spec_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self._store.insert_pending(
            doc_path=doc_path, intent_payload=payload, spec_hash=spec_hash
        )

    def commit(self, row_id: str, recovery: dict | None = None) -> None:
        self._store.mark_committed(
            row_id,
            recovery_json=json.dumps(recovery, default=str) if recovery else None,
        )

    def mark_failed(self, row_id: str) -> None:
        """Optional terminal-failure marker (not on the Journal protocol; the
        session leaves fatal rows PENDING as the resume anchor, but exposed for
        callers that want to quarantine a known-unrecoverable transaction)."""
        self._store.mark_failed(row_id)
