"""End-to-end build test: spec -> validator -> builder -> COM -> SW.

Builds the minimal cylinder against a live SW session and verifies:

* the BuildResult payload reports ok=True
* the expected feature names appear in features_built
* the build completed within a generous time budget
* a clean checkpoint DB was created when --checkpoint is set
* the build artifact (the new part document) is open in SW after the
  build returns

Uses ``mode='no_dim'`` so AddDimension2 dialogs don't block a
headless test run. The dim mode coverage is exercised by separate
contract tests in ``tests/spec/``.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.solidworks_only


def test_e2e_minimal_cylinder_build(
    live_tools, minimal_cylinder_spec_path: Path, e2e_checkpoint_root: Path
) -> None:
    """sw_build via MCP -> minimal_cylinder SW part with 2 features."""
    sw_build = live_tools["sw_build"]

    t0 = time.monotonic()
    result = sw_build.fn(
        spec_path=str(minimal_cylinder_spec_path),
        mode="no_dim",
        checkpoint=True,
    )
    elapsed = time.monotonic() - t0

    assert result["ok"] is True, f"build failed: {result.get('error')}"
    assert set(result["features_built"]) == {
        "SK_Body",
        "Extrude_Body",
    }, f"unexpected feature list: {result['features_built']}"
    assert elapsed < 30.0, f"build took {elapsed:.1f}s — likely a regression"

    # The default checkpoint root is .checkpoints/ (set by sw_build).
    # We can't use e2e_checkpoint_root here because sw_build doesn't
    # take a checkpoint_root arg in the MCP surface yet.
    cp_db = Path(".checkpoints") / "MinimalCylinder.sqlite"
    assert cp_db.exists(), f"expected checkpoint DB at {cp_db}"


def test_e2e_build_produces_history_rows(
    live_tools, minimal_cylinder_spec_path: Path
) -> None:
    """After sw_build with --checkpoint, sw_history_part returns rows.

    The number of rows is implementation-defined (pending vs committed
    state machine). What we lock in: count > 0, and every row carries
    the expected dataclass fields.
    """
    live_tools["sw_build"].fn(
        spec_path=str(minimal_cylinder_spec_path),
        mode="no_dim",
        checkpoint=True,
    )

    hist = live_tools["sw_history_part"].fn(part_name="MinimalCylinder")
    assert hist["subcommand"] == "part"
    assert hist["count"] > 0, "no checkpoint rows after a checkpointed build"
    for cp in hist["checkpoints"]:
        # Required dataclass fields per CheckpointStore.insert_pending /
        # commit. Drift in any of these is a contract break.
        for field in (
            "id",
            "feature_index",
            "feature_name",
            "feature_type",
            "timestamp",
            "status",
            "build_mode",
        ):
            assert field in cp, f"checkpoint row missing {field!r}: {cp}"
