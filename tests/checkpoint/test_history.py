"""Tests for checkpoint/history.py (spec.md §5.6)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ai_sw_bridge.checkpoint import (
    CheckpointStore,
    by_locals,
    by_part,
    commit_post_feature,
    feature_diff,
    since,
    write_pre_feature,
)


def _spec(locals_data: dict[str, str] | None = None) -> dict:
    return {
        "name": "TestPart",
        "locals": locals_data or {"PART_LENGTH": "80"},
        "features": [
            {"name": "SK_Body", "type": "sketch_rectangle_on_plane"},
        ],
    }


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(part_name="TestPart", root=tmp_path)


def _commit(store: CheckpointStore, *, index: int = 0, spec: dict | None = None) -> int:
    spec = spec or _spec()
    feat = spec["features"][min(index, len(spec["features"]) - 1)]
    row_id = write_pre_feature(
        store, spec=spec, feature=feat, feature_index=index
    )
    commit_post_feature(store, row_id, already_built=[feat])
    return row_id


def test_by_part_returns_all_most_recent_first(
    store: CheckpointStore,
) -> None:
    _commit(store, index=0)
    time.sleep(0.01)
    _commit(store, index=0)
    time.sleep(0.01)
    _commit(store, index=0)
    rows = by_part(store)
    assert len(rows) == 3
    # Most-recent first.
    assert rows[0].id > rows[1].id > rows[2].id


def test_by_part_empty_store(store: CheckpointStore) -> None:
    assert by_part(store) == []


def test_by_locals_matches_canonical_snapshot(
    store: CheckpointStore, tmp_path: Path
) -> None:
    _commit(store)
    locals_path = tmp_path / "locals.txt"
    locals_path.write_text('"PART_LENGTH" = 80\n', encoding="utf-8")
    matches = by_locals(store, locals_path)
    assert len(matches) == 1


def test_by_locals_different_file_returns_empty(
    store: CheckpointStore, tmp_path: Path
) -> None:
    _commit(store, spec=_spec({"PART_LENGTH": "80"}))
    locals_path = tmp_path / "locals.txt"
    locals_path.write_text('"PART_LENGTH" = 99\n', encoding="utf-8")
    assert by_locals(store, locals_path) == []


def test_by_locals_missing_file_returns_empty(
    store: CheckpointStore, tmp_path: Path
) -> None:
    _commit(store)
    assert by_locals(store, tmp_path / "missing.txt") == []


def test_since_filters_by_timestamp(store: CheckpointStore) -> None:
    _commit(store)
    time.sleep(0.01)
    from datetime import datetime, timezone

    cutoff = datetime.now(timezone.utc).isoformat()
    time.sleep(0.01)
    _commit(store)
    _commit(store)
    rows = since(store, cutoff)
    assert len(rows) == 2


def test_since_with_datetime(store: CheckpointStore) -> None:
    _commit(store)
    time.sleep(0.01)
    from datetime import datetime, timezone

    cutoff = datetime.now(timezone.utc)
    time.sleep(0.01)
    _commit(store)
    rows = since(store, cutoff)
    assert len(rows) == 1


def test_feature_diff_no_change(store: CheckpointStore) -> None:
    id_a = _commit(store)
    # Same spec + same locals + same tree -> all False.
    id_b = _commit(store)
    a = store.get(id_a)
    b = store.get(id_b)
    diff = feature_diff(a, b)
    assert diff["a_id"] == id_a
    assert diff["b_id"] == id_b
    # Tree changes because post_tree_hash of a becomes pre_tree_hash of b
    # (one feature added between them); spec + locals stay equal.
    assert diff["spec_changed"] is False
    assert diff["locals_changed"] is False


def test_feature_diff_spec_change(store: CheckpointStore) -> None:
    id_a = _commit(store, spec=_spec({"PART_LENGTH": "80"}))
    id_b = _commit(store, spec=_spec({"PART_LENGTH": "99"}))
    a = store.get(id_a)
    b = store.get(id_b)
    diff = feature_diff(a, b)
    assert diff["locals_changed"] is True


def test_feature_diff_tree_change(store: CheckpointStore) -> None:
    id_a = _commit(store)
    # Force a different post_tree_hash by committing with a different
    # already_built list.
    feat = _spec()["features"][0]
    row_id = write_pre_feature(
        store, spec=_spec(), feature=feat, feature_index=0
    )
    commit_post_feature(store, row_id, already_built=[])  # empty vs [feat]
    a = store.get(id_a)
    b = store.get(row_id)
    diff = feature_diff(a, b)
    assert diff["tree_changed"] is True
