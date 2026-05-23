"""Tests for telemetry.store — SQLite metrics storage."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta

from ai_sw_bridge.telemetry.store import TelemetryStore


def test_record_and_query(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    store.record("builds_total", 1.0, {"mode": "no_dim", "outcome": "ok"})
    store.record("builds_total", 1.0, {"mode": "no_dim", "outcome": "fail"})

    rows = store.query("builds_total")
    assert len(rows) == 2
    assert rows[0]["metric_name"] == "builds_total"
    assert rows[0]["labels"]["mode"] == "no_dim"
    store.close()


def test_query_filters_by_labels(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    store.record("builds_total", 1.0, {"mode": "no_dim", "outcome": "ok"})
    store.record("builds_total", 1.0, {"mode": "parametric", "outcome": "ok"})

    rows = store.query("builds_total", labels={"mode": "no_dim"})
    assert len(rows) == 1
    assert rows[0]["labels"]["mode"] == "no_dim"
    store.close()


def test_query_filters_by_time(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    store.record("builds_total", 1.0, {"mode": "no_dim", "outcome": "ok"})

    since = datetime.now(timezone.utc) + timedelta(hours=1)
    rows = store.query("builds_total", since=since)
    assert len(rows) == 0
    store.close()


def test_db_created_on_first_flush(tmp_path):
    db = tmp_path / "subdir" / "test.sqlite"
    store = TelemetryStore(db_path=db)
    store.record("test_metric", 42.0)
    # Buffered — not on disk yet until flush/close
    assert not db.exists()
    store.close()
    assert db.exists()


def test_buffered_records_flush_on_close(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    store.record("test_metric", 42.0)
    store.close()

    # Read directly from SQLite
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()
    conn.close()
    assert rows[0] == 1


def test_wal_mode(tmp_path):
    db = tmp_path / "test.sqlite"
    store = TelemetryStore(db_path=db)
    store.record("test", 1.0)
    store.close()

    conn = sqlite3.connect(str(db))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"
