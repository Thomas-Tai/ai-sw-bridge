"""Tests for brep/fingerprint.py (spec.md §2.4)."""

from __future__ import annotations

import re

import pytest

from ai_sw_bridge.brep.fingerprint import fingerprint


def _face(
    *,
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0),
    centroid: tuple[float, float, float] = (0.0, 0.0, 0.0025),
    area_mm2: float = 400.0,
) -> dict:
    return {
        "normal": list(normal),
        "centroid": list(centroid),
        "area_mm2": area_mm2,
    }


def test_fingerprint_is_16_hex_chars() -> None:
    fp = fingerprint(_face())
    assert len(fp) == 16
    assert re.fullmatch(r"[0-9a-f]{16}", fp)


def test_fingerprint_deterministic_across_calls() -> None:
    f = _face()
    assert fingerprint(f) == fingerprint(f)


def test_same_face_same_fingerprint() -> None:
    a = _face(normal=(1.0, 0.0, 0.0), centroid=(0.01, 0.0, 0.005))
    b = _face(normal=(1.0, 0.0, 0.0), centroid=(0.01, 0.0, 0.005))
    assert fingerprint(a) == fingerprint(b)


def test_perturbation_within_tolerance_collapses() -> None:
    """Perturbation smaller than the quantization step -> same fingerprint.

    Normal tolerance: 1e-6 (6 decimals). Perturbing a component by
    1e-8 must not change the fingerprint.
    """
    base = _face(normal=(0.0, 0.0, 1.0), centroid=(0.0, 0.0, 0.005))
    nudged = _face(normal=(0.0, 0.0, 1.0 + 1e-8), centroid=(0.0, 0.0, 0.005))
    assert fingerprint(base) == fingerprint(nudged)


def test_perturbation_beyond_tolerance_differs() -> None:
    """Perturbation larger than the quantization step -> different fingerprint."""
    base = _face(normal=(0.0, 0.0, 1.0), centroid=(0.0, 0.0, 0.005))
    moved = _face(normal=(0.0, 0.0, 1.0), centroid=(0.0, 0.0, 0.006))
    assert fingerprint(base) != fingerprint(moved)


def test_normal_change_changes_fingerprint() -> None:
    base = _face(normal=(1.0, 0.0, 0.0))
    different = _face(normal=(0.0, 1.0, 0.0))
    assert fingerprint(base) != fingerprint(different)


def test_area_change_beyond_1e3_changes_fingerprint() -> None:
    """Area tolerance is 1e-3 mm² (3 decimals)."""
    base = _face(area_mm2=400.0)
    different = _face(area_mm2=400.001)  # +1e-3 — at the boundary, should differ
    # Boundary case: 400.000 vs 400.001 differ at the 3rd decimal -> differ
    assert fingerprint(base) != fingerprint(different)


def test_area_change_within_tolerance_collapses() -> None:
    base = _face(area_mm2=400.0)
    nudged = _face(area_mm2=400.0 + 1e-4)  # +1e-4, below 1e-3 step
    assert fingerprint(base) == fingerprint(nudged)


def test_signed_zero_collapses() -> None:
    """-0.0 and 0.0 must quantize identically."""
    a = _face(centroid=(0.0, -0.0, 0.005))
    b = _face(centroid=(0.0, 0.0, 0.005))
    assert fingerprint(a) == fingerprint(b)


def test_key_order_independence_of_input() -> None:
    """The fingerprint reads named keys; dict insertion order is irrelevant."""
    face = {
        "area_mm2": 400.0,
        "normal": [0.0, 0.0, 1.0],
        "centroid": [0.0, 0.0, 0.0025],
    }
    assert fingerprint(face) == fingerprint(_face())


def test_missing_key_raises() -> None:
    with pytest.raises(ValueError, match="must contain"):
        fingerprint({"normal": [0.0, 0.0, 1.0], "centroid": [0.0, 0.0, 0.0]})


def test_six_faces_of_box_get_distinct_fingerprints() -> None:
    """Every face of a cube must produce a unique fingerprint."""
    faces = [
        _face(normal=(1.0, 0.0, 0.0), centroid=(0.01, 0.0, 0.005)),
        _face(normal=(-1.0, 0.0, 0.0), centroid=(-0.01, 0.0, 0.005)),
        _face(normal=(0.0, 1.0, 0.0), centroid=(0.0, 0.01, 0.005)),
        _face(normal=(0.0, -1.0, 0.0), centroid=(0.0, -0.01, 0.005)),
        _face(normal=(0.0, 0.0, 1.0), centroid=(0.0, 0.0, 0.01)),
        _face(normal=(0.0, 0.0, -1.0), centroid=(0.0, 0.0, 0.0)),
    ]
    fps = [fingerprint(f) for f in faces]
    assert len(set(fps)) == 6, f"collision detected: {fps}"
