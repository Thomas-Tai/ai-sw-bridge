"""Tests for brep/resolver.py (spec.md §2.6)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.brep.resolver import (
    FaceAmbiguityError,
    FaceResolutionError,
    resolve_face_role,
)


def _face(role: str, fingerprint: str = "deadbeef" * 2) -> dict:
    return {
        "fingerprint": fingerprint,
        "role_hint": role,
        "normal": [0.0, 0.0, 1.0],
        "centroid": [0.0, 0.0, 0.005],
        "bbox": [[-0.01, -0.01, 0.005], [0.01, 0.01, 0.005]],
        "area_mm2": 400.0,
    }


def _parent_block(*faces: dict) -> dict:
    return {"feature": "Extrude_Plate", "faces": list(faces)}


def test_resolve_known_face_role() -> None:
    parent = _parent_block(
        _face("+z_outboard"),
        _face("-z_outboard"),
        _face("+x_outboard"),
    )
    match = resolve_face_role(
        feature_name="Hole_1",
        face_role="+z_outboard",
        parent_brep_block=parent,
    )
    assert match["role_hint"] == "+z_outboard"


def test_resolve_unknown_role_raises_with_available() -> None:
    parent = _parent_block(
        _face("+z_outboard"),
        _face("-z_outboard"),
    )
    with pytest.raises(FaceResolutionError) as excinfo:
        resolve_face_role(
            feature_name="Hole_1",
            face_role="+y_outboard",
            parent_brep_block=parent,
        )
    assert excinfo.value.feature_name == "Hole_1"
    assert excinfo.value.face_role == "+y_outboard"
    assert set(excinfo.value.available_roles) == {"+z_outboard", "-z_outboard"}


def test_resolve_ambiguous_role_lists_candidates() -> None:
    parent = _parent_block(
        _face("+z_outboard", fingerprint="a" * 16),
        _face("+z_outboard", fingerprint="b" * 16),
    )
    with pytest.raises(FaceAmbiguityError) as excinfo:
        resolve_face_role(
            feature_name="Hole_1",
            face_role="+z_outboard",
            parent_brep_block=parent,
        )
    assert excinfo.value.feature_name == "Hole_1"
    assert len(excinfo.value.candidates) == 2


@pytest.mark.parametrize(
    "role_in_spec,role_in_manifest",
    [
        ("top", "TOP"),
        ("+Z_OUTBOARD", "+z_outboard"),
        ("+z_Outboard", "+z_outboard"),
    ],
)
def test_case_insensitive_matching(
    role_in_spec: str, role_in_manifest: str
) -> None:
    parent = _parent_block(_face(role_in_manifest))
    match = resolve_face_role(
        feature_name="Hole_1",
        face_role=role_in_spec,
        parent_brep_block=parent,
    )
    assert match["role_hint"] == role_in_manifest


def test_empty_parent_block_raises_resolution_error() -> None:
    parent = _parent_block()  # no faces
    with pytest.raises(FaceResolutionError):
        resolve_face_role(
            feature_name="Hole_1",
            face_role="+z_outboard",
            parent_brep_block=parent,
        )


def test_empty_face_role_raises_resolution_error() -> None:
    parent = _parent_block(_face("+z_outboard"))
    with pytest.raises(FaceResolutionError):
        resolve_face_role(
            feature_name="Hole_1",
            face_role="",
            parent_brep_block=parent,
        )


def test_non_string_face_role_raises() -> None:
    parent = _parent_block(_face("+z_outboard"))
    with pytest.raises(FaceResolutionError):
        resolve_face_role(
            feature_name="Hole_1",
            face_role=42,  # type: ignore[arg-type]
            parent_brep_block=parent,
        )


def test_faces_without_role_hint_are_ignored() -> None:
    """Faces missing a role_hint (e.g. surfaces with 'oblique' unset) are
    not candidates for resolution."""
    parent = {"feature": "P", "faces": [{"fingerprint": "x" * 16}, _face("+z_outboard")]}
    match = resolve_face_role(
        feature_name="H",
        face_role="+z_outboard",
        parent_brep_block=parent,
    )
    assert match["fingerprint"] == "deadbeef" * 2
