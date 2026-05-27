"""Tests for the face_role shape check in spec.validator (E2.5, §2.6)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec.validator import ValidationError, _check_face_role_shapes


def _face_bound_feature(
    name: str = "Hole_1",
    face_role: str = "+z_outboard",
    ftype: str = "simple_hole",
) -> dict:
    return {
        "type": ftype,
        "name": name,
        "of_feature": "Extrude_Plate",
        "face_role": face_role,
        "diameter": 5.0,
    }


def test_no_face_role_passes() -> None:
    spec = {"features": [{"type": "boss_extrude_blind", "name": "E"}]}
    _check_face_role_shapes(spec)  # no raise


def test_valid_face_role_passes() -> None:
    spec = {"features": [_face_bound_feature()]}
    _check_face_role_shapes(spec)  # no raise


def test_empty_face_role_rejected() -> None:
    spec = {"features": [_face_bound_feature(face_role="")]}
    with pytest.raises(ValidationError) as excinfo:
        _check_face_role_shapes(spec)
    assert "face_role" in str(excinfo.value)
    assert excinfo.value.path == "features/0/face_role"


def test_whitespace_only_face_role_rejected() -> None:
    spec = {"features": [_face_bound_feature(face_role="   ")]}
    with pytest.raises(ValidationError):
        _check_face_role_shapes(spec)


def test_non_string_face_role_rejected() -> None:
    feat = _face_bound_feature()
    feat["face_role"] = 42  # type: ignore[assignment]
    spec = {"features": [feat]}
    with pytest.raises(ValidationError, match="non-empty string"):
        _check_face_role_shapes(spec)


def test_face_role_on_non_face_bound_feature_rejected() -> None:
    feat = {
        "type": "boss_extrude_blind",
        "name": "Extrude1",
        "sketch": "SK_Body",
        "face_role": "+z_outboard",
    }
    spec = {"features": [feat]}
    with pytest.raises(ValidationError, match="only supported on face-bound"):
        _check_face_role_shapes(spec)


@pytest.mark.parametrize(
    "ftype",
    [
        "sketch_rectangle_on_face",
        "sketch_circle_on_face",
        "sketch_circles_on_face",
        "simple_hole",
    ],
)
def test_face_role_accepted_on_all_face_bound_types(ftype: str) -> None:
    feat = _face_bound_feature(ftype=ftype)
    # simple_hole needs diameter; face-sketches need circles / width+height
    if ftype.startswith("sketch_"):
        feat.pop("diameter", None)
        if ftype == "sketch_rectangle_on_face":
            feat["width"] = 10.0
            feat["height"] = 10.0
        elif ftype == "sketch_circle_on_face":
            feat["diameter"] = 5.0
        elif ftype == "sketch_circles_on_face":
            feat["circles"] = [{"diameter": 5.0}]
    spec = {"features": [feat]}
    _check_face_role_shapes(spec)  # no raise
