"""Tests for brep.surface_eval — E2 surface UV evaluation (Wave-5).

Mock-tests evaluate_surface_at_uv and get_surface_parameter_range
without a SOLIDWORKS seat.

Seat-validated findings baked in:
  - ISurface.Evaluate takes 4 args (u, v, u, v) and returns 6-tuple
    (x, y, z, nx, ny, nz).
  - typed() (not typed_qi) is used for IFace2 and ISurface.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.brep.surface_eval import (
    evaluate_surface_at_uv,
    get_surface_parameter_range,
)


class _FakeSurface:
    """Fake ISurface with Evaluate (4-arg, seat-validated)."""

    def __init__(
        self,
        point: tuple[float, ...] = (0.01, 0.02, 0.03),
        normal: tuple[float, ...] = (0.0, 0.0, 1.0),
        param_range: tuple[float, ...] = (0.0, 1.0, 0.0, 1.0),
    ) -> None:
        self._point = point
        self._normal = normal
        # Seat-validated (SW 2024 SP1, 2026-06-01): Parameterization()
        # returns an 11-element tuple whose first 4 entries are
        # (u_min, u_max, v_min, v_max). The remaining 7 entries are
        # garbage floats; pad with zeros for the fake.
        self._param_range = tuple(param_range) + (0.0,) * (11 - len(param_range))

    def Evaluate(self, u1: float, v1: float, u2: float, v2: float) -> tuple[float, ...]:
        """Seat-validated 4-arg form returns (x, y, z, nx, ny, nz)."""
        return (*self._point, *self._normal)

    def Parameterization(self) -> tuple[float, ...]:
        return self._param_range


class _FakeFace:
    """Fake IFace2 with GetSurface."""

    def __init__(self, surface: Any = None) -> None:
        self._surface = surface or _FakeSurface()

    def GetSurface(self) -> Any:
        return self._surface


class _FakeFaceNoSurface:
    def GetSurface(self) -> Any:
        return None


class _FakeFaceRaise:
    def GetSurface(self) -> Any:
        raise RuntimeError("COM error")


def _fake_typed(obj: Any, iface: str, module: Any = None) -> Any:
    """Passthrough — returns the object unchanged."""
    return obj


class TestEvaluateSurfaceAtUv:
    def test_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ai_sw_bridge.com.earlybind as eb_mod
        monkeypatch.setattr(eb_mod, "typed", _fake_typed)
        face = _FakeFace()
        result = evaluate_surface_at_uv(face, 0.5, 0.5)
        assert result["ok"] is True
        assert result["point_mm"] == [pytest.approx(10.0), pytest.approx(20.0), pytest.approx(30.0)]
        assert result["normal"] == [pytest.approx(0.0), pytest.approx(0.0), pytest.approx(1.0)]
        assert result["error"] is None

    def test_get_surface_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ai_sw_bridge.com.earlybind as eb_mod
        monkeypatch.setattr(eb_mod, "typed", _fake_typed)
        face = _FakeFaceNoSurface()
        result = evaluate_surface_at_uv(face, 0.5, 0.5)
        assert result["ok"] is False
        assert "returned None" in result["error"]

    def test_get_surface_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ai_sw_bridge.com.earlybind as eb_mod
        monkeypatch.setattr(eb_mod, "typed", _fake_typed)
        face = _FakeFaceRaise()
        result = evaluate_surface_at_uv(face, 0.5, 0.5)
        assert result["ok"] is False
        assert "GetSurface failed" in result["error"]


class TestGetSurfaceParameterRange:
    def test_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ai_sw_bridge.com.earlybind as eb_mod
        monkeypatch.setattr(eb_mod, "typed", _fake_typed)
        face = _FakeFace()
        result = get_surface_parameter_range(face)
        assert result["ok"] is True
        assert result["u_min"] == pytest.approx(0.0)
        assert result["u_max"] == pytest.approx(1.0)

    def test_get_surface_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ai_sw_bridge.com.earlybind as eb_mod
        monkeypatch.setattr(eb_mod, "typed", _fake_typed)
        face = _FakeFaceNoSurface()
        result = get_surface_parameter_range(face)
        assert result["ok"] is False
