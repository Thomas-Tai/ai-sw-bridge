"""Tests for ``ai-sw-build --auto-retry`` (FR-v0.11-L2-04).

The CLI flag wires the RetryGuard into the build flow so an identical
spec submission within the same session exits with a structured
``identical_spec_resubmitted`` error envelope on stdout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _minimal_spec(tmp_path: Path) -> Path:
    """Write a smallest-possible valid spec — fails fast in validation
    if missing fields, so a real build never fires."""
    spec = {
        "schema_version": 1,
        "name": "AutoRetryProbe",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 20.0,
                "height": 20.0,
            }
        ],
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def _run_build(
    *extra_args: str,
    spec_path: Path,
) -> subprocess.CompletedProcess:
    argv = [
        sys.executable,
        "-m",
        "ai_sw_bridge.cli.build",
        "--validate-only",
        *extra_args,
        str(spec_path),
    ]
    return subprocess.run(argv, capture_output=True, text=True, cwd=REPO_ROOT)


def test_help_mentions_auto_retry() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ai_sw_bridge.cli.build", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--auto-retry" in result.stdout


def test_first_submission_passes_validate_only(tmp_path: Path) -> None:
    """An auto-retry'd first submission is not yet 'identical' to anything;
    --validate-only succeeds and the guard records the attempt."""
    spec_path = _minimal_spec(tmp_path)
    result = _run_build("--auto-retry", spec_path=spec_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload.get("ok") is True


def test_retry_guard_check_raises_on_identical(tmp_path: Path) -> None:
    """Direct unit-level: the RetryGuard refuses an identical second
    submission within the same process (without telemetry persistence,
    cross-process re-runs would need the store wired in)."""
    from ai_sw_bridge.errors.auto_retry import IdenticalSpecError, RetryGuard

    spec = {
        "schema_version": 1,
        "name": "X",
        "features": [],
    }
    guard = RetryGuard()
    h1 = guard.check(spec)
    assert isinstance(h1, str)
    guard.record_attempt(spec, error="first attempt failed", hint_key="some_hint")
    with pytest.raises(IdenticalSpecError) as ei:
        guard.check(spec)
    assert ei.value.spec_hash == h1
    assert ei.value.last_hint_key == "some_hint"


def test_auto_retry_off_by_default(tmp_path: Path) -> None:
    """Without --auto-retry, the second submission is accepted (no guard)."""
    spec_path = _minimal_spec(tmp_path)
    # First submission
    r1 = _run_build(spec_path=spec_path)
    assert r1.returncode == 0
    # Second submission, also no --auto-retry — no guard kicks in
    r2 = _run_build(spec_path=spec_path)
    assert r2.returncode == 0
