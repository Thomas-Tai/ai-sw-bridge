"""Offline tests — ``patterns`` handler (W21 pattern family, Recipe-C relocation).

The three pattern handlers (linear/circular/mirror) were relocated from
``mutate.py`` into the HANDLER_REGISTRY by Recipe-C (the first 1.0.0
strangler-fig cut). These tests pin:
  - importability and callability of the three public handler functions
  - registry presence and correct mapping
  - SPIKE_STATUS sentinel
  - the two relocated helpers (``materialized`` / ``find_feature_by_name``)
  - early-validation fail-close on bad params (no live COM needed)
  - disjointness invariant: registry ∩ _SUPPORTED_FEATURE_TYPES == ∅
"""

from __future__ import annotations

import types

import ai_sw_bridge.features as features
import ai_sw_bridge.mutate as mutate
from ai_sw_bridge.features.patterns import (
    create_circular_pattern,
    create_linear_pattern,
    create_mirror_feature,
    SPIKE_STATUS,
)
from ai_sw_bridge.features.verify import find_feature_by_name, materialized


# ---------------------------------------------------------------------------
# 1. Importability and callability
# ---------------------------------------------------------------------------


class TestImportability:
    def test_create_linear_pattern_is_callable(self):
        assert callable(create_linear_pattern)

    def test_create_circular_pattern_is_callable(self):
        assert callable(create_circular_pattern)

    def test_create_mirror_feature_is_callable(self):
        assert callable(create_mirror_feature)

    def test_spike_status_is_green(self):
        assert SPIKE_STATUS == "GREEN"


# ---------------------------------------------------------------------------
# 2. Registry presence and correct mapping
# ---------------------------------------------------------------------------


class TestRegistryPresence:
    def test_linear_pattern_in_registry(self):
        assert "linear_pattern" in features.HANDLER_REGISTRY

    def test_circular_pattern_in_registry(self):
        assert "circular_pattern" in features.HANDLER_REGISTRY

    def test_mirror_feature_in_registry(self):
        assert "mirror_feature" in features.HANDLER_REGISTRY

    def test_linear_pattern_maps_to_correct_handler(self):
        assert features.HANDLER_REGISTRY["linear_pattern"] is create_linear_pattern

    def test_circular_pattern_maps_to_correct_handler(self):
        assert features.HANDLER_REGISTRY["circular_pattern"] is create_circular_pattern

    def test_mirror_feature_maps_to_correct_handler(self):
        assert features.HANDLER_REGISTRY["mirror_feature"] is create_mirror_feature


# ---------------------------------------------------------------------------
# 3. Relocated helpers: materialized / find_feature_by_name
# ---------------------------------------------------------------------------


class TestMaterialized:
    def test_none_is_not_materialized(self):
        assert materialized(None) is False

    def test_zero_int_is_not_materialized(self):
        assert materialized(0) is False

    def test_nonzero_int_is_not_materialized(self):
        # CreateFeature returns int error codes on failure — all ints are "not materialized"
        assert materialized(1) is False
        assert materialized(-1) is False

    def test_plain_object_is_materialized(self):
        assert materialized(object()) is True

    def test_string_is_materialized(self):
        # Non-None, non-int → materialized
        assert materialized("feature_handle") is True

    def test_false_bool_is_int_subclass_so_not_materialized(self):
        # bool is a subclass of int, so False (== 0) is not materialized
        assert materialized(False) is False

    def test_true_bool_is_int_subclass_so_not_materialized(self):
        # True (== 1) is an int subclass — NOT materialized
        assert materialized(True) is False


class TestFindFeatureByName:
    def _make_fake_feature(self, name: str) -> object:
        """Fake IFeature with a plain .Name string attribute."""
        f = types.SimpleNamespace()
        f.Name = name
        return f

    def _make_fake_feature_callable_name(self, name: str) -> object:
        """Fake IFeature where .Name is a callable (late-bound dispatch style)."""
        f = types.SimpleNamespace()
        f.Name = lambda: name
        return f

    def _make_fake_doc(self, features_list):
        """Minimal fake doc whose FeatureManager.GetFeatures(True) returns the list."""

        class FakeFM:
            def __init__(self, feats):
                self._feats = feats

            def GetFeatures(self, topology):
                return self._feats

        doc = types.SimpleNamespace()
        doc.FeatureManager = FakeFM(features_list)
        return doc

    def test_finds_matching_feature_by_name(self):
        f1 = self._make_fake_feature("Boss-Extrude1")
        f2 = self._make_fake_feature("Cut-Extrude1")
        doc = self._make_fake_doc([f1, f2])
        result = find_feature_by_name(doc, "Cut-Extrude1")
        assert result is f2

    def test_returns_none_when_not_found(self):
        f1 = self._make_fake_feature("Boss-Extrude1")
        doc = self._make_fake_doc([f1])
        result = find_feature_by_name(doc, "NoSuchFeature")
        assert result is None

    def test_returns_none_on_empty_feature_list(self):
        doc = self._make_fake_doc([])
        result = find_feature_by_name(doc, "Boss-Extrude1")
        assert result is None

    def test_returns_none_when_getfeatures_returns_none(self):
        doc = self._make_fake_doc(None)
        result = find_feature_by_name(doc, "Boss-Extrude1")
        assert result is None

    def test_handles_callable_name_property(self):
        """Late-bound COM proxies may return .Name as a callable."""
        f1 = self._make_fake_feature_callable_name("Fillet1")
        doc = self._make_fake_doc([f1])
        result = find_feature_by_name(doc, "Fillet1")
        assert result is f1

    def test_skips_feature_that_raises_on_name_access(self):
        """A feature that raises on .Name access is skipped (no crash)."""

        class BrokenFeature:
            @property
            def Name(self):
                raise RuntimeError("COM error")

        f_broken = BrokenFeature()
        f_good = self._make_fake_feature("LPattern1")
        doc = self._make_fake_doc([f_broken, f_good])
        result = find_feature_by_name(doc, "LPattern1")
        assert result is f_good

    def test_returns_first_matching_feature(self):
        """When names collide, the first match wins (tree order)."""
        f1 = self._make_fake_feature("Mirror1")
        f2 = self._make_fake_feature("Mirror1")
        doc = self._make_fake_doc([f1, f2])
        result = find_feature_by_name(doc, "Mirror1")
        assert result is f1


