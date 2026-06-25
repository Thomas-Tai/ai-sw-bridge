"""SQLite-backed BATCH-TRANSACTION ledger (resilience Tier-2 durability).

Distinct from :mod:`ai_sw_bridge.checkpoint.store`, which is a per-FEATURE
geometry checkpoint ledger (every row carries a ``pre_tree_hash`` /
``post_tree_hash``). A *batch transaction* is a different entity: it has an
intent payload (the declarative proposal list), a ``spec_hash``, and a
PENDING|COMMITTED|FAILED status — but **no geometric tree hash**. Forcing it
into the ``checkpoints`` table would mean writing dummy values into NOT-NULL
hash columns, so the resilience journal gets its own table here.

Lifecycle (the single atomic terminal save of the v1.x batch contract):

* :meth:`insert_pending` writes ``status='pending'`` with the proposals JSON
  BEFORE the batch runs and returns the transaction id.
* :meth:`mark_committed` flips it to ``status='committed'`` once the supervised
  ``execute()`` reaches a recovered/successful terminal state.
* :meth:`mark_failed` flips it to ``status='failed'``.

A host crash mid-recovery therefore leaves the row ``pending`` on disk — the
durable anchor a next process reads via :meth:`get_pending_transactions` to
resume (replay the intent) or roll back. One global DB (cross-doc) so all
unfinished transactions are discoverable from a single place on restart.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(".checkpoints")
_DEFAULT_DB_NAME = "_transactions.sqlite"


class TransactionStatus(str, Enum):
    """Batch-transaction lifecycle states."""

    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id              TEXT    PRIMARY KEY,
    doc_path        TEXT    NOT NULL,
    spec_hash       TEXT    NOT NULL,
    intent_payload  TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_txn_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_txn_doc ON transactions(doc_path);
"""

_SELECT_COLUMNS = (
    "id, doc_path, spec_hash, intent_payload, status, created_at, updated_at"
)


@dataclass(frozen=True)
class Transaction:
    """One row of the ``transactions`` table."""

    id: str
    doc_path: str
    spec_hash: str
    intent_payload: str
    status: TransactionStatus
    created_at: str
    updated_at: str


def _row(row: tuple[Any, ...]) -> Transaction:
    return Transaction(
        id=row[0],
        doc_path=row[1],
        spec_hash=row[2],
        intent_payload=row[3],
        status=TransactionStatus(row[4]),
        created_at=row[5],
        updated_at=row[6],
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TransactionStore:
    """Per-host SQLite ledger of batch transactions (PENDING|COMMITTED|FAILED).

    Args:
        root: Parent directory for the ledger DB. Defaults to ``./.checkpoints``
            (co-located with the feature checkpoints). Tests pass ``tmp_path``.
        db_name: Ledger filename within *root*.
    """

    def __init__(
        self, root: Path | None = None, *, db_name: str = _DEFAULT_DB_NAME
    ) -> None:
        self._root = Path(root) if root is not None else _DEFAULT_ROOT
        self._db_path = self._root / db_name
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        self._conn = conn
        return conn

    # -- writes ------------------------------------------------------------

    def insert_pending(
        self,
        *,
        doc_path: str,
        intent_payload: str,
        spec_hash: str,
        txn_id: str | None = None,
        now: str | None = None,
    ) -> str:
        """Write a ``status='pending'`` row before the batch runs; return its id."""
        conn = self._connect()
        tid = txn_id or uuid.uuid4().hex
        ts = now or _utcnow()
        conn.execute(
            "INSERT INTO transactions "
            "(id, doc_path, spec_hash, intent_payload, status, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                doc_path,
                spec_hash,
                intent_payload,
                TransactionStatus.PENDING.value,
                ts,
                ts,
            ),
        )
        conn.commit()
        return tid

    def mark_committed(self, txn_id: str, *, now: str | None = None) -> None:
        """Transition a pending row to ``status='committed'``."""
        self._transition(txn_id, TransactionStatus.COMMITTED, now)

    def mark_failed(self, txn_id: str, *, now: str | None = None) -> None:
        """Transition a pending row to ``status='failed'``."""
        self._transition(txn_id, TransactionStatus.FAILED, now)

    def _transition(self, txn_id: str, to: TransactionStatus, now: str | None) -> None:
        conn = self._connect()
        cur = conn.execute(
            "UPDATE transactions SET status = ?, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (to.value, now or _utcnow(), txn_id, TransactionStatus.PENDING.value),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise LookupError(
                f"no pending transaction id={txn_id!r} to mark {to.value}"
            )

    # -- reads -------------------------------------------------------------

    def get(self, txn_id: str) -> Transaction | None:
        conn = self._connect()
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM transactions WHERE id = ?",
            (txn_id,),
        ).fetchone()
        return _row(row) if row is not None else None

    def get_pending_transactions(self) -> list[Transaction]:
        """Every still-PENDING transaction — the host-crash resume queue."""
        conn = self._connect()
        rows = conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM transactions WHERE status = ? "
            "ORDER BY created_at ASC, id ASC",
            (TransactionStatus.PENDING.value,),
        ).fetchall()
        return [_row(r) for r in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
