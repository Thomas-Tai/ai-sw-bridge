"""Focused FieldSpec builders for extrude-family primitives.

Split out of ``descriptors.py`` so that (grandfathered, shrink-only) module
stays under its ``tools/module_size_gate.py`` budget when the extrude
descriptors grow. Cycle-free by construction: this module imports only
``FieldSpec`` from ``_build_context``; the shared ``LENGTH_SCHEMA`` is passed
in by the caller (``descriptors.py``) rather than imported here, so there is no
``descriptors`` <-> ``_extrude_fields`` import cycle -- the layering promise in
``descriptors.py``'s module docstring still holds.
"""

from __future__ import annotations

from typing import Any

from ._build_context import FieldSpec


def boss_extrude_blind_fields(length_schema: dict[str, Any]) -> list[FieldSpec]:
    """Field list for the ``boss_extrude_blind`` primitive.

    ``length_schema`` is ``descriptors.LENGTH_SCHEMA`` (passed in to avoid an
    import cycle). The returned list is identical to the former inline literal
    in ``descriptors.FEATURE_FIELDS`` -- the golden schema fixture guards this.
    """
    return [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": "Name of an earlier sketch feature to extrude.",
            },
            True,
        ),
        FieldSpec("depth", length_schema, True),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": "Extrude in -normal instead of +normal direction.",
            },
            False,
        ),
        FieldSpec(
            "merge",
            {
                "type": "boolean",
                "default": True,
                "description": (
                    "true (default) = fuse this boss into the existing solid body "
                    "it overlaps (modeling-time boolean UNION). false = keep it as a "
                    "separate solid body (multi-body). Express unions HERE, at the "
                    "extrusion phase: there is no post-hoc 'combine' feature."
                ),
            },
            False,
        ),
        FieldSpec(
            "start_offset",
            {
                **length_schema,
                "description": (
                    "Optional. Begin the extrude this many mm from the sketch "
                    "plane (SW start condition swStartOffset) instead of on it; "
                    "the blind `depth` is then measured from that offset start. "
                    "OMIT for the normal start-on-sketch-plane behaviour (byte-"
                    "identical to before). Lets a boss build offset from a "
                    "standard plane -- e.g. a side plate sketched on Top Plane "
                    "but extruded to begin at part-Y=+40. Pair with "
                    "`flip_start_offset` to choose the offset direction."
                ),
            },
            False,
        ),
        FieldSpec(
            "flip_start_offset",
            {
                "type": "boolean",
                "default": False,
                "description": (
                    "Offset toward -normal instead of +normal (SW "
                    "FlipStartOffset). Only meaningful when `start_offset` is set."
                ),
            },
            False,
        ),
    ]
