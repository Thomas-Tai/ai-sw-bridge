"""Tests for brep.math_util — E3 math-utility wrapper (Wave-5).

Mock-tests the MathUtility wrapper without a SOLIDWORKS seat.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.brep.math_util import MathUtility


class _FakeMathUtility:
    """Fake IMathUtility that records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def CreatePoint(self, coords: tuple[float, ...]) -> str:
        self.calls.append(("CreatePoint", coords))
        return f"MathPoint({coords})"

    def CreateVector(self, coords: tuple[float, ...]) -> str:
        self.calls.append(("CreateVector", coords))
        return f"MathVector({coords})"

    def CreateTransform(self, data: tuple[float, ...]) -> str:
        self.calls.append(("CreateTransform", data))
        return f"MathTransform({len(data)} elements)"


class _FakeApp:
    """Fake ISldWorks that returns a _FakeMathUtility."""

    def __init__(self, util: _FakeMathUtility | None = None) -> None:
        self._util = util

    def GetMathUtility(self) -> Any:
        return self._util


class TestMathUtilityFromApp:
    def test_from_app_ok(self) -> None:
        fake = _FakeMathUtility()
        mu = MathUtility.from_app(_FakeApp(fake))
        assert mu.raw is fake

    def test_from_app_none_raises(self) -> None:
        with pytest.raises(RuntimeError, match="GetMathUtility returned None"):
            MathUtility.from_app(_FakeApp(None))


class TestCreatePoint:
    def test_creates_point(self) -> None:
        fake = _FakeMathUtility()
        mu = MathUtility(fake)
        result = mu.create_point((0.01, 0.02, 0.03))
        assert result == "MathPoint((0.01, 0.02, 0.03))"
        assert fake.calls == [("CreatePoint", (0.01, 0.02, 0.03))]

    def test_rejects_wrong_length(self) -> None:
        mu = MathUtility(_FakeMathUtility())
        with pytest.raises(ValueError, match="point needs 3"):
            mu.create_point((1.0, 2.0))

    def test_coerces_int_to_float(self) -> None:
        fake = _FakeMathUtility()
        mu = MathUtility(fake)
        mu.create_point((1, 2, 3))
        assert fake.calls[0][1] == (1.0, 2.0, 3.0)


class TestCreateVector:
    def test_creates_vector(self) -> None:
        fake = _FakeMathUtility()
        mu = MathUtility(fake)
        result = mu.create_vector((0.0, 0.0, 1.0))
        assert result == "MathVector((0.0, 0.0, 1.0))"

    def test_rejects_wrong_length(self) -> None:
        mu = MathUtility(_FakeMathUtility())
        with pytest.raises(ValueError, match="vector needs 3"):
            mu.create_vector((1.0,))


class TestCreateTransform:
    def test_creates_transform(self) -> None:
        fake = _FakeMathUtility()
        mu = MathUtility(fake)
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        result = mu.create_transform(identity)
        assert "16 elements" in result

    def test_rejects_wrong_length(self) -> None:
        mu = MathUtility(_FakeMathUtility())
        with pytest.raises(ValueError, match="transform needs 16"):
            mu.create_transform([1.0, 2.0, 3.0])


class TestCreateTransformFromMoves:
    def test_pure_translation(self) -> None:
        fake = _FakeMathUtility()
        mu = MathUtility(fake)
        mu.create_transform_from_moves(0.01, 0.02, 0.03)
        method, data = fake.calls[0]
        assert method == "CreateTransform"
        assert data[3] == 0.01  # tx
        assert data[7] == 0.02  # ty
        assert data[11] == 0.03  # tz
        assert data[0] == 1.0  # r00
