"""Focused FieldSpec builders for the seven general-purpose sketch primitives
(line / arc / spline / slot / polygon / ellipse / text).

Split out of ``descriptors.py`` for the same reason as ``_extrude_fields.py``
and ``_advanced_sketch_fields.py``: that (grandfathered, shrink-only) module
must not grow past its ``tools/module_size_gate.py`` baseline. Cycle-free by
construction: this module imports only ``FieldSpec`` from ``_build_context``;
the shared sub-schemas (``_SKETCH_POINT_2D``, ``_SKETCH_SPLINE_POINTS``,
``_SLOT_TYPE_ENUM``, ``LENGTH_SCHEMA``, ``RELATIONS_SCHEMA``) are passed in by
the caller (``descriptors.py``) rather than imported here, so there is no
``descriptors`` <-> ``_basic_sketch_fields`` import cycle. The returned field
lists are byte-identical to the former inline literals; the golden schema
fixture guards this.
"""

from __future__ import annotations

from typing import Any

from ._build_context import FieldSpec

_PLANE_FIELD: dict[str, Any] = {
    "enum": ["Front", "Top", "Right"],
    "description": "Default reference plane to host the sketch.",
}


def sketch_line_fields(
    sketch_point_2d: dict[str, Any], relations_schema: dict[str, Any]
) -> list[FieldSpec]:
    """Field list for ``sketch_line``: a single line segment (start -> end)."""
    return [
        FieldSpec("plane", _PLANE_FIELD, True),
        FieldSpec(
            "start",
            {**sketch_point_2d, "description": "Line start point (sketch-local mm)."},
            True,
        ),
        FieldSpec(
            "end",
            {**sketch_point_2d, "description": "Line end point (sketch-local mm)."},
            True,
        ),
        FieldSpec(
            "construction",
            {
                "type": "boolean",
                "default": False,
                "description": "If true, mark the segment as a construction (centerline) entity.",
            },
            False,
        ),
        FieldSpec("relations", relations_schema, False),
    ]


def sketch_arc_fields(
    sketch_point_2d: dict[str, Any], relations_schema: dict[str, Any]
) -> list[FieldSpec]:
    """Field list for ``sketch_arc``: a circular arc (center + start + end)."""
    return [
        FieldSpec("plane", _PLANE_FIELD, True),
        FieldSpec(
            "center",
            {**sketch_point_2d, "description": "Arc center point (sketch-local mm)."},
            True,
        ),
        FieldSpec(
            "start",
            {**sketch_point_2d, "description": "Arc start point (sketch-local mm)."},
            True,
        ),
        FieldSpec(
            "end",
            {**sketch_point_2d, "description": "Arc end point (sketch-local mm)."},
            True,
        ),
        FieldSpec(
            "direction",
            {
                "enum": ["cw", "ccw"],
                "default": "ccw",
                "description": "Arc direction from start to end about the center.",
            },
            False,
        ),
        FieldSpec(
            "construction",
            {
                "type": "boolean",
                "default": False,
                "description": "If true, mark the arc as a construction entity.",
            },
            False,
        ),
        FieldSpec("relations", relations_schema, False),
    ]


def sketch_spline_fields(
    spline_points_schema: dict[str, Any], relations_schema: dict[str, Any]
) -> list[FieldSpec]:
    """Field list for ``sketch_spline``: a freeform spline (min 2 points).

    No ``closed`` field: a point-based periodic (C2) closed spline has no
    out-of-process API on this seat -- ISketchSpline.MakeClosed and
    ISketchManager.CreateClosedSpline do not exist (verified via
    GetIDsOfNames -> DISP_E_UNKNOWNNAME and a full typelib scan), and
    appending the first point yields a C0 cusp, not a periodic spline.
    Requesting `closed` therefore fails validation rather than faking it.
    """
    return [
        FieldSpec("plane", _PLANE_FIELD, True),
        FieldSpec("points", spline_points_schema, True),
        FieldSpec(
            "construction",
            {
                "type": "boolean",
                "default": False,
                "description": "If true, mark the spline as a construction entity.",
            },
            False,
        ),
        FieldSpec("relations", relations_schema, False),
    ]


def sketch_slot_fields(
    sketch_point_2d: dict[str, Any],
    length_schema: dict[str, Any],
    slot_type_enum: dict[str, Any],
    relations_schema: dict[str, Any],
) -> list[FieldSpec]:
    """Field list for ``sketch_slot``: a rounded-end (arc) slot.

    No ``construction`` field: CreateSketchSlot returns a read-only slot
    object (not a settable ISketchSegment) -- `ConstructionGeometry can not
    be set` on the seat. Unpacking the macro-feature's underlying segment
    array to mutate each is COM-index fragile, so construction is rejected
    for slots rather than faked.
    """
    return [
        FieldSpec("plane", _PLANE_FIELD, True),
        FieldSpec(
            "center",
            {**sketch_point_2d, "description": "Slot center point (sketch-local mm)."},
            True,
        ),
        FieldSpec(
            "width",
            {
                **length_schema,
                "description": "Slot width (mm) -- the diameter of the two rounded end caps.",
            },
            True,
        ),
        FieldSpec(
            "length",
            {
                **length_schema,
                "description": (
                    "Slot length (mm) -- the center-to-center distance "
                    "between the two rounded ends, along the slot's major axis."
                ),
            },
            True,
        ),
        FieldSpec("slot_type", slot_type_enum, False),
        FieldSpec(
            "angle_deg",
            {
                "type": "number",
                "default": 0.0,
                "description": "Rotation of the slot's major axis from the sketch X axis (degrees).",
            },
            False,
        ),
        FieldSpec("relations", relations_schema, False),
    ]


