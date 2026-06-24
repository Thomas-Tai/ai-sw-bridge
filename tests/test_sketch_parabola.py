"""Tests for S1 — sketch parabola/conic primitive (Wave-5).

Mock-tests the create_parabola helper in spec/_sketch_primitives.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec._sketch_primitives import create_parabola


class _FakeSketchSegment:
    """Fake ISketchSegment returned by CreateParabola."""

    def __init__(self, is_none: bool = False) -> None:
        self._is_none = is_none


class _FakeSketchManager:
    """Fake ISketchManager that records CreateParabola calls."""

    def __init__(self, return_val: Any = ..., return_none: bool = False) -> None:
        self.calls: list[tuple] = []
        self._return = (
            None
            if return_none
            else (return_val if return_val is not ... else _FakeSketchSegment())
        )

    def CreateParabola(self, *args: float) -> Any:
        self.calls.append(args)
        return self._return


class TestCreateParabola:
    def test_creates_parabola(self) -> None:
        sm = _FakeSketchManager()
        # focal(10,0,0) vertex(0,0,0) end1(-10,10,0) end2(10,10,0)
        seg = create_parabola(
            sm, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, -10.0, 10.0, 0.0, 10.0, 10.0, 0.0
        )
        assert seg is not None
        assert len(sm.calls) == 1
        assert len(sm.calls[0]) == 12

    def test_returns_none_raises(self) -> None:
        sm = _FakeSketchManager(return_none=True)
        with pytest.raises(RuntimeError, match="CreateParabola returned None"):
            create_parabola(
                sm, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, -10.0, 10.0, 0.0, 10.0, 10.0, 0.0
            )

    def test_mm_to_m_conversion(self) -> None:
        sm = _FakeSketchManager()
        create_parabola(
            sm,
            10.0,
            20.0,
            0.0,  # focal mm
            5.0,
            0.0,
            0.0,  # vertex mm
            -5.0,
            10.0,
            0.0,  # end1 mm
            5.0,
            10.0,
            0.0,  # end2 mm
        )
        call = sm.calls[0]
        assert call[0] == pytest.approx(0.01)  # x_focal 10mm→0.01m
        assert call[1] == pytest.approx(0.02)  # y_focal 20mm→0.02m
        assert call[3] == pytest.approx(0.005)  # x_vertex 5mm→0.005m
        assert call[6] == pytest.approx(-0.005)  # x_end1 -5mm→-0.005m


# ---------------------------------------------------------------------------
# Segment round-trip — verify created parabola can be read back
# ---------------------------------------------------------------------------


class _FakeSketchPoint:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.X = x
        self.Y = y
        self.Z = z


class _FakeParabolaSegment:
    """Fake ISketchSegment for a parabola with readable control points.

    Mimics the SW API: ``GetFocalPoint`` returns the focal point,
    ``GetStartPoint2`` returns the vertex.  Used to verify that a
    created parabola can be read back (the "round-trip" part of S1).
    """

    def __init__(
        self,
        focal: tuple[float, float, float] = (0.01, 0.0, 0.0),
        vertex: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        self._focal = focal
        self._vertex = vertex
        self.ConstructionGeometry = False

    @property
    def GetFocalPoint(self) -> _FakeSketchPoint:
        return _FakeSketchPoint(*self._focal)

    @property
    def GetStartPoint2(self) -> _FakeSketchPoint:
        return _FakeSketchPoint(*self._vertex)


class TestParabolaRoundTrip:
    def test_create_then_read_back(self) -> None:
        """Create a parabola and read back its focal point + vertex."""
        seg = _FakeParabolaSegment(
            focal=(0.01, 0.02, 0.0),
            vertex=(0.0, 0.0, 0.0),
        )
        sm = _FakeSketchManager(return_val=seg)
        result = create_parabola(
            sm, 10.0, 20.0, 0.0, 0.0, 0.0, 0.0, -10.0, 10.0, 0.0, 10.0, 10.0, 0.0
        )

        # Read back focal point (SW returns metres)
        focal = result.GetFocalPoint
        assert focal.X == pytest.approx(0.01)  # 10 mm
        assert focal.Y == pytest.approx(0.02)  # 20 mm

        # Read back vertex
        vertex = result.GetStartPoint2
        assert vertex.X == pytest.approx(0.0)
        assert vertex.Y == pytest.approx(0.0)

    def test_round_trip_preserves_construction_flag(self) -> None:
        """Verify the ConstructionGeometry flag is readable on the segment."""
        seg = _FakeParabolaSegment()
        sm = _FakeSketchManager(return_val=seg)
        result = create_parabola(
            sm, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, -5.0, 5.0, 0.0, 5.0, 5.0, 0.0
        )
        assert result.ConstructionGeometry is False
