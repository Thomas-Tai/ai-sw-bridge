"""Tests for tools/spec_redact.py (W3.3, privacy_review §4.4).

Round-trips known specs through the redactor and verifies:
- rhs bindings are replaced with "<redacted>"
- feature names are anonymized to <type_index>
- cross-references (sketch, of_feature) are rewritten consistently
- _comment fields are stripped
- file paths reduced to basenames
- --coarsen rounds floats to 10mm boundaries
- output passes schema validation
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from spec_redact import (  # noqa: E402
    _coarsen_number,
    redact_spec,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ai_sw_bridge.spec import validate  # noqa: E402

# ---------------------------------------------------------------------------
# _coarsen_number
# ---------------------------------------------------------------------------


class TestCoarsenNumber:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            (0.0, 0.0),
            (4.9, 0.0),
            (5.0, 10.0),
            (14.9, 10.0),
            (15.0, 20.0),
            (100.0, 100.0),
            (12.345, 10.0),
            (-7.5, -10.0),
        ],
    )
    def test_rounding(self, inp: float, expected: float) -> None:
        assert _coarsen_number(inp) == expected


# ---------------------------------------------------------------------------
# redact_spec — rhs redaction
# ---------------------------------------------------------------------------


class TestRedactRhs:
    def test_rhs_replaced(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [
                {
                    "type": "sketch_circle_on_plane",
                    "name": "SK_1",
                    "plane": "Front",
                    "diameter": {"rhs": '"SOME_SECRET_VAR"'},
                    "center": {"x": 0.0, "y": 0.0},
                },
            ],
        }
        out = redact_spec(spec)
        assert out["features"][0]["diameter"] == {"rhs": "<redacted>"}

    def test_nested_rhs_replaced(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [
                {
                    "type": "boss_extrude_blind",
                    "name": "E1",
                    "sketch": "SK_1",
                    "depth": {"rhs": '"DEPTH_VAR"'},
                },
            ],
        }
        out = redact_spec(spec)
        assert out["features"][0]["depth"] == {"rhs": "<redacted>"}


# ---------------------------------------------------------------------------
# redact_spec — feature names
# ---------------------------------------------------------------------------


class TestRedactNames:
    def test_names_anonymized(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [
                {"type": "sketch_rectangle_on_plane", "name": "SK_SecretPlate"},
                {"type": "boss_extrude_blind", "name": "Extrude_SecretBody"},
            ],
        }
        out = redact_spec(spec)
        assert out["features"][0]["name"] == "redact_sketch_rectangle_on_plane_0"
        assert out["features"][1]["name"] == "redact_boss_extrude_blind_1"

    def test_cross_references_rewritten(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [
                {"type": "sketch_circle_on_plane", "name": "SK_Hole"},
                {
                    "type": "cut_extrude_through_all",
                    "name": "Cut_Hole",
                    "sketch": "SK_Hole",
                },
            ],
        }
        out = redact_spec(spec)
        assert out["features"][1]["sketch"] == "redact_sketch_circle_on_plane_0"

    def test_of_feature_rewritten(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [
                {"type": "boss_extrude_blind", "name": "Body"},
                {
                    "type": "sketch_circle_on_face",
                    "name": "SK_Pocket",
                    "of_feature": "Body",
                    "face": "+z",
                },
            ],
        }
        out = redact_spec(spec)
        assert out["features"][1]["of_feature"] == "redact_boss_extrude_blind_0"


# ---------------------------------------------------------------------------
# redact_spec — metadata stripping
# ---------------------------------------------------------------------------


class TestRedactMetadata:
    def test_comments_stripped(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "_comment": "proprietary design notes",
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK_1",
                    "_comment": "secret design intent",
                },
            ],
        }
        out = redact_spec(spec)
        assert "_comment" not in out
        assert "_comment" not in out["features"][0]

    def test_name_redacted(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "ACME_SuperWidget_v3",
            "features": [],
        }
        out = redact_spec(spec)
        assert out["name"] == "redacted_spec"

    def test_locals_path_reduced_to_basename(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "locals": "/home/user/secret/project/locals.txt",
            "features": [],
        }
        out = redact_spec(spec)
        assert out["locals"] == "locals.txt"


# ---------------------------------------------------------------------------
# --coarsen
# ---------------------------------------------------------------------------


class TestCoarsen:
    def test_floats_rounded(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK_1",
                    "plane": "Front",
                    "width": 23.7,
                    "height": 47.2,
                },
            ],
        }
        out = redact_spec(spec, coarsen=True)
        assert out["features"][0]["width"] == 20.0
        assert out["features"][0]["height"] == 50.0

    def test_schema_version_not_coarsened(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [],
        }
        out = redact_spec(spec, coarsen=True)
        assert out["schema_version"] == 1  # not rounded to 0

    def test_no_coarsen_preserves_precision(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK_1",
                    "plane": "Front",
                    "width": 23.7,
                    "height": 47.2,
                },
            ],
        }
        out = redact_spec(spec, coarsen=False)
        assert out["features"][0]["width"] == 23.7
        assert out["features"][0]["height"] == 47.2

    def test_expect_mass_delta_coarsened(self) -> None:
        spec = {
            "schema_version": 1,
            "name": "test",
            "features": [
                {
                    "type": "boss_extrude_blind",
                    "name": "E1",
                    "sketch": "SK_1",
                    "depth": 12.345,
                    "_expect": {"mass_delta_mm3": 1234.56, "tolerance_mm3": 5.7},
                },
            ],
        }
        out = redact_spec(spec, coarsen=True)
        assert out["features"][0]["depth"] == 10.0
        assert out["features"][0]["_expect"]["mass_delta_mm3"] == 1230.0
        assert out["features"][0]["_expect"]["tolerance_mm3"] == 10.0


# ---------------------------------------------------------------------------
# Integration: drive_roller spec round-trip
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_drive_roller_redacts_all_rhs(self) -> None:
        """The drive_roller spec has rhs bindings — all must be redacted."""
        spec_path = (
            Path(__file__).resolve().parent.parent
            / "examples"
            / "drive_roller"
            / "spec.json"
        )
        if not spec_path.exists():
            pytest.skip("drive_roller example not found")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        out = redact_spec(spec)
        # Walk the output and verify no raw rhs values remain
        raw = json.dumps(out)
        assert "S1B_ROLLER_DIA" not in raw
        assert "S1B_ROLLER_W" not in raw
        assert "S1B_ROLLER_BORE" not in raw
        assert "S1B_BEARING_POCKET" not in raw
        # Redacted markers present
        assert "<redacted>" in raw

    def test_drive_roller_coarsen_10mm_boundary(self) -> None:
        spec_path = (
            Path(__file__).resolve().parent.parent
            / "examples"
            / "drive_roller"
            / "spec.json"
        )
        if not spec_path.exists():
            pytest.skip("drive_roller example not found")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        out = redact_spec(spec, coarsen=True)
        # All floats should be on 10mm boundary
        for feat in out.get("features", []):
            for k, v in feat.items():
                if isinstance(v, float):
                    assert v % 10 == 0.0, f"{k}={v} not on 10mm boundary"

    def test_filleted_box_roundtrip_validates(self) -> None:
        """Redacted filleted_box spec still passes schema validation."""
        spec_path = (
            Path(__file__).resolve().parent.parent
            / "examples"
            / "filleted_box"
            / "spec.json"
        )
        if not spec_path.exists():
            pytest.skip("filleted_box example not found")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        out = redact_spec(spec)
        # Should not raise
        validate(out)
