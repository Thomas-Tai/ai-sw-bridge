"""Local SQLite telemetry store for ai-sw-bridge.

Stores metric emissions as rows in a per-user SQLite database. No PII, no
automatic upload (per privacy_review.md). Schema mirrors spec.md §8.8.

Performance: records are buffered in memory and flushed to SQLite on
close() or when the buffer exceeds _FLUSH_THRESHOLD rows. This keeps
Counter.inc under the 100 µs budget (spec.md §8.8) by amortizing WAL
sync costs.
"""

from __future__ import annotations

import atexit
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_DB_DIR = Path.home() / ".ai-sw-bridge"
_DEFAULT_DB_NAME = "telemetry.sqlite"
_FLUSH_THRESHOLD = 64


def _default_db_path() -> Path:
    return _DEFAULT_DB_DIR / _DEFAULT_DB_NAME


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    metric_name TEXT    NOT NULL,
    labels_json TEXT    NOT NULL DEFAULT '{}',
    value       REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_name_ts
    ON metrics (metric_name, timestamp);
"""


class TelemetryStore:
    """Buffered SQLite metrics store.

    Records are accumulated in an in-memory buffer and flushed to SQLite
    when the buffer size exceeds _FLUSH_THRESHOLD or on close(). This
    amortizes WAL sync cost across many emissions, keeping per-emission
    overhead well under the spec budget (Counter.inc < 100 µs).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._buffer: list[tuple[str, str, str, float]] = []
        atexit.register(self.close)

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(str(self._db_path))
        conn.executescript(_SCHEMA_SQL)
        conn.execute("PRAGMA journal_mode=WAL")
        self._conn = conn
        return conn

    @property
    def db_path(self) -> Path:
        return self._db_path

    def record(
        self,
        metric_name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Buffer one metric emission. Flushes automatically when threshold is reached."""
        ts = datetime.now(timezone.utc).isoformat()
        labels_json = json.dumps(labels or {}, sort_keys=True)
        self._buffer.append((ts, metric_name, labels_json, value))
        if len(self._buffer) >= _FLUSH_THRESHOLD:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        conn = self._connect()
        conn.executemany(
            "INSERT INTO metrics (timestamp, metric_name, labels_json, value) "
            "VALUES (?, ?, ?, ?)",
            self._buffer,
        )
        conn.commit()
        self._buffer.clear()

    def query(
        self,
        metric_name: str,
        since: datetime | None = None,
        labels: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query metrics rows, optionally filtered by name, time, and labels."""
        self._flush()
        conn = self._connect()
        clauses: list[str] = ["metric_name = ?"]
        params: list[Any] = [metric_name]
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since.isoformat())
        rows = conn.execute(
            f"SELECT id, timestamp, metric_name, labels_json, value "
            f"FROM metrics WHERE {' AND '.join(clauses)} ORDER BY timestamp",
            params,
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            row_labels = json.loads(row[3])
            if labels:
                if not all(row_labels.get(k) == v for k, v in labels.items()):
                    continue
            results.append(
                {
                    "id": row[0],
                    "timestamp": row[1],
                    "metric_name": row[2],
                    "labels": row_labels,
                    "value": row[4],
                }
            )
        return results

    def close(self) -> None:
        self._flush()
        if self._conn is not None:
            self._conn.close()
            self._conn = None
