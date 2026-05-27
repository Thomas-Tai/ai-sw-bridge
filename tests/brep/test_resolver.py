"""Tests for brep/resolver.py (spec.md §2.6)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.brep.resolver import (
    FaceAmbiguityError,
    FaceResolutionError,
    find_face_by_normal,
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
def test_case_insensitive_matching(role_in_spec: str, role_in_manifest: str) -> None:
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
    parent = {
        "feature": "P",
        "faces": [{"fingerprint": "x" * 16}, _face("+z_outboard")],
    }
    match = resolve_face_role(
        feature_name="H",
        face_role="+z_outboard",
        parent_brep_block=parent,
    )
    assert match["fingerprint"] == "deadbeef" * 2


# ---------------------------------------------------------------------------
# find_face_by_normal (FR-v0.11-L1-02 direct normal lookup)
# ---------------------------------------------------------------------------


def _face_with_normal(normal: tuple[float, float, float], fingerprint: str) -> dict:
    return {
        "fingerprint": fingerprint,
        "role_hint": "any",
        "normal": list(normal),
        "centroid": [0.0, 0.0, 0.0],
        "bbox": [[0.0, 0.0, 0.0], [0.01, 0.01, 0.005]],
        "area_mm2": 100.0,
    }


def test_find_face_by_normal_exact_match() -> None:
    parent = {
        "feature": "P",
        "faces": [
            _face_with_normal((1.0, 0.0, 0.0), "ax"),
            _face_with_normal((0.0, 1.0, 0.0), "ay"),
            _face_with_normal((0.0, 0.0, 1.0), "az"),
        ],
    }
    hit = find_face_by_normal(parent, (0.0, 0.0, 1.0))
    assert hit is not None
    assert hit["fingerprint"] == "az"


def test_find_face_by_normal_within_tolerance() -> None:
    parent = {
        "feature": "P",
        "faces": [
            _face_with_normal((0.0, 0.0, 1.0), "az"),
        ],
    }
    # 5° off from +Z — within default 8° tolerance
    import math

    angle = math.radians(5)
    nz = math.cos(angle)
    nx = math.sin(angle)
    hit = find_face_by_normal(parent, (nx, 0.0, nz))
    assert hit is not None
    assert hit["fingerprint"] == "az"


def test_find_face_by_normal_outside_tolerance_returns_none() -> None:
    parent = {
        "feature": "P",
        "faces": [_face_with_normal((0.0, 0.0, 1.0), "az")],
    }
    # 30° off from +Z — way outside the 8° default tolerance
    import math

    angle = math.radians(30)
    nz = math.cos(angle)
    nx = math.sin(angle)
    assert find_face_by_normal(parent, (nx, 0.0, nz)) is None


def test_find_face_by_normal_picks_closest_when_multiple_in_range() -> None:
    parent = {
        "feature": "P",
        "faces": [
            _face_with_normal((0.0, 0.0, 1.0), "az_exact"),
            _face_with_normal((0.01, 0.0, 0.9999), "az_close"),
        ],
    }
    hit = find_face_by_normal(parent, (0.0, 0.0, 1.0))
    assert hit is not None
    assert hit["fingerprint"] == "az_exact"


def test_find_face_by_normal_custom_tolerance() -> None:
    parent = {
        "feature": "P",
        "faces": [_face_with_normal((0.0, 0.0, 1.0), "az")],
    }
    # With tolerance=0.5 (huge), even a 60° offset matches.
    import math

    angle = math.radians(60)
    nz = math.cos(angle)
    nx = math.sin(angle)
    hit = find_face_by_normal(parent, (nx, 0.0, nz), tolerance=0.5)
    assert hit is not None


def test_find_face_by_normal_skips_malformed_face() -> None:
    parent = {
        "feature": "P",
        "faces": [
            {"fingerprint": "bad", "normal": "not a list"},
            _face_with_normal((0.0, 0.0, 1.0), "good"),
        ],
    }
    hit = find_face_by_normal(parent, (0.0, 0.0, 1.0))
    assert hit is not None
    assert hit["fingerprint"] == "good"


def test_find_face_by_normal_empty_brep_block_returns_none() -> None:
    parent = {"feature": "P", "faces": []}
    assert find_face_by_normal(parent, (0.0, 0.0, 1.0)) is None
