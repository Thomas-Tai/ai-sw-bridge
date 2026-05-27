"""SQLite-backed checkpoint store (spec.md §5.2, §5.3, §5.9).

One SQLite database per part, located at ``./.checkpoints/<part_name>.sqlite``.
The schema mirrors spec.md §5.2 verbatim:

    checkpoints(
        id, part_name, feature_index, feature_name, feature_type,
        timestamp, locals_snapshot, spec_hash, pre_tree_hash,
        post_tree_hash, com_call_log, build_mode, status
    )

Lifecycle
---------

* ``insert_pending(...)`` writes a row with ``status='pending'`` before the
  feature executes and returns the new row id.
* ``commit(row_id, post_tree_hash, com_call_log)`` transitions the row to
  ``status='committed'`` after the feature succeeds.
* ``mark_failed(row_id)`` transitions the row to ``status='failed'`` on
  exception.  The bridge does not auto-rollback (spec.md §5.3 step 9).

The ``status='rolled_back'`` value is written by ``rollback.py`` (E3.2)
through :meth:`record_rollback`.

Concurrency
-----------

WAL mode + a row-level ``part_name`` filter keep concurrent builds of
*different* parts fully parallel. Two builds of the *same* part serialize
on SQLite's write lock — the bridge is single-process per part today,
so this is a correctness backstop rather than a hot path.

Telemetry
---------

Every successful write emits ``checkpoint_writes_total{outcome}`` via the
bound :class:`~ai_sw_bridge.telemetry.Counter`. ``outcome`` is one of
``pending``, ``committed``, ``failed``, ``rolled_back``, ``query_error``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(".checkpoints")


class CheckpointStatus(str, Enum):
    """Checkpoint lifecycle states (spec.md §5.2)."""

    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    part_name       TEXT    NOT NULL,
    feature_index   INTEGER NOT NULL,
    feature_name    TEXT    NOT NULL,
    feature_type    TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,
    locals_snapshot TEXT    NOT NULL,
    spec_hash       TEXT    NOT NULL,
    pre_tree_hash   TEXT    NOT NULL,
    post_tree_hash  TEXT,
    com_call_log    TEXT    NOT NULL,
    build_mode      TEXT    NOT NULL,
    status          TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_part_timestamp
    ON checkpoints(part_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_status
    ON checkpoints(status);
"""


@dataclass(frozen=True)
class Checkpoint:
    """One row of the ``checkpoints`` table.

    ``post_tree_hash`` is ``None`` until the feature commits.  ``com_call_log``
    is the empty string until commit populates it (pending rows pass ``""``).
    """

    id: int
    part_name: str
    feature_index: int
    feature_name: str
    feature_type: str
    timestamp: str
    locals_snapshot: str
    spec_hash: str
    pre_tree_hash: str
    post_tree_hash: str | None
    com_call_log: str
    build_mode: str
    status: CheckpointStatus


def _row_from_tuple(row: tuple[Any, ...]) -> Checkpoint:
    return Checkpoint(
        id=row[0],
        part_name=row[1],
        feature_index=row[2],
        feature_name=row[3],
        feature_type=row[4],
        timestamp=row[5],
        locals_snapshot=row[6],
        spec_hash=row[7],
        pre_tree_hash=row[8],
        post_tree_hash=row[9],
        com_call_log=row[10],
        build_mode=row[11],
        status=CheckpointStatus(row[12]),
    )


_SELECT_COLUMNS = (
    "id, part_name, feature_index, feature_name, feature_type, timestamp, "
    "locals_snapshot, spec_hash, pre_tree_hash, post_tree_hash, "
    "com_call_log, build_mode, status"
)


