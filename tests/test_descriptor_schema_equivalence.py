"""X3 regression gate (FR-X-03): the descriptor-assembled feature fragments
must stay byte-identical to the frozen golden snapshot.

History: the migration was proven by asserting assemble_feature_schema(name)
== the hand-written schema.py constant for all 16 primitives (commit X3.2a).
Those literals are now gone -- SCHEMA is built from descriptors.assemble_all().
The golden snapshot (tests/fixtures/feature_schema_golden.json), captured from
that proven-equivalent output, is the ongoing guard: an accidental descriptor
edit that changes any primitive's schema fails here.

To intentionally change a primitive's schema, regenerate the golden:
    python -c "import json; from ai_sw_bridge.spec import descriptors as d; \
        json.dump(d.assemble_all(), open('tests/fixtures/feature_schema_golden.json','w'), \
        indent=2, ensure_ascii=False)"
and review the diff.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_sw_bridge.spec import descriptors, schema

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "feature_schema_golden.json").read_text(
        encoding="utf-8"
    )
)


def test_assembled_matches_golden():
    # Order-sensitive list equality: catches both shape drift and reordering.
    assert descriptors.assemble_all() == GOLDEN


def test_schema_oneof_is_built_from_assembler():
    # The live top-level SCHEMA must use the assembled fragments.
    one_of = schema.SCHEMA["properties"]["features"]["items"]["oneOf"]
    assert one_of == descriptors.assemble_all()
    assert one_of == GOLDEN


def test_required_order_preserved_per_fragment():
    by_name = {f["properties"]["type"]["const"]: f for f in GOLDEN}
    for name in descriptors.FEATURE_ORDER:
        assert (
            descriptors.assemble_feature_schema(name)["required"]
            == by_name[name]["required"]
        )


def test_subschemas_reexported_from_descriptors():
    # schema.py re-exports the sub-schemas from descriptors (same objects).
    assert schema.LENGTH_SCHEMA is descriptors.LENGTH_SCHEMA
    assert schema.CENTERLINE_SCHEMA is descriptors.CENTERLINE_SCHEMA
    assert schema.EXPECT_SCHEMA is descriptors.EXPECT_SCHEMA
    assert schema.NAME_PATTERN is descriptors.NAME_PATTERN


def test_feature_order_covers_all_16():
    assert len(descriptors.FEATURE_ORDER) == 16
    assert set(descriptors.FEATURE_ORDER) == set(descriptors.FEATURE_FIELDS)
    assert len(GOLDEN) == 16
