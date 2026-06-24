"""Offline tests for observe_section — W58 (READ-ONLY-SEAT lane).

Tests the parser (read_section_props) and the top-level observer
(sw_get_section_props) with mocked COM objects.  No SOLIDWORKS session
required; run as part of the standard offline suite.

All analytic values match the 20 mm × 20 mm square section used in the
W58 spike (spike_section_props.py).

Gate: every test here must be green before the W0 seat fire.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_sw_bridge.observe_section import (
    _sw_get_section_props_impl,
    read_section_props,
)

# ── Analytic fixture values — 20 mm × 20 mm square section ───────────────────
#
# A 20 mm × 20 mm square face (top face of a 20 mm cube, at Z = 20 mm).
# All values as returned by SW GetSectionProperties2 (SI/metric units).
#
# - area            = 0.020 × 0.020 = 4.000e-4 m²
# - centroid        = (0, 0, 0.020) m
# - Ixx = Iyy       = 0.020 × (0.020)³ / 12 = 1.3333e-8 m⁴
# - Ixy             = 0  (symmetric)
# - polar Jp        = Ixx + Iyy = 2.6667e-8 m⁴
# - principal lx=ly = 1.3333e-8 m⁴ (square → already principal)
# - principal angle = 0 rad

_IXX_M4 = 0.020 * (0.020**3) / 12  # 1.3333e-8
_JP_M4 = 2 * _IXX_M4  # 2.6667e-8


def _good_raw() -> list[float]:
    """Build the 24-element array that GetSectionProperties2 would return
    for a 20 mm × 20 mm square face.

    Array layout (CHM, GetSectionProperties2 Remarks):
      [0]   status = 0 (success)
      [1]   area   = 4.0e-4 m²
      [2-4] centroid (0, 0, 0.020) m
      [5]   Ixx = 1.333e-8 m⁴
      [6]   Iyy = 1.333e-8 m⁴
      [7]   Izz = 1.333e-8 m⁴  (same for a square)
      [8]   -Ixy = 0  m⁴
      [9]   -Izx = 0  m⁴
      [10]  -Iyz = 0  m⁴
      [11]  Jp   = 2.667e-8 m⁴
      [12]  principal angle = 0 rad
      [13]  principal lx = 1.333e-8 m⁴
      [14]  principal ly = 1.333e-8 m⁴
      [15-17] principal axis X = (1, 0, 0)
      [18-20] principal axis Y = (0, 1, 0)
      [21-23] principal axis Z = (0, 0, 1)
    """
    return [
        0.0,  # [0]  status = success
        4.0e-4,  # [1]  area m²
        0.0,  # [2]  centroid x m
        0.0,  # [3]  centroid y m
        0.020,  # [4]  centroid z m
        _IXX_M4,  # [5]  Ixx m⁴
        _IXX_M4,  # [6]  Iyy m⁴
        _IXX_M4,  # [7]  Izz m⁴
        0.0,  # [8]  -Ixy m⁴
        0.0,  # [9]  -Izx m⁴
        0.0,  # [10] -Iyz m⁴
        _JP_M4,  # [11] polar Jp m⁴
        0.0,  # [12] principal angle rad
        _IXX_M4,  # [13] principal lx m⁴
        _IXX_M4,  # [14] principal ly m⁴
        1.0,
        0.0,
        0.0,  # [15-17] axis X direction
        0.0,
        1.0,
        0.0,  # [18-20] axis Y direction
        0.0,
        0.0,
        1.0,  # [21-23] axis Z direction
    ]


# ── Tests: read_section_props parser ─────────────────────────────────────────


class TestReadSectionProps:

    def test_status_ok_flag(self):
        props = read_section_props(_good_raw())
        assert props["status"] == 0
        assert props["status_ok"] is True
        assert props["status_message"] is None
        assert props["errors"] == []

    def test_area_conversion(self):
        props = read_section_props(_good_raw())
        # 4.0e-4 m² × 1e6 = 400.0 mm²
        assert props["area_mm2"] == pytest.approx(400.0, rel=1e-6)

    def test_centroid_conversion(self):
        props = read_section_props(_good_raw())
        cx = props["centroid_mm"]
        assert cx is not None
        assert cx[0] == pytest.approx(0.0, abs=1e-9)
        assert cx[1] == pytest.approx(0.0, abs=1e-9)
        # 0.020 m × 1e3 = 20.0 mm
        assert cx[2] == pytest.approx(20.0, rel=1e-6)

    def test_moment_ixx_conversion(self):
        props = read_section_props(_good_raw())
        # 1.3333e-8 m⁴ × 1e12 = 13333.33 mm⁴
        assert props["ixx_mm4"] == pytest.approx(13333.33, rel=1e-4)

    def test_moment_iyy_equal_to_ixx(self):
        props = read_section_props(_good_raw())
        assert props["iyy_mm4"] == pytest.approx(props["ixx_mm4"], rel=1e-9)

    def test_product_ixy_near_zero(self):
        props = read_section_props(_good_raw())
        # Symmetric square → -Ixy = 0
        assert props["ixy_mm4"] == pytest.approx(0.0, abs=1e-9)

    def test_polar_moment_jp(self):
        props = read_section_props(_good_raw())
        # Jp = Ixx + Iyy = 2 × 13333.33 = 26666.67 mm⁴
        assert props["jp_mm4"] == pytest.approx(26666.67, rel=1e-4)

    def test_principal_angle_degrees(self):
        props = read_section_props(_good_raw())
        # 0 rad → 0 deg
        assert props["principal_angle_deg"] == pytest.approx(0.0, abs=1e-9)

    def test_principal_axis_x(self):
        props = read_section_props(_good_raw())
        ax = props["principal_axis_x"]
        assert ax is not None
        assert ax == pytest.approx([1.0, 0.0, 0.0], abs=1e-9)

    def test_principal_axis_y(self):
        props = read_section_props(_good_raw())
        assert props["principal_axis_y"] == pytest.approx([0.0, 1.0, 0.0], abs=1e-9)

    def test_principal_axis_z(self):
        props = read_section_props(_good_raw())
        assert props["principal_axis_z"] == pytest.approx([0.0, 0.0, 1.0], abs=1e-9)

    def test_status_invalid_input(self):
        raw = _good_raw()
        raw[0] = 1.0  # status = invalid input
        props = read_section_props(raw)
        assert props["status_ok"] is False
        assert props["status"] == 1
        assert "invalid input" in props["status_message"]
        assert props["area_mm2"] is None  # not populated on non-zero status

    def test_status_not_coplanar(self):
        raw = _good_raw()
        raw[0] = 2.0
        props = read_section_props(raw)
        assert props["status_ok"] is False
        assert "not in the same or parallel planes" in props["status_message"]

    def test_status_compute_fail(self):
        raw = _good_raw()
        raw[0] = 3.0
        props = read_section_props(raw)
        assert props["status_ok"] is False
        assert "unable to compute" in props["status_message"]

    def test_returns_none_on_none_input(self):
        props = read_section_props(None)
        assert props["status_ok"] is False
        assert props["errors"]
        assert props["area_mm2"] is None

    def test_returns_error_on_short_array(self):
        props = read_section_props([0.0] * 10)  # only 10 elements
        assert props["errors"]
        assert "expected 24 elements" in props["errors"][0]

    def test_all_output_keys_present(self):
        props = read_section_props(_good_raw())
        expected_keys = {
            "status",
            "status_ok",
            "status_message",
            "area_mm2",
            "centroid_mm",
            "ixx_mm4",
            "iyy_mm4",
            "izz_mm4",
            "ixy_mm4",
            "izx_mm4",
            "iyz_mm4",
            "jp_mm4",
            "principal_angle_deg",
            "ix_mm4",
            "iy_mm4",
            "principal_axis_x",
            "principal_axis_y",
            "principal_axis_z",
            "errors",
        }
        assert set(props.keys()) == expected_keys


# ── Tests: sw_get_section_props top-level observer ────────────────────────────


def _make_mock_doc(raw: list[float]) -> MagicMock:
    """Build a minimal mock of an IModelDoc2 dispatch object whose
    ``Extension.GetSectionProperties2(None)`` returns the given raw array."""
    ext = MagicMock()
    ext.GetSectionProperties2.return_value = raw
    doc = MagicMock()
    doc.Extension = ext
    return doc


class TestSwGetSectionProps:

    def test_ok_result_shape(self):
        doc = _make_mock_doc(_good_raw())
        result = _sw_get_section_props_impl(doc)
        assert result["ok"] is True
        assert result["error"] is None
        assert isinstance(result["section"], dict)

    def test_section_keys_complete(self):
        doc = _make_mock_doc(_good_raw())
        result = _sw_get_section_props_impl(doc)
        expected = {
            "area_mm2",
            "centroid_mm",
            "ixx_mm4",
            "iyy_mm4",
            "izz_mm4",
            "ixy_mm4",
            "izx_mm4",
            "iyz_mm4",
            "jp_mm4",
            "principal_angle_deg",
            "ix_mm4",
            "iy_mm4",
            "principal_axis_x",
            "principal_axis_y",
            "principal_axis_z",
        }
        assert set(result["section"].keys()) == expected

    def test_area_value_propagated(self):
        doc = _make_mock_doc(_good_raw())
        result = _sw_get_section_props_impl(doc)
        assert result["section"]["area_mm2"] == pytest.approx(400.0, rel=1e-6)

    def test_centroid_value_propagated(self):
        doc = _make_mock_doc(_good_raw())
        result = _sw_get_section_props_impl(doc)
        cx = result["section"]["centroid_mm"]
        assert cx[2] == pytest.approx(20.0, rel=1e-6)

    def test_no_active_doc(self):
        result = _sw_get_section_props_impl(None)
        assert result["ok"] is False
        assert result["error"] == "no_active_doc"
        assert result["section"] is None

    def test_extension_attribute_error(self):
        """doc.Extension raises AttributeError — observer should fall back
        to typed() path.  Since no real typed() is available offline, it
        is expected to fail cleanly (ok=False, error non-empty)."""
        doc = MagicMock(spec=[])  # spec=[] → AttributeError on all attrs
        result = _sw_get_section_props_impl(doc)
        assert result["ok"] is False
        assert result["error"] is not None

    def test_get_section_props_com_failure(self):
        """GetSectionProperties2 raises — observer returns ok=False."""
        ext = MagicMock()
        ext.GetSectionProperties2.side_effect = Exception("COM error: member not found")
        doc = MagicMock()
        doc.Extension = ext
        result = _sw_get_section_props_impl(doc)
        assert result["ok"] is False
        assert "GetSectionProperties2 failed" in result["error"]
        # section dict is None when COM itself raises
        assert result["section"] is None

    def test_com_returns_none(self):
        """GetSectionProperties2 returns None — observer reports error."""
        doc = _make_mock_doc(None)
        result = _sw_get_section_props_impl(doc)
        assert result["ok"] is False
        assert result["error"] is not None

    def test_status_nonzero_propagates_error(self):
        raw = _good_raw()
        raw[0] = 2.0  # not coplanar
        doc = _make_mock_doc(raw)
        result = _sw_get_section_props_impl(doc)
        assert result["ok"] is False
        assert "not in the same or parallel planes" in result["error"]

    def test_getsectionprops2_called_with_none(self):
        """Verify GetSectionProperties2 is invoked with None as the
        Sections argument (the pre-selected face path)."""
        doc = _make_mock_doc(_good_raw())
        _sw_get_section_props_impl(doc)
        doc.Extension.GetSectionProperties2.assert_called_once_with(None)
