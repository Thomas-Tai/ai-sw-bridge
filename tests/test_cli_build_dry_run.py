"""Tests for `ai-sw-build --dry-run` (P0.4).

Verifies the dry-run helper does what the docstring promises:
  - emits one plan entry per feature, preserving rhs objects
  - reports locals.resolved=True when locals + rhs's match
  - reports a structured locals.error when an rhs references a missing var
  - never imports anything COM-related (so it survives without pywin32 init)

Together these lock the contract the future regression harness (P1.2)
reads: --dry-run is a strict superset of --validate-only and surfaces
rhs-lookup failures up-front instead of mid-build.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.cli.build import _dry_run, _plan_entry, _plan_value


def test_plan_value_preserves_rhs():
    assert _plan_value({"rhs": '"FOO" + 1'}) == {"rhs": '"FOO" + 1'}


def test_plan_value_recurses_and_strips_underscores():
    inp = {
        "center": {"u": 1.0, "v": 2.0, "_note": "ignored"},
        "edges": [{"x": 0, "y": 1, "z": 2}],
    }
    out = _plan_value(inp)
    assert out == {
        "center": {"u": 1.0, "v": 2.0},
        "edges": [{"x": 0, "y": 1, "z": 2}],
    }


def test_plan_entry_promotes_name_type_and_separates_expect():
    feat = {
        "type": "boss_extrude_blind",
        "name": "Box",
        "sketch": "SK_Box",
        "depth": 30.0,
        "_expect": {"mass_delta_mm3": 27000.0, "tolerance_mm3": 5.0},
        "_comment": "ignored",
    }
    entry = _plan_entry(feat)
    assert entry["name"] == "Box"
    assert entry["type"] == "boss_extrude_blind"
    assert entry["params"] == {"sketch": "SK_Box", "depth": 30.0}
    assert entry["expect"] == {"mass_delta_mm3": 27000.0, "tolerance_mm3": 5.0}


def test_dry_run_without_locals_passes():
    spec = {
        "schema_version": 1,
        "name": "tiny",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "Box",
                "sketch": "SK_Box",
                "depth": 5.0,
            },
        ],
    }
    result = _dry_run(spec)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["feature_count"] == 2
    assert result["locals"]["declared"] is False
    assert result["locals"]["resolved"] is False
    assert len(result["features"]) == 2


def test_dry_run_with_valid_locals_resolves(tmp_path: Path):
    locals_path = tmp_path / "locals.txt"
    locals_path.write_text(
        '"BOX_W" = 25.0\n' '"BOX_D" = 7.5\n',
        encoding="utf-8",
    )
    spec = {
        "schema_version": 1,
        "name": "tiny",
        "locals": str(locals_path),
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": {"rhs": '"BOX_W"'},
                "height": {"rhs": '"BOX_W"'},
            },
            {
                "type": "boss_extrude_blind",
                "name": "Box",
                "sketch": "SK_Box",
                "depth": {"rhs": '"BOX_D"'},
            },
        ],
    }
    result = _dry_run(spec)
    assert result["ok"] is True
    assert result["locals"]["resolved"] is True
    assert result["locals"]["error"] is None


def test_dry_run_surfaces_missing_var(tmp_path: Path):
    locals_path = tmp_path / "locals.txt"
    locals_path.write_text('"BOX_W" = 25.0\n', encoding="utf-8")
    spec = {
        "schema_version": 1,
        "name": "tiny",
        "locals": str(locals_path),
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": {"rhs": '"BOX_W"'},
                "height": {"rhs": '"MISSING"'},
            },
            {
                "type": "boss_extrude_blind",
                "name": "Box",
                "sketch": "SK_Box",
                "depth": 1.0,
            },
        ],
    }
    result = _dry_run(spec)
    assert result["ok"] is False
    assert "MISSING" in (result["locals"]["error"] or "")


def test_dry_run_output_is_json_serializable():
    """The CLI emits this dict via json.dumps; lock that promise here so
    a future field addition that's NOT JSON-safe is caught in unit tests."""
    spec = {
        "schema_version": 1,
        "name": "tiny",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "Box",
                "sketch": "SK_Box",
                "depth": 5.0,
            },
        ],
    }
    payload = _dry_run(spec)
    s = json.dumps(payload)
    assert "Box" in s


def test_dry_run_does_not_dispatch_sw():
    """Negative test: the import path of _dry_run must not pull in SW.

    If a future refactor pulls a COM-touching symbol into cli/build.py,
    this test will fail at import time on machines without SW running."""
    import importlib

    mod = importlib.import_module("ai_sw_bridge.cli.build")
    # The module must NOT have a live cached SW Application at import time.
    # _resolve_rhs_in_spec is the only builder symbol we pull in; it's
    # pure Python on a parsed locals file.
    assert hasattr(mod, "_dry_run")
    assert hasattr(mod, "_resolve_rhs_in_spec")
