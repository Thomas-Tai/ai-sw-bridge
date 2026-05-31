"""Tests for the P1.7s sketch-primitive handlers.

The seven handlers (builder._build_sketch_*) run the literal-size life-cycle:
select the named reference plane -> InsertSketch -> call the seat-proven
ISketchManager.Create* (or IModelDoc2.InsertSketchText) -> close the sketch ->
rename the new sketch feature -> return a BuiltFeature. These tests drive each
handler against a fake COM seam (no pywin32, no SOLIDWORKS): they assert the
plane is selected, the sketch is opened and closed, the right Create* call fires
with the expected metre-converted args, and the BuiltFeature is shaped right.

The spline test monkeypatches ``builder._r8_safearray`` to an identity wrap so
the SAFEARRAY/VARIANT path needs no pywin32.

Live-seat validation (the geometry actually materialising) is covered by
spikes/v0_16/spike_sketch_primitives.py and _seatcheck_sketch_primitives_pae.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec import builder


class _FakeSketchFeature:
    def __init__(self) -> None:
        self.Name: str | None = None


class _FakeSketchManager:
    """Records every Create* call as (method_name, args)."""

    def __init__(self, log: list[tuple[str, tuple]]) -> None:
        self._log = log

    def InsertSketch(self, close: bool) -> None:
        self._log.append(("InsertSketch", (close,)))

    def __getattr__(self, name: str) -> Any:
        # Any Create* call (CreateLine, CreateArc, ...) is recorded generically.
        def _recorder(*args: Any) -> Any:
            self._log.append((name, args))
            return _FakeSketchFeature()

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

    def InsertSketchText(self, *args: Any) -> Any:
        self.log.append(("InsertSketchText", args))
        return _FakeSketchFeature()


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


def _assert_plane_lifecycle(ctx: _Ctx, name: str) -> None:
    # Plane selected by full name, sketch opened then closed, feature renamed.
    sel = _only(ctx, "SelectByID")
    assert sel[0] == "Front Plane" and sel[1] == "PLANE"
    inserts = _calls(ctx, "InsertSketch")
    assert inserts == [(True,), (True,)], inserts  # open then close
    assert ctx.doc._feat.Name == name


class TestSketchPrimitiveHandlers:
    def test_line(self) -> None:
        ctx = _Ctx()
        bf = builder._build_sketch_line(ctx, {
            "type": "sketch_line", "name": "L1", "plane": "Front",
            "start": {"x": 0.0, "y": 0.0}, "end": {"x": 20.0, "y": 20.0},
        })
        _approx_seq(_only(ctx, "CreateLine"), [0.0, 0.0, 0.0, 0.02, 0.02, 0.0])
        _assert_plane_lifecycle(ctx, "L1")
        assert (bf.name, bf.type) == ("L1", "sketch_line")

    def test_arc_ccw_default(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_arc(ctx, {
            "type": "sketch_arc", "name": "A1", "plane": "Front",
            "center": {"x": 30.0, "y": 0.0}, "start": {"x": 40.0, "y": 0.0},
            "end": {"x": 30.0, "y": 10.0},
        })
        _approx_seq(_only(ctx, "CreateArc"),
                    [0.03, 0.0, 0.0, 0.04, 0.0, 0.0, 0.03, 0.01, 0.0, 1])
        _assert_plane_lifecycle(ctx, "A1")

    def test_arc_cw_direction(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_arc(ctx, {
            "type": "sketch_arc", "name": "A2", "plane": "Front",
            "center": {"x": 0.0, "y": 0.0}, "start": {"x": 10.0, "y": 0.0},
            "end": {"x": 0.0, "y": 10.0}, "direction": "cw",
        })
        assert _only(ctx, "CreateArc")[-1] == -1

    def test_spline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(builder, "_r8_safearray", lambda v: list(v))
        ctx = _Ctx()
        builder._build_sketch_spline(ctx, {
            "type": "sketch_spline", "name": "Sp1", "plane": "Front",
            "points": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 5.0}, {"x": 20.0, "y": 0.0}],
        })
        args = _only(ctx, "CreateSpline2")
        assert args[1] is False
        _approx_seq(tuple(args[0]),
                    [0.0, 0.0, 0.0, 0.01, 0.005, 0.0, 0.02, 0.0, 0.0])
        _assert_plane_lifecycle(ctx, "Sp1")

    def test_slot(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_slot(ctx, {
            "type": "sketch_slot", "name": "Sl1", "plane": "Front",
            "center": {"x": 30.0, "y": 30.0}, "width": 6.0, "length": 20.0,
            "slot_type": "arc",
        })
        args = _only(ctx, "CreateSketchSlot")
        # creationType / lengthType must be ints (VT_I4), not floats.
        assert args[0] == 0 and isinstance(args[0], int)
        assert args[1] == 0 and isinstance(args[1], int)
        # width, P1, P2, P3, addDim, centerline
        _approx_seq(args, [
            0, 0, 0.006,
            0.02, 0.03, 0.0,   # P1 = center - half_len along +x
            0.04, 0.03, 0.0,   # P2 = center + half_len
            0.04, 0.033, 0.0,  # P3 = P2 + width/2 perpendicular
            False, True,
        ])
        _assert_plane_lifecycle(ctx, "Sl1")

    def test_polygon(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_polygon(ctx, {
            "type": "sketch_polygon", "name": "Pg1", "plane": "Front",
            "center": {"x": 50.0, "y": 30.0}, "sides": 6, "radius": 8.0,
        })
        args = _only(ctx, "CreatePolygon")
        _approx_seq(args, [0.05, 0.03, 0.0, 0.058, 0.03, 0.0, 6, True])
        assert isinstance(args[6], int)
        _assert_plane_lifecycle(ctx, "Pg1")

    def test_ellipse(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_ellipse(ctx, {
            "type": "sketch_ellipse", "name": "El1", "plane": "Front",
            "center": {"x": 70.0, "y": 30.0}, "major_radius": 10.0, "minor_radius": 5.0,
        })
        _approx_seq(_only(ctx, "CreateEllipse"),
                    [0.07, 0.03, 0.0, 0.08, 0.03, 0.0, 0.07, 0.035, 0.0])
        _assert_plane_lifecycle(ctx, "El1")

    def test_text(self) -> None:
        ctx = _Ctx()
        builder._build_sketch_text(ctx, {
            "type": "sketch_text", "name": "Tx1", "plane": "Front",
            "position": {"x": 0.0, "y": 50.0}, "content": "hello",
            "height": 3.0, "font": "Arial",
        })
        args = _only(ctx, "InsertSketchText")
        # x, y, z, content, useDocFmt(int), fmtX, fmtY, fmtZ, fmtAngle
        assert args[3] == "hello"
        assert args[4] == 1 and isinstance(args[4], int)
        _approx_seq((args[0], args[1], args[2]), [0.0, 0.05, 0.0])
        _assert_plane_lifecycle(ctx, "Tx1")


class TestMmToMHelper:
    """_mm_to_m converts LENGTH_SCHEMA mm literals to SW metres; {rhs} -> 0.0 placeholder."""

    def test_literal_mm_to_metres(self) -> None:
        assert builder._mm_to_m(1000.0) == pytest.approx(1.0)
        assert builder._mm_to_m(10.0) == pytest.approx(0.01)
        assert builder._mm_to_m(0.5) == pytest.approx(0.0005)

    def test_rhs_dict_returns_placeholder(self) -> None:
        assert builder._mm_to_m({"rhs": '"S1B_W"'}) == 0.0


class TestDescriptorRegistryCoversP17s:
    """Each P1.7s primitive is fully wired in the live DESCRIPTORS dict."""

    P17S_TYPES = (
        "sketch_line",
        "sketch_arc",
        "sketch_spline",
        "sketch_slot",
        "sketch_polygon",
        "sketch_ellipse",
        "sketch_text",
    )

    @pytest.mark.parametrize("name", P17S_TYPES)
    def test_descriptor_has_handler_and_fields(self, name: str) -> None:
        desc = builder.DESCRIPTORS[name]
        assert desc.handler is not None, f"{name} has no handler"
        assert desc.fields, f"{name} has no FieldSpec entries"
        assert desc.doc, f"{name} has no doc one-liner"
        assert desc.example_ref == "sketch_primitives"

    @pytest.mark.parametrize("name", P17S_TYPES)
    def test_handler_is_registered_and_callable(self, name: str) -> None:
        assert name in builder.HANDLERS
        assert callable(builder.HANDLERS[name])
