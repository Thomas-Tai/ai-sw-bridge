"""Tests for tools/checkpoint_redact.py (W3.2)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from ai_sw_bridge.checkpoint.crypto import KeySource, generate_key
from ai_sw_bridge.checkpoint.store import CheckpointStore

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REDACT_TOOL = _REPO_ROOT / "tools" / "checkpoint_redact.py"


def _create_test_checkpoint(
    tmp_path: Path,
    part_name: str = "test_part",
    *,
    encrypted: bool = False,
    key_source=None,
) -> Path:
    """Create a test checkpoint DB with sample data."""
    store = CheckpointStore(part_name, root=tmp_path, key_source=key_source)
    store.insert_pending(
        feature_index=0,
        feature_name="SK_Box",
        feature_type="sketch",
        locals_snapshot='{"WIDTH": 100.0, "HEIGHT": 50.0}',
        spec_hash="a" * 64,
        pre_tree_hash="b" * 64,
        build_mode="deferred-dim",
    )
    store.commit(
        1,
        post_tree_hash="c" * 64,
        com_call_log="Created sketch with WIDTH = 100.0 mm",
    )
    store.close()
    return tmp_path / f"{part_name}.sqlite"


class TestCheckpointRedact:
    def test_plain_db_redaction(self, tmp_path: Path) -> None:
        """Redact a plain checkpoint DB."""
        db_path = _create_test_checkpoint(tmp_path)

        result = subprocess.run(
            [sys.executable, str(_REDACT_TOOL), str(db_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "redacted checkpoint written to" in result.stderr

        # Find the output file
        output_files = list(tmp_path.glob("*.redacted.*"))
        assert len(output_files) == 1
        out_path = output_files[0]

        # Verify redaction
        conn = sqlite3.connect(str(out_path))
        try:
            row = conn.execute(
                "SELECT locals_snapshot, com_call_log, spec_hash FROM checkpoints"
            ).fetchone()
            assert row[0] == "<redacted_local>"
            assert "WIDTH = 100.0" not in row[1]  # Pattern redacted
            assert "<redacted>" in row[1]
            assert row[2] == "a" * 64  # Hash preserved
        finally:
            conn.close()

    def test_encrypted_db_redaction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redact a encrypted checkpoint DB with key source."""
        key = generate_key().decode()
        monkeypatch.setenv("TEST_KEY", key)
        key_source = KeySource.parse("env:TEST_KEY")

        db_path = _create_test_checkpoint(
            tmp_path, part_name="encrypted_part", encrypted=True, key_source=key_source
        )

        env = os.environ.copy()
        env["TEST_KEY"] = key

        result = subprocess.run(
            [
                sys.executable,
                str(_REDACT_TOOL),
                str(db_path),
                "--from-key-source",
                "env:TEST_KEY",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0

        # Verify output is plain (no _meta table)
        output_files = list(tmp_path.glob("*.redacted.*"))
        assert len(output_files) == 1
        out_path = output_files[0]

        conn = sqlite3.connect(str(out_path))
        try:
            meta = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_meta'"
            ).fetchone()
            assert meta is None  # No _meta table in output

            row = conn.execute(
                "SELECT locals_snapshot, com_call_log FROM checkpoints"
            ).fetchone()
            assert row[0] == "<redacted_local>"
        finally:
            conn.close()

    def test_output_path_override(self, tmp_path: Path) -> None:
        """Override output path with --output flag."""
        db_path = _create_test_checkpoint(tmp_path)
        custom_output = tmp_path / "custom_redacted.sqlite"

        result = subprocess.run(
            [
                sys.executable,
                str(_REDACT_TOOL),
                str(db_path),
                "--output",
                str(custom_output),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert custom_output.exists()
        assert str(custom_output) in result.stderr

    def test_missing_db_returns_error(self, tmp_path: Path) -> None:
        """Return error code 2 when DB not found."""
        fake_path = tmp_path / "nonexistent.sqlite"

        result = subprocess.run(
            [sys.executable, str(_REDACT_TOOL), str(fake_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 2
        assert "not found" in result.stderr

    def test_tree_hashes_preserved(self, tmp_path: Path) -> None:
        """Verify tree hashes are preserved (not redacted)."""
        db_path = _create_test_checkpoint(tmp_path)

        result = subprocess.run(
            [sys.executable, str(_REDACT_TOOL), str(db_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        output_files = list(tmp_path.glob("*.redacted.*"))
        out_path = output_files[0]

        conn = sqlite3.connect(str(out_path))
        try:
            row = conn.execute(
                "SELECT spec_hash, pre_tree_hash, post_tree_hash FROM checkpoints"
            ).fetchone()
            assert row[0] == "a" * 64
            assert row[1] == "b" * 64
            assert row[2] == "c" * 64
        finally:
            conn.close()

    def test_com_call_log_patterns_redacted(self, tmp_path: Path) -> None:
        """Verify trade-secret patterns in com_call_log are redacted."""
        store = CheckpointStore("pattern_test", root=tmp_path)
        store.insert_pending(
            feature_index=0,
            feature_name="SK_Test",
            feature_type="sketch",
            locals_snapshot="{}",
            spec_hash="0" * 64,
            pre_tree_hash="1" * 64,
            build_mode="deferred-dim",
        )
        store.commit(
            1,
            post_tree_hash="2" * 64,
            com_call_log="Set SECRET_PARAM = 999.99 mm, updated 123.45 inch",
        )
        store.close()

        db_path = tmp_path / "pattern_test.sqlite"
        result = subprocess.run(
            [sys.executable, str(_REDACT_TOOL), str(db_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        output_files = list(tmp_path.glob("*.redacted.*"))
        out_path = output_files[0]

        conn = sqlite3.connect(str(out_path))
        try:
            row = conn.execute("SELECT com_call_log FROM checkpoints").fetchone()
            log = row[0]
            # Patterns should be redacted
            assert "SECRET_PARAM = 999.99" not in log
            assert "123.45 mm" not in log
            assert "123.45 inch" not in log
            # Redaction markers present
            assert "<redacted>" in log
        finally:
            conn.close()
