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
        cz_m = float(center.get("z", 0.0)) / 1000.0
        return SketchFrame(center_part=(cx_m, cy_m, cz_m))

    def _draw_geometry(
        self, ctx: BuildContext, feat: dict[str, Any], frame: SketchFrame
    ) -> dict[str, Any]:
        width_m = _literal_or_default(feat["width"], PLACEHOLDER_MM["rectangle_side"])
        height_m = _literal_or_default(feat["height"], PLACEHOLDER_MM["rectangle_side"])
        cx_m, cy_m, cz_m = frame.center_part

        # The user's `center` is in PART-frame mm. The COM call
        # CreateCenterRectangle, however, takes SKETCH-local 2D coords
        # (the 3rd arg is ignored when called inside an open sketch).
        # We project the user's part-frame center onto the sketch plane's
        # two in-plane axes to get sketch-local (sx, sy), then issue the
        # COM call in those coords. Width extends along the plane's first
        # in-plane axis; height extends along the second. Front Plane:
        # sketch_X=part_X, sketch_Y=part_Y (preserves legacy behavior).
        # Top Plane: sketch_X=part_X, sketch_Y=part_Z. Right Plane:
        # sketch_X=part_Y, sketch_Y=part_Z. The original DriveRoller
        # groove failure mode was passing part-frame coords directly to
        # the COM call without this projection, landing the rectangle
        # outside the cylinder body.
        # Sketch-local 2D axis directions on each default plane, verified
        # empirically via ISketch.ModelToSketchTransform (Spike 2026-05-22):
        # Front Plane (XY): sketch_X = +part_X, sketch_Y = +part_Y.
        # Top Plane (XZ):   sketch_X = +part_X, sketch_Y = -part_Z (!!).
        # Right Plane (YZ): sketch_X = +part_Z, sketch_Y = +part_Y (TBD --
        #   not exercised by shipped specs as of this date).
        plane = feat["plane"]
        if plane == "Front":
            sx_m, sy_m = cx_m, cy_m
        elif plane == "Top":
            sx_m, sy_m = cx_m, -cz_m
        else:  # Right
            sx_m, sy_m = cz_m, cy_m
        half_w = width_m / 2
        half_h = height_m / 2

        # CreateCenterRectangle (NOT CreateCornerRectangle) so the rectangle
        # is internally anchored to its CENTER via construction diagonals.
        # Capture the returned segment tuple so the inline path can select
        # edges via Select4(captured_ptr) instead of coordinate SelectByID --
        # the post-Midpoint-delete sketch has unsettled selection priorities
        # that cause SelectByID to pick midpoint vertices instead of edges.
        rect_segs = ctx.doc.SketchManager.CreateCenterRectangle(
            sx_m,
            sy_m,
            0.0,
            sx_m + half_w,
            sy_m + half_h,
            0.0,
        )
        return {
            "rect_segs": rect_segs,
            "width_m": width_m,
            "height_m": height_m,
            "cx_m": cx_m,
            "cy_m": cy_m,
            "cz_m": cz_m,
            "sx_m": sx_m,
            "sy_m": sy_m,
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
        sx_m = geometry["sx_m"]
        sy_m = geometry["sy_m"]
        width_m = geometry["width_m"]
        height_m = geometry["height_m"]
        rect_segs = geometry["rect_segs"]

        top_edge = _identify_rect_edge(rect_segs, "horiz_top")
        left_edge = _identify_rect_edge(rect_segs, "vert_left")

        # Leader points are in SKETCH-local 2D coords (same convention as
        # CreateCenterRectangle above). Width-dim leader sits just above
        # the top edge; height-dim leader sits just left of the left edge.
        # The 5 thou epsilon nudges the leader off the edge so
        # AddDimension2 anchors to the edge instead of the leader vertex.
        top_y = sy_m + height_m / 2
        left_x = sx_m - width_m / 2

        vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

        # Template called ClearSelection2 before this method; re-clear
        # between picks so each AddDimension2 sees only its own edge.
        if top_edge is None or not top_edge.Select4(False, vt_disp_none):
            raise RuntimeError("could not select rectangle top edge for width dim")
        dim_w = ctx.doc.AddDimension2(sx_m, top_y + 0.005, 0.0)
        if dim_w is None:
            raise RuntimeError("AddDimension2 returned None for width")
        _dismiss_dim_pane(ctx.doc)

        ctx.doc.ClearSelection2(True)
        if left_edge is None or not left_edge.Select4(False, vt_disp_none):
            raise RuntimeError("could not select rectangle left edge for height dim")
        dim_h = ctx.doc.AddDimension2(left_x - 0.005, sy_m, 0.0)
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
        sx_m = geometry["sx_m"]
        sy_m = geometry["sy_m"]
        width_m = geometry["width_m"]
        height_m = geometry["height_m"]
        top_y = sy_m + height_m / 2
        left_x = sx_m - width_m / 2

        # Sketch-local 2D coords for select+leader (third arg ignored by
        # the deferred-dim consumer in the same way CreateCenterRectangle
        # ignores it for the 3rd component).
        ctx.deferred_dims.append(
            DeferredDim(
                sketch_name=feat["name"],
                select_type="SKETCHSEGMENT",
                select_xyz=(sx_m, top_y, 0.0),
                leader_xyz=(sx_m, top_y + 0.005, 0.0),
                expected_dim_name=f"D1@{feat['name']}",
                field_label=f"width of {feat['name']}",
            )
        )
        ctx.deferred_dims.append(
            DeferredDim(
                sketch_name=feat["name"],
                select_type="SKETCHSEGMENT",
                select_xyz=(left_x, sy_m, 0.0),
                leader_xyz=(left_x - 0.005, sy_m, 0.0),
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
        cz_m = geometry["cz_m"]
        return BuiltFeature(
            name=feat["name"],
            type=feat["type"],
            sw_object=sketch_feat,
            sketch_center_part=(cx_m, cy_m, cz_m),
            sketch_extent_uv=(width_m / 2, height_m / 2),
        )
