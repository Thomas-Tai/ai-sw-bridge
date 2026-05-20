"""Rectangle sketched on a named reference plane (Front/Top/Right)."""

from __future__ import annotations

from typing import Any

import pythoncom
import win32com.client

from .._build_context import BuildContext, BuiltFeature, DeferredDim
from .._face_geometry import PLANE_FULL_NAME
from .._sketch_primitives import (
    PLACEHOLDER_MM,
    _dismiss_dim_pane,
    _draw_centerline_if_present,
    _identify_rect_edge,
    _literal_or_default,
    _strip_centerrectangle_midpoint_relation,
)
from .base import SketchFrame, SketchHandler


class RectangleOnPlaneHandler(SketchHandler):
    """Rectangle sketched on a reference plane via ``CreateCenterRectangle``.

    The Spike ZF Type-14 Midpoint relation is stripped before adding
    dimensions so D1 and D2 land as independent driving dims. Inline mode
    selects edges via captured ``ISketchSegment`` pointers (``Select4``)
    rather than coordinate-based ``SelectByID`` to dodge the
    post-Midpoint-delete vertex-selection issue.
    """

    def _enter_sketch(self, ctx: BuildContext, feat: dict[str, Any]) -> SketchFrame:
        plane = feat["plane"]
        full = PLANE_FULL_NAME[plane]
        ok = ctx.doc.SelectByID(full, "PLANE", 0.0, 0.0, 0.0)
        if not ok:
            raise RuntimeError(f"could not select {full}")
        ctx.doc.SketchManager.InsertSketch(True)

        center = feat.get("center", {})
        cx_m = float(center.get("x", 0.0)) / 1000.0
        cy_m = float(center.get("y", 0.0)) / 1000.0
        return SketchFrame(center_part=(cx_m, cy_m, 0.0))

    def _draw_geometry(
        self, ctx: BuildContext, feat: dict[str, Any], frame: SketchFrame
    ) -> dict[str, Any]:
        width_m = _literal_or_default(feat["width"], PLACEHOLDER_MM["rectangle_side"])
        height_m = _literal_or_default(feat["height"], PLACEHOLDER_MM["rectangle_side"])
        cx_m, cy_m, _ = frame.center_part

        # CreateCenterRectangle (NOT CreateCornerRectangle) so the rectangle
        # is internally anchored to its CENTER via construction diagonals.
        # Capture the returned segment tuple so the inline path can select
        # edges via Select4(captured_ptr) instead of coordinate SelectByID --
        # the post-Midpoint-delete sketch has unsettled selection priorities
        # that cause SelectByID to pick midpoint vertices instead of edges.
        rect_segs = ctx.doc.SketchManager.CreateCenterRectangle(
            cx_m,
            cy_m,
            0.0,
            cx_m + width_m / 2,
            cy_m + height_m / 2,
            0.0,
        )
        return {
            "rect_segs": rect_segs,
            "width_m": width_m,
            "height_m": height_m,
            "cx_m": cx_m,
            "cy_m": cy_m,
        }

    def _strip_relations(
        self, ctx: BuildContext, feat: dict[str, Any], geometry: Any
    ) -> None:
        _strip_centerrectangle_midpoint_relation(ctx.doc)

    def _add_dimensions_inline(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        cx_m = geometry["cx_m"]
        cy_m = geometry["cy_m"]
        width_m = geometry["width_m"]
        height_m = geometry["height_m"]
        rect_segs = geometry["rect_segs"]

        top_edge = _identify_rect_edge(rect_segs, "horiz_top", cx_m, cy_m)
        left_edge = _identify_rect_edge(rect_segs, "vert_left", cx_m, cy_m)
        top_y = cy_m + height_m / 2
        left_x = cx_m - width_m / 2

        vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

        # Template called ClearSelection2 before this method; re-clear
        # between picks so each AddDimension2 sees only its own edge.
        if top_edge is None or not top_edge.Select4(False, vt_disp_none):
            raise RuntimeError("could not select rectangle top edge for width dim")
        dim_w = ctx.doc.AddDimension2(cx_m, top_y + 0.005, 0.0)
        if dim_w is None:
            raise RuntimeError("AddDimension2 returned None for width")
        _dismiss_dim_pane(ctx.doc)

        ctx.doc.ClearSelection2(True)
        if left_edge is None or not left_edge.Select4(False, vt_disp_none):
            raise RuntimeError("could not select rectangle left edge for height dim")
        dim_h = ctx.doc.AddDimension2(left_x - 0.005, cy_m, 0.0)
        if dim_h is None:
            raise RuntimeError("AddDimension2 returned None for height")
        _dismiss_dim_pane(ctx.doc)

    def _record_deferred_dimensions(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        cx_m = geometry["cx_m"]
        cy_m = geometry["cy_m"]
        width_m = geometry["width_m"]
        height_m = geometry["height_m"]
        top_y = cy_m + height_m / 2
        left_x = cx_m - width_m / 2

        ctx.deferred_dims.append(
            DeferredDim(
                sketch_name=feat["name"],
                select_type="SKETCHSEGMENT",
                select_xyz=(cx_m, top_y, 0.0),
                leader_xyz=(cx_m, top_y + 0.005, 0.0),
                expected_dim_name=f"D1@{feat['name']}",
                field_label=f"width of {feat['name']}",
            )
        )
        ctx.deferred_dims.append(
            DeferredDim(
                sketch_name=feat["name"],
                select_type="SKETCHSEGMENT",
                select_xyz=(left_x, cy_m, 0.0),
                leader_xyz=(left_x - 0.005, cy_m, 0.0),
                expected_dim_name=f"D2@{feat['name']}",
                field_label=f"height of {feat['name']}",
            )
        )

    def _finalize(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> BuiltFeature:
        sm = ctx.doc.SketchManager
        _draw_centerline_if_present(sm, feat)
        sm.InsertSketch(True)

        sketch_feat = ctx.doc.FeatureByPositionReverse(0)
        if sketch_feat is None:
            raise RuntimeError("no sketch produced by CreateCornerRectangle")
        sketch_feat.Name = feat["name"]

        width_m = geometry["width_m"]
        height_m = geometry["height_m"]
        cx_m = geometry["cx_m"]
        cy_m = geometry["cy_m"]
        return BuiltFeature(
            name=feat["name"],
            type=feat["type"],
            sw_object=sketch_feat,
            sketch_center_part=(cx_m, cy_m, 0.0),
            sketch_extent_uv=(width_m / 2, height_m / 2),
        )
