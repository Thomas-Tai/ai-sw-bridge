"""Multiple circles in one sketch on a parent extrusion's face.

Variant of CircleOnFaceHandler: each circle gets its own driving diameter
dim. Selection order determines dim numbering — the first circle's
diameter is D1, the second D2, etc. The handler dimensions each circle
immediately after creating it so the array order matches the dim suffix.

Because the create+dim interleave is essential (the ordering constraint
cannot be split across separate ``_draw_geometry`` and
``_add_dimensions_inline`` phases without losing the guarantee), this
handler overrides the template ``build`` method rather than the four
hooks. It still uses ``SketchHandler`` for the shared error-recovery
behavior in the template ``build``'s ``try/except``.
"""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext, BuiltFeature, DeferredDim
from .._face_geometry import (
    _face_frame,
    _select_extrude_face,
    _sketch_uv_to_part,
)
from .._sketch_primitives import (
    PLACEHOLDER_MM,
    _dismiss_dim_pane,
    _literal_or_default,
)
from .base import SketchFrame, SketchHandler


class CirclesOnFaceHandler(SketchHandler):
    """N circles in one sketch with per-circle dim binding."""

    # ABC method stubs: the template build() is overridden, so these are
    # never reached. They exist only to satisfy the abstract contract.
    def _enter_sketch(
        self, ctx: BuildContext, feat: dict[str, Any]
    ) -> SketchFrame:  # pragma: no cover
        raise NotImplementedError("CirclesOnFaceHandler overrides build()")

    def _draw_geometry(
        self, ctx: BuildContext, feat: dict[str, Any], frame: SketchFrame
    ) -> Any:  # pragma: no cover
        raise NotImplementedError("CirclesOnFaceHandler overrides build()")

    def _add_dimensions_inline(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:  # pragma: no cover
        raise NotImplementedError("CirclesOnFaceHandler overrides build()")

    def _record_deferred_dimensions(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> None:  # pragma: no cover
        raise NotImplementedError("CirclesOnFaceHandler overrides build()")

    def _finalize(
        self,
        ctx: BuildContext,
        feat: dict[str, Any],
        frame: SketchFrame,
        geometry: Any,
    ) -> BuiltFeature:  # pragma: no cover
        raise NotImplementedError("CirclesOnFaceHandler overrides build()")

    def build(self, ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
        parent_name = feat["of_feature"]
        parent = ctx.features_by_name.get(parent_name)
        if parent is None:
            raise RuntimeError(f"sketch_circles_on_face: '{parent_name}' not built yet")
        if parent.extrude_axis is None:
            raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

        face = feat["face"]
        # NOTE: no _warn_face_sketch_offset here. sketch_circles_on_face
        # is the multi-hole variant; users already specify explicit
        # per-circle u/v positions, so they have opted into the "I know
        # where these go" mode.

        face_geom = _face_frame(parent, face)

        ok, fx, fy, fz = _select_extrude_face(ctx, parent, face)
        if not ok:
            raise RuntimeError(
                f"face select returned False for {face} face of {parent_name} -- "
                f"tried center and offsets"
            )

        sm = ctx.doc.SketchManager
        sm.InsertSketch(True)
        try:
            for k, c in enumerate(feat["circles"]):
                u_m = float(c["u"]) / 1000.0
                v_m = float(c["v"]) / 1000.0
                diameter_m = _literal_or_default(
                    c["diameter"], PLACEHOLDER_MM["circle_diameter_multi"]
                )
                radius_m = diameter_m / 2
                sm.CreateCircle(u_m, v_m, 0.0, u_m + radius_m, v_m, 0.0)
                if ctx.no_dim:
                    continue

                # Stagger leader offset so consecutive dim leaders do not overlap.
                lead_offset = 0.005 + 0.003 * k
                dx, dy, dz = _sketch_uv_to_part(
                    face_geom, u_m + radius_m + lead_offset, v_m + lead_offset
                )
                if ctx.deferred_dim:
                    sx0, sy0, sz0 = _sketch_uv_to_part(face_geom, u_m + radius_m, v_m)
                    ctx.deferred_dims.append(
                        DeferredDim(
                            sketch_name=feat["name"],
                            select_type="SKETCHSEGMENT",
                            select_xyz=(sx0, sy0, sz0),
                            leader_xyz=(dx, dy, dz),
                            expected_dim_name=f"D{k+1}@{feat['name']}",
                            field_label=(
                                f"diameter of circle #{k} in {feat['name']} "
                                f"(on {face})"
                            ),
                        )
                    )
                    continue

                # Dimension this circle BEFORE creating the next one so dim
                # numbering matches array index.
                ctx.doc.ClearSelection2(True)
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
                        f"could not select circle #{k} (perimeter at radius "
                        f"{radius_m*1000:.2f}mm from sketch center "
                        f"({u_m*1000:.1f}, {v_m*1000:.1f}) mm, face={face}) -- "
                        f"tried 4 cardinal perimeter points in part frame"
                    )
                dim = ctx.doc.AddDimension2(dx, dy, dz)
                if dim is None:
                    raise RuntimeError(f"AddDimension2 returned None for circle #{k}")
                _dismiss_dim_pane(ctx.doc)

            sm.InsertSketch(True)
        except Exception:
            try:
                sm.InsertSketch(True)
            except Exception:
                pass
            raise

        sketch_feat = ctx.doc.FeatureByPositionReverse(0)
        if sketch_feat is None:
            raise RuntimeError("no multi-circle sketch produced")
        sketch_feat.Name = feat["name"]

        return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=sketch_feat)
