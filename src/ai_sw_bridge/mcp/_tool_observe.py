"""Observation MCP tools (W5.4, §6.1, W30, W37, W43).

Twenty read-only tools that mirror the ``ai-sw-observe`` CLI
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

from ..client import SolidWorksClient
from ..observe import SolidWorksObserver
from .tools import com_tool


def register(mcp: Any) -> None:
    """Register every §6.1 observation tool against *mcp*."""

    @mcp.tool()
    @com_tool
    def sw_active_doc() -> dict[str, Any]:
        """Return metadata about the currently active SOLIDWORKS document."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.active_doc()

    @mcp.tool()
    @com_tool
    def sw_feature_errors() -> dict[str, Any]:
        """Walk the active document's feature tree and report non-OK features."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.feature_errors()

    @mcp.tool()
    @com_tool
    def sw_equations() -> dict[str, Any]:
        """Dump every equation in the active document with values and status."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.equations()

    @mcp.tool()
    @com_tool
    def sw_bbox() -> dict[str, Any]:
        """Return the active part's axis-aligned bounding box."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.bbox()

    @mcp.tool()
    @com_tool
    def sw_volume() -> dict[str, Any]:
        """Return volume, surface area, mass, and center of mass of the active part."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.volume()

    @mcp.tool()
    @com_tool
    def sw_feature_statistics() -> dict[str, Any]:
        """Return the active model's build-tree statistics (W71).

        Reads IFeatureManager.FeatureStatistics (Refresh()ed first):
        feature_count, solid_bodies_count, surface_bodies_count,
        total_rebuild_time, and per-feature name/type/update-time arrays.
        Lets the system introspect its own generated build tree. Part/assembly.
        """
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.feature_statistics()

    @mcp.tool()
    @com_tool
    def sw_screenshot(
        width: int = 640,
        height: int = 360,
        fit_view: bool = False,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Capture the active SW viewport to a PNG file."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.screenshot(
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
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.measure(entity_a=entity_a, entity_b=entity_b)

    @mcp.tool()
    @com_tool
    def sw_mate_errors() -> dict[str, Any]:
        """Walk an assembly's mate set and report status per mate."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.mate_errors()

    @mcp.tool()
    @com_tool
    def sw_custom_props() -> dict[str, Any]:
        """Read every custom property from the active document."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.custom_props()

    @mcp.tool()
    @com_tool
    def sw_enabled_addins() -> dict[str, Any]:
        """Enumerate currently-loaded SOLIDWORKS add-ins."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.enabled_addins()

    @mcp.tool()
    @com_tool
    def sw_interference() -> dict[str, Any]:
        """Detect physical interferences in the active assembly (W27/E4).

        Uses IAssemblyDoc.InterferenceDetectionManager to detect component
        clashes. Returns interference_count and a list of interferences with
        component names and volumes (mm³). Assembly documents only.
        """
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.interference()

    @mcp.tool()
    @com_tool
    def sw_bounding_box() -> dict[str, Any]:
        """Return the active part's bounding box (W30 perception axis).

        Uses IPartDoc.GetPartBox(True) to get axis-aligned bounding box
        in the part's coordinate system. Returns mm values only:
        {x_min_mm, x_max_mm, y_min_mm, y_max_mm, z_min_mm, z_max_mm,
        dx_mm, dy_mm, dz_mm}. Parts only — assemblies/drawings error.
        """
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.bbox_from_doc()

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
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.get_inertia()

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
    def sw_analyze_stackup(
        components: list[str],
        check_endpoints: bool = True,
    ) -> dict[str, Any]:
        """Accumulate inter-component gaps along an ordered stack chain (W77).

        Read-only orchestration verb: composes IMeasure-based component
        clearance over CONSECUTIVE pairs of an ordered chain
        (components[0]↔[1], [1]↔[2], …) and sums the gaps. Lets the model
        audit a tolerance stack-up (e.g. mount → spacer → sensor) and verify
        the accumulated dimension. With check_endpoints (chains of ≥3) it also
        measures the first↔last span — for a collinear stack that span is ≥ the
        gap sum (it includes the intervening bodies); linear_consistent=False
        flags a non-collinear/misaligned chain.

        components: ordered IComponent2.Name2 values, e.g.
        ['base-1', 'spacer-1', 'top-1']. At least two required.
        Returns {ok, pairs, accumulated_gap_mm, endpoint_span_mm,
        intervening_span_mm, linear_consistent, warnings}. Assembly docs only.
        """
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.analyze_stackup(
            components, check_endpoints=check_endpoints
        )

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
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.draft_analysis(
            pull_direction, min_angle_deg
        )

    @mcp.tool()
    @com_tool
    def sw_undercut_faces(
        pull_x: float = 0.0,
        pull_y: float = 1.0,
        pull_z: float = 0.0,
    ) -> dict[str, Any]:
        """Report part faces that block mold/tool withdrawal along a pull direction (DFM)."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.undercut_faces(
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
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.selection()

    @mcp.tool()
    @com_tool
    def sw_min_wall_thickness(samples_per_face: int = 4) -> dict[str, Any]:
        """Report the minimum wall thickness of the active solid part (DFM)."""
        # v0.18 slice: route through the class-based SolidWorksClient.
        return SolidWorksClient().observe.min_wall_thickness(
            samples_per_face=samples_per_face
        )
