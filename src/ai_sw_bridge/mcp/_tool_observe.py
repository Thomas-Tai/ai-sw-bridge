"""Observation MCP tools (W5.4, §6.1).

Ten read-only tools that mirror the ``ai-sw-observe`` CLI
subcommands. Each tool is a thin wrapper around the matching
``ai_sw_bridge.observe.sw_*`` function, decorated with ``@com_tool``
so the body runs on the ComExecutor's STA worker thread.

Registration is done via :func:`register`, called from
``server.create_server`` with the live FastMCP instance.

Design: ``docs/mcp_server_design.md`` §6.1.
"""

from __future__ import annotations

from typing import Any

from .. import observe
from .tools import com_tool


def register(mcp: Any) -> None:
    """Register every §6.1 observation tool against *mcp*."""

    @mcp.tool()
    @com_tool
    def sw_active_doc() -> dict[str, Any]:
        """Return metadata about the currently active SOLIDWORKS document."""
        return observe.sw_get_active_doc()

    @mcp.tool()
    @com_tool
    def sw_feature_errors() -> dict[str, Any]:
        """Walk the active document's feature tree and report non-OK features."""
        return observe.sw_get_feature_errors()

    @mcp.tool()
    @com_tool
    def sw_equations() -> dict[str, Any]:
        """Dump every equation in the active document with values and status."""
        return observe.sw_get_equations()

    @mcp.tool()
    @com_tool
    def sw_bbox() -> dict[str, Any]:
        """Return the active part's axis-aligned bounding box."""
        return observe.sw_get_bbox()

    @mcp.tool()
    @com_tool
    def sw_volume() -> dict[str, Any]:
        """Return volume, surface area, mass, and center of mass of the active part."""
        return observe.sw_get_volume()

    @mcp.tool()
    @com_tool
    def sw_screenshot(
        width: int = 640,
        height: int = 360,
        fit_view: bool = False,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Capture the active SW viewport to a PNG file."""
        return observe.sw_screenshot(
            width=width,
            height=height,
            fit_view=fit_view,
            filename=filename,
        )

    @mcp.tool()
    @com_tool
    def sw_measure(
        entity_a: str | None = None,
        entity_b: str | None = None,
    ) -> dict[str, Any]:
        """Measure entities in the active document."""
        return observe.sw_measure(entity_a=entity_a, entity_b=entity_b)

    @mcp.tool()
    @com_tool
    def sw_mate_errors() -> dict[str, Any]:
        """Walk an assembly's mate set and report status per mate."""
        return observe.sw_get_mate_errors()

    @mcp.tool()
    @com_tool
    def sw_custom_props() -> dict[str, Any]:
        """Read every custom property from the active document."""
        return observe.sw_get_custom_props()

    @mcp.tool()
    @com_tool
    def sw_enabled_addins() -> dict[str, Any]:
        """Enumerate currently-loaded SOLIDWORKS add-ins."""
        return observe.sw_get_enabled_addins()