# ---------------------------------------------------------------------------
# 4. Early-validation fail-close (no COM touch — bare object() doc is fine)
# ---------------------------------------------------------------------------


class TestLinearPatternValidation:
    def test_missing_seed_returns_false(self):
        ok, err = create_linear_pattern(object(), {}, {})
        assert ok is False
        assert err is not None and len(err) > 0

    def test_missing_direction_returns_false(self):
        ok, err = create_linear_pattern(
            object(), {"spacing_mm": 10, "count": 2}, {"seed": "Boss1"}
        )
        assert ok is False
        assert err is not None

    def test_missing_spacing_mm_returns_false(self):
        ok, err = create_linear_pattern(
            object(),
            {"count": 2},
            {"seed": "Boss1", "direction": {"x": 1, "y": 0, "z": 0}},
        )
        assert ok is False
        assert err is not None

    def test_count_less_than_2_returns_false(self):
        ok, err = create_linear_pattern(
            object(),
            {"spacing_mm": 10, "count": 1},
            {"seed": "Boss1", "direction": {"x": 1, "y": 0, "z": 0}},
        )
        assert ok is False
        assert err is not None

    def test_non_dict_feature_returns_false(self):
        ok, err = create_linear_pattern(object(), None, {"seed": "Boss1"})
        assert ok is False


class TestCircularPatternValidation:
    def test_missing_seed_returns_false(self):
        ok, err = create_circular_pattern(object(), {}, {})
        assert ok is False
        assert err is not None

    def test_missing_axis_returns_false(self):
        ok, err = create_circular_pattern(object(), {"count": 3}, {"seed": "Boss1"})
        assert ok is False
        assert err is not None

    def test_count_less_than_2_returns_false(self):
        ok, err = create_circular_pattern(
            object(), {"count": 1}, {"seed": "Boss1", "axis": "Axis1"}
        )
        assert ok is False
        assert err is not None

    def test_non_dict_feature_returns_false(self):
        ok, err = create_circular_pattern(
            object(), None, {"seed": "Boss1", "axis": "Axis1"}
        )
        assert ok is False


class TestMirrorFeatureValidation:
    def test_missing_seed_returns_false(self):
        ok, err = create_mirror_feature(object(), {}, {})
        assert ok is False
        assert err is not None

    def test_missing_plane_returns_false(self):
        ok, err = create_mirror_feature(object(), {}, {"seed": "Boss1"})
        assert ok is False
        assert err is not None

    def test_non_dict_target_returns_false(self):
        ok, err = create_mirror_feature(object(), {}, None)
        assert ok is False


# ---------------------------------------------------------------------------
# 5. Disjointness invariant
# ---------------------------------------------------------------------------


class TestDisjointnessInvariant:
    def test_registry_and_supported_types_are_disjoint(self):
        """The three pattern kinds must have moved OUT of _SUPPORTED_FEATURE_TYPES
        now that they live in the registry — a collision would shadow the registry
        entry silently (test_feature_registry.py already asserts this globally;
        this local test pins the specific kinds)."""
        overlap = set(features.HANDLER_REGISTRY) & set(mutate._SUPPORTED_FEATURE_TYPES)
        assert overlap == set(), f"keys collide: {overlap}"

    def test_linear_pattern_not_in_supported_types(self):
        assert "linear_pattern" not in mutate._SUPPORTED_FEATURE_TYPES

    def test_circular_pattern_not_in_supported_types(self):
        assert "circular_pattern" not in mutate._SUPPORTED_FEATURE_TYPES

    def test_mirror_feature_not_in_supported_types(self):
        assert "mirror_feature" not in mutate._SUPPORTED_FEATURE_TYPES
