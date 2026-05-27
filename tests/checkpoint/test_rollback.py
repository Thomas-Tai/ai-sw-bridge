"""Tests for checkpoint/rollback.py (spec.md §5.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.checkpoint import (
    CheckpointStatus,
    CheckpointStore,
    RollbackError,
    commit_post_feature,
    rollback_to,
    write_pre_feature,
)


def _spec() -> dict:
    return {
        "name": "TestPart",
        "locals": {"PART_LENGTH": "80", "PART_WIDTH": "40"},
        "features": [
            {"name": "SK_Body", "type": "sketch_rectangle_on_plane"},
        ],
    }


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(part_name="TestPart", root=tmp_path)


def _commit_one(store: CheckpointStore) -> int:
    row_id = write_pre_feature(
        store,
        spec=_spec(),
        feature=_spec()["features"][0],
        feature_index=0,
        already_built=[],
        build_mode="no_dim",
    )
    commit_post_feature(store, row_id, already_built=[_spec()["features"][0]])
    return row_id


def test_rollback_to_committed_writes_audit_row(
    store: CheckpointStore, tmp_path: Path
) -> None:
    target_id = _commit_one(store)
    target = rollback_to(store, target_id)
    assert target.id == target_id
    # Audit row appended.
    rows = store.query(status=CheckpointStatus.ROLLED_BACK)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.feature_type == "rollback"
    assert "__rollback_to_" in audit.feature_name


def test_rollback_missing_id_raises(store: CheckpointStore) -> None:
    with pytest.raises(RollbackError, match="not found"):
        rollback_to(store, 999)


def test_rollback_pending_target_rejected(store: CheckpointStore) -> None:
    # Insert a pending row and DON'T commit it.
    row_id = write_pre_feature(
        store, spec=_spec(), feature=_spec()["features"][0], feature_index=0
    )
    with pytest.raises(RollbackError, match="status='pending'"):
        rollback_to(store, row_id)


def test_rollback_restores_locals_file(
    store: CheckpointStore, tmp_path: Path
) -> None:
    target_id = _commit_one(store)
    locals_path = tmp_path / "locals.txt"
    rollback_to(store, target_id, locals_path=locals_path)
    text = locals_path.read_text(encoding="utf-8")
    # Sorted name order, one entry per line, "NAME" = value form.
    assert '"PART_LENGTH" = 80' in text
    assert '"PART_WIDTH" = 40' in text


def test_rollback_corrupt_locals_snapshot_raises(
    store: CheckpointStore, tmp_path: Path
) -> None:
    # Commit, then tamper the locals_snapshot JSON in the DB.
    target_id = _commit_one(store)
    conn = store._connect()
    conn.execute(
        "UPDATE checkpoints SET locals_snapshot = ? WHERE id = ?",
        ("not valid json", target_id),
    )
    conn.commit()
    locals_path = tmp_path / "locals.txt"
    with pytest.raises(RollbackError, match="not valid JSON"):
        rollback_to(store, target_id, locals_path=locals_path)


def test_rollback_returns_target_checkpoint(
    store: CheckpointStore,
) -> None:
    target_id = _commit_one(store)
    target = rollback_to(store, target_id)
    assert target.id == target_id
    assert target.status is CheckpointStatus.COMMITTED  # original unchanged


def test_rollback_without_locals_path_skips_restore(
    store: CheckpointStore, tmp_path: Path
) -> None:
    target_id = _commit_one(store)
    # No locals_path -> no file written; audit row still appended.
    rollback_to(store, target_id, locals_path=None)
    assert not (tmp_path / "locals.txt").exists()
    rows = store.query(status=CheckpointStatus.ROLLED_BACK)
    assert len(rows) == 1
