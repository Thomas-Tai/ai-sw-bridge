"""Tests for ai-sw-observe custom_props subcommand (W2.1).

Runs WITHOUT a running SOLIDWORKS session: get_sw_app() will raise
com_error, the function catches it, and returns its typed error dict.
What we verify here is the SHAPE of that dict -- every key the wire
contract promises is present, error is populated, ok is False.

Also verifies the CLI parser wires the custom_props subcommand correctly
and the experimental tier is registered.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from ai_sw_bridge.cli.observe import _build_parser
from ai_sw_bridge.observe import sw_get_custom_props

CUSTOM_PROPS_KEYS = frozenset(
    {
        "ok",
        "properties",
        "active_configuration",
        "count",
        "error",
    }
)


def test_sw_get_custom_props_shape_when_sw_unavailable():
    result = sw_get_custom_props()
    assert isinstance(result, dict)
    assert set(result.keys()) == CUSTOM_PROPS_KEYS
    if not result["ok"]:
        assert result["error"] is not None


def test_sw_get_custom_props_with_mock_doc():
    mock_doc = MagicMock()
    mock_doc.GetCustomInfoNames3 = ("Description", "PartNo", "Revision")
    mock_doc.GetCustomInfoValue2 = MagicMock(
        side_effect=lambda cfg, name: {
            "Description": "Test Part",
            "PartNo": "P-001",
            "Revision": "A",
        }[name]
    )
    cfg_mock = MagicMock()
    cfg_mock.Name = "Default"
    mock_doc.IGetActiveConfiguration = cfg_mock

    mock_sw = MagicMock()
    with (
        patch("ai_sw_bridge.observe.get_sw_app", return_value=mock_sw),
        patch("ai_sw_bridge.observe.get_active_doc", return_value=mock_doc),
    ):
        result = sw_get_custom_props()

    assert result["ok"] is True
    assert result["count"] == 3
    assert result["properties"]["Description"] == "Test Part"
    assert result["properties"]["PartNo"] == "P-001"
    assert result["properties"]["Revision"] == "A"
    assert result["active_configuration"] == "Default"
    assert result["error"] is None


def test_sw_get_custom_props_empty_doc():
    mock_doc = MagicMock()
    mock_doc.GetCustomInfoNames3 = None
    mock_doc.IGetActiveConfiguration = None

    mock_sw = MagicMock()
    with (
        patch("ai_sw_bridge.observe.get_sw_app", return_value=mock_sw),
        patch("ai_sw_bridge.observe.get_active_doc", return_value=mock_doc),
    ):
        result = sw_get_custom_props()

    assert result["ok"] is True
    assert result["properties"] == {}
    assert result["count"] == 0


def test_sw_get_custom_props_no_active_doc():
    mock_sw = MagicMock()
    with (
        patch("ai_sw_bridge.observe.get_sw_app", return_value=mock_sw),
        patch("ai_sw_bridge.observe.get_active_doc", return_value=None),
    ):
        result = sw_get_custom_props()

    assert result["ok"] is False
    assert result["error"] == "no_active_doc"
    assert result["properties"] == {}


def test_custom_props_subcommand_in_parser():
    parser = _build_parser()
    args = parser.parse_args(["custom_props"])
    assert args.tool == "custom_props"
    assert hasattr(args, "func")


def test_custom_props_subcommand_help_shows_experimental():
    parser = _build_parser()
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            parser.parse_args(["custom_props", "--help"])
        except SystemExit:
            pass
    help_text = buf.getvalue()
    assert "experimental" in help_text.lower()
