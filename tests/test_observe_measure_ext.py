"""Offline tests for observe_measure extensions (W52).

Tests durable-ref pair, angle measure, and area measure
WITHOUT a running SOLIDWORKS session. Uses mocks for COM objects.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

from ai_sw_bridge.observe_measure import (
    read_measure_angle,
    read_measure_area,
    read_measure_durable_pair,
    sw_get_measure_angle_from_doc,
    sw_get_measure_area_from_doc,
    sw_get_measure_durable_pair,
)


MEASURE_PAIR_KEYS = frozenset(
    {"distance_mm", "delta_x_mm", "delta_y_mm", "delta_z_mm", "errors"}
)

SW_DURABLE_PAIR_KEYS = frozenset({"ok", "error", "measure"})
SW_ANGLE_KEYS = frozenset({"ok", "error", "measure"})
SW_AREA_KEYS = frozenset({"ok", "error", "measure"})


def _mock_typed_side_effect(iface_map):
    def side_effect(obj, iface, module=None):
        if iface in iface_map:
            return iface_map[iface]
        return MagicMock()
    return side_effect


def test_read_measure_angle_green():
    """Angle of pi/4 radians → 45.0 degrees."""
    mock_measure = MagicMock()
    mock_measure.Angle = math.pi / 4.0

    result = read_measure_angle(mock_measure)
    assert result["errors"] == []
    assert result["angle_deg"] is not None
    assert abs(result["angle_deg"] - 45.0) < 0.001


def test_read_measure_angle_none():
    """Angle returning None → error."""
    mock_measure = MagicMock()
    mock_measure.Angle = None

    result = read_measure_angle(mock_measure)
    assert result["angle_deg"] is None
    assert len(result["errors"]) > 0


def test_read_measure_angle_not_applicable():
    """Angle returning -1.0 → not applicable."""
    mock_measure = MagicMock()
    mock_measure.Angle = -1.0

    result = read_measure_angle(mock_measure)
    assert result["angle_deg"] is None
    assert any("not applicable" in e for e in result["errors"])


def test_read_measure_angle_30_degrees():
    """30-degree angle: pi/6 radians → 30.0 degrees."""
    mock_measure = MagicMock()
    mock_measure.Angle = math.pi / 6.0

    result = read_measure_angle(mock_measure)
    assert result["errors"] == []
    assert abs(result["angle_deg"] - 30.0) < 0.001


def test_read_measure_angle_60_degrees():
    """60-degree angle: pi/3 radians → 60.0 degrees."""
    mock_measure = MagicMock()
    mock_measure.Angle = math.pi / 3.0

    result = read_measure_angle(mock_measure)
    assert result["errors"] == []
    assert abs(result["angle_deg"] - 60.0) < 0.001


def test_read_measure_area_green():
    """Area of 0.001 m² → 1000.0 mm²."""
    mock_measure = MagicMock()
    mock_measure.Area = 0.001

    result = read_measure_area(mock_measure)
    assert result["errors"] == []
    assert result["area_mm2"] is not None
    assert abs(result["area_mm2"] - 1000.0) < 0.001


def test_read_measure_area_none():
    """Area returning None → error."""
    mock_measure = MagicMock()
    mock_measure.Area = None

    result = read_measure_area(mock_measure)
    assert result["area_mm2"] is None
    assert len(result["errors"]) > 0


def test_read_measure_area_not_applicable():
    """Area returning -1.0 → not applicable."""
    mock_measure = MagicMock()
    mock_measure.Area = -1.0

    result = read_measure_area(mock_measure)
    assert result["area_mm2"] is None
    assert any("not applicable" in e for e in result["errors"])


def test_read_measure_area_100mm2_face():
    """10mm × 10mm face → area 100 mm² = 1e-4 m²."""
    mock_measure = MagicMock()
    mock_measure.Area = 1e-4

    result = read_measure_area(mock_measure)
    assert result["errors"] == []
    assert abs(result["area_mm2"] - 100.0) < 0.01


def test_sw_get_measure_angle_no_selection():
    """No entities selected → error."""
    mock_doc = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=0)
    mock_doc.SelectionManager = sel_mgr

    result = sw_get_measure_angle_from_doc(mock_doc)
    assert result["ok"] is False
    assert "no entities selected" in str(result["error"])


def test_sw_get_measure_area_no_selection():
    """No entities selected → error."""
    mock_doc = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=0)
    mock_doc.SelectionManager = sel_mgr

    result = sw_get_measure_area_from_doc(mock_doc)
    assert result["ok"] is False
    assert "no entities selected" in str(result["error"])


def test_sw_get_measure_angle_green():
    """Pre-selected entities, Angle = pi/6 → 30 deg."""
    mock_doc = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=2)
    mock_doc.SelectionManager = sel_mgr

    ext = MagicMock()
    mock_measure = MagicMock()
    mock_measure.Angle = math.pi / 6.0
    mock_measure.Calculate = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=mock_measure)
    mock_doc.Extension = ext

    result = sw_get_measure_angle_from_doc(mock_doc)
    assert result["ok"] is True
    assert result["measure"]["angle_deg"] is not None
    assert abs(result["measure"]["angle_deg"] - 30.0) < 0.001


def test_sw_get_measure_area_green():
    """Pre-selected face, Area = 1e-4 m² → 100 mm²."""
    mock_doc = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=1)
    mock_doc.SelectionManager = sel_mgr

    ext = MagicMock()
    mock_measure = MagicMock()
    mock_measure.Area = 1e-4
    mock_measure.Calculate = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=mock_measure)
    mock_doc.Extension = ext

    result = sw_get_measure_area_from_doc(mock_doc)
    assert result["ok"] is True
    assert result["measure"]["area_mm2"] is not None
    assert abs(result["measure"]["area_mm2"] - 100.0) < 0.01


def test_sw_get_measure_angle_create_measure_none():
    """CreateMeasure returning None → error."""
    mock_doc = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=1)
    mock_doc.SelectionManager = sel_mgr

    ext = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=None)
    mock_doc.Extension = ext

    result = sw_get_measure_angle_from_doc(mock_doc)
    assert result["ok"] is False
    assert "CreateMeasure" in str(result["error"])


def test_sw_get_measure_area_result_shape():
    """Verify sw_get_measure_area return shape keys."""
    mock_doc = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=0)
    mock_doc.SelectionManager = sel_mgr

    result = sw_get_measure_area_from_doc(mock_doc)
    assert set(result.keys()) == SW_AREA_KEYS


def test_sw_get_measure_angle_result_shape():
    """Verify sw_get_measure_angle return shape keys."""
    mock_doc = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=0)
    mock_doc.SelectionManager = sel_mgr

    result = sw_get_measure_angle_from_doc(mock_doc)
    assert set(result.keys()) == SW_ANGLE_KEYS


def test_read_measure_durable_pair_shape_on_bad_ref():
    """Bad durable ref → errors populated, all measurements None."""
    mock_doc = MagicMock()

    with patch("ai_sw_bridge.observe_measure.typed_extension", side_effect=Exception("no extension")):
        result = read_measure_durable_pair(mock_doc, "ref_a", "ref_b")
    assert isinstance(result, dict)
    assert set(result.keys()) == MEASURE_PAIR_KEYS
    assert result["distance_mm"] is None
    assert len(result["errors"]) > 0


def test_sw_get_measure_durable_pair_shape():
    """Verify sw_get_measure_durable_pair return shape."""
    mock_doc = MagicMock()

    with patch("ai_sw_bridge.observe_measure.typed_extension") as mock_ext, \
         patch("ai_sw_bridge.observe_measure.typed") as mock_typed:
        mock_ext.side_effect = Exception("no extension")
        mock_typed.side_effect = Exception("no typed")

        result = sw_get_measure_durable_pair(mock_doc, "ref_a", "ref_b")
    assert set(result.keys()) == SW_DURABLE_PAIR_KEYS
    assert result["ok"] is False
    assert result["measure"] is not None


def test_sw_get_measure_durable_pair_green():
    """Resolve two durable refs → select both → measure 10mm."""
    import base64
    mock_doc = MagicMock()
    mock_entity_a = MagicMock()
    mock_entity_b = MagicMock()
    mock_ientity_a = MagicMock()
    mock_ientity_a.Select4 = MagicMock(return_value=True)
    mock_ientity_b = MagicMock()
    mock_ientity_b.Select4 = MagicMock(return_value=True)

    mock_ext = MagicMock()
    pid_a = base64.urlsafe_b64encode(b"\x01\x02\x03").decode().rstrip("=")
    pid_b = base64.urlsafe_b64encode(b"\x04\x05\x06").decode().rstrip("=")

    mock_ext.GetObjectByPersistReference3 = MagicMock(
        side_effect=[(mock_entity_a, 0), (mock_entity_b, 0)]
    )

    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    ext2 = MagicMock()
    mock_measure = MagicMock()
    mock_measure.Distance = 0.010
    mock_measure.DeltaX = 0.010
    mock_measure.DeltaY = 0.0
    mock_measure.DeltaZ = 0.0
    mock_measure.Calculate = MagicMock()
    ext2.CreateMeasure = MagicMock(return_value=mock_measure)
    mock_doc_typed.Extension = ext2

    with patch("ai_sw_bridge.observe_measure.typed_extension", return_value=mock_ext), \
         patch("ai_sw_bridge.observe_measure.typed") as mock_typed_fn:
        def typed_se(obj, iface, module=None):
            if iface == "IModelDoc2":
                return mock_doc_typed
            if iface == "IEntity":
                if obj is mock_entity_a:
                    return mock_ientity_a
                return mock_ientity_b
            return MagicMock()
        mock_typed_fn.side_effect = typed_se

        result = sw_get_measure_durable_pair(mock_doc, pid_a, pid_b)

    assert result["ok"] is True
    assert result["measure"]["distance_mm"] == 10.0


def test_measure_angle_subcommand_in_parser():
    """The 'measure_angle' subcommand is registered."""
    from ai_sw_bridge.cli.observe import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["measure_angle"])
    assert args.tool == "measure_angle"
    assert hasattr(args, "func")


def test_measure_area_subcommand_in_parser():
    """The 'measure_area' subcommand is registered."""
    from ai_sw_bridge.cli.observe import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["measure_area"])
    assert args.tool == "measure_area"
    assert hasattr(args, "func")


def test_measure_durable_pair_subcommand_in_parser():
    """The 'measure_durable_pair' subcommand is registered with required args."""
    from ai_sw_bridge.cli.observe import _build_parser
    import pytest

    parser = _build_parser()
    args = parser.parse_args(["measure_durable_pair", "--ref-a", "abc", "--ref-b", "def"])
    assert args.tool == "measure_durable_pair"
    assert args.ref_a == "abc"
    assert args.ref_b == "def"

    with pytest.raises(SystemExit):
        parser.parse_args(["measure_durable_pair", "--ref-a", "abc"])
