"""Verbalizer gauntlet — deterministic recipe text, no JSON-syntax noise."""

from __future__ import annotations

import json

from ai_sw_bridge.rag.design_verbalizer import (
    verbalize_assembly,
    verbalize_drawing,
    verbalize_feature,
    verbalize_feature_add,
    verbalize_part_build,
    verbalize_proposal_record,
    verbalize_transaction,
)


def test_feature_phrase_is_natural_language_not_json():
    s = verbalize_feature(
        {"type": "ref_plane", "distance_mm": 20.0}, {"plane": "Front Plane"}
    )
    assert s == "reference plane 20 mm offset from Front Plane"
    assert "{" not in s and '"type"' not in s  # the anti-pattern guard


def test_feature_pattern_params_rendered():
    s = verbalize_feature(
        {"type": "linear_pattern", "count": 5, "spacing_mm": 10.0}, {"seed": "Boss1"}
    )
    assert s == "linear pattern 5 instances, spaced 10 mm on seed"


def test_unknown_kind_falls_back_to_humanized():
    s = verbalize_feature({"type": "sketch_circle_on_plane"}, {})
    assert s == "sketch circle on plane"  # graceful, no raise


def test_feature_add_recipe_header_and_lines():
    proposals = [
        {
            "feature": {"type": "ref_plane", "distance_mm": 20.0},
            "target": {"plane": "Front Plane"},
        },
        {
            "feature": {"type": "fillet_constant_radius", "radius_mm": 3.0},
            "target": {"edge": "E1"},
        },
    ]
    text, kinds = verbalize_feature_add(proposals, doc="C:/p/bracket.SLDPRT")
    assert text.splitlines()[0] == (
        "Part build: bracket  |  2 features: ref_plane, fillet_constant_radius"
    )
    assert "- reference plane 20 mm offset from Front Plane" in text
    assert "- constant-radius fillet radius 3 mm on edge" in text
    assert kinds == ["ref_plane", "fillet_constant_radius"]
    assert "{" not in text


def test_drawing_recipe():
    spec = {
        "kind": "drawing",
        "name": "test_drawing",
        "model": "part.sldprt",
        "views": ["front", "top", "right", "isometric"],
        "revision_table": True,
        "general_table": True,
        "weldment_table": True,
    }
    text, kinds = verbalize_drawing(spec)
    assert text.splitlines()[0] == "Drawing: test_drawing of part"
    assert "views: front, top, right, isometric" in text
    assert "tables: revision, general, weldment" in text
    assert "view:front" in kinds and "table:revision" in kinds


def test_assembly_recipe():
    spec = {
        "kind": "assembly",
        "name": "edit_test",
        "components": [
            {"id": "a", "part": "C:/t/w15_a.SLDPRT"},
            {"id": "b", "part": "C:/t/w15_b.SLDPRT"},
        ],
        "mates": [{"type": "coincident"}, {"type": "concentric"}],
    }
    text, kinds = verbalize_assembly(spec)
    assert text.splitlines()[0] == "Assembly: edit_test  |  2 components, 2 mates"
    assert "component a: w15_a" in text
    assert "coincident mate" in text
    assert "mate:coincident" in kinds and "mate:concentric" in kinds


def test_part_build_from_checkpoint_rows():
    rows = [
        (1, "Extrude_Body", "boss_extrude_blind"),
        (0, "SK_Body", "sketch_circle_on_plane"),
    ]
    text, kinds = verbalize_part_build("MinimalCylinder", rows)
    lines = text.splitlines()
    assert lines[0].startswith("Part build: MinimalCylinder  |  2 features:")
    assert lines[1] == "- sketch circle on plane (SK_Body)"  # ordered by index
    assert kinds == ["sketch_circle_on_plane", "boss_extrude_blind"]


def test_proposal_record_dispatch():
    drawing = verbalize_proposal_record(
        {
            "kind": "drawing",
            "state": "committed",
            "spec": {"name": "d", "model": "m.sldprt", "views": ["front"]},
        },
        ref="abc123",
    )
    assert drawing is not None and drawing.kind == "drawing"
    assert drawing.state == "committed" and drawing.source == "proposals"
    assert drawing.retrieval_key() == "proposals:drawing:abc123"

    # empty feature_add stub -> None (skipped, not indexed)
    assert (
        verbalize_proposal_record(
            {"kind": "feature_add", "state": "proposed", "spec": {}}, ref="x"
        )
        is None
    )
    # unknown kind -> None
    assert (
        verbalize_proposal_record(
            {"kind": "mystery", "state": "proposed", "spec": {"a": 1}}, ref="y"
        )
        is None
    )


def test_transaction_recipe_from_intent_payload():
    payload = json.dumps(
        [
            {
                "feature": {"type": "ref_plane", "distance_mm": 10.0},
                "target": {"plane": "Front Plane"},
            },
        ]
    )
    rec = verbalize_transaction("C:/p/run.SLDPRT", payload, ref="txn1")
    assert rec is not None
    assert rec.source == "transactions" and rec.kind == "feature_add"
    assert rec.ref == "txn1" and rec.doc == "run"
    assert "reference plane 10 mm offset from Front Plane" in rec.recipe_text
    assert verbalize_transaction("d", "not json", ref="z") is None
    assert verbalize_transaction("d", "[]", ref="z") is None


def test_recipe_spec_hash_is_stable_and_text_derived():
    a = verbalize_transaction(
        "d", json.dumps([{"feature": {"type": "shell"}, "target": {}}]), ref="r"
    )
    b = verbalize_transaction(
        "d", json.dumps([{"feature": {"type": "shell"}, "target": {}}]), ref="r2"
    )
    assert a.spec_hash == b.spec_hash  # same recipe text -> same hash
