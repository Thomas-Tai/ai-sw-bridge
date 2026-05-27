"""Live-SW rollback regression (v0.12 E3.5, execution_plan_90d.md #3.12).

End-to-end verification that the L4 checkpoint round-trip works against a
running SOLIDWORKS session:

1. Build the S1b motor-mount plate (MMP) spec with ``--checkpoint``.
2. Confirm one committed checkpoint row per built feature.
3. Corrupt the locals file to simulate a downstream-feature failure.
4. ``rollback_to(checkpoint_5)`` restores the locals.
5. Rebuild; assert the tree hashes match the pre-corruption state.

No SW process restart between build and rollback -- that's the load-bearing
assumption this test guards. Per spec.md §5.5 step 9.

The ``solidworks_only`` marker gates this test to sessions with a live SW
(see ``tests/conftest.py`` for the auto-skip hook).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge.checkpoint import (
    CheckpointStatus,
    CheckpointStore,
    rollback_to,
)
from ai_sw_bridge.spec.builder import _load_locals_map, build, get_sw_app
from ai_sw_bridge.spec.validator import validate

EXAMPLES_ROOT = Path(__file__).resolve().parents[2] / "examples"
MMP_SPEC_PATH = EXAMPLES_ROOT / "motor_mount_plate" / "spec.json"
MMP_LOCALS_PATH = EXAMPLES_ROOT / "s1b_conveyor_locals.txt"
MMP_FEATURE_COUNT = 10


pytestmark = pytest.mark.solidworks_only


def _parse_locals(text: str, tmp_path: Path) -> dict[str, float]:
    """Parse a locals.txt blob via the production parser.

    ``_load_locals_map`` takes a path, so round-trip through a tmp file.
    Returns the fully-resolved name->float map (recursive expressions
    evaluated), so two differently-formatted files with the same semantic
    content compare equal.
    """
    probe = tmp_path / "__locals_probe.txt"
    probe.write_text(text, encoding="utf-8")
    return _load_locals_map(probe)


def _copy_mmp_to(tmp_path: Path) -> tuple[Path, Path]:
    """Copy the MMP spec + locals into tmp_path and rewrite the locals ref."""
    spec_dir = tmp_path / "mmp"
    spec_dir.mkdir()
    spec_copy = spec_dir / "spec.json"
    locals_copy = spec_dir / "locals.txt"
    shutil.copy(MMP_SPEC_PATH, spec_copy)
    shutil.copy(MMP_LOCALS_PATH, locals_copy)
    spec_data = json.loads(spec_copy.read_text(encoding="utf-8"))
    spec_data["locals"] = "locals.txt"
    spec_copy.write_text(json.dumps(spec_data, indent=2), encoding="utf-8")
    return spec_copy, locals_copy


def _load_spec(spec_path: Path) -> dict:
    """Load the spec and normalize its locals path against the spec dir.

    Mirrors the relative-path resolution in ``cli/build.py``: the builder's
    ``_load_locals_map`` reads ``spec['locals']`` verbatim, so a relative
    path must be anchored at the spec's directory before the build runs.
    """
    with spec_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data.get("locals"), str):
        locals_path = Path(data["locals"])
        if not locals_path.is_absolute():
            data["locals"] = str((spec_path.parent / locals_path).resolve())
    return data


def _close_all_docs(sw) -> None:
    """Best-effort: close every open doc without saving.

    The live-SW regression runs multiple builds in one SW session; between
    them we drop any open parts so the next ``create_blank_part`` starts
    from a clean slate. ``CloseAllDocuments`` is the documented late-binding
    API; we ignore any error so a missing method on a SW version doesn't
    fail the test.
    """
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


@pytest.fixture
def mmp_env(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Stage the MMP spec + locals in tmp_path; yield (tmp, spec, locals, cp_root)."""
    spec_copy, locals_copy = _copy_mmp_to(tmp_path)
    cp_root = tmp_path / "checkpoints"
    cp_root.mkdir()
    return tmp_path, spec_copy, locals_copy, cp_root


