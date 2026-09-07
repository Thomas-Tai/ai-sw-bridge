"""Focused FieldSpec builders for extrude-family primitives.

Split out of ``descriptors.py`` so that (grandfathered, shrink-only) module
stays under its ``tools/module_size_gate.py`` budget when the extrude
descriptors grow. Cycle-free by construction: this module imports only
``FieldSpec`` from ``_build_context``; the shared ``LENGTH_SCHEMA`` (and, for
the primitives added below, ``_FACE_ENUM``) are passed in by the caller
(``descriptors.py``) rather than imported here, so there is no
``descriptors`` <-> ``_extrude_fields`` import cycle -- the layering promise in
``descriptors.py``'s module docstring still holds.
"""

from __future__ import annotations

from typing import Any

from ._build_context import FieldSpec

# Shared `merge` schema for every boss variant EXCEPT boss_extrude_blind
# (whose field list above carries its own, textually-identical copy inline).
# Kept as one constant so the four boss_extrude_* fragments below can't drift
# from each other or from boss_extrude_blind's copy.
_BOSS_MERGE_SCHEMA: dict[str, Any] = {
    "type": "boolean",
    "default": True,
    "description": (
        "true (default) = fuse this boss into the existing solid body it "
        "overlaps (modeling-time boolean UNION). false = keep it as a "
        "separate solid body (multi-body). Express unions HERE, at the "
        "extrusion phase: there is no post-hoc 'combine' feature."
    ),
}

# Shared `flip` schema for the three single-direction cut variants
# (cut_extrude_through_all/_blind/_midplane). FeatureCut4 arg 2 (`Flip`) is
# proven NOT to reverse cut direction (issue #40, seat-proven 2026-09-05) --
# the builder derives the real +normal/-normal sweep automatically from
# whether the sketch is plane- or face-hosted (see
# docs/coordinate_conventions.md §4). `cut_extrude_two_direction` gets its
# own hedged copy inline below since that arg shape was not covered by the
# #40 seat proof.
_CUT_FLIP_SCHEMA: dict[str, Any] = {
    "type": "boolean",
    "default": False,
    "description": (
        "Bound to FeatureCut4 arg 2 (`Flip`); proven not to reverse cut "
        "direction (issue #40, seat-proven 2026-09-05). The builder sets "
        "the real +normal/-normal sweep direction automatically depending "
        "on whether the sketch is plane- or face-hosted."
    ),
}


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
        FieldSpec(
            "depth",
            {**length_schema, "description": "Extrusion depth (mm)."},
            True,
        ),
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


def boss_extrude_midplane_fields(length_schema: dict[str, Any]) -> list[FieldSpec]:
    """Field list for ``boss_extrude_midplane``."""
    return [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": "Name of an earlier sketch feature to extrude.",
            },
            True,
        ),
        FieldSpec(
            "depth",
            {
                **length_schema,
                "description": (
                    "Total extrusion depth (mm), centred on the sketch plane "
                    "(depth/2 of material added each side)."
                ),
            },
            True,
        ),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": (
                    "Reserved; a mid-plane extrude is symmetric about the "
                    "sketch plane, so the direction is immaterial."
                ),
            },
            False,
        ),
        FieldSpec("merge", _BOSS_MERGE_SCHEMA, False),
    ]


def boss_extrude_through_all_fields() -> list[FieldSpec]:
    """Field list for ``boss_extrude_through_all``."""
    return [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": "Name of an earlier sketch feature to extrude.",
            },
            True,
        ),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": "Extrude in -normal instead of +normal direction.",
            },
            False,
        ),
        FieldSpec("merge", _BOSS_MERGE_SCHEMA, False),
    ]


def boss_extrude_two_direction_fields(length_schema: dict[str, Any]) -> list[FieldSpec]:
    """Field list for ``boss_extrude_two_direction``."""
    return [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": "Name of an earlier sketch feature to extrude.",
            },
            True,
        ),
        FieldSpec(
            "depth",
            {**length_schema, "description": "Extrusion depth into +normal (mm)."},
            True,
        ),
        FieldSpec(
            "depth2",
            {**length_schema, "description": "Extrusion depth into -normal (mm)."},
            True,
        ),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": (
                    "Swap which side `depth` (+normal) vs `depth2` (-normal) "
                    "extrudes into."
                ),
            },
            False,
        ),
        FieldSpec("merge", _BOSS_MERGE_SCHEMA, False),
    ]


