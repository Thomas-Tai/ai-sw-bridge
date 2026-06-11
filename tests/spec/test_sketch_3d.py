"""Tests for the W53 3D-sketch primitive handler.

The handler (``builder._build_sketch_3d_sketch``) runs the literal-size
life-cycle: open a 3D sketch via ``Insert3DSketch(True)`` (BOOL
UpdateEditRebuild, no plane selection) ->
call ``CreateLine`` for each consecutive point pair with real X/Y/Z -> close
via ``Insert3DSketch(True)`` -> rename -> return ``BuiltFeature``.

These tests drive the handler against a fake COM seam (no pywin32, no
SOLIDWORKS): they assert the 3D sketch is opened and closed (via
``Insert3DSketch``, NOT ``InsertSketch``), the right ``CreateLine`` calls
fire with the expected metre-converted args (including real Z), and the
``BuiltFeature`` is shaped right.

Live-seat validation is covered by ``spikes/v0_21/spike_sketch_3d.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec import builder


class _FakeSketchFeature:
    """A created sketch segment."""

    def __init__(self) -> None:
        self.Name: str | None = None


class _FakeSketchManager:
    """Records every Insert3DSketch / Create* call as (method_name, args)."""

    def __init__(self, log: list[tuple[str, tuple]]) -> None:
        self._log = log

    def Insert3DSketch(self, update: bool = False) -> None:
        self._log.append(("Insert3DSketch", (update,)))

    def __getattr__(self, name: str) -> Any:
        def _recorder(*args: Any) -> Any:
            self._log.append((name, args))
            return _FakeSketchFeature()

        return _recorder


class _FakeDoc:
    def __init__(self) -> None:
        self.log: list[tuple[str, tuple]] = []
        self._sm = _FakeSketchManager(self.log)
        self._feat = _FakeSketchFeature()

    @property
    def SketchManager(self) -> _FakeSketchManager:
        return self._sm

    def FeatureByPositionReverse(self, idx: int) -> _FakeSketchFeature:
        self.log.append(("FeatureByPositionReverse", (idx,)))
        return self._feat


class _Ctx:
    def __init__(self) -> None:
        self.doc = _FakeDoc()


def _calls(ctx: _Ctx, method: str) -> list[tuple]:
    return [args for (name, args) in ctx.doc.log if name == method]


def _only(ctx: _Ctx, method: str) -> tuple:
    hits = _calls(ctx, method)
    assert len(hits) == 1, f"expected exactly one {method}, got {len(hits)}"
    return hits[0]


def _approx_seq(actual: tuple, expected: list) -> None:
    assert len(actual) == len(expected), (actual, expected)
    for a, e in zip(actual, expected):
        if isinstance(e, float):
            assert a == pytest.approx(e, abs=1e-9), (actual, expected)
        else:
            assert a == e, (actual, expected)


_NON_PLANAR_POINTS = [
    {"x": 0.0, "y": 0.0, "z": 0.0},
    {"x": 100.0, "y": 0.0, "z": 0.0},
    {"x": 100.0, "y": 50.0, "z": 30.0},
    {"x": 0.0, "y": 50.0, "z": 60.0},
]


class TestSketch3DHandler:
    def test_non_planar_polyline(self) -> None:
        ctx = _Ctx()
        bf = builder._build_sketch_3d_sketch(ctx, {
            "type": "sketch_3d_sketch",
            "name": "S3D1",
            "points": _NON_PLANAR_POINTS,
        })
        assert (bf.name, bf.type) == ("S3D1", "sketch_3d_sketch")

    def test_insert3d_sketch_opens_and_closes(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_3d_sketch(ctx, {
            "type": "sketch_3d_sketch",
            "name": "S3D1",
            "points": _NON_PLANAR_POINTS,
        })
        toggles = _calls(ctx, "Insert3DSketch")
        assert len(toggles) == 2, f"expected open+close toggles, got {toggles}"
        assert toggles == [(True,), (True,)]

    def test_no_plane_selection(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_3d_sketch(ctx, {
            "type": "sketch_3d_sketch",
            "name": "S3D1",
            "points": _NON_PLANAR_POINTS,
        })
        sel = _calls(ctx, "SelectByID")
        assert sel == [], f"3D sketch must NOT select a plane, got {sel}"

    def test_no_insert_sketch_2d(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_3d_sketch(ctx, {
            "type": "sketch_3d_sketch",
            "name": "S3D1",
            "points": _NON_PLANAR_POINTS,
        })
        ins2d = _calls(ctx, "InsertSketch")
        assert ins2d == [], f"3D sketch must use Insert3DSketch, got {ins2d}"

    def test_create_line_segments_with_real_z(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_3d_sketch(ctx, {
            "type": "sketch_3d_sketch",
            "name": "S3D1",
            "points": _NON_PLANAR_POINTS,
        })
        lines = _calls(ctx, "CreateLine")
        assert len(lines) == 3, f"4 points -> 3 segments, got {len(lines)}"
        _approx_seq(lines[0], [0.0, 0.0, 0.0, 0.1, 0.0, 0.0])
        _approx_seq(lines[1], [0.1, 0.0, 0.0, 0.1, 0.05, 0.03])
        _approx_seq(lines[2], [0.1, 0.05, 0.03, 0.0, 0.05, 0.06])

    def test_z_extent_nonzero(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_3d_sketch(ctx, {
            "type": "sketch_3d_sketch",
            "name": "S3D1",
            "points": _NON_PLANAR_POINTS,
        })
        lines = _calls(ctx, "CreateLine")
        z_vals = [args[2] for args in lines] + [args[5] for args in lines]
        assert any(z != 0.0 for z in z_vals), "Z extent must be non-zero"

    def test_feature_renamed(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_3d_sketch(ctx, {
            "type": "sketch_3d_sketch",
            "name": "S3D1",
            "points": _NON_PLANAR_POINTS,
        })
        assert ctx.doc._feat.Name == "S3D1"

    def test_two_point_minimum(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_3d_sketch(ctx, {
            "type": "sketch_3d_sketch",
            "name": "S3D1",
            "points": [
                {"x": 0.0, "y": 0.0, "z": 0.0},
                {"x": 10.0, "y": 20.0, "z": 30.0},
            ],
        })
        lines = _calls(ctx, "CreateLine")
        assert len(lines) == 1
        _approx_seq(lines[0], [0.0, 0.0, 0.0, 0.01, 0.02, 0.03])


class TestDescriptorRegistryCoversW53:
    """sketch_3d_sketch is fully wired in the live DESCRIPTORS dict."""

    def test_descriptor_has_handler_and_fields(self) -> None:
        desc = builder.DESCRIPTORS["sketch_3d_sketch"]
        assert desc.handler is not None, "sketch_3d_sketch has no handler"
        assert desc.fields, "sketch_3d_sketch has no FieldSpec entries"
        assert desc.doc, "sketch_3d_sketch has no doc one-liner"
        assert desc.example_ref == "sketch_3d_primitives"

    def test_handler_is_registered_and_callable(self) -> None:
        assert "sketch_3d_sketch" in builder.HANDLERS
        assert callable(builder.HANDLERS["sketch_3d_sketch"])

    def test_schema_types_includes_3d_sketch(self) -> None:
        from ai_sw_bridge.spec.schema import SKETCH_TYPES

        assert "sketch_3d_sketch" in SKETCH_TYPES

    def test_points_field_requires_xyz(self) -> None:
        desc = builder.DESCRIPTORS["sketch_3d_sketch"]
        points_field = next(f for f in desc.fields if f.name == "points")
        item_schema = points_field.schema["items"]
        assert "z" in item_schema["required"], (
            "3D-sketch points must require z (non-planar prerequisite)"
        )

    def test_no_plane_field(self) -> None:
        desc = builder.DESCRIPTORS["sketch_3d_sketch"]
        field_names = [f.name for f in desc.fields]
        assert "plane" not in field_names, (
            "3D sketch must NOT have a plane field"
        )
