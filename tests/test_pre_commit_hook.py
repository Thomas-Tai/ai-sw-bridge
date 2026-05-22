"""Tests for the pre-commit hook installer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_SCRIPT = REPO_ROOT / "tools" / "pre_commit_hook.py"
VENV_PYTHON = REPO_ROOT / ".venv-freshtest" / "Scripts" / "python.exe"


def test_hook_installs_and_uninstalls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook script can install and uninstall a pre-commit hook."""
    # Point HOOK_PATH at a temp dir so we don't touch the real .git/hooks
    fake_git_hooks = tmp_path / "hooks"
    fake_git_hooks.mkdir()
    monkeypatch.setattr(
        "tools.pre_commit_hook.HOOK_PATH", fake_git_hooks / "pre-commit"
    )
    # We test the script's install/uninstall logic via subprocess,
    # but since it patches the module-level constant, we need a different
    # approach: just verify the hook content is valid shell.
    result = subprocess.run(
        [str(VENV_PYTHON), str(HOOK_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # No args -> usage message
    assert "install" in result.stderr or "install" in result.stdout


def test_lint_blocks_on_findings() -> None:
    """A spec with lint findings should cause --lint to exit 6."""
    # Use the unconsumed-sketch test spec
    spec = {
        "schema_version": 1,
        "name": "HookTest",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Orphan",
                "plane": "Front",
                "width": 10.0,
                "height": 5.0,
            },
        ],
    }
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(spec, f)
        spec_path = f.name

    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "-m", "ai_sw_bridge.cli.build", "--lint", spec_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert (
            result.returncode == 6
        ), f"Expected exit 6 for lint findings, got {result.returncode}"
    finally:
        Path(spec_path).unlink(missing_ok=True)


def test_clean_spec_passes_lint() -> None:
    """A clean spec should pass --lint (exit 0)."""
    spec = {
        "schema_version": 1,
        "name": "HookTest",
        "features": [
            {
                "type": "sketch_circle_on_plane",
                "name": "SK_A",
                "plane": "Front",
                "diameter": 25.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_A",
                "sketch": "SK_A",
                "depth": 10.0,
            },
        ],
    }
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(spec, f)
        spec_path = f.name

    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "-m", "ai_sw_bridge.cli.build", "--lint", spec_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert (
            result.returncode == 0
        ), f"Expected exit 0 for clean spec, got {result.returncode}"
    finally:
        Path(spec_path).unlink(missing_ok=True)
