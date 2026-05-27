"""Tests for the ai-sw-history CLI (E3.3, spec.md §5.7)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ai_sw_bridge.checkpoint import (
    CheckpointStore,
    commit_post_feature,
    write_pre_feature,
)
from ai_sw_bridge.cli.history import main
from ai_sw_bridge.cli.stability import TIER_REGISTRY


def _spec(name: str = "TestPart") -> dict:
    return {
        "name": name,
        "locals": {"PART_LENGTH": "80"},
        "features": [{"name": "SK", "type": "sketch_rectangle_on_plane"}],
    }


def _seed(root: Path, part_name: str, count: int) -> None:
    store = CheckpointStore(part_name=part_name, root=root)
    feat = _spec(part_name)["features"][0]
    for i in range(count):
        row_id = write_pre_feature(
            store, spec=_spec(part_name), feature=feat, feature_index=i
        )
        commit_post_feature(store, row_id, already_built=[feat])
        time.sleep(0.005)
    store.close()


# ---------------------------------------------------------------------------
# Stability tier
# ---------------------------------------------------------------------------


def test_cli_is_registered_experimental() -> None:
    assert TIER_REGISTRY.get("ai_sw_bridge.cli.history") == "experimental"


# ---------------------------------------------------------------------------
# --help (no side effects)
# ---------------------------------------------------------------------------


def test_help_exits_zero_and_prints_usage(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "ai-sw-history" in captured.out
    assert "experimental" in captured.out  # tier banner present


def test_subcommand_help_exits_zero(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["part", "--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "part_name" in captured.out


# ---------------------------------------------------------------------------
# `part` subcommand
# ---------------------------------------------------------------------------


def test_part_lists_all_checkpoints(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 3)
    rc = main(["--root", str(tmp_path), "part", "TestPart"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["subcommand"] == "part"
    assert payload["count"] == 3
    # Most-recent first.
    ids = [cp["id"] for cp in payload["checkpoints"]]
    assert ids == sorted(ids, reverse=True)


def test_part_missing_root_returns_zero_with_stderr_notice(
    tmp_path: Path, capsys
) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(SystemExit) as excinfo:
        main(["--root", str(missing), "part", "Any"])
    # The CLI exits 0 with a stderr notice when no checkpoints exist —
    # downstream tools can pipe the stdout without failing on empty data.
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "does not exist" in captured.err


def test_part_missing_part_file_returns_zero_with_stderr_notice(
    tmp_path: Path, capsys
) -> None:
    tmp_path.mkdir(exist_ok=True)  # root exists but no part.sqlite
    with pytest.raises(SystemExit) as excinfo:
        main(["--root", str(tmp_path), "part", "Missing"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "Missing" in captured.err


# ---------------------------------------------------------------------------
# `locals` subcommand
# ---------------------------------------------------------------------------


def test_locals_matches_canonical(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 2)
    locals_path = tmp_path / "locals.txt"
    locals_path.write_text('"PART_LENGTH" = 80\n', encoding="utf-8")
    rc = main(
        [
            "--root",
            str(tmp_path),
            "locals",
            "TestPart",
            str(locals_path),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subcommand"] == "locals"
    assert payload["count"] == 2


def test_locals_missing_file_returns_nonzero(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 1)
    rc = main(
        [
            "--root",
            str(tmp_path),
            "locals",
            "TestPart",
            str(tmp_path / "missing.txt"),
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err


# ---------------------------------------------------------------------------
# `since` subcommand
# ---------------------------------------------------------------------------


def test_since_filters_by_timestamp(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 2)
    time.sleep(0.01)
    from datetime import datetime, timezone

    cutoff = datetime.now(timezone.utc).isoformat()
    time.sleep(0.01)
    _seed(tmp_path, "TestPart", 2)  # adds 2 more rows after cutoff
    rc = main(["--root", str(tmp_path), "since", "TestPart", cutoff])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 2


def test_since_invalid_timestamp_returns_nonzero(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 1)
    rc = main(["--root", str(tmp_path), "since", "TestPart", "not-a-date"])
    assert rc == 2
    assert "invalid ISO" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# `diff` subcommand (bonus)
# ---------------------------------------------------------------------------


def test_diff_reports_change(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 2)
    # Two committed rows exist with ids 1 and 2.
    rc = main(["--root", str(tmp_path), "diff", "TestPart", "1", "2"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subcommand"] == "diff"
    assert payload["a_id"] == 1
    assert payload["b_id"] == 2
    assert "spec_changed" in payload
    assert "locals_changed" in payload
    assert "tree_changed" in payload


def test_diff_missing_id_returns_nonzero(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 1)
    rc = main(["--root", str(tmp_path), "diff", "TestPart", "1", "999"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Subprocess invocation — two-stream purity
# ---------------------------------------------------------------------------


def test_subprocess_stdout_is_valid_json(tmp_path: Path) -> None:
    _seed(tmp_path, "TestPart", 2)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_sw_bridge.cli.history",
            "--root",
            str(tmp_path),
            "part",
            "TestPart",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    # stdout is parseable JSON; no stray print() leakage.
    payload = json.loads(proc.stdout)
    assert payload["subcommand"] == "part"


# ---------------------------------------------------------------------------
# `rollback` subcommand (v0.12.2 — FR-v0.11-L4-02 part A)
# ---------------------------------------------------------------------------


def test_rollback_subcommand_in_help(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as ei:
        main(["--help"])
    assert ei.value.code == 0
    captured = capsys.readouterr()
    assert "rollback" in captured.out


def test_rollback_audit_only_succeeds(tmp_path: Path, capsys) -> None:
    """rollback without --locals-path inserts the audit row but
    doesn't touch any locals file."""
    _seed(tmp_path, "TestPart", 3)
    rc = main(["--root", str(tmp_path), "rollback", "TestPart", "1"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["subcommand"] == "rollback"
    assert payload["ok"] is True
    assert payload["rolled_back_to_id"] == 1
    assert payload["locals_path"] is None


def test_rollback_writes_locals_when_path_given(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 2)
    locals_path = tmp_path / "locals.txt"
    rc = main(
        [
            "--root",
            str(tmp_path),
            "rollback",
            "TestPart",
            "1",
            "--locals-path",
            str(locals_path),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["locals_path"] == str(locals_path)
    # The locals file was actually written.
    assert locals_path.exists()


def test_rollback_unknown_checkpoint_id_returns_nonzero(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, "TestPart", 1)
    rc = main(["--root", str(tmp_path), "rollback", "TestPart", "9999"])
    assert rc == 8  # verification failure per UIUX §3.2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert "rollback failed" in captured.err
