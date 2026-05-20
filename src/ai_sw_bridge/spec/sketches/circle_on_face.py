"""Single circle sketched on a face of a parent extrusion."""

from __future__ import annotations

from typing import Any

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
    _literal_or_default,
)
from .base import SketchFrame, SketchHandler


class CircleOnFaceHandler(SketchHandler):
    """Single circle on a face; inline mode probes 4 cardinal perimeter
    points (in part-frame) so the dim binds reliably across all 6
    face labels."""

    def _enter_sketch(self, ctx: BuildContext, feat: dict[str, Any]) -> SketchFrame:
        parent_name = feat["of_feature"]
        parent = ctx.features_by_name.get(parent_name)
        if parent is None:
            raise RuntimeError(f"sketch_circle_on_face: '{parent_name}' not built yet")
        if parent.extrude_axis is None:
            raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

        face = feat["face"]
        _warn_face_sketch_offset(parent, face, feat, ("u", "v"))
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
        diameter_m = _literal_or_default(
            feat["diameter"], PLACEHOLDER_MM["circle_diameter_face"]
        )
        radius_m = diameter_m / 2
        c = feat.get("center", {})
        u_m = float(c.get("u", 0.0)) / 1000.0
        v_m = float(c.get("v", 0.0)) / 1000.0

        ctx.doc.SketchManager.CreateCircle(u_m, v_m, 0.0, u_m + radius_m, v_m, 0.0)

        parent = ctx.features_by_name[feat["of_feature"]]
        face_geom = _face_frame(parent, feat["face"])
        return {
            "u_m": u_m,
            "v_m": v_m,
            "radius_m": radius_m,
            "face_geom": face_geom,
        }

    def _add_dimensions_inline(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        u_m = geometry["u_m"]
        v_m = geometry["v_m"]
        radius_m = geometry["radius_m"]
        face_geom = geometry["face_geom"]
        face = feat["face"]

        # Four cardinal perimeter points in sketch coords; transform each
        # to part frame and try until one selects.
        perim_uv = [
            (u_m + radius_m, v_m),
            (u_m, v_m + radius_m),
            (u_m - radius_m, v_m),
            (u_m, v_m - radius_m),
        ]
        selected = False
        for pu, pv in perim_uv:
            sx, sy, sz = _sketch_uv_to_part(face_geom, pu, pv)
            if ctx.doc.SelectByID("", "SKETCHSEGMENT", sx, sy, sz):
                selected = True
                break
        if not selected:
            raise RuntimeError(
                f"could not select face-sketch circle for diameter dim "
                f"(face={face}, u={u_m*1000:.1f}mm, r={radius_m*1000:.2f}mm)"
            )
        dx, dy, dz = _sketch_uv_to_part(
            face_geom, u_m + radius_m + 0.005, v_m + radius_m + 0.005
        )
        dim_d = ctx.doc.AddDimension2(dx, dy, dz)
        if dim_d is None:
            raise RuntimeError("AddDimension2 returned None for face-sketch diameter")
        _dismiss_dim_pane(ctx.doc)

    def _record_deferred_dimensions(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        u_m = geometry["u_m"]
        v_m = geometry["v_m"]
        radius_m = geometry["radius_m"]
        face_geom = geometry["face_geom"]
        face = feat["face"]

        sx0, sy0, sz0 = _sketch_uv_to_part(face_geom, u_m + radius_m, v_m)
        dx, dy, dz = _sketch_uv_to_part(
            face_geom, u_m + radius_m + 0.005, v_m + radius_m + 0.005
        )
        ctx.deferred_dims.append(
            DeferredDim(
                sketch_name=feat["name"],
                select_type="SKETCHSEGMENT",
                select_xyz=(sx0, sy0, sz0),
                leader_xyz=(dx, dy, dz),
                expected_dim_name=f"D1@{feat['name']}",
                field_label=f"diameter of {feat['name']} (on {face})",
            )
        )

    def _finalize(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> BuiltFeature:
        ctx.doc.SketchManager.InsertSketch(True)
        sketch_feat = ctx.doc.FeatureByPositionReverse(0)
        if sketch_feat is None:
            raise RuntimeError("no sketch produced on face")
        sketch_feat.Name = feat["name"]

        return BuiltFeature(
            name=feat["name"],
            type=feat["type"],
            sw_object=sketch_feat,
            parent_plane_normal=frame.out_normal,
            parent_face_origin=frame.face_origin,
        )
