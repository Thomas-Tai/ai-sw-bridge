"""Quickstart smoke test.

Validates that the commands documented in README.md "5-minute quickstart"
actually work on a fresh install. No SOLIDWORKS required — uses --validate-only
and --dry-run which never touch the COM layer.

The quickstart section lists:
  1. pip install -e .
  2. ai-sw-build examples/filleted_box/spec.json --validate-only
  3. ai-sw-build examples/filleted_box/spec.json --dry-run

If these break, the README quickstart section must be updated to match
reality -- tests are never twisted to match broken docs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_SPEC = REPO_ROOT / "examples" / "filleted_box" / "spec.json"

pytestmark = pytest.mark.onboarding


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


class TestQuickstartSmoke:
    def test_validate_only_succeeds(self):
        """ai-sw-build <spec> --validate-only exits 0 and returns ok:true."""
        proc = _run(
            [sys.executable, "-m", "ai_sw_bridge.cli.build", str(EXAMPLE_SPEC), "--validate-only"]
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["validated"] is True
        assert payload["feature_count"] > 0

    def test_dry_run_succeeds(self):
        """ai-sw-build <spec> --dry-run exits 0 and returns a feature plan."""
        proc = _run(
            [sys.executable, "-m", "ai_sw_bridge.cli.build", str(EXAMPLE_SPEC), "--dry-run"]
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["dry_run"] is True
        assert payload["feature_count"] > 0
        assert len(payload["features"]) == payload["feature_count"]

    def test_dry_run_output_is_valid_json(self):
        """Dry-run output parses as valid JSON with the expected schema keys."""
        proc = _run(
            [sys.executable, "-m", "ai_sw_bridge.cli.build", str(EXAMPLE_SPEC), "--dry-run"]
        )
        payload = json.loads(proc.stdout)
        for key in ("ok", "dry_run", "spec_name", "schema_version", "feature_count", "features"):
            assert key in payload, f"missing key: {key}"

    def test_example_spec_file_exists(self):
        """The quickstart example spec must exist at the documented path."""
        assert EXAMPLE_SPEC.exists(), f"quickstart example not found: {EXAMPLE_SPEC}"

    def test_validate_only_rejects_bad_spec(self, tmp_path):
        """Validate-only returns a non-zero exit and ok:false on invalid JSON."""
        bad_spec = tmp_path / "bad.json"
        bad_spec.write_text('{"schema_version": 1, "name": "X"}', encoding="utf-8")
        proc = _run(
            [sys.executable, "-m", "ai_sw_bridge.cli.build", str(bad_spec), "--validate-only"]
        )
        assert proc.returncode != 0
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False

    def test_help_shows_usage(self):
        """ai-sw-build --help exits 0 and shows usage information."""
        proc = _run([sys.executable, "-m", "ai_sw_bridge.cli.build", "--help"])
        assert proc.returncode == 0
        assert "Build a SOLIDWORKS part" in proc.stdout

    def test_lint_flag_works(self):
        """ai-sw-build <spec> --lint exits 0 on the clean example spec."""
        proc = _run(
            [sys.executable, "-m", "ai_sw_bridge.cli.build", str(EXAMPLE_SPEC), "--lint"]
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        payload = json.loads(proc.stdout)
        assert "lint" in payload
