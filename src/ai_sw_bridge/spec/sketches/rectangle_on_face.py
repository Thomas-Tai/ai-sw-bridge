"""Rectangle sketched on a face of a parent extrusion.

Used for stacked extrudes where each upper block's profile starts from the
previous block's top face (e.g. TensionBracket cap-slab-cap stack).
"""

from __future__ import annotations

from typing import Any

import pythoncom
import win32com.client

from .._build_context import BuildContext, BuiltFeature, DeferredDim
from .._face_geometry import (
    _face_frame,
    _select_extrude_face,
    _sketch_uv_to_part,
    _warn_face_sketch_offset,
)
from .._sketch_primitives import (
    PLACEHOLDER_MM,
    _dismiss_dim_pane,
    _identify_rect_edge,
    _literal_or_default,
    _strip_centerrectangle_midpoint_relation,
)
from .base import SketchFrame, SketchHandler


class RectangleOnFaceHandler(SketchHandler):
    """Rectangle on a parent extrusion's face. Same Spike ZF Midpoint
    strip + ``Select4(captured_ptr)`` pattern as the on-plane handler."""

    def _enter_sketch(self, ctx: BuildContext, feat: dict[str, Any]) -> SketchFrame:
        parent_name = feat["of_feature"]
        parent = ctx.features_by_name.get(parent_name)
        if parent is None:
            raise RuntimeError(
                f"sketch_rectangle_on_face: '{parent_name}' not built yet"
            )
        if parent.extrude_axis is None:
            raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

        face = feat["face"]
        _warn_face_sketch_offset(parent, face, feat, ("u", "v"))

        # Build the face frame (validates parent axis/extents); used for
        # the face-center seed point and the spiral-offset probe.
        frame_geom = _face_frame(parent, face)

        ok, fx, fy, fz = _select_extrude_face(ctx, parent, face)
        if not ok:
            raise RuntimeError(
                f"SelectByID returned False for {face} face of {parent_name} -- "
                f"tried center and offset points, none hit material"
            )

        ctx.doc.SketchManager.InsertSketch(True)

        return SketchFrame(
            center_part=(fx, fy, fz),
            face_origin=(fx, fy, fz),
            out_normal=frame_geom.out_normal,
        )

    def _draw_geometry(
        self, ctx: BuildContext, feat: dict[str, Any], frame: SketchFrame
    ) -> dict[str, Any]:
        width_m = _literal_or_default(feat["width"], PLACEHOLDER_MM["rectangle_side"])
        height_m = _literal_or_default(feat["height"], PLACEHOLDER_MM["rectangle_side"])
        # Face-local center offset (u, v); default (0, 0) = sketch origin
        # (which lands at the face center for +/-z; see FaceFrame docs).
        c = feat.get("center", {})
        cu_m = float(c.get("u", 0.0)) / 1000.0
        cv_m = float(c.get("v", 0.0)) / 1000.0

        # Capture segments so inline mode can use Select4(captured_ptr).
        rect_segs = ctx.doc.SketchManager.CreateCenterRectangle(
            cu_m,
            cv_m,
            0.0,
            cu_m + width_m / 2,
            cv_m + height_m / 2,
            0.0,
        )

        # Need to recompute the face frame for sketch-UV-to-part on the
        # dim-add hooks; SketchFrame carries out_normal but not the full
        # FaceFrame transform.
        parent = ctx.features_by_name[feat["of_feature"]]
        face_geom = _face_frame(parent, feat["face"])
        return {
            "rect_segs": rect_segs,
            "width_m": width_m,
            "height_m": height_m,
            "cu_m": cu_m,
            "cv_m": cv_m,
            "face_geom": face_geom,
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
        cu_m = geometry["cu_m"]
        cv_m = geometry["cv_m"]
        width_m = geometry["width_m"]
        height_m = geometry["height_m"]
        rect_segs = geometry["rect_segs"]
        face_geom = geometry["face_geom"]
        face = feat["face"]

        top_edge = _identify_rect_edge(rect_segs, "horiz_top")
        left_edge = _identify_rect_edge(rect_segs, "vert_left")
        top_v = cv_m + height_m / 2

        vt_disp_none = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

        # Template already ran ClearSelection2; clear again between picks.
        if top_edge is None or not top_edge.Select4(False, vt_disp_none):
            raise RuntimeError(
                f"could not select rect top edge for width dim "
                f"(face={face}, center=({cu_m*1000:.1f}, {cv_m*1000:.1f}) mm)"
            )
        dwx, dwy, dwz = _sketch_uv_to_part(face_geom, cu_m, top_v + 0.005)
        dim_w = ctx.doc.AddDimension2(dwx, dwy, dwz)
        if dim_w is None:
            raise RuntimeError("AddDimension2 returned None for width on face")
        _dismiss_dim_pane(ctx.doc)

        ctx.doc.ClearSelection2(True)
        if left_edge is None or not left_edge.Select4(False, vt_disp_none):
            raise RuntimeError(
                f"could not select rect left edge for height dim "
                f"(face={face}, center=({cu_m*1000:.1f}, {cv_m*1000:.1f}) mm)"
            )
        dhx, dhy, dhz = _sketch_uv_to_part(face_geom, cu_m - width_m / 2 - 0.005, cv_m)
        dim_h = ctx.doc.AddDimension2(dhx, dhy, dhz)
        if dim_h is None:
            raise RuntimeError("AddDimension2 returned None for height on face")
        _dismiss_dim_pane(ctx.doc)

    def _record_deferred_dimensions(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        cu_m = geometry["cu_m"]
        cv_m = geometry["cv_m"]
        width_m = geometry["width_m"]
        height_m = geometry["height_m"]
        face_geom = geometry["face_geom"]
        face = feat["face"]
        top_v = cv_m + height_m / 2
        left_u = cu_m - width_m / 2

        tx, ty, tz = _sketch_uv_to_part(face_geom, cu_m, top_v)
        dwx, dwy, dwz = _sketch_uv_to_part(face_geom, cu_m, top_v + 0.005)
        lx, ly, lz = _sketch_uv_to_part(face_geom, left_u, cv_m)
        dhx, dhy, dhz = _sketch_uv_to_part(face_geom, cu_m - width_m / 2 - 0.005, cv_m)
        ctx.deferred_dims.append(
            DeferredDim(
                sketch_name=feat["name"],
                select_type="SKETCHSEGMENT",
                select_xyz=(tx, ty, tz),
                leader_xyz=(dwx, dwy, dwz),
                expected_dim_name=f"D1@{feat['name']}",
                field_label=f"width of {feat['name']} (on {face})",
            )
        )
        ctx.deferred_dims.append(
            DeferredDim(
                sketch_name=feat["name"],
                select_type="SKETCHSEGMENT",
                select_xyz=(lx, ly, lz),
                leader_xyz=(dhx, dhy, dhz),
                expected_dim_name=f"D2@{feat['name']}",
                field_label=f"height of {feat['name']} (on {face})",
            )
        )

    def _finalize(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> BuiltFeature:
        # Face handlers never called _draw_centerline_if_present; preserved.
        ctx.doc.SketchManager.InsertSketch(True)

        sketch_feat = ctx.doc.FeatureByPositionReverse(0)
        if sketch_feat is None:
            raise RuntimeError("no rectangle sketch produced on face")
        sketch_feat.Name = feat["name"]

        width_m = geometry["width_m"]
        height_m = geometry["height_m"]
        return BuiltFeature(
            name=feat["name"],
            type=feat["type"],
            sw_object=sketch_feat,
            parent_plane_normal=frame.out_normal,
            parent_face_origin=frame.face_origin,
            sketch_extent_uv=(width_m / 2, height_m / 2),
        )
