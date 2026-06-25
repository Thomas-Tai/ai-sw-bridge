"""Resilience layer — supervised, crash-recoverable COM sessions.

The commercial session layer that wraps the (fail-soft, atomic-save) batch
transaction in a detect -> respawn -> idempotent-replay envelope, shielding the
agent from upstream SOLIDWORKS deaths. See ``docs/supervised_session_spec.md`` and
``docs/supervised_session_test_spec.md``.
"""

from .journal_adapter import TransactionStoreJournal
from .session import (
    ExecutorSeatController,
    FileSnapshotter,
    InMemoryJournal,
    SeatRespawnTimeout,
    SupervisedSession,
    SystemClock,
)

__all__ = [
    "SupervisedSession",
    "ExecutorSeatController",
    "SeatRespawnTimeout",
    "FileSnapshotter",
    "InMemoryJournal",
    "SystemClock",
    "TransactionStoreJournal",
]