def sketch_polygon_fields(
    sketch_point_2d: dict[str, Any],
    length_schema: dict[str, Any],
    relations_schema: dict[str, Any],
) -> list[FieldSpec]:
    """Field list for ``sketch_polygon``: a regular N-sided polygon."""
    return [
        FieldSpec("plane", _PLANE_FIELD, True),
        FieldSpec(
            "center",
            {
                **sketch_point_2d,
                "description": "Polygon center point (sketch-local mm).",
            },
            True,
        ),
        FieldSpec(
            "sides",
            {
                "type": "integer",
                "minimum": 3,
                "maximum": 40,
                "description": "Number of polygon sides (3..40).",
            },
            True,
        ),
        FieldSpec(
            "radius",
            {
                **length_schema,
                "description": (
                    "Polygon radius (mm); see `inscribed` for whether this "
                    "is the apothem (inscribed) or circumscribed radius."
                ),
            },
            True,
        ),
        FieldSpec(
            "inscribed",
            {
                "type": "boolean",
                "default": True,
                "description": (
                    "If true, `radius` is the inscribed (apothem) radius — polygon "
                    "edges are tangent to the circle. If false, `radius` is the "
                    "circumscribed radius — polygon vertices lie on the circle."
                ),
            },
            False,
        ),
        FieldSpec(
            "angle_deg",
            {
                "type": "number",
                "default": 0.0,
                "description": "Rotation of the polygon's first vertex from the sketch X axis (degrees).",
            },
            False,
        ),
        FieldSpec(
            "construction",
            {
                "type": "boolean",
                "default": False,
                "description": "If true, mark the polygon as a construction entity.",
            },
            False,
        ),
        FieldSpec("relations", relations_schema, False),
    ]


def sketch_ellipse_fields(
    sketch_point_2d: dict[str, Any],
    length_schema: dict[str, Any],
    relations_schema: dict[str, Any],
) -> list[FieldSpec]:
    """Field list for ``sketch_ellipse``."""
    return [
        FieldSpec("plane", _PLANE_FIELD, True),
        FieldSpec(
            "center",
            {
                **sketch_point_2d,
                "description": "Ellipse center point (sketch-local mm).",
            },
            True,
        ),
        FieldSpec(
            "major_radius",
            {**length_schema, "description": "Semi-major axis length (mm)."},
            True,
        ),
        FieldSpec(
            "minor_radius",
            {**length_schema, "description": "Semi-minor axis length (mm)."},
            True,
        ),
        FieldSpec(
            "angle_deg",
            {
                "type": "number",
                "default": 0.0,
                "description": "Rotation of the major axis from the sketch X axis (degrees).",
            },
            False,
        ),
        FieldSpec(
            "construction",
            {
                "type": "boolean",
                "default": False,
                "description": "If true, mark the ellipse as a construction entity.",
            },
            False,
        ),
        FieldSpec("relations", relations_schema, False),
    ]


def sketch_text_fields(
    sketch_point_2d: dict[str, Any],
    length_schema: dict[str, Any],
    relations_schema: dict[str, Any],
) -> list[FieldSpec]:
    """Field list for ``sketch_text``: a plain-text annotation sketch.

    No ``angle_deg`` or ``construction`` field: InsertSketchText exposes no
    angle parameter and ITextFormat carries no rotation, so text baseline
    rotation has no out-of-process API on this seat; and text is not a
    sketch segment, so ConstructionGeometry does not apply. Both are
    rejected at validation rather than silently ignored.
    """
    return [
        FieldSpec("plane", _PLANE_FIELD, True),
        FieldSpec(
            "position",
            {
                **sketch_point_2d,
                "description": "Text insertion point (sketch-local mm).",
            },
            True,
        ),
        FieldSpec(
            "content",
            {
                "type": "string",
                "minLength": 1,
                "description": "Text content. Plain ASCII; no rich formatting.",
            },
            True,
        ),
        FieldSpec(
            "height",
            {
                **length_schema,
                "description": "Text cap height (mm), applied as CharHeight.",
            },
            True,
        ),
        FieldSpec(
            "font",
            {
                "type": "string",
                "description": (
                    "Font family name (e.g. 'Arial'). Applied via the inserted "
                    "ISketchText's text format (GetTextFormat -> TypeFaceName -> "
                    "SetTextFormat); `height` sets CharHeight in the same call."
                ),
            },
            False,
        ),
        FieldSpec("relations", relations_schema, False),
    ]
