"""Tests for observe_inertia — E1 inertia-tensor helper (Wave-5).

Mock-tests the read_inertia / sw_get_inertia functions without a SW seat.
Seat-validated findings baked in: IMassProperty2 typed QI fails
(E_NOINTERFACE), inertia tensor reads need VARIANT marshaling that
currently fails out-of-process.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from ai_sw_bridge.observe_inertia import read_inertia, sw_get_inertia


class _FakeMassProperty:
    """Fake IMassProperty2 (late-bound proxy behavior).

    Volume/SurfaceArea/Mass/Density/CenterOfMass work as properties.
    Inertia tensor methods fail (COM marshaling wall).
    """

    def __init__(self) -> None:
        self.Volume = 4e-6
        self.SurfaceArea = 0.0016
        self.Mass = 4e-6
        self.Density = 1000.0
        self.CenterOfMass = (0.0, 0.0, 0.005)


class _FakeMassPropertyFailing:
    """Fake IMassProperty2 where all reads raise."""

    @property
    def CenterOfMass(self) -> Any:
        raise RuntimeError("COM error")


class _FakeDocExtension:
    def __init__(self, mp: Any) -> None:
        self._mp = mp

    @property
    def CreateMassProperty(self) -> Any:
        return self._mp


class _FakeDoc:
    def __init__(self, mp: Any) -> None:
        self.Extension = _FakeDocExtension(mp)


class _FakeDocNoExt:
    @property
    def Extension(self) -> Any:
        raise RuntimeError("Extension unavailable")


def _fake_typed(obj: Any, iface: str, module: Any = None) -> Any:
    """Passthrough typed() that returns the object unchanged."""
    return obj


class TestReadInertia:
    @patch("ai_sw_bridge.observe_inertia.typed", _fake_typed)
    def test_reads_center_of_mass(self) -> None:
        mp = _FakeMassProperty()
        result = read_inertia(mp)
        assert result["center_of_mass_mm"] == [
            pytest.approx(0.0),
            pytest.approx(0.0),
            pytest.approx(5.0),
        ]

    @patch("ai_sw_bridge.observe_inertia.typed", _fake_typed)
    def test_inertia_reads_fail_soft(self) -> None:
        """Inertia tensor reads fail due to COM marshaling wall — fail-soft."""
        mp = _FakeMassProperty()
        result = read_inertia(mp)
        # PrincipalAxesOfInertia and GetMomentOfInertia are not on the
        # fake — they'll error, which is expected behavior.
        assert result["principal_axes"] is None
        assert result["moments_of_inertia_kg_mm2"] is None
        assert len(result["errors"]) >= 1

    @patch("ai_sw_bridge.observe_inertia.typed", _fake_typed)
    def test_handles_com_failure(self) -> None:
        mp = _FakeMassPropertyFailing()
        result = read_inertia(mp)
        assert result["center_of_mass_mm"] is None
        assert any("CenterOfMass" in e for e in result["errors"])


class TestSwGetInertia:
    @patch("ai_sw_bridge.observe_inertia.typed", _fake_typed)
    @patch("ai_sw_bridge.com.earlybind.typed", _fake_typed)
    @patch("ai_sw_bridge.com.sw_type_info.wrapper_module", lambda: object())
    def test_ok(self) -> None:
        mp = _FakeMassProperty()
        doc = _FakeDoc(mp)
        result = sw_get_inertia(doc)
        assert result["ok"] is True
        assert result["center_of_mass_mm"] is not None

    def test_extension_fails(self) -> None:
        doc = _FakeDocNoExt()
        result = sw_get_inertia(doc)
        assert result["ok"] is False
        assert "Extension" in result["error"]

    @patch("ai_sw_bridge.com.earlybind.typed", _fake_typed)
    @patch("ai_sw_bridge.com.sw_type_info.wrapper_module", lambda: object())
    def test_mass_property_none(self) -> None:
        doc = _FakeDoc(None)
        result = sw_get_inertia(doc)
        assert result["ok"] is False
        assert "returned None" in result["error"]
