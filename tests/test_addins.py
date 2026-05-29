"""Tests for W7.1 add-in enumeration (shape contract + CLI wiring).

These run WITHOUT a running SOLIDWORKS session: get_sw_app() will raise
com_error, the functions catch it, and return their typed error dict.
What we verify here is the SHAPE of that dict -- every key the wire
contract promises is present, error is populated, ok is False.

Mirrors the pattern established by test_observe_shape.py (P0.2) for
bbox/volume.

No SOLIDWORKS required.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from ai_sw_bridge.observe import (
    KNOWN_PROBLEMATIC_ADDINS,
    sw_get_enabled_addins,
)

ADDIN_KEYS = frozenset({"ok", "addins", "known_problematic", "error"})


# -- Shape contract (no SW needed) ----------------------------------------


def test_sw_get_enabled_addins_shape_when_sw_unavailable():
    """Wire-contract test: every promised key is present in the result dict."""
    result = sw_get_enabled_addins()
    assert isinstance(result, dict)
    assert set(result.keys()) == ADDIN_KEYS
    if not result["ok"]:
        assert result["error"] is not None


def test_known_problematic_addins_is_frozenset():
    """KNOWN_PROBLEMATIC_ADDINS must be a frozenset for immutability."""
    assert isinstance(KNOWN_PROBLEMATIC_ADDINS, frozenset)
    assert len(KNOWN_PROBLEMATIC_ADDINS) > 0


def test_known_problematic_addins_contains_toolbox():
    """SOLIDWORKS Toolbox is the canonical problematic add-in."""
    assert "SOLIDWORKS Toolbox" in KNOWN_PROBLEMATIC_ADDINS


def test_known_problematic_addins_contains_pdm():
    """PDM Standard and Professional are both listed."""
    assert "SOLIDWORKS PDM Standard" in KNOWN_PROBLEMATIC_ADDINS
    assert "SOLIDWORKS PDM Professional" in KNOWN_PROBLEMATIC_ADDINS


# -- CLI wiring (no SW needed) -------------------------------------------


def test_build_cli_accepts_disable_addins():
    """ai-sw-build --help mentions --disable-addins."""
    proc = subprocess.run(
        [sys.executable, "-m", "ai_sw_bridge.cli.build", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    assert "--disable-addins" in proc.stdout


def test_build_cli_accepts_strict_addins():
    """ai-sw-build --help mentions --strict-addins."""
    proc = subprocess.run(
        [sys.executable, "-m", "ai_sw_bridge.cli.build", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    assert "--strict-addins" in proc.stdout


def test_observe_addins_subcommand_exists():
    """ai-sw-observe addins --help works and mentions W7.1."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_sw_bridge.cli.observe",
            "addins",
            "--help",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    assert "W7.1" in proc.stdout


def test_observe_addins_returns_json():
    """ai-sw-observe addins returns a JSON object with the right keys.

    When SW is unavailable, ok=False and error is populated -- but the
    output is still valid JSON with the wire-contract keys.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "ai_sw_bridge.cli.observe", "addins"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    # Exit code is 1 when ok=False (SW unavailable), which is expected.
    data = json.loads(proc.stdout)
    assert set(data.keys()) == ADDIN_KEYS


# -- Live-SW tests (skipped without a running session) -------------------


@pytest.mark.solidworks_only
def test_sw_get_enabled_addins_live():
    """With SW running, we get a real list of add-ins back."""
    result = sw_get_enabled_addins()
    assert result["ok"] is True
    assert isinstance(result["addins"], list)
    assert isinstance(result["known_problematic"], list)
    # Every known_problematic entry must also appear in addins
    for name in result["known_problematic"]:
        assert name in result["addins"]
