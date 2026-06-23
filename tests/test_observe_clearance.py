"""Offline tests for observe_clearance (W35).

Tests schema/arg validation, fail-closed paths, and unit conversion
WITHOUT a running SOLIDWORKS session. Uses mocks for COM objects.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_sw_bridge.observe_clearance import read_clearance, _sw_get_clearance_impl


# ── Schema / shape tests ──────────────────────────────────────────────────

CLEARANCE_RESULT_KEYS = frozenset(
    {
        "min_distance_mm",
        "components",
        "touching",
        "errors",
    }
)


SW_CLEARANCE_KEYS = frozenset(
    {
        "ok",
        "error",
        "clearance",
    }
)


def test_read_clearance_shape_when_component_not_found():
    """Component not found → errors list populated, min_distance_mm is None."""
    mock_asm = MagicMock()
    mock_asm.GetComponents = MagicMock(return_value=None)

    result = read_clearance(mock_asm, "comp_a", "comp_b")
    assert isinstance(result, dict)
    assert set(result.keys()) == CLEARANCE_RESULT_KEYS
    assert result["min_distance_mm"] is None
    assert result["components"] == ["comp_a", "comp_b"]
    assert len(result["errors"]) > 0


def test_sw_get_clearance_shape_when_not_assembly():
    """Non-assembly doc → ok=False with typed error."""
    mock_doc = MagicMock()
    # doc.GetType returns 1 = SW_DOC_PART
    mock_doc.GetType = 1

    result = _sw_get_clearance_impl(mock_doc, "comp_a", "comp_b")
    assert isinstance(result, dict)
    assert set(result.keys()) == SW_CLEARANCE_KEYS
    assert result["ok"] is False
    assert "assembly document" in str(result["error"])


def test_sw_get_clearance_same_component_names():
    """Same name for comp_a and comp_b → error (no self-distance)."""
    mock_doc = MagicMock()
    mock_doc.GetType = 2  # SW_DOC_ASSEMBLY

    result = _sw_get_clearance_impl(mock_doc, "same_name", "same_name")
    assert result["ok"] is False
    assert result["error"] is not None


def test_read_clearance_same_component_names():
    """read_clearance rejects same name for both components."""
    mock_asm = MagicMock()
    mock_asm.GetComponents = MagicMock(return_value=None)

    result = read_clearance(mock_asm, "comp_a", "comp_a")
    assert result["min_distance_mm"] is None
    assert any("same component" in e for e in result["errors"])


# ── Unit conversion tests ─────────────────────────────────────────────────

def test_read_clearance_m_to_mm_conversion():
    """Distance returned by IMeasure is in metres; verify conversion to mm."""
    # Build mock component objects
    mock_comp_a = MagicMock()
    mock_comp_a.Name2 = "block_20mm-1"
    mock_comp_a.Select2 = MagicMock(return_value=True)

    mock_comp_b = MagicMock()
    mock_comp_b.Name2 = "block_20mm-2"
    mock_comp_b.Select2 = MagicMock(return_value=True)

    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=(mock_comp_a, mock_comp_b))

    # Build mock doc
    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=2)
    mock_doc_typed.SelectionManager = sel_mgr

    ext = MagicMock()
    mock_measure = MagicMock()
    # Distance = 0.010 m → should return 10.0 mm
    mock_measure.Distance = 0.010
    mock_measure.Calculate = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=mock_measure)
    mock_doc_typed.Extension = ext

    # Patch typed() to return our mock
    with patch("ai_sw_bridge.observe_clearance.typed") as mock_typed:
        def typed_side_effect(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                return mock_asm_typed
            elif iface == "IModelDoc2":
                return mock_doc_typed
            return MagicMock()

        mock_typed.side_effect = typed_side_effect

        result = read_clearance(mock_asm_typed, "block_20mm-1", "block_20mm-2")

    assert result["errors"] == []
    assert result["min_distance_mm"] == 10.0
    assert result["touching"] is False


def test_read_clearance_touching_returns_true():
    """Distance == -1.0 → touching=True, min_distance_mm=None."""
    mock_comp_a = MagicMock()
    mock_comp_a.Name2 = "block_20mm-1"
    mock_comp_a.Select2 = MagicMock(return_value=True)

    mock_comp_b = MagicMock()
    mock_comp_b.Name2 = "block_20mm-2"
    mock_comp_b.Select2 = MagicMock(return_value=True)

    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=(mock_comp_a, mock_comp_b))

    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=2)
    mock_doc_typed.SelectionManager = sel_mgr

    ext = MagicMock()
    mock_measure = MagicMock()
    # Distance = -1.0 → touching
    mock_measure.Distance = -1.0
    mock_measure.Calculate = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=mock_measure)
    mock_doc_typed.Extension = ext

    with patch("ai_sw_bridge.observe_clearance.typed") as mock_typed:
        def typed_side_effect(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                return mock_asm_typed
            elif iface == "IModelDoc2":
                return mock_doc_typed
            return MagicMock()

        mock_typed.side_effect = typed_side_effect

        result = read_clearance(mock_asm_typed, "block_20mm-1", "block_20mm-2")

    assert result["errors"] == []
    assert result["min_distance_mm"] is None
    assert result["touching"] is True


def test_read_clearance_select2_failure_returns_error():
    """Select2 returning False → error propagated."""
    mock_comp_a = MagicMock()
    mock_comp_a.Name2 = "block_20mm-1"
    mock_comp_a.Select2 = MagicMock(return_value=False)  # Selection fails

    mock_comp_b = MagicMock()
    mock_comp_b.Name2 = "block_20mm-2"
    mock_comp_b.Select2 = MagicMock(return_value=True)

    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=(mock_comp_a, mock_comp_b))

    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()

    with patch("ai_sw_bridge.observe_clearance.typed") as mock_typed:
        def typed_side_effect(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                return mock_asm_typed
            elif iface == "IModelDoc2":
                return mock_doc_typed
            return MagicMock()

        mock_typed.side_effect = typed_side_effect

        result = read_clearance(mock_asm_typed, "block_20mm-1", "block_20mm-2")

    assert result["min_distance_mm"] is None
    assert any("Select2" in e for e in result["errors"])


def test_read_clearance_create_measure_none_returns_error():
    """CreateMeasure returning None → error."""
    mock_comp_a = MagicMock()
    mock_comp_a.Name2 = "block_20mm-1"
    mock_comp_a.Select2 = MagicMock(return_value=True)

    mock_comp_b = MagicMock()
    mock_comp_b.Name2 = "block_20mm-2"
    mock_comp_b.Select2 = MagicMock(return_value=True)

    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=(mock_comp_a, mock_comp_b))

    mock_doc_typed = MagicMock()
    mock_doc_typed.ClearSelection2 = MagicMock()
    sel_mgr = MagicMock()
    sel_mgr.GetSelectedObjectCount2 = MagicMock(return_value=2)
    mock_doc_typed.SelectionManager = sel_mgr

    ext = MagicMock()
    ext.CreateMeasure = MagicMock(return_value=None)  # CreateMeasure fails
    mock_doc_typed.Extension = ext

    with patch("ai_sw_bridge.observe_clearance.typed") as mock_typed:
        def typed_side_effect(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                return mock_asm_typed
            elif iface == "IModelDoc2":
                return mock_doc_typed
            return MagicMock()

        mock_typed.side_effect = typed_side_effect

        result = read_clearance(mock_asm_typed, "block_20mm-1", "block_20mm-2")

    assert result["min_distance_mm"] is None
    assert any("CreateMeasure" in e for e in result["errors"])


# ── CLI subcommand parser tests ──────────────────────────────────────────

def test_clearance_subcommand_in_parser():
    """The 'clearance' subcommand is registered in the CLI parser."""
    from ai_sw_bridge.cli.observe import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["clearance", "--comp-a", "block-1", "--comp-b", "block-2"])
    assert args.tool == "clearance"
    assert args.comp_a == "block-1"
    assert args.comp_b == "block-2"
    assert hasattr(args, "func")


def test_clearance_subcommand_requires_both_args():
    """Both --comp-a and --comp-b are required."""
    from ai_sw_bridge.cli.observe import _build_parser
    import pytest

    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["clearance", "--comp-a", "block-1"])
    with pytest.raises(SystemExit):
        parser.parse_args(["clearance", "--comp-b", "block-2"])
