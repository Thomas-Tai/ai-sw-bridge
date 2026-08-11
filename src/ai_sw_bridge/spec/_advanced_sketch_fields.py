"""Focused FieldSpec builders + descriptor stubs for the advanced sketch
primitives (the multi-point ``sketch_3d_sketch`` and ``sketch_polyline_on_plane``).

Split out of ``descriptors.py`` / ``builder.py`` so those (grandfathered,
shrink-only) modules stay under their ``tools/module_size_gate.py`` budget as the
sketch-primitive family grows. Cycle-free by construction, exactly like
``_extrude_fields``: this module imports only ``FieldSpec`` / ``FeatureType``
from ``_build_context``. The shared ``_SKETCH_POINT_2D`` sub-schema is passed in
by the caller (``descriptors.py``) rather than imported here, so the
``descriptors`` <-> ``_advanced_sketch_fields`` layering has no import cycle --
the promise in ``descriptors.py``'s module docstring still holds. The returned
field lists / stubs are byte-identical to the former inline literals; the golden
schema fixture guards that.
"""

from __future__ import annotations

from typing import Any

from ._build_context import FeatureType, FieldSpec


def sketch_3d_sketch_fields() -> list[FieldSpec]:
    """Field list for ``sketch_3d_sketch``.

    W53 — 3D-sketch primitive.  No ``plane`` field (3D sketches are not
    constrained to a reference plane).  Points carry real X/Y/Z coordinates
    (mm, all three required).  The polyline connects consecutive points via
    ISketchManager.CreateLine inside a 3D sketch (Insert3DSketch).
    """
    return [
        FieldSpec(
            "points",
            {
                "type": "array",
                "minItems": 2,
                "description": (
                    "Ordered 3D control points of the polyline.  Consecutive "
                    "points are connected by line segments.  All three axes "
                    "(x, y, z) are required — use a non-zero z extent to "
                    "create a non-planar path (weldment / sweep prerequisite)."
                ),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["x", "y", "z"],
                    "properties": {
                        "x": {
                            "type": "number",
                            "description": "X coordinate (mm) in the part frame.",
                        },
                        "y": {
                            "type": "number",
                            "description": "Y coordinate (mm) in the part frame.",
                        },
                        "z": {
                            "type": "number",
                            "description": "Z coordinate (mm) in the part frame.",
                        },
                    },
                },
            },
            True,
        ),
    ]


def sketch_polyline_on_plane_fields(
    sketch_point_2d: dict[str, Any],
) -> list[FieldSpec]:
    """Field list for ``sketch_polyline_on_plane``.

    ``sketch_point_2d`` is ``descriptors._SKETCH_POINT_2D`` (passed in to avoid
    an import cycle). Composite closed polyline on a standard plane: multiple
    connected line segments in ONE plane sketch -> a closed profile a boss/cut
    extrude can consume. The primitive for non-axis-aligned closed profiles
    (45 deg parallelograms) that the axis-aligned rectangle / regular polygon /
    single-segment line cannot express.
    """
    return [
        FieldSpec(
            "plane",
            {
                "enum": ["Front", "Top", "Right"],
                "description": "Default reference plane to host the sketch.",
            },
            True,
        ),
        FieldSpec(
            "points",
            {
                "type": "array",
                "minItems": 3,
                "description": (
                    "Ordered vertices of the profile in sketch-local 2D (mm). "
                    "Consecutive points are joined by line segments; when "
                    "`closed` is true (default) a final segment joins the last "
                    "point back to the first. At least 3 points for a closed "
                    "profile."
                ),
                "items": sketch_point_2d,
            },
            True,
        ),
        FieldSpec(
            "closed",
            {
                "type": "boolean",
                "default": True,
                "description": (
                    "If true (default) auto-close the loop (last→first) so the "
                    "profile is extrudable. Set false for an open polyline."
                ),
            },
            False,
        ),
        FieldSpec(
            "construction",
            {
                "type": "boolean",
                "default": False,
                "description": "If true, mark the segments as construction entities.",
            },
            False,
        ),
    ]


# Registry stubs for the two advanced sketch primitives (moved out of the
# ``builder.DESCRIPTORS`` literal). ``handler=None`` / ``dim_fields={}`` matches
# the other sketch-primitive stubs; ``builder._wire_handlers`` attaches the real
# handler + fields at module-load time. Kept here (not in builder) so builder.py
# stays under its shrink-only size budget.
ADVANCED_SKETCH_FEATURE_TYPES: dict[str, FeatureType] = {
    # W53 — 3D-sketch primitive. Not on a reference plane; uses Insert3DSketch(True)
    # (BOOL UpdateEditRebuild) and carries real X/Y/Z. Unblocks weldments (FR-5-06)
    # and swept/lofted surfaces (FR-5-02).
    "sketch_3d_sketch": FeatureType(
        name="sketch_3d_sketch",
        handler=None,
        dim_fields={},
    ),
    # Composite closed polyline on a standard plane — the primitive for
    # non-axis-aligned closed profiles (45 deg parallelograms) that
    # sketch_rectangle_on_plane / sketch_polygon / sketch_line cannot express.
    "sketch_polyline_on_plane": FeatureType(
        name="sketch_polyline_on_plane",
        handler=None,
        dim_fields={},
    ),
}
