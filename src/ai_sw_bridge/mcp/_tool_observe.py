"""Observation MCP tools (W5.4, §6.1, W30, W37, W43).

Nineteen read-only tools that mirror the ``ai-sw-observe`` CLI
subcommands. Each tool is a thin wrapper around a
:class:`ai_sw_bridge.observe.SolidWorksObserver` method, decorated
with ``@com_tool`` so the body runs on the ComExecutor's STA
worker thread.

Registration is done via :func:`register`, called from
``server.create_server`` with the live FastMCP instance.

Design: ``docs/mcp_server_design.md`` §6.1.
"""

from __future__ import annotations

from typing import Any

from ..observe import SolidWorksObserver
from .tools import com_tool


def register(mcp: Any) -> None:
    """Register every §6.1 observation tool against *mcp*."""

    @mcp.tool()
    @com_tool
    def sw_active_doc() -> dict[str, Any]:
        """Return metadata about the currently active SOLIDWORKS document."""
        return SolidWorksObserver().active_doc()

    @mcp.tool()
    @com_tool
    def sw_feature_errors() -> dict[str, Any]:
        """Walk the active document's feature tree and report non-OK features."""
        return SolidWorksObserver().feature_errors()

    @mcp.tool()
    @com_tool
    def sw_equations() -> dict[str, Any]:
        """Dump every equation in the active document with values and status."""
        return SolidWorksObserver().equations()

    @mcp.tool()
    @com_tool
    def sw_bbox() -> dict[str, Any]:
        """Return the active part's axis-aligned bounding box."""
        return SolidWorksObserver().bbox()

    @mcp.tool()
    @com_tool
    def sw_volume() -> dict[str, Any]:
        """Return volume, surface area, mass, and center of mass of the active part."""
        return SolidWorksObserver().volume()

    @mcp.tool()
    @com_tool
    def sw_screenshot(
        width: int = 640,
        height: int = 360,
        fit_view: bool = False,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Capture the active SW viewport to a PNG file."""
        return SolidWorksObserver().screenshot(
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
        return SolidWorksObserver().measure(entity_a=entity_a, entity_b=entity_b)

    @mcp.tool()
    @com_tool
    def sw_mate_errors() -> dict[str, Any]:
        """Walk an assembly's mate set and report status per mate."""
        return SolidWorksObserver().mate_errors()

    @mcp.tool()
    @com_tool
    def sw_custom_props() -> dict[str, Any]:
        """Read every custom property from the active document."""
        return SolidWorksObserver().custom_props()

    @mcp.tool()
    @com_tool
    def sw_enabled_addins() -> dict[str, Any]:
        """Enumerate currently-loaded SOLIDWORKS add-ins."""
        return SolidWorksObserver().enabled_addins()

    @mcp.tool()
    @com_tool
    def sw_interference() -> dict[str, Any]:
        """Detect physical interferences in the active assembly (W27/E4).

        Uses IAssemblyDoc.InterferenceDetectionManager to detect component
        clashes. Returns interference_count and a list of interferences with
        component names and volumes (mm³). Assembly documents only.
        """
        return SolidWorksObserver().interference()

    @mcp.tool()
    @com_tool
    def sw_bounding_box() -> dict[str, Any]:
        """Return the active part's bounding box (W30 perception axis).

        Uses IPartDoc.GetPartBox(True) to get axis-aligned bounding box
        in the part's coordinate system. Returns mm values only:
        {x_min_mm, x_max_mm, y_min_mm, y_max_mm, z_min_mm, z_max_mm,
        dx_mm, dy_mm, dz_mm}. Parts only — assemblies/drawings error.
        """
        return SolidWorksObserver().bounding_box()

    @mcp.tool()
    @com_tool
    def sw_measure_selection() -> dict[str, Any]:
        """Measure currently selected entities (W30 perception axis).

        Uses IModelDocExtension.CreateMeasure → IMeasure.Calculate(None)
        to measure whatever is currently selected in SW. Returns
        {distance_mm, delta_x_mm, delta_y_mm, delta_z_mm}.
        Pre-select entities via select_entity or SW UI before calling.
        """
        return SolidWorksObserver().measure_selection()

    @mcp.tool()
    @com_tool
    def sw_inertia() -> dict[str, Any]:
        """Return inertia tensor of the active part (W5 E1).

        Uses IMassProperty2.GetMomentOfInertia(0) to read the full
        3x3 inertia tensor about the center of mass. Returns
        center_of_mass_mm, inertia_tensor_kg_m2, principal_moments_kg_m2,
        principal_axes. Parts only — assemblies/drawings error.
        """
        return SolidWorksObserver().inertia()

    @mcp.tool()
    @com_tool
    def sw_clearance(comp_a: str, comp_b: str) -> dict[str, Any]:
        """Measure minimum distance between two assembly components (W35).

        Uses IModelDocExtension.CreateMeasure → IMeasure.Distance after
        selecting both components via IComponent2.Select2. Returns
        {min_distance_mm, components: [a, b], touching: bool}.
        comp_a and comp_b are IComponent2.Name2 values
        (e.g. 'block_20mm-1', 'block_20mm-2'). Assembly docs only.
        """
        return SolidWorksObserver().clearance(comp_a=comp_a, comp_b=comp_b)

    @mcp.tool()
    @com_tool
    def sw_draft_analysis(
        pull_direction: str,
        min_angle_deg: float = 1.0,
    ) -> dict[str, Any]:
        """DFM draft analysis of the active part (W37).

        Classifies every face as positive/negative/vertical draft relative
        to pull_direction. Uses first-principles face-normal sweep
        (GetBodies2 → GetFaces → IFace2.Normal vs pull vector). Returns
        {pull_direction, faces_total, faces_positive, faces_negative,
        faces_vertical, min_draft_deg, faces_below_threshold}.
        pull_direction: front, back, top, bottom, right, left, or
        +x, -x, +y, -y, +z, -z. Part docs only.
        """
        return SolidWorksObserver().draft_analysis(
            pull_direction=pull_direction,
            min_angle_deg=min_angle_deg,
        )

    @mcp.tool()
    @com_tool
    def sw_undercut_faces(
        pull_x: float = 0.0,
        pull_y: float = 1.0,
        pull_z: float = 0.0,
    ) -> dict[str, Any]:
        """Report part faces that block mold/tool withdrawal along a pull direction (DFM)."""
        return SolidWorksObserver().undercut_faces(
            pull_x=pull_x, pull_y=pull_y, pull_z=pull_z
        )

    @mcp.tool()
    @com_tool
    def sw_current_selection() -> dict[str, Any]:
        """Read the active document's current selection (W43).

        Reports whatever entities are currently selected in SW via
        SelectionManager. Returns {count, selections: [{index, type,
        type_name, durable_ref, entity_info}]}. Works on any document
        type. Empty selection is valid (count=0). durable_ref is a
        base64url-encoded persist token from GetPersistReference3 when
        obtainable, null otherwise.
        """
        return SolidWorksObserver().selection()

    @mcp.tool()
    @com_tool
    def sw_min_wall_thickness(samples_per_face: int = 4) -> dict[str, Any]:
        """Report the minimum wall thickness of the active solid part (DFM)."""
        return SolidWorksObserver().min_wall_thickness(
            samples_per_face=samples_per_face
        )
