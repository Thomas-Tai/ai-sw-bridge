"""Tests for the P1.7s sketch-primitive stub handlers.

Every stub follows the same contract: it pulls its spec fields into locals,
assembles the arg tuple for the matching ``ISketchManager.Create*`` call,
then raises ``NotImplementedError`` with the SEAT marker
``"P1.7-seat/W0"``. These tests pin the contract so a future P1.7-seat
session can replace each body with the live COM call and delete the test
(or rewrite it as a green-path assertion).

No COM is touched — ``ctx`` is a bare stub object since the handlers never
read ``ctx.doc`` before raising.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec import builder


class _StubCtx:
    """Stand-in for BuildContext — the stubs never read it."""


_PLANE = "Front"


class TestSketchStubsRaiseWithSeatMarker:
    """Each stub must raise NotImplementedError mentioning 'P1.7-seat/W0'."""

    def _check(self, handler, feat: dict[str, Any]) -> None:
        with pytest.raises(NotImplementedError, match=r"P1\.7-seat/W0"):
            handler(_StubCtx(), feat)

    def test_sketch_line(self) -> None:
        self._check(
            builder._build_sketch_line,
            {
                "type": "sketch_line",
                "name": "L1",
                "plane": _PLANE,
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 20.0, "y": 20.0},
            },
        )

    def test_sketch_arc(self) -> None:
        self._check(
            builder._build_sketch_arc,
            {
                "type": "sketch_arc",
                "name": "A1",
                "plane": _PLANE,
                "center": {"x": 30.0, "y": 0.0},
                "start": {"x": 40.0, "y": 0.0},
                "end": {"x": 30.0, "y": 10.0},
            },
        )

    def test_sketch_spline_2d(self) -> None:
        self._check(
            builder._build_sketch_spline,
            {
                "type": "sketch_spline",
                "name": "Sp1",
                "plane": _PLANE,
                "points": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 5.0},
                    {"x": 20.0, "y": 0.0},
                ],
            },
        )

    def test_sketch_spline_3d_detects_b3d(self) -> None:
        with pytest.raises(NotImplementedError, match=r"b3D=True"):
            builder._build_sketch_spline(
                _StubCtx(),
                {
                    "type": "sketch_spline",
                    "name": "Sp3d",
                    "plane": _PLANE,
                    "points": [
                        {"x": 0.0, "y": 0.0, "z": 0.0},
                        {"x": 10.0, "y": 5.0, "z": 1.0},
                    ],
                },
            )

    def test_sketch_slot(self) -> None:
        self._check(
            builder._build_sketch_slot,
            {
                "type": "sketch_slot",
                "name": "Sl1",
                "plane": _PLANE,
                "center": {"x": 30.0, "y": 30.0},
                "width": 6.0,
                "length": 20.0,
                "slot_type": "arc",
            },
        )

    def test_sketch_polygon(self) -> None:
        self._check(
            builder._build_sketch_polygon,
            {
                "type": "sketch_polygon",
                "name": "Pg1",
                "plane": _PLANE,
                "center": {"x": 50.0, "y": 30.0},
                "sides": 6,
                "radius": 8.0,
            },
        )

    def test_sketch_ellipse(self) -> None:
        self._check(
            builder._build_sketch_ellipse,
            {
                "type": "sketch_ellipse",
                "name": "El1",
                "plane": _PLANE,
                "center": {"x": 70.0, "y": 30.0},
                "major_radius": 10.0,
                "minor_radius": 5.0,
            },
        )

    def test_sketch_text(self) -> None:
        self._check(
            builder._build_sketch_text,
            {
                "type": "sketch_text",
                "name": "Tx1",
                "plane": _PLANE,
                "position": {"x": 0.0, "y": 50.0},
                "content": "hello",
                "height": 3.0,
                "font": "Arial",
            },
        )


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
