"""Offline tests for observe_bbox assembly extensions (W52).

Tests assembly bounding-box extraction WITHOUT a running SOLIDWORKS session.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_sw_bridge.observe_bbox import (
    read_assembly_bbox,
    sw_get_assembly_bbox_from_doc,
    _transform_point,
)


ASM_BBOX_KEYS = frozenset({
    "x_min_mm", "x_max_mm", "y_min_mm", "y_max_mm",
    "z_min_mm", "z_max_mm", "dx_mm", "dy_mm", "dz_mm",
    "component_count", "errors",
})

SW_ASM_BBOX_KEYS = frozenset({"ok", "error", "bounding_box"})


def test_transform_point_identity():
    """Identity transform → point unchanged."""
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    tx, ty, tz = _transform_point(identity, 1.0, 2.0, 3.0)
    assert abs(tx - 1.0) < 1e-9
    assert abs(ty - 2.0) < 1e-9
    assert abs(tz - 3.0) < 1e-9


def test_transform_point_translation():
    """Pure translation by (10, 20, 30)."""
    m = [1, 0, 0, 0.010, 0, 1, 0, 0.020, 0, 0, 1, 0.030, 0, 0, 0, 1]
    tx, ty, tz = _transform_point(m, 0.0, 0.0, 0.0)
    assert abs(tx - 0.010) < 1e-9
    assert abs(ty - 0.020) < 1e-9
    assert abs(tz - 0.030) < 1e-9


def test_sw_get_assembly_bbox_rejects_part_doc():
    """Part doc type → ok=False with typed error."""
    mock_doc = MagicMock()
    mock_doc.GetType = 1  # SW_DOC_PART

    result = sw_get_assembly_bbox_from_doc(mock_doc)
    assert result["ok"] is False
    assert "assembly document" in str(result["error"])


def test_sw_get_assembly_bbox_rejects_drawing_doc():
    """Drawing doc type → ok=False with typed error."""
    mock_doc = MagicMock()
    mock_doc.GetType = 3  # SW_DOC_DRAWING

    result = sw_get_assembly_bbox_from_doc(mock_doc)
    assert result["ok"] is False
    assert "assembly document" in str(result["error"])


def test_read_assembly_bbox_no_components():
    """Empty assembly → error."""
    mock_asm = MagicMock()
    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=None)

    with patch("ai_sw_bridge.observe_bbox.typed", return_value=mock_asm_typed):
        result = read_assembly_bbox(mock_asm)

    assert result["errors"]
    assert any("no components" in e for e in result["errors"])


def test_read_assembly_bbox_single_component():
    """Single 20×30×40mm box at origin → exact bbox in mm."""
    mock_comp = MagicMock()
    mock_comp.Transform2 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    mock_part_doc = MagicMock()
    mock_part_typed = MagicMock()
    # 20×30×40mm box: (0,0,0) to (0.020, 0.030, 0.040) m
    mock_part_typed.GetPartBox = MagicMock(return_value=(0, 0, 0, 0.020, 0.030, 0.040))
    mock_comp.GetModelDoc2 = MagicMock(return_value=mock_part_doc)

    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=(mock_comp,))

    with patch("ai_sw_bridge.observe_bbox.typed") as mock_typed_fn:
        def typed_se(obj, iface, module=None):
            if iface == "IAssemblyDoc":
                return mock_asm_typed
            if iface == "IPartDoc":
                return mock_part_typed
            return MagicMock()
        mock_typed_fn.side_effect = typed_se

        result = read_assembly_bbox(mock_asm_typed)

    assert result["errors"] == []
    assert abs(result["x_min_mm"] - 0.0) < 0.01
    assert abs(result["x_max_mm"] - 20.0) < 0.01
    assert abs(result["y_min_mm"] - 0.0) < 0.01
    assert abs(result["y_max_mm"] - 30.0) < 0.01
    assert abs(result["z_min_mm"] - 0.0) < 0.01
    assert abs(result["z_max_mm"] - 40.0) < 0.01
    assert abs(result["dx_mm"] - 20.0) < 0.01
    assert abs(result["dy_mm"] - 30.0) < 0.01
    assert abs(result["dz_mm"] - 40.0) < 0.01
    assert result["component_count"] == 1


def test_read_assembly_bbox_two_components_offset():
    """Two boxes: one at origin (10mm cube), one offset 50mm in X.

    Combined bbox should span x: 0..60mm, y: 0..10mm, z: 0..10mm.
    """
    comp_a = MagicMock()
    comp_a.Transform2 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    part_a = MagicMock()
    part_a_typed = MagicMock()
    part_a_typed.GetPartBox = MagicMock(return_value=(0, 0, 0, 0.010, 0.010, 0.010))
    comp_a.GetModelDoc2 = MagicMock(return_value=part_a)

    comp_b = MagicMock()
    comp_b.Transform2 = [1, 0, 0, 0.050, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    part_b = MagicMock()
    part_b_typed = MagicMock()
    part_b_typed.GetPartBox = MagicMock(return_value=(0, 0, 0, 0.010, 0.010, 0.010))
    comp_b.GetModelDoc2 = MagicMock(return_value=part_b)

    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=(comp_a, comp_b))

    def typed_se(obj, iface, module=None):
        if iface == "IAssemblyDoc":
            return mock_asm_typed
        if iface == "IPartDoc":
            if obj is part_a:
                return part_a_typed
            return part_b_typed
        return MagicMock()

    with patch("ai_sw_bridge.observe_bbox.typed", side_effect=typed_se):
        result = read_assembly_bbox(mock_asm_typed)

    assert result["errors"] == []
    assert abs(result["x_min_mm"] - 0.0) < 0.01
    assert abs(result["x_max_mm"] - 60.0) < 0.01
    assert abs(result["dx_mm"] - 60.0) < 0.01
    assert abs(result["dy_mm"] - 10.0) < 0.01
    assert result["component_count"] == 2


def test_read_assembly_bbox_component_no_model_doc():
    """Component with no model doc is skipped."""
    comp = MagicMock()
    comp.Transform2 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    comp.GetModelDoc2 = MagicMock(return_value=None)

    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=(comp,))

    with patch("ai_sw_bridge.observe_bbox.typed", return_value=mock_asm_typed):
        result = read_assembly_bbox(mock_asm_typed)

    assert any("no component bounding boxes readable" in e for e in result["errors"])


def test_sw_get_assembly_bbox_green_shape():
    """Full pipeline with mocked assembly → ok=True, bbox shape correct."""
    mock_doc = MagicMock()
    mock_doc.GetType = 2  # SW_DOC_ASSEMBLY

    mock_comp = MagicMock()
    mock_comp.Transform2 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    mock_part = MagicMock()
    mock_part_typed = MagicMock()
    mock_part_typed.GetPartBox = MagicMock(return_value=(0, 0, 0, 0.010, 0.010, 0.010))
    mock_comp.GetModelDoc2 = MagicMock(return_value=mock_part)

    mock_asm_typed = MagicMock()
    mock_asm_typed.GetComponents = MagicMock(return_value=(mock_comp,))

    def typed_se(obj, iface, module=None):
        if iface == "IAssemblyDoc":
            return mock_asm_typed
        if iface == "IPartDoc":
            return mock_part_typed
        return MagicMock()

    with patch("ai_sw_bridge.observe_bbox.typed", side_effect=typed_se):
        result = sw_get_assembly_bbox_from_doc(mock_doc)

    assert result["ok"] is True
    assert set(result.keys()) == SW_ASM_BBOX_KEYS
    assert result["bounding_box"]["dx_mm"] is not None


def test_assembly_bbox_subcommand_in_parser():
    """The 'assembly_bbox' subcommand is registered."""
    from ai_sw_bridge.cli.observe import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["assembly_bbox"])
    assert args.tool == "assembly_bbox"
    assert hasattr(args, "func")