def boss_extrude_up_to_surface_fields(face_enum: list[str]) -> list[FieldSpec]:
    """Field list for ``boss_extrude_up_to_surface``.

    ``face_enum`` is ``descriptors._FACE_ENUM`` (passed in to avoid an import
    cycle), reused for the durable ``target_ref.face`` reference.
    """
    target_ref_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["of_feature", "face"],
        "properties": {
            "of_feature": {
                "type": "string",
                "description": (
                    "Name of an earlier extrusion whose face the boss extrudes "
                    "up to (the up-to termination surface)."
                ),
            },
            "face": {
                "enum": face_enum,
                "description": "Outward normal of the up-to target face.",
            },
        },
        "description": (
            "Durable reference to the up-to termination surface (a face of an "
            "earlier extrusion). Required — the boss has no fixed depth."
        ),
    }
    return [
        FieldSpec(
            "sketch",
            {"type": "string", "description": "Name of an earlier sketch to extrude."},
            True,
        ),
        FieldSpec("target_ref", target_ref_schema, True),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": "Extrude in -normal instead of +normal direction.",
            },
            False,
        ),
        FieldSpec("merge", _BOSS_MERGE_SCHEMA, False),
    ]


def cut_extrude_through_all_fields() -> list[FieldSpec]:
    """Field list for ``cut_extrude_through_all``."""
    return [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": "Name of an earlier sketch to cut along.",
            },
            True,
        ),
        FieldSpec("flip", _CUT_FLIP_SCHEMA, False),
    ]


def cut_extrude_blind_fields(length_schema: dict[str, Any]) -> list[FieldSpec]:
    """Field list for ``cut_extrude_blind``."""
    return [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": "Name of an earlier sketch feature to cut along.",
            },
            True,
        ),
        FieldSpec(
            "depth",
            {**length_schema, "description": "Cut depth (mm)."},
            True,
        ),
        FieldSpec("flip", _CUT_FLIP_SCHEMA, False),
    ]


def cut_extrude_midplane_fields(length_schema: dict[str, Any]) -> list[FieldSpec]:
    """Field list for ``cut_extrude_midplane``."""
    return [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": "Name of an earlier sketch feature to cut along.",
            },
            True,
        ),
        FieldSpec(
            "depth",
            {
                **length_schema,
                "description": (
                    "Total cut depth (mm), centred on the sketch plane "
                    "(depth/2 removed each side)."
                ),
            },
            True,
        ),
        FieldSpec("flip", _CUT_FLIP_SCHEMA, False),
    ]


def cut_extrude_two_direction_fields(length_schema: dict[str, Any]) -> list[FieldSpec]:
    """Field list for ``cut_extrude_two_direction``.

    ``flip`` is deliberately hedged: the issue #40 seat proof (2026-09-05)
    only covers one-directional cuts, so its effect on this two-direction
    arg shape is unverified.
    """
    return [
        FieldSpec(
            "sketch",
            {
                "type": "string",
                "description": "Name of an earlier sketch feature to cut along.",
            },
            True,
        ),
        FieldSpec(
            "depth",
            {
                **length_schema,
                "description": "Cut depth into the +normal direction (mm).",
            },
            True,
        ),
        FieldSpec(
            "depth2",
            {
                **length_schema,
                "description": "Cut depth into the -normal direction (mm).",
            },
            True,
        ),
        FieldSpec(
            "flip",
            {
                "type": "boolean",
                "default": False,
                "description": (
                    "Bound to FeatureCut4 arg 2 (`Flip`). The issue #40 seat "
                    "proof (2026-09-05) only covers one-directional cuts, so "
                    "this field's effect on a two-direction cut is UNVERIFIED "
                    "-- `depth`/`depth2` are what determine which side is "
                    "removed, not `flip`."
                ),
            },
            False,
        ),
    ]
