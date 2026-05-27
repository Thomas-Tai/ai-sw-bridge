"""Tests for checkpoint.store — SQLite checkpoint storage (Task E3.1).

Covers: schema creation, insert/commit/mark_failed lifecycle, query filters
(status / since / limit / most-recent-first ordering), index existence,
WAL mode, cross-session persistence, telemetry counter emission, and
validation errors for bad transitions.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_sw_bridge.checkpoint.store import (
    Checkpoint,
    CheckpointStatus,
    CheckpointStore,
)


def _store(tmp_path: Path, part: str = "test_part") -> CheckpointStore:
    return CheckpointStore(part_name=part, root=tmp_path)


def _insert_pending(
    store: CheckpointStore,
    feature_index: int = 0,
    feature_name: str = "EX_Box",
    feature_type: str = "boss_extrude_blind",
    locals_snapshot: str = '"PART_DIAMETER" = 25.0\n',
    spec_hash: str = "abc123" * 10 + "abcd",
    pre_tree_hash: str = "tree_a" * 10 + "tree",
    build_mode: str = "no-dim",
) -> int:
    return store.insert_pending(
        feature_index=feature_index,
        feature_name=feature_name,
        feature_type=feature_type,
        locals_snapshot=locals_snapshot,
        spec_hash=spec_hash,
        pre_tree_hash=pre_tree_hash,
        build_mode=build_mode,
    )


class TestSchema:
    def test_schema_created_on_open(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store._connect()
        conn = sqlite3.connect(str(store.db_path))
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "checkpoints" in tables
        conn.close()
        store.close()

    def test_columns_match_spec(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store._connect()
        conn = sqlite3.connect(str(store.db_path))
        cols = [
            row[1]
            for row in conn.execute("PRAGMA table_info(checkpoints)").fetchall()
        ]
        conn.close()
        store.close()
        assert cols == [
            "id",
            "part_name",
            "feature_index",
            "feature_name",
            "feature_type",
            "timestamp",
            "locals_snapshot",
            "spec_hash",
            "pre_tree_hash",
            "post_tree_hash",
            "com_call_log",
            "build_mode",
            "status",
        ]

    def test_indexes_exist(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store._connect()
        conn = sqlite3.connect(str(store.db_path))
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        conn.close()
        store.close()
        assert "idx_part_timestamp" in indexes
        assert "idx_status" in indexes

    def test_wal_mode(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store._connect()
        conn = sqlite3.connect(str(store.db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        store.close()
        assert mode.lower() == "wal"

    def test_db_path_layout(self, tmp_path: Path) -> None:
        store = _store(tmp_path, part="motor_mount_plate")
        assert store.db_path == tmp_path / "motor_mount_plate.sqlite"
        store.close()


class TestInsertPending:
    def test_returns_row_id(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        row_id = _insert_pending(store, feature_index=0)
        assert isinstance(row_id, int)
        assert row_id >= 1
        store.close()

    def test_pending_row_fields(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        row_id = _insert_pending(
            store,
            feature_index=3,
            feature_name="EX_Box",
            feature_type="boss_extrude_blind",
            locals_snapshot='"X" = 1.0\n',
            spec_hash="s" * 64,
            pre_tree_hash="t" * 64,
            build_mode="no-dim",
        )
        row = store.get(row_id)
        assert row is not None
        assert row.part_name == "test_part"
        assert row.feature_index == 3
        assert row.feature_name == "EX_Box"
        assert row.feature_type == "boss_extrude_blind"
        assert row.locals_snapshot == '"X" = 1.0\n'
        assert row.spec_hash == "s" * 64
        assert row.pre_tree_hash == "t" * 64
        assert row.post_tree_hash is None
        assert row.com_call_log == ""
        assert row.build_mode == "no-dim"
        assert row.status is CheckpointStatus.PENDING
        store.close()

    def test_timestamp_default_utc_iso(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        row_id = _insert_pending(store)
        row = store.get(row_id)
        assert row is not None
        parsed = datetime.fromisoformat(row.timestamp)
        assert parsed.tzinfo is not None or row.timestamp.endswith("Z") or "+" in row.timestamp
        store.close()

    def test_timestamp_explicit(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        ts = "2026-05-27T12:34:56+00:00"
        row_id = store.insert_pending(
            feature_index=0,
            feature_name="SK_Box",
            feature_type="sketch_rectangle_on_plane",
            locals_snapshot="",
            spec_hash="h" * 64,
            pre_tree_hash="p" * 64,
            build_mode="no-dim",
            timestamp=ts,
        )
        row = store.get(row_id)
        assert row is not None
        assert row.timestamp == ts
        store.close()

    def test_multiple_inserts_increment_id(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        a = _insert_pending(store, feature_index=0)
        b = _insert_pending(store, feature_index=1)
        c = _insert_pending(store, feature_index=2)
        assert a < b < c
        store.close()


class TestCommitAndFail:
    def test_commit_transitions_to_committed(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        row_id = _insert_pending(store)
        store.commit(
            row_id,
            post_tree_hash="post" * 16,
            com_call_log="FeatureExtrusion2 OK\n",
        )
        row = store.get(row_id)
        assert row is not None
        assert row.status is CheckpointStatus.COMMITTED
        assert row.post_tree_hash == "post" * 16
        assert row.com_call_log == "FeatureExtrusion2 OK\n"
        store.close()

    def test_commit_unknown_row_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store._connect()
        with pytest.raises(LookupError):
            store.commit(9999, post_tree_hash="x", com_call_log="")
        store.close()

    def test_commit_already_failed_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        row_id = _insert_pending(store)
        store.mark_failed(row_id)
        with pytest.raises(LookupError):
            store.commit(row_id, post_tree_hash="x", com_call_log="")
        store.close()

    def test_mark_failed_transitions(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        row_id = _insert_pending(store)
        store.mark_failed(row_id)
        row = store.get(row_id)
        assert row is not None
        assert row.status is CheckpointStatus.FAILED
        assert row.post_tree_hash is None
        store.close()

    def test_mark_failed_unknown_row_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store._connect()
        with pytest.raises(LookupError):
            store.mark_failed(9999)
        store.close()

    def test_mark_failed_already_committed_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        row_id = _insert_pending(store)
        store.commit(row_id, post_tree_hash="p", com_call_log="")
        with pytest.raises(LookupError):
            store.mark_failed(row_id)
        store.close()

    def test_record_rollback_inserts_audit_row(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        original = _insert_pending(store)
        store.commit(original, post_tree_hash="p", com_call_log="")
        rb_id = store.record_rollback(
            rolled_back_to_id=original,
            feature_name="EX_Box",
            feature_type="boss_extrude_blind",
            locals_snapshot='"X" = 1.0\n',
            spec_hash="h" * 64,
            pre_tree_hash="pre",
            post_tree_hash="pre",
            build_mode="no-dim",
        )
        row = store.get(rb_id)
        assert row is not None
        assert row.status is CheckpointStatus.ROLLED_BACK
        assert "rollback_to=" in row.com_call_log
        store.close()


class TestQuery:
    def test_query_empty(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.query() == []
        store.close()

    def test_query_returns_most_recent_first(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        a = _insert_pending(store, feature_index=0)
        b = _insert_pending(store, feature_index=1)
        c = _insert_pending(store, feature_index=2)
        rows = store.query()
        ids = [r.id for r in rows]
        assert ids == [c, b, a]
        store.close()

    def test_query_filter_by_status(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        a = _insert_pending(store, feature_index=0)
        b = _insert_pending(store, feature_index=1)
        store.commit(b, post_tree_hash="p", com_call_log="")
        pending = store.query(status=CheckpointStatus.PENDING)
        committed = store.query(status=CheckpointStatus.COMMITTED)
        assert [r.id for r in pending] == [a]
        assert [r.id for r in committed] == [b]
        store.close()

    def test_query_filter_by_since(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        old_ts = "2020-01-01T00:00:00+00:00"
        new_ts = "2099-01-01T00:00:00+00:00"
        store.insert_pending(
            feature_index=0,
            feature_name="SK_Old",
            feature_type="sketch_rectangle_on_plane",
            locals_snapshot="",
            spec_hash="h" * 64,
            pre_tree_hash="p" * 64,
            build_mode="no-dim",
            timestamp=old_ts,
        )
        store.insert_pending(
            feature_index=1,
            feature_name="SK_New",
            feature_type="sketch_rectangle_on_plane",
            locals_snapshot="",
            spec_hash="h" * 64,
            pre_tree_hash="p" * 64,
            build_mode="no-dim",
            timestamp=new_ts,
        )
        rows = store.query(since="2050-01-01T00:00:00+00:00")
        assert len(rows) == 1
        assert rows[0].feature_name == "SK_New"
        store.close()

    def test_query_since_datetime(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _insert_pending(store)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        rows = store.query(since=past)
        assert len(rows) == 1
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        assert store.query(since=future) == []
        store.close()

    def test_query_limit(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(5):
            _insert_pending(store, feature_index=i)
        rows = store.query(limit=3)
        assert len(rows) == 3
        store.close()

    def test_query_scoped_to_part(self, tmp_path: Path) -> None:
        a = CheckpointStore(part_name="part_a", root=tmp_path)
        b = CheckpointStore(part_name="part_b", root=tmp_path)
        _insert_pending(a, feature_index=0)
        _insert_pending(a, feature_index=1)
        _insert_pending(b, feature_index=0)
        assert len(a.query()) == 2
        assert len(b.query()) == 1
        a.close()
        b.close()

    def test_get_returns_none_for_unknown(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.get(9999) is None
        store.close()

    def test_get_scoped_to_part(self, tmp_path: Path) -> None:
        a = CheckpointStore(part_name="part_a", root=tmp_path)
        row_id = _insert_pending(a)
        b = CheckpointStore(part_name="part_b", root=tmp_path)
        assert b.get(row_id) is None
        assert a.get(row_id) is not None
        a.close()
        b.close()


class TestIndexCorrectness:
    def test_part_timestamp_index_used(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(10):
            _insert_pending(store, feature_index=i)
        conn = sqlite3.connect(str(store.db_path))
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM checkpoints "
            "WHERE part_name = ? AND timestamp >= ? ORDER BY timestamp",
            ("test_part", "2000-01-01"),
        ).fetchall()
        conn.close()
        store.close()
        plan_text = " ".join(str(row) for row in plan)
        assert "idx_part_timestamp" in plan_text

    def test_status_index_used(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(10):
            _insert_pending(store, feature_index=i)
        conn = sqlite3.connect(str(store.db_path))
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM checkpoints WHERE status = ?",
            ("pending",),
        ).fetchall()
        conn.close()
        store.close()
        plan_text = " ".join(str(row) for row in plan)
        assert "idx_status" in plan_text


class TestCrossSessionPersistence:
    def test_close_and_reopen_preserves_rows(self, tmp_path: Path) -> None:
        s1 = _store(tmp_path)
        a = _insert_pending(s1, feature_index=0)
        s1.commit(a, post_tree_hash="p", com_call_log="log line 1")
        s1.close()

        s2 = _store(tmp_path)
        rows = s2.query()
        s2.close()
        assert len(rows) == 1
        assert rows[0].status is CheckpointStatus.COMMITTED
        assert rows[0].post_tree_hash == "p"
        assert rows[0].com_call_log == "log line 1"

    def test_separate_parts_separate_dbs(self, tmp_path: Path) -> None:
        a = CheckpointStore(part_name="alpha", root=tmp_path)
        b = CheckpointStore(part_name="beta", root=tmp_path)
        _insert_pending(a)
        _insert_pending(b)
        _insert_pending(b)
        assert a.db_path != b.db_path
        assert len(a.query()) == 1
        assert len(b.query()) == 2
        a.close()
        b.close()


class TestValidation:
    def test_empty_part_name_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            CheckpointStore(part_name="", root=tmp_path)

    def test_root_created_if_missing(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "root"
        store = CheckpointStore(part_name="p", root=nested)
        _insert_pending(store)
        store.close()
        assert store.db_path.exists()

    def test_checkpoint_dataclass_frozen(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        row_id = _insert_pending(store)
        row = store.get(row_id)
        assert row is not None
        with pytest.raises(AttributeError):
            row.status = CheckpointStatus.COMMITTED  # type: ignore[misc]
        store.close()


class TestTelemetryCounter:
    def test_counter_emits_on_writes(self, tmp_path: Path, monkeypatch) -> None:
        events: list[tuple[str, dict[str, str]]] = []

        def fake_counter(name: str, **labels: str) -> None:
            events.append((name, labels))

        import ai_sw_bridge.telemetry as telemetry_mod

        monkeypatch.setattr(telemetry_mod, "counter", fake_counter)

        store = _store(tmp_path)
        store._counter_emit = fake_counter
        row_id = _insert_pending(store)
        store.commit(row_id, post_tree_hash="p", com_call_log="")
        row_id2 = _insert_pending(store)
        store.mark_failed(row_id2)
        store.close()

        outcomes = [labels["outcome"] for _, labels in events if _ == "checkpoint_writes_total"]
        assert "pending" in outcomes
        assert "committed" in outcomes
        assert "failed" in outcomes
