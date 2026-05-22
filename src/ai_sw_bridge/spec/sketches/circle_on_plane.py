"""Circle sketched on a named reference plane (Front/Top/Right)."""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext, BuiltFeature, DeferredDim
from .._face_geometry import PLANE_FULL_NAME
from .._sketch_primitives import (
    PLACEHOLDER_MM,
    _dismiss_dim_pane,
    _draw_centerline_if_present,
    _literal_or_default,
)
from .base import SketchFrame, SketchHandler


class CircleOnPlaneHandler(SketchHandler):
    """Circle sketched on a reference plane.

    Uses ``CreateCircle(xc, yc, zc, xp, yp, zp)`` with the perimeter probe
    point at ``(cx + radius, cy)``; the diameter dim is bound by selecting
    that perimeter point in part-frame coords.
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
        diameter_m = _literal_or_default(
            feat["diameter"], PLACEHOLDER_MM["circle_diameter_plane"]
        )
        radius_m = diameter_m / 2
        cx_m, cy_m, cz_m = frame.center_part

        # Project part-frame center onto the sketch plane's two in-plane
        # axes -- CreateCircle expects sketch-local 2D coords (3rd arg
        # ignored by SW when called inside an open sketch). See
        # rectangle_on_plane._draw_geometry for the full rationale; this
        # is the same projection convention.
        # See rectangle_on_plane._draw_geometry for the empirically-verified
        # sketch-axis-to-part-axis mapping (Spike 2026-05-22 transform read).
        plane = feat["plane"]
        if plane == "Front":
            sx_m, sy_m = cx_m, cy_m
        elif plane == "Top":
            sx_m, sy_m = cx_m, -cz_m
        else:  # Right
            sx_m, sy_m = cz_m, cy_m

        # CreateCircle(xc, yc, zc, xp, yp, zp) -- perimeter point at
        # (sx + radius, sy) in sketch-local 2D.
        ctx.doc.SketchManager.CreateCircle(sx_m, sy_m, 0.0, sx_m + radius_m, sy_m, 0.0)
        return {
            "cx_m": cx_m,
            "cy_m": cy_m,
            "cz_m": cz_m,
            "sx_m": sx_m,
            "sy_m": sy_m,
            "radius_m": radius_m,
        }

    def _add_dimensions_inline(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:
        sx_m = geometry["sx_m"]
        sy_m = geometry["sy_m"]
        radius_m = geometry["radius_m"]

        if not ctx.doc.SelectByID("", "SKETCHSEGMENT", sx_m + radius_m, sy_m, 0.0):
            raise RuntimeError("could not select circle for diameter dim")
        dim_d = ctx.doc.AddDimension2(
            sx_m + radius_m + 0.005, sy_m + radius_m + 0.005, 0.0
        )
        if dim_d is None:
            raise RuntimeError("AddDimension2 returned None for diameter")
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
        radius_m = geometry["radius_m"]
        ctx.deferred_dims.append(
            DeferredDim(
                sketch_name=feat["name"],
                select_type="SKETCHSEGMENT",
                select_xyz=(sx_m + radius_m, sy_m, 0.0),
                leader_xyz=(sx_m + radius_m + 0.005, sy_m + radius_m + 0.005, 0.0),
                expected_dim_name=f"D1@{feat['name']}",
                field_label=f"diameter of {feat['name']}",
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
            raise RuntimeError("no sketch produced by CreateCircle")
        sketch_feat.Name = feat["name"]

        cx_m = geometry["cx_m"]
        cy_m = geometry["cy_m"]
        cz_m = geometry["cz_m"]
        return BuiltFeature(
            name=feat["name"],
            type=feat["type"],
            sw_object=sketch_feat,
            sketch_center_part=(cx_m, cy_m, cz_m),
        )
