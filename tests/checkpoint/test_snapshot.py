"""Tests for checkpoint/snapshot.py (spec.md §5.3 lifecycle)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.checkpoint import (
    CheckpointStatus,
    CheckpointStore,
    commit_post_feature,
    write_pre_feature,
)


def _spec(name: str = "TestPart") -> dict:
    return {
        "name": name,
        "locals": {"PART_LENGTH": "80", "PART_WIDTH": "40"},
        "features": [
            {"name": "SK_Body", "type": "sketch_rectangle_on_plane"},
            {"name": "Extrude_Body", "type": "boss_extrude_blind"},
        ],
    }


def _feature(index: int) -> dict:
    return _spec()["features"][index]


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(part_name="TestPart", root=tmp_path)


def test_write_pre_feature_opens_pending_row(store: CheckpointStore) -> None:
    row_id = write_pre_feature(
        store,
        spec=_spec(),
        feature=_feature(0),
        feature_index=0,
        already_built=[],
        build_mode="no_dim",
    )
    assert isinstance(row_id, int) and row_id > 0
    cp = store.get(row_id)
    assert cp is not None
    assert cp.status is CheckpointStatus.PENDING
    assert cp.feature_name == "SK_Body"
    assert cp.feature_type == "sketch_rectangle_on_plane"
    assert cp.feature_index == 0
    assert cp.build_mode == "no_dim"


def test_commit_post_feature_transitions_to_committed(
    store: CheckpointStore,
) -> None:
    row_id = write_pre_feature(
        store, spec=_spec(), feature=_feature(0), feature_index=0
    )
    commit_post_feature(store, row_id, already_built=[_feature(0)])
    cp = store.get(row_id)
    assert cp is not None
    assert cp.status is CheckpointStatus.COMMITTED
    assert cp.post_tree_hash is not None
    assert cp.post_tree_hash != cp.pre_tree_hash  # tree grew by one feature


def test_pre_tree_hash_changes_with_already_built(
    store: CheckpointStore,
) -> None:
    r0 = write_pre_feature(
        store, spec=_spec(), feature=_feature(0), feature_index=0, already_built=[]
    )
    commit_post_feature(store, r0, already_built=[_feature(0)])
    r1 = write_pre_feature(
        store,
        spec=_spec(),
        feature=_feature(1),
        feature_index=1,
        already_built=[_feature(0)],
    )
    cp0 = store.get(r0)
    cp1 = store.get(r1)
    assert cp0.pre_tree_hash != cp1.pre_tree_hash


def test_locals_snapshot_captures_spec_locals(
    store: CheckpointStore,
) -> None:
    row_id = write_pre_feature(
        store, spec=_spec(), feature=_feature(0), feature_index=0
    )
    cp = store.get(row_id)
    snap = json.loads(cp.locals_snapshot)
    assert snap == {"PART_LENGTH": "80", "PART_WIDTH": "40"}


def test_mark_failed_still_works_via_store(store: CheckpointStore) -> None:
    row_id = write_pre_feature(
        store, spec=_spec(), feature=_feature(0), feature_index=0
    )
    store.mark_failed(row_id)
    cp = store.get(row_id)
    assert cp.status is CheckpointStatus.FAILED


def test_anonymous_feature_falls_back_to_generated_name(
    store: CheckpointStore,
) -> None:
    row_id = write_pre_feature(
        store,
        spec=_spec(),
        feature={"type": "boss_extrude_blind"},  # no "name"
        feature_index=7,
    )
    cp = store.get(row_id)
    assert cp.feature_name == "__anon_7"