class CheckpointStore:
    """Per-part SQLite checkpoint store.

    Args:
        part_name: Canonical part name; selects the database file at
            ``<root>/<part_name>.sqlite``.
        root: Parent directory for checkpoint databases.  Defaults to
            ``./.checkpoints``.  Tests pass ``tmp_path`` here.
    """

    def __init__(
        self,
        part_name: str,
        root: Path | None = None,
    ) -> None:
        if not part_name:
            raise ValueError("part_name must be a non-empty string")
        self._part_name = part_name
        self._root = Path(root) if root is not None else _DEFAULT_ROOT
        self._db_path = self._root / f"{part_name}.sqlite"
        self._conn: sqlite3.Connection | None = None
        self._counter_emit: Any | None = None
        try:
            from ..telemetry import counter as _telemetry_counter

            self._counter_emit = _telemetry_counter
        except Exception:
            self._counter_emit = None

    @property
    def part_name(self) -> str:
        return self._part_name

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

    def _emit(self, outcome: str) -> None:
        if self._counter_emit is None:
            return
        try:
            self._counter_emit("checkpoint_writes_total", outcome=outcome)
        except Exception:
            pass

    def insert_pending(
        self,
        *,
        feature_index: int,
        feature_name: str,
        feature_type: str,
        locals_snapshot: str,
        spec_hash: str,
        pre_tree_hash: str,
        build_mode: str,
        timestamp: str | None = None,
    ) -> int:
        """Insert a ``status='pending'`` row before the feature executes.

        Returns the new row id.  Callers pass this id to :meth:`commit` or
        :meth:`mark_failed` after the feature attempt.
        """
        conn = self._connect()
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO checkpoints "
            "(part_name, feature_index, feature_name, feature_type, timestamp, "
            "locals_snapshot, spec_hash, pre_tree_hash, post_tree_hash, "
            "com_call_log, build_mode, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, '', ?, ?)",
            (
                self._part_name,
                feature_index,
                feature_name,
                feature_type,
                ts,
                locals_snapshot,
                spec_hash,
                pre_tree_hash,
                build_mode,
                CheckpointStatus.PENDING.value,
            ),
        )
        conn.commit()
        self._emit("pending")
        assert cur.lastrowid is not None
        return int(cur.lastrowid)

    def commit(
        self,
        row_id: int,
        *,
        post_tree_hash: str,
        com_call_log: str,
    ) -> None:
        """Transition a pending row to ``status='committed'``.

        Only updates rows that are still ``pending`` — protects against a
        stray commit call on a row that was already marked ``failed`` or
        ``rolled_back`` by a concurrent code path.
        """
        conn = self._connect()
        cur = conn.execute(
            "UPDATE checkpoints "
            "SET status = ?, post_tree_hash = ?, com_call_log = ? "
            "WHERE id = ? AND part_name = ? AND status = ?",
            (
                CheckpointStatus.COMMITTED.value,
                post_tree_hash,
                com_call_log,
                row_id,
                self._part_name,
                CheckpointStatus.PENDING.value,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise LookupError(
                f"no pending checkpoint row id={row_id} for part "
                f"{self._part_name!r}"
            )
        self._emit("committed")

    def mark_failed(self, row_id: int) -> None:
        """Transition a pending row to ``status='failed'``."""
        conn = self._connect()
        cur = conn.execute(
            "UPDATE checkpoints SET status = ? WHERE id = ? AND part_name = ? "
            "AND status = ?",
            (
                CheckpointStatus.FAILED.value,
                row_id,
                self._part_name,
                CheckpointStatus.PENDING.value,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise LookupError(
                f"no pending checkpoint row id={row_id} for part "
                f"{self._part_name!r}"
            )
        self._emit("failed")

    def record_rollback(
        self,
        *,
        rolled_back_to_id: int,
        feature_name: str,
        feature_type: str,
        locals_snapshot: str,
        spec_hash: str,
        pre_tree_hash: str,
        post_tree_hash: str,
        build_mode: str,
        feature_index: int = -1,
        timestamp: str | None = None,
    ) -> int:
        """Insert a ``status='rolled_back'`` audit row (spec.md §5.5 step 9)."""
        conn = self._connect()
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO checkpoints "
            "(part_name, feature_index, feature_name, feature_type, timestamp, "
            "locals_snapshot, spec_hash, pre_tree_hash, post_tree_hash, "
            "com_call_log, build_mode, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self._part_name,
                feature_index,
                feature_name,
                feature_type,
                ts,
                locals_snapshot,
                spec_hash,
                pre_tree_hash,
                post_tree_hash,
                f"rollback_to={rolled_back_to_id}",
                build_mode,
                CheckpointStatus.ROLLED_BACK.value,
            ),
        )
        conn.commit()
        self._emit("rolled_back")
        assert cur.lastrowid is not None
        return int(cur.lastrowid)

    def get(self, row_id: int) -> Checkpoint | None:
        """Fetch one row by id, scoped to this store's part_name."""
        conn = self._connect()
        row = conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM checkpoints "
            "WHERE id = ? AND part_name = ?",
            (row_id, self._part_name),
        ).fetchone()
        if row is None:
            return None
        return _row_from_tuple(row)

    def query(
        self,
        *,
        status: CheckpointStatus | None = None,
        since: datetime | str | None = None,
        limit: int | None = None,
    ) -> list[Checkpoint]:
        """Query checkpoints for this part, most-recent-first."""
        conn = self._connect()
        clauses = ["part_name = ?"]
        params: list[Any] = [self._part_name]
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if since is not None:
            ts = since.isoformat() if isinstance(since, datetime) else since
            clauses.append("timestamp >= ?")
            params.append(ts)
        sql = (
            f"SELECT {_SELECT_COLUMNS} FROM checkpoints "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY timestamp DESC, id DESC"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = conn.execute(sql, params).fetchall()
        return [_row_from_tuple(r) for r in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
