"""X3 migration guard (FR-X-03): the descriptor-assembled schema fragments
must be byte-identical to the hand-written fragments in schema.py.

This proves the refactor doesn't silently change validation for any of the 16
existing primitives. It runs while BOTH representations exist; once schema.py
is rewired to build SCHEMA from the assembler (and the literals deleted), the
frozen-snapshot test in tests/ takes over as the ongoing regression gate.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec import descriptors, schema

# name -> the hand-written fragment constant currently in schema.py.
HANDWRITTEN = {
    "sketch_rectangle_on_plane": schema.SKETCH_RECTANGLE_ON_PLANE,
    "sketch_rectangle_on_face": schema.SKETCH_RECTANGLE_ON_FACE,
    "sketch_circle_on_plane": schema.SKETCH_CIRCLE_ON_PLANE,
    "sketch_circle_on_face": schema.SKETCH_CIRCLE_ON_FACE,
    "sketch_circles_on_face": schema.SKETCH_CIRCLES_ON_FACE,
    "boss_extrude_blind": schema.BOSS_EXTRUDE_BLIND,
    "cut_extrude_through_all": schema.CUT_EXTRUDE_THROUGH_ALL,
    "cut_extrude_blind": schema.CUT_EXTRUDE_BLIND,
    "revolve_boss": schema.REVOLVE_BOSS,
    "revolve_cut": schema.REVOLVE_CUT,
    "simple_hole": schema.SIMPLE_HOLE,
    "fillet_constant_radius": schema.FILLET_CONSTANT_RADIUS,
    "chamfer_edge": schema.CHAMFER_EDGE,
    "linear_pattern": schema.LINEAR_PATTERN,
    "circular_pattern": schema.CIRCULAR_PATTERN,
    "mirror_feature": schema.MIRROR_FEATURE,
}


@pytest.mark.parametrize("name", sorted(HANDWRITTEN))
def test_assembled_fragment_matches_handwritten(name):
    assembled = descriptors.assemble_feature_schema(name)
    assert assembled == HANDWRITTEN[name], (
        f"assembled schema for {name!r} differs from the hand-written fragment"
    )


def test_assembled_required_order_matches():
    # `required` is a list -> order-sensitive. Guard it explicitly so a
    # reordered FieldSpec list can't pass on dict-equality alone.
    for name, frag in HANDWRITTEN.items():
        assert descriptors.assemble_feature_schema(name)["required"] == frag["required"]


def test_assemble_all_matches_schema_oneof():
    # The ordered list the top-level SCHEMA will be built from must equal the
    # current hand-written oneOf, element for element.
    assembled = descriptors.assemble_all()
    current = schema.SCHEMA["properties"]["features"]["items"]["oneOf"]
    assert assembled == current


def test_shared_subschemas_match():
    # The sub-schemas moved into descriptors.py must equal schema.py's copies
    # (until schema.py re-exports them from descriptors in the next step).
    assert descriptors.LENGTH_SCHEMA == schema.LENGTH_SCHEMA
    assert descriptors.CENTERLINE_SCHEMA == schema.CENTERLINE_SCHEMA
    assert descriptors.EXPECT_SCHEMA == schema.EXPECT_SCHEMA


def test_feature_order_covers_all_16():
    assert len(descriptors.FEATURE_ORDER) == 16
    assert set(descriptors.FEATURE_ORDER) == set(descriptors.FEATURE_FIELDS)
