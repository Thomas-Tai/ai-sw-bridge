"""Tests for checkpoint/gc.py (audit_review.md §2.9)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_sw_bridge.checkpoint import CheckpointStore, commit_post_feature, write_pre_feature
from ai_sw_bridge.checkpoint.gc import GCReport, GCPolicy, run


def _spec(name: str = "TestPart") -> dict:
    return {
        "name": name,
        "locals": {"X": "1"},
        "features": [{"name": "F", "type": "boss_extrude_blind"}],
    }


def _seed(
    root: Path,
    part_name: str,
    count: int,
    *,
    sleep_between: float = 0.005,
) -> CheckpointStore:
    """Insert *count* committed checkpoints for *part_name*."""
    store = CheckpointStore(part_name=part_name, root=root)
    feat = _spec(part_name)["features"][0]
    for i in range(count):
        row_id = write_pre_feature(
            store, spec=_spec(part_name), feature=feat, feature_index=i
        )
        commit_post_feature(store, row_id, already_built=[feat])
        if sleep_between:
            time.sleep(sleep_between)
    store.close()
    return store


# ---------------------------------------------------------------------------
# Policy construction
# ---------------------------------------------------------------------------


def test_policy_defaults() -> None:
    p = GCPolicy()
    assert p.max_count_per_part == 100
    assert p.max_age_days == 30
    assert p.max_db_size_mb == 50.0


def test_policy_from_toml_full() -> None:
    p = GCPolicy.from_toml(
        {
            "max_count_per_part": 25,
            "max_age_days": 7,
            "max_db_size_mb": 10.0,
        }
    )
    assert p.max_count_per_part == 25
    assert p.max_age_days == 7
    assert p.max_db_size_mb == 10.0


def test_policy_from_toml_partial() -> None:
    p = GCPolicy.from_toml({"max_count_per_part": 5})
    assert p.max_count_per_part == 5
    assert p.max_age_days == 30  # default
    assert p.max_db_size_mb == 50.0


def test_policy_from_toml_ignores_unknown() -> None:
    p = GCPolicy.from_toml({"max_count_per_part": 5, "unrelated_key": True})
    assert p.max_count_per_part == 5


def test_policy_from_toml_bad_input_returns_defaults() -> None:
    p = GCPolicy.from_toml("not a dict")  # type: ignore[arg-type]
    assert p == GCPolicy()


# ---------------------------------------------------------------------------
# Run outcomes
# ---------------------------------------------------------------------------


def test_run_on_missing_root_is_noop(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    report = run(root=missing)
    assert report == GCReport(0, 0, 0, 0, {})


def test_run_with_no_policy_dimensions_disabled(tmp_path: Path) -> None:
    _seed(tmp_path, "PartA", 5)
    # Every dimension disabled -> nothing pruned.
    report = run(root=tmp_path, policy=GCPolicy(None, None, None))
    assert report.rows_pruned == 0
    assert report.rows_remaining == 5


def test_max_count_retention(tmp_path: Path) -> None:
    _seed(tmp_path, "PartA", 10)
    report = run(
        root=tmp_path,
        policy=GCPolicy(max_count_per_part=3, max_age_days=None, max_db_size_mb=None),
    )
    assert report.rows_pruned == 7
    assert report.rows_remaining == 3
    # The 3 remaining are the most recent.
    store = CheckpointStore(part_name="PartA", root=tmp_path)
    rows = store.query()
    store.close()
    assert len(rows) == 3
    indexes = sorted(r.feature_index for r in rows)
    assert indexes == [7, 8, 9]


def test_max_age_pruning(tmp_path: Path) -> None:
    _seed(tmp_path, "PartA", 5)
    # Pretend it's 60 days in the future; everything is older than 30 days.
    future = datetime.now(timezone.utc) + timedelta(days=60)
    report = run(
        root=tmp_path,
        policy=GCPolicy(max_count_per_part=None, max_age_days=30, max_db_size_mb=None),
        now=future,
    )
    assert report.rows_pruned == 5
    assert report.rows_remaining == 0


def test_max_age_keeps_recent(tmp_path: Path) -> None:
    _seed(tmp_path, "PartA", 3)
    # now = present; rows are fresh, so nothing pruned by age alone.
    report = run(
        root=tmp_path,
        policy=GCPolicy(max_count_per_part=None, max_age_days=30, max_db_size_mb=None),
    )
    assert report.rows_pruned == 0
    assert report.rows_remaining == 3


def test_max_db_size_cap(tmp_path: Path) -> None:
    # 50 rows, then cap the DB at 1 byte — forces everything to drop.
    _seed(tmp_path, "PartA", 50)
    report = run(
        root=tmp_path,
        policy=GCPolicy(
            max_count_per_part=None, max_age_days=None, max_db_size_mb=1e-6
        ),
    )
    assert report.rows_pruned > 0
    assert report.rows_remaining < 50


def test_run_across_multiple_parts(tmp_path: Path) -> None:
    _seed(tmp_path, "PartA", 10)
    _seed(tmp_path, "PartB", 8)
    report = run(
        root=tmp_path,
        policy=GCPolicy(max_count_per_part=2, max_age_days=None, max_db_size_mb=None),
    )
    assert report.files_visited == 2
    assert report.rows_pruned == (10 - 2) + (8 - 2)  # 14
    assert report.rows_remaining == 4
    assert report.per_file["PartA.sqlite"]["rows_pruned"] == 8
    assert report.per_file["PartB.sqlite"]["rows_pruned"] == 6


def test_bytes_freed_is_non_negative(tmp_path: Path) -> None:
    _seed(tmp_path, "PartA", 10)
    report = run(
        root=tmp_path,
        policy=GCPolicy(max_count_per_part=1, max_age_days=None, max_db_size_mb=None),
    )
    assert report.bytes_freed >= 0


def test_gc_does_not_touch_solidworks() -> None:
    """Pure-SQLite guarantee: gc.py never imports sw_com or builder.

    Enforced via AST scan of gc.py's import statements so the check
    is deterministic (sys.modules depends on test execution order).
    """
    import ast
    from pathlib import Path

    import ai_sw_bridge.checkpoint.gc as gc_mod

    src_path = Path(gc_mod.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))

    forbidden = {"ai_sw_bridge.sw_com", "ai_sw_bridge.spec.builder"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden:
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module in forbidden
                or any(node.module.startswith(f"{m}.") for m in forbidden)
            ):
                found.add(node.module)
    assert not found, f"gc.py imports COM-touching modules: {found}"
