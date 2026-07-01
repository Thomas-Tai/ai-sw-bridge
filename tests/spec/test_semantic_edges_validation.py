"""Schema + validator gating for semantic edge selectors (#9).

Two layers, both COM-free:

* Schema (``_check_schema``): the ``edges[]`` item is a ``oneOf`` of three
  disjoint forms. Acceptance is flag-INDEPENDENT (the grammar always admits the
  shape); the feature flag governs whether a spec may USE it.
* References (``_check_references``): the ``semantic_edges`` flag gate
  (fail-closed, default OFF) plus the nested ``of_feature`` topological check
  the JSON schema can't express, plus the anti-parallel ``between_faces`` guard.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec import validator
from ai_sw_bridge.spec.validator import ValidationError, _check_schema, validate


def _spec(edges):
    return {
        "schema_version": 1,
        "name": "edge_demo",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 20.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "Box",
                "sketch": "SK_Box",
                "depth": 10.0,
            },
            {
                "type": "fillet_constant_radius",
                "name": "F1",
                "radius": 2.0,
                "edges": edges,
            },
        ],
    }


@pytest.fixture
def flag_on(monkeypatch):
    """Force the semantic_edges flag ON for the validator gate."""
    monkeypatch.setattr(validator, "_semantic_edges_enabled", lambda: True)


@pytest.fixture
def flag_off(monkeypatch):
    """Force the semantic_edges flag OFF (it defaults ON since v1.7)."""
    monkeypatch.setattr(validator, "_semantic_edges_enabled", lambda: False)


# --- Schema layer (flag-independent grammar) -------------------------------


@pytest.mark.parametrize(
    "edges",
    [
        [{"x": 10.0, "y": 0.0, "z": 10.0}],  # legacy literal
        [{"of_feature": "Box", "face": "+z"}],  # of_face
        [{"of_feature": "Box", "between_faces": ["+z", "+x"]}],  # between_faces
        [  # all three forms in one array
            {"x": 10.0, "y": 0.0, "z": 10.0},
            {"of_feature": "Box", "face": "+z"},
            {"of_feature": "Box", "between_faces": ["+z", "+x"]},
        ],
    ],
)
def test_schema_accepts_all_three_forms(edges):
    # Schema acceptance does not depend on the flag.
    _check_schema(_spec(edges))


@pytest.mark.parametrize(
    "bad_item",
    [
        {"x": 1.0, "y": 2.0, "z": 3.0, "of_feature": "Box"},  # matches >1 branch keys
        {"of_feature": "Box", "face": "+q"},  # bad face enum
        {"of_feature": "Box", "between_faces": ["+z"]},  # minItems 2
        {"of_feature": "Box", "between_faces": ["+z", "+x", "+y"]},  # maxItems 2
        {"of_feature": "Box", "face": "+z", "extra": 1},  # additionalProperties
        {"x": 1.0, "y": 2.0},  # incomplete literal
    ],
)
def test_schema_rejects_malformed_edge_items(bad_item):
    with pytest.raises(ValidationError):
        _check_schema(_spec([bad_item]))


# --- Reference layer: feature-flag gate ------------------------------------


def test_semantic_selector_rejected_when_flag_off(flag_off):
    # Fail-closed: with the flag forced OFF a semantic selector is rejected at
    # validation (the flag defaults ON since v1.7, so this pins the OFF path).
    with pytest.raises(ValidationError) as ei:
        validate(_spec([{"of_feature": "Box", "face": "+z"}]))
    assert "semantic_edges" in str(ei.value)


def test_semantic_selector_accepted_by_default():
    # The flag ships default-ON (live-seat PAE green): a semantic selector
    # validates without any override.
    validate(_spec([{"of_feature": "Box", "face": "+z"}]))


def test_literal_only_spec_passes_with_flag_off(flag_off):
    # Existing literal specs must be untouched regardless of the flag.
    validate(_spec([{"x": 10.0, "y": 0.0, "z": 10.0}]))


def test_of_face_passes_when_flag_on(flag_on):
    validate(_spec([{"of_feature": "Box", "face": "+z"}]))


def test_between_faces_passes_when_flag_on(flag_on):
    validate(_spec([{"of_feature": "Box", "between_faces": ["+z", "+x"]}]))


# --- Reference layer: nested of_feature topological check ------------------


def test_of_feature_must_be_earlier_feature(flag_on):
    with pytest.raises(ValidationError) as ei:
        validate(_spec([{"of_feature": "Nonexistent", "face": "+z"}]))
    assert "not an earlier feature" in str(ei.value)
    assert "edges/0/of_feature" in ei.value.path


def test_of_feature_must_be_fixed_extent_boss(flag_on, monkeypatch):
    # Point of_feature at the sketch (not a boss extrude). _face_frame can only
    # resolve faces of fixed-extent bosses, so this must be a clean
    # ValidationError, not a build-time AssertionError.
    spec = _spec([{"of_feature": "SK_Box", "face": "+z"}])
    with pytest.raises(ValidationError) as ei:
        validate(spec)
    assert "fixed-extent boss extrude" in str(ei.value)


def test_between_faces_antiparallel_rejected(flag_on):
    with pytest.raises(ValidationError) as ei:
        validate(_spec([{"of_feature": "Box", "between_faces": ["+z", "-z"]}]))
    assert "never share an edge" in str(ei.value)
    assert "between_faces" in ei.value.path