def test_build_writes_per_feature_checkpoints(mmp_env) -> None:
    """Build MMP with --checkpoint; assert one committed row per feature."""
    _tmp_path, spec_path, _locals_path, cp_root = mmp_env
    spec = _load_spec(spec_path)
    validate(spec, spec_path=spec_path)

    result = build(spec, no_dim=True, checkpoint=True, checkpoint_root=cp_root)
    assert result.ok, f"build failed at feature {result.error_feature}: {result.error}"
    assert len(result.features_built) == MMP_FEATURE_COUNT

    store = CheckpointStore(part_name=spec["name"], root=cp_root)
    try:
        committed = store.query(status=CheckpointStatus.COMMITTED)
    finally:
        store.close()
    assert len(committed) == MMP_FEATURE_COUNT


def test_rollback_restores_locals_after_corruption(mmp_env) -> None:
    """Corrupt locals, rollback to checkpoint 5, assert locals restored."""
    tmp_path, spec_path, locals_path, cp_root = mmp_env
    spec = _load_spec(spec_path)
    validate(spec, spec_path=spec_path)
    sw = get_sw_app()

    try:
        result_a = build(spec, no_dim=True, checkpoint=True, checkpoint_root=cp_root)
        assert (
            result_a.ok
        ), f"build A failed at feature {result_a.error_feature}: {result_a.error}"
        assert len(result_a.features_built) == MMP_FEATURE_COUNT

        store = CheckpointStore(part_name=spec["name"], root=cp_root)
        try:
            committed = store.query(status=CheckpointStatus.COMMITTED)
            assert len(committed) == MMP_FEATURE_COUNT
            pre_hashes = [
                (cp.pre_tree_hash, cp.post_tree_hash)
                for cp in sorted(committed, key=lambda c: c.feature_index)
            ]
            target = sorted(committed, key=lambda c: c.feature_index)[5]
            original_text = locals_path.read_text(encoding="utf-8")
            original_map = _parse_locals(original_text, tmp_path)

            locals_path.write_text(
                '"S1B_MMP_H" = THIS_IS_NOT_A_NUMBER\n',
                encoding="utf-8",
            )
            assert "THIS_IS_NOT_A_NUMBER" in locals_path.read_text(encoding="utf-8")

            rollback_to(store, target.id, locals_path=locals_path)
        finally:
            store.close()

        restored_map = _parse_locals(locals_path.read_text(encoding="utf-8"), tmp_path)
        assert restored_map == original_map, (
            "restored locals dict diverged from original; "
            "rollback did not preserve pre-corruption equation values"
        )

        audit_store = CheckpointStore(part_name=spec["name"], root=cp_root)
        try:
            rolled_back = audit_store.query(status=CheckpointStatus.ROLLED_BACK)
        finally:
            audit_store.close()
        assert len(rolled_back) == 1
        assert rolled_back[0].feature_type == "rollback"

        _close_all_docs(sw)

        spec_b = _load_spec(spec_path)
        result_b = build(spec_b, no_dim=True, checkpoint=True, checkpoint_root=cp_root)
        assert (
            result_b.ok
        ), f"build B failed at feature {result_b.error_feature}: {result_b.error}"
        assert len(result_b.features_built) == MMP_FEATURE_COUNT

        final_store = CheckpointStore(part_name=spec["name"], root=cp_root)
        try:
            all_committed = final_store.query(status=CheckpointStatus.COMMITTED)
        finally:
            final_store.close()
        # Within one build, feature_index is unique; pick the most-recent
        # row per index to isolate build B from build A (both share the
        # same store because both use the same spec name). Iterate by
        # descending id so setdefault keeps the NEWEST row per index.
        by_index: dict[int, Any] = {}
        for row in sorted(all_committed, key=lambda c: c.id, reverse=True):
            by_index.setdefault(row.feature_index, row)
        post_hashes = [
            (by_index[i].pre_tree_hash, by_index[i].post_tree_hash)
            for i in range(MMP_FEATURE_COUNT)
            if i in by_index
        ]
        # Most-recent-first query means by_index holds the NEWEST row per
        # feature_index -- which is build B's. Verify the hash sequence
        # matches build A's (same spec + same locals = same tree hashes).
        assert len(post_hashes) == MMP_FEATURE_COUNT
        assert pre_hashes == post_hashes, (
            "tree-hash sequence diverged after rollback+rebuild; "
            "rollback did not restore pre-corruption state"
        )
    finally:
        _close_all_docs(sw)
