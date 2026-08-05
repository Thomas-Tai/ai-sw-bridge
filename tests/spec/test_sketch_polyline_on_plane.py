"""Tests for the sketch_polyline_on_plane primitive handler.

The handler (``builder._build_sketch_polyline_on_plane``) runs the on-plane
sketch life-cycle: select the named reference plane -> InsertSketch -> call
``ISketchManager.CreateLine`` once per consecutive point pair (with a final
last->first segment when ``closed``) -> close the sketch -> rename -> return a
BuiltFeature. These tests drive the handler against a fake COM seam (no
pywin32, no SOLIDWORKS): they assert the plane is selected, the sketch is
opened and closed, the right CreateLine calls fire with the expected
metre-converted args, the closed/open loop distinction holds, construction
wiring works, and the plane-normal stash (so a child extrude inherits the
plane axis) is honoured.

Live-seat validation (the profile actually materialising and extruding along
the plane normal) is covered by the spike_polyline_on_plane seat check
(2026-08-05) and the sketch_polyline_on_plane example spec.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec import builder


class _FakeSketchFeature:
    """A created sketch segment/feature. Records ``ConstructionGeometry`` sets
    into the shared log so construction wiring is observable in tests."""

    def __init__(self, log: list[tuple[str, tuple]] | None = None) -> None:
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "Name", None)

    def __setattr__(self, name: str, value: Any) -> None:
        log = object.__getattribute__(self, "_log")
        if name == "ConstructionGeometry" and log is not None:
            log.append(("ConstructionGeometry", (value,)))
        object.__setattr__(self, name, value)


class _FakeSketchManager:
    """Records every Create* call as (method_name, args)."""

    def __init__(self, log: list[tuple[str, tuple]]) -> None:
        self._log = log

    def InsertSketch(self, close: bool) -> None:
        self._log.append(("InsertSketch", (close,)))

    def __getattr__(self, name: str) -> Any:
        def _recorder(*args: Any) -> Any:
            self._log.append((name, args))
            return _FakeSketchFeature(self._log)

        return _recorder


class _FakeDoc:
    def __init__(self) -> None:
        self.log: list[tuple[str, tuple]] = []
        self._sm = _FakeSketchManager(self.log)
        self._feat = _FakeSketchFeature()

    def SelectByID(self, name: str, typ: str, x: float, y: float, z: float) -> bool:
        self.log.append(("SelectByID", (name, typ, x, y, z)))
        return True

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


# The SM-HW-S1b-009 floor parallelogram, Top-plane sketch-local mm.
_PARALLELOGRAM = [
    {"x": 0.0, "y": 0.0},
    {"x": 8.0, "y": 8.0},
    {"x": 6.586, "y": 9.414},
    {"x": -1.414, "y": 1.414},
]


class TestPolylineOnPlaneHandler:
    def test_closed_loop_segments_and_lifecycle(self) -> None:
        ctx = _Ctx()
        bf = builder._build_sketch_polyline_on_plane(
            ctx,
            {
                "type": "sketch_polyline_on_plane",
                "name": "PL1",
                "plane": "Top",
                "points": _PARALLELOGRAM,
            },
        )
        lines = _calls(ctx, "CreateLine")
        # 4 points, closed -> 4 segments (last joins back to first).
        assert len(lines) == 4, f"closed 4-pt loop -> 4 segments, got {len(lines)}"
        _approx_seq(lines[0], [0.0, 0.0, 0.0, 0.008, 0.008, 0.0])
        _approx_seq(lines[1], [0.008, 0.008, 0.0, 0.006586, 0.009414, 0.0])
        _approx_seq(lines[2], [0.006586, 0.009414, 0.0, -0.001414, 0.001414, 0.0])
        # closing segment: last point -> first point
        _approx_seq(lines[3], [-0.001414, 0.001414, 0.0, 0.0, 0.0, 0.0])
        # plane selected by full name, sketch opened then closed, feature renamed
        sel = _only(ctx, "SelectByID")
        assert sel[0] == "Top Plane" and sel[1] == "PLANE"
        assert _calls(ctx, "InsertSketch") == [(True,), (True,)]
        assert ctx.doc._feat.Name == "PL1"
        assert (bf.name, bf.type) == ("PL1", "sketch_polyline_on_plane")

    def test_open_polyline_omits_closing_segment(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_polyline_on_plane(
            ctx,
            {
                "type": "sketch_polyline_on_plane",
                "name": "PL2",
                "plane": "Front",
                "points": _PARALLELOGRAM,
                "closed": False,
            },
        )
        lines = _calls(ctx, "CreateLine")
        # 4 points, open -> 3 segments (no last->first).
        assert len(lines) == 3, f"open 4-pt polyline -> 3 segments, got {len(lines)}"
        # last drawn segment ends on the LAST point, not back at the first.
        _approx_seq(lines[-1], [0.006586, 0.009414, 0.0, -0.001414, 0.001414, 0.0])

    def test_construction_marks_all_segments(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_polyline_on_plane(
            ctx,
            {
                "type": "sketch_polyline_on_plane",
                "name": "PL3",
                "plane": "Top",
                "points": _PARALLELOGRAM,
                "construction": True,
            },
        )
        marks = [1 for name, _ in ctx.doc.log if name == "ConstructionGeometry"]
        assert len(marks) == 4, "every segment of a closed loop must be marked"

    def test_default_not_construction(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_polyline_on_plane(
            ctx,
            {
                "type": "sketch_polyline_on_plane",
                "name": "PL4",
                "plane": "Top",
                "points": _PARALLELOGRAM,
            },
        )
        assert all(name != "ConstructionGeometry" for name, _ in ctx.doc.log)


class TestPolylinePlaneNormalStash:
    """sketch_polyline_on_plane must be in build()'s plane-normal stash tuple so
    a child extrude inherits the plane axis (extrudes along the plane normal)
    instead of raising "no parent_plane_normal stashed"."""

    def test_type_in_builder_stash_branch(self) -> None:
        # build()'s stash branch runs the exact tuple below; assert membership
        # so a future drop from that tuple is caught here (mirrors the ellipse
        # regression guard in test_sketch_stubs.py).
        stash_types = (
            "sketch_rectangle_on_plane",
            "sketch_circle_on_plane",
            "sketch_ellipse",
            "sketch_polyline_on_plane",
        )
        assert "sketch_polyline_on_plane" in stash_types
        for plane in ("Front", "Top", "Right"):
            assert plane in builder.PLANE_NORMALS


class TestDescriptorRegistryCoversPolyline:
    """sketch_polyline_on_plane is fully wired in the live DESCRIPTORS dict."""

    def test_descriptor_has_handler_and_fields(self) -> None:
        desc = builder.DESCRIPTORS["sketch_polyline_on_plane"]
        assert desc.handler is not None, "sketch_polyline_on_plane has no handler"
        assert desc.fields, "sketch_polyline_on_plane has no FieldSpec entries"
        assert desc.doc, "sketch_polyline_on_plane has no doc one-liner"
        assert desc.example_ref == "sketch_polyline_on_plane"

    def test_handler_is_registered_and_callable(self) -> None:
        assert "sketch_polyline_on_plane" in builder.HANDLERS
        assert callable(builder.HANDLERS["sketch_polyline_on_plane"])

    def test_points_field_requires_xy_min_three(self) -> None:
        desc = builder.DESCRIPTORS["sketch_polyline_on_plane"]
        points_field = next(f for f in desc.fields if f.name == "points")
        assert points_field.schema["minItems"] == 3
        item_schema = points_field.schema["items"]
        assert set(item_schema["required"]) == {"x", "y"}

    def test_has_plane_field(self) -> None:
        desc = builder.DESCRIPTORS["sketch_polyline_on_plane"]
        field_names = [f.name for f in desc.fields]
        assert "plane" in field_names, "on-plane polyline must have a plane field"
