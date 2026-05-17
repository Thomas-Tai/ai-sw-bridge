"""Tests for ai_sw_bridge.spec.validator."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from ai_sw_bridge.spec.validator import (
    ValidationError,
    _strip_comments,
    validate,
)


# -----------------------------------------------------------------------------
# Happy path: example specs validate
# -----------------------------------------------------------------------------


def test_validate_accepts_cylinder_spec(cylinder_spec: dict) -> None:
    # cylinder spec references its own locals path that exists on disk.
    validate(cylinder_spec)


def test_validate_accepts_mmp_spec(mmp_spec: dict) -> None:
    # MMP spec references a locals file under the Lego Sorter repo. If that
    # file doesn't exist on this machine, skip rather than fail (it's an
    # integration-with-other-repo concern).
    if not Path(mmp_spec["locals"]).exists():
        pytest.skip(f"MMP locals file not present: {mmp_spec['locals']}")
    validate(mmp_spec)


# -----------------------------------------------------------------------------
# _strip_comments()
# -----------------------------------------------------------------------------


def test_strip_comments_removes_underscore_keys_at_top_level() -> None:
    node = {"_comment": "x", "name": "P", "features": []}
    out = _strip_comments(node)
    assert "_comment" not in out
    assert out == {"name": "P", "features": []}


def test_strip_comments_removes_underscore_keys_at_any_depth() -> None:
    node = {
        "features": [
            {"_comment": "nested", "type": "T", "sub": {"_note": "z", "ok": 1}},
        ],
    }
    out = _strip_comments(node)
    assert "_comment" not in out["features"][0]
    assert "_note" not in out["features"][0]["sub"]
    assert out["features"][0]["sub"] == {"ok": 1}


def test_strip_comments_preserves_non_dict_values() -> None:
    assert _strip_comments(5) == 5
    assert _strip_comments("hello") == "hello"
    assert _strip_comments([1, 2, 3]) == [1, 2, 3]


# -----------------------------------------------------------------------------
# Reference checks
# -----------------------------------------------------------------------------


def _minimal_spec() -> dict:
    """A clean minimal spec: one sketch + one extrude. All literal, no locals."""
    return {
        "schema_version": 1,
        "name": "MinSpec",
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


def test_reference_fails_when_sketch_points_to_unknown_feature() -> None:
    spec = _minimal_spec()
    spec["features"][1]["sketch"] = "DoesNotExist"
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "DoesNotExist" in str(exc.value)


def test_reference_fails_when_sketch_points_to_non_sketch() -> None:
    spec = _minimal_spec()
    # Add a second extrude pointing at the first extrude as its "sketch"
    spec["features"].append(
        {
            "type": "boss_extrude_blind",
            "name": "EX_B",
            "sketch": "EX_A",  # not a sketch
            "depth": 5.0,
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    msg = str(exc.value)
    assert "sketch" in msg.lower()
    assert "EX_A" in msg


def test_reference_fails_when_of_feature_points_to_non_extrusion() -> None:
    spec = _minimal_spec()
    # Add a circle-on-face that references a SKETCH (not an extrusion)
    spec["features"].append(
        {
            "type": "sketch_circle_on_face",
            "name": "SK_Hole",
            "of_feature": "SK_A",  # SK_A is a sketch, not an extrusion
            "face": "+z",
            "diameter": 5.0,
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    msg = str(exc.value)
    assert "extrusion" in msg.lower()
    assert "SK_A" in msg


def test_reference_enforces_topological_order() -> None:
    """The extrude must come AFTER its sketch in the features list."""
    spec = _minimal_spec()
    # Swap order: extrude before sketch
    spec["features"] = [spec["features"][1], spec["features"][0]]
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "earlier" in str(exc.value).lower() or "not" in str(exc.value).lower()


# -----------------------------------------------------------------------------
# Locals checks
# -----------------------------------------------------------------------------


def test_locals_fails_when_rhs_used_but_no_locals_path() -> None:
    spec = _minimal_spec()
    spec["features"][0]["diameter"] = {"rhs": '"FOO"'}
    # Intentionally NO `locals` key
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    msg = str(exc.value)
    assert "locals" in msg.lower()


def test_locals_fails_when_rhs_references_unknown_variable(tmp_path: Path) -> None:
    locals_file = tmp_path / "locals.txt"
    locals_file.write_text('"OTHER" = 1.0\n', encoding="utf-8")

    spec = _minimal_spec()
    spec["locals"] = str(locals_file)
    spec["features"][0]["diameter"] = {"rhs": '"MISSING"'}

    with pytest.raises(ValidationError) as exc:
        validate(spec)
    msg = str(exc.value)
    assert "MISSING" in msg


def test_locals_passes_when_all_refs_resolve(tmp_path: Path) -> None:
    locals_file = tmp_path / "locals.txt"
    locals_file.write_text(
        '"D" = 25.0\n"L" = 80.0\n',
        encoding="utf-8",
    )

    spec = _minimal_spec()
    spec["locals"] = str(locals_file)
    spec["features"][0]["diameter"] = {"rhs": '"D"'}
    spec["features"][1]["depth"] = {"rhs": '"L"'}

    # Should not raise
    validate(spec)


# -----------------------------------------------------------------------------
# ValidationError API (positional + kwargs constructor)
# -----------------------------------------------------------------------------


def test_validation_error_positional_constructor() -> None:
    err = ValidationError("something broke", "features/0/name")
    assert err.message == "something broke"
    assert err.path == "features/0/name"
    assert "features/0/name" in str(err)
    assert "something broke" in str(err)


def test_validation_error_kwargs_constructor() -> None:
    err = ValidationError(message="boom", path="$/locals")
    assert err.message == "boom"
    assert err.path == "$/locals"


def test_validation_error_is_exception_subclass() -> None:
    # @dataclass on Exception would break .args; verify it is intact.
    err = ValidationError("msg", "p")
    assert isinstance(err, Exception)
    assert err.args == ("msg",)


def test_validation_error_path_optional() -> None:
    err = ValidationError("msg")
    assert err.path == ""
    assert str(err) == "msg"
