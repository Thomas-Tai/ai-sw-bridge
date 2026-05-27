"""Tests for checkpoint/rollback.py (spec.md §5.5)."""

from __future__ import annotations

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


def test_rollback_restores_locals_file(store: CheckpointStore, tmp_path: Path) -> None:
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


# ---------------------------------------------------------------------------
# Live-SW leg — EditRollback + tree-hash verification (FR-v0.11-L4-02)
# ---------------------------------------------------------------------------


class _FakeFeature:
    """Mock IFeature carrying name/type for tree-hash enumeration."""

    def __init__(self, name: str, type_name: str) -> None:
        self.Name = name
        self.GetTypeName2 = type_name
        self._next: "_FakeFeature | None" = None

    def GetNextFeature(self):
        return self._next


class _FakeDoc:
    """Mock IModelDoc2 — controls EditRollback outcome + feature chain.

    The ``edit_rollback_result`` selector lets a test pretend SW
    refused the rollback (returns False), succeeded (True), or raised.
    """

    def __init__(
        self,
        feature_chain: list[tuple[str, str]],
        edit_rollback_result: object = True,
    ) -> None:
        self._features = self._build_chain(feature_chain)
        self._edit_rollback_result = edit_rollback_result

    @staticmethod
    def _build_chain(chain: list[tuple[str, str]]) -> _FakeFeature | None:
        head: _FakeFeature | None = None
        prev: _FakeFeature | None = None
        for name, typ in chain:
            f = _FakeFeature(name, typ)
            if head is None:
                head = f
            if prev is not None:
                prev._next = f
            prev = f
        return head

    @property
    def FirstFeature(self):
        return self._features

    @property
    def EditRollback(self):
        if isinstance(self._edit_rollback_result, Exception):
            raise self._edit_rollback_result
        return self._edit_rollback_result


def test_rollback_with_doc_calls_editrollback_and_verifies_hash(
    store: CheckpointStore,
) -> None:
    """A successful EditRollback + matching tree hash should pass."""
    from ai_sw_bridge.checkpoint.snapshot import _tree_hash

    # Seed two committed checkpoints so we have a non-trivial chain.
    feat = _spec()["features"][0]
    row_id = write_pre_feature(
        store,
        spec=_spec(),
        feature=feat,
        feature_index=0,
        already_built=[],
        build_mode="no_dim",
    )
    commit_post_feature(store, row_id, already_built=[feat])
    target = store.get(row_id)
    assert target is not None

    # Fake doc whose feature chain hashes to the SAME value as
    # target.pre_tree_hash (the empty list — pre_tree_hash for the
    # first feature is hash of []).
    assert target.pre_tree_hash == _tree_hash([])
    doc = _FakeDoc(feature_chain=[])  # empty chain -> hash of []
    result = rollback_to(store, row_id, doc=doc)
    assert result.id == row_id


def test_rollback_with_doc_tree_hash_mismatch_raises(
    store: CheckpointStore,
) -> None:
    """A successful EditRollback but mismatched tree hash should raise."""
    target_id = _commit_one(store)
    # Fake doc returns a feature chain whose hash doesn't match the
    # target's pre_tree_hash (which was hash of []).
    doc = _FakeDoc(
        feature_chain=[("Unexpected_Feat", "sketch_rectangle_on_plane")],
    )
    with pytest.raises(RollbackError, match="tree-hash mismatch"):
        rollback_to(store, target_id, doc=doc)


def test_rollback_with_doc_editrollback_returns_false_raises(
    store: CheckpointStore,
) -> None:
    target_id = _commit_one(store)
    doc = _FakeDoc(feature_chain=[], edit_rollback_result=False)
    with pytest.raises(RollbackError, match="EditRollback returned False"):
        rollback_to(store, target_id, doc=doc)


def test_rollback_with_doc_editrollback_raises_wraps(
    store: CheckpointStore,
) -> None:
    target_id = _commit_one(store)
    doc = _FakeDoc(
        feature_chain=[],
        edit_rollback_result=RuntimeError("COM marshaling failed"),
    )
    with pytest.raises(RollbackError, match="EditRollback raised"):
        rollback_to(store, target_id, doc=doc)


def test_rollback_with_doc_verify_disabled_skips_hash_check(
    store: CheckpointStore,
) -> None:
    """When verify_tree_hash=False, a mismatched chain still passes."""
    target_id = _commit_one(store)
    doc = _FakeDoc(
        feature_chain=[("Mismatched_Feat", "type_x")],
    )
    # Should NOT raise — verification is opt-out.
    result = rollback_to(store, target_id, doc=doc, verify_tree_hash=False)
    assert result.id == target_id
