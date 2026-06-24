"""Offline tests for observe_clearance face-pair extension (W52).

Tests face-pair clearance WITHOUT a running SOLIDWORKS session.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_sw_bridge.observe_clearance import (
    read_face_pair_clearance,
    _sw_get_face_clearance_impl,
)


FACE_CLEARANCE_KEYS = frozenset({"min_distance_mm", "faces", "touching", "errors"})

SW_FACE_CLEARANCE_KEYS = frozenset({"ok", "error", "clearance"})


def test_read_face_clearance_shape_when_same_face():
    """Same name for both faces → error."""
    mock_doc = MagicMock()
    result = read_face_pair_clearance(mock_doc, "Face<1>", "Face<1>")
    assert isinstance(result, dict)
    assert set(result.keys()) == FACE_CLEARANCE_KEYS
    assert result["min_distance_mm"] is None
    assert any("same face" in e for e in result["errors"])


def test_sw_get_face_clearance_shape():
    """Verify return shape keys."""
    mock_doc = MagicMock()
    result = _sw_get_face_clearance_impl(mock_doc, "Face<1>", "Face<1>")
    assert set(result.keys()) == SW_FACE_CLEARANCE_KEYS
    assert result["ok"] is False


def test_read_face_clearance_green_10mm():
    """Two faces 10mm apart → min_distance_mm = 10.0."""
    mock_doc = MagicMock()
    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    mock_doc_typed.SelectByID2 = MagicMock(return_value=True)

    ext = MagicMock()
    mock_measure = MagicMock()
    mock_measure.Distance = 0.010
    mock_measure.Calculate = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=mock_measure)
    mock_doc_typed.Extension = ext

    with patch("ai_sw_bridge.observe_clearance.typed", return_value=mock_doc_typed):
        result = read_face_pair_clearance(mock_doc, "Face<1>", "Face<2>")

    assert result["errors"] == []
    assert result["min_distance_mm"] == 10.0
    assert result["touching"] is False
    assert result["faces"] == ["Face<1>", "Face<2>"]


def test_read_face_clearance_touching():
    """Distance == -1.0 → touching=True."""
    mock_doc = MagicMock()
    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    mock_doc_typed.SelectByID2 = MagicMock(return_value=True)

    ext = MagicMock()
    mock_measure = MagicMock()
    mock_measure.Distance = -1.0
    mock_measure.Calculate = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=mock_measure)
    mock_doc_typed.Extension = ext

    with patch("ai_sw_bridge.observe_clearance.typed", return_value=mock_doc_typed):
        result = read_face_pair_clearance(mock_doc, "Face<1>", "Face<2>")

    assert result["errors"] == []
    assert result["min_distance_mm"] is None
    assert result["touching"] is True


def test_read_face_clearance_select_fail():
    """SelectByID2 returning False → error."""
    mock_doc = MagicMock()
    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    mock_doc_typed.SelectByID2 = MagicMock(return_value=False)

    with patch("ai_sw_bridge.observe_clearance.typed", return_value=mock_doc_typed):
        result = read_face_pair_clearance(mock_doc, "Face<1>", "Face<2>")

    assert result["min_distance_mm"] is None
    assert any("SelectByID2" in e for e in result["errors"])


def test_read_face_clearance_create_measure_none():
    """CreateMeasure returning None → error."""
    mock_doc = MagicMock()
    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    mock_doc_typed.SelectByID2 = MagicMock(return_value=True)

    ext = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=None)
    mock_doc_typed.Extension = ext

    with patch("ai_sw_bridge.observe_clearance.typed", return_value=mock_doc_typed):
        result = read_face_pair_clearance(mock_doc, "Face<1>", "Face<2>")

    assert result["min_distance_mm"] is None
    assert any("CreateMeasure" in e for e in result["errors"])


def test_sw_get_face_clearance_green():
    """Full pipeline → ok=True, correct scalar."""
    mock_doc = MagicMock()
    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    mock_doc_typed.SelectByID2 = MagicMock(return_value=True)

    ext = MagicMock()
    mock_measure = MagicMock()
    mock_measure.Distance = 0.025
    mock_measure.Calculate = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=mock_measure)
    mock_doc_typed.Extension = ext

    with patch("ai_sw_bridge.observe_clearance.typed", return_value=mock_doc_typed):
        result = _sw_get_face_clearance_impl(mock_doc, "Face<1>", "Face<2>")

    assert result["ok"] is True
    assert result["clearance"]["min_distance_mm"] == 25.0
    assert result["clearance"]["faces"] == ["Face<1>", "Face<2>"]


def test_face_clearance_subcommand_in_parser():
    """The 'face_clearance' subcommand is registered with required args."""
    from ai_sw_bridge.cli.observe import _build_parser
    import pytest

    parser = _build_parser()
    args = parser.parse_args(
        ["face_clearance", "--face-a", "Face<1>", "--face-b", "Face<2>"]
    )
    assert args.tool == "face_clearance"
    assert args.face_a == "Face<1>"
    assert args.face_b == "Face<2>"

    with pytest.raises(SystemExit):
        parser.parse_args(["face_clearance", "--face-a", "Face<1>"])
