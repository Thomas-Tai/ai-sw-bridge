"""Tests for the hint catalog (spec.md §3.4)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.errors.hints import (
    HINT_CATALOG,
    Hint,
    default_hint,
    resolve_hint,
)


REQUIRED_KEYS = [
    "face_no_longer_exists",
    "sketch_under_constrained",
    "end_condition_mismatch",
    "plane_not_found",
    "unconsumed_sketch",
    "addim_popup_blocking",
    "feature_cut_arg_count_mismatch",
    "negative_offset_clash",
    "parametric_value_out_of_range",
]

# Sketch contour validity entries added in v0.12.2 (audit §6.4).
SKETCH_VALIDITY_KEYS = [
    "sketch_self_intersect",
    "sketch_open_contour_needed_closed",
    "sketch_construction_only",
    "sketch_tangent_dim_conflict",
]


def test_catalog_has_thirteen_required_entries() -> None:
    for key in REQUIRED_KEYS + SKETCH_VALIDITY_KEYS:
        assert key in HINT_CATALOG, f"missing catalog entry: {key}"
    # 9 from E1.3 + 4 sketch validity entries from audit §6.4
    assert len(HINT_CATALOG) == 13


@pytest.mark.parametrize("key", REQUIRED_KEYS + SKETCH_VALIDITY_KEYS)
def test_each_hint_has_non_empty_fields(key: str) -> None:
    hint = HINT_CATALOG[key]
    assert isinstance(hint, Hint)
    assert hint.key == key
    assert hint.summary.strip(), f"{key} has empty summary"
    assert hint.remedy.strip(), f"{key} has empty remedy"
    assert hint.ref_doc.strip(), f"{key} has empty ref_doc"


@pytest.mark.parametrize(
    "iface_method,feature_type,expected_key",
    [
        (
            "IFeatureManager.FeatureExtrusion2",
            "sketch_self_intersect",
            "sketch_self_intersect",
        ),
        (
            "IFeatureManager.FeatureCut4",
            "sketch_self_intersect",
            "sketch_self_intersect",
        ),
        (
            "IFeatureManager.FeatureExtrusion2",
            "sketch_open_contour_needed_closed",
            "sketch_open_contour_needed_closed",
        ),
        (
            "IFeatureManager.FeatureCut4",
            "sketch_open_contour_needed_closed",
            "sketch_open_contour_needed_closed",
        ),
        (
            "IFeatureManager.FeatureExtrusion2",
            "sketch_construction_only",
            "sketch_construction_only",
        ),
        (
            "ISketchManager.AddRelation",
            "sketch_tangent_dim_conflict",
            "sketch_tangent_dim_conflict",
        ),
    ],
)
def test_sketch_validity_hints_resolve(
    iface_method: str, feature_type: str, expected_key: str
) -> None:
    hint = resolve_hint(
        hresult=None,
        iface_method=iface_method,
        feature_type=feature_type,
    )
    assert hint is not None, f"hint not found for {iface_method}/{feature_type}"
    assert hint.key == expected_key


def test_hint_is_frozen() -> None:
    hint = HINT_CATALOG["face_no_longer_exists"]
    with pytest.raises(AttributeError):
        hint.remedy = "changed"  # type: ignore[misc]


def test_resolve_hint_by_hresult_match() -> None:
    hint = resolve_hint(
        hresult="0x80004005",
        iface_method="IFeatureManager.FeatureExtrusion2",
    )
    assert hint is not None
    assert hint.key == "face_no_longer_exists"


def test_resolve_hint_hresult_normalization() -> None:
    # lowercase hex still matches
    hint = resolve_hint(
        hresult="0x80004005",
        iface_method="IFeatureManager.FeatureExtrusion2",
    )
    assert hint is not None
    # uppercase prefix
    hint2 = resolve_hint(
        hresult="0X80004005",
        iface_method="IFeatureManager.FeatureExtrusion2",
    )
    assert hint2 is not None
    assert hint2.key == hint.key


def test_resolve_hint_by_feature_type_fallback() -> None:
    hint = resolve_hint(
        hresult=None,
        iface_method="IFeatureManager.FeatureExtrusion2",
        feature_type="boss_extrude_blind",
    )
    assert hint is not None
    assert hint.key == "end_condition_mismatch"


def test_resolve_hint_returns_none_on_unknown_hresult() -> None:
    hint = resolve_hint(
        hresult="0xDEADBEEF",
        iface_method="IFeatureManager.FeatureExtrusion2",
    )
    assert hint is None  # no hallucination


def test_resolve_hint_returns_none_on_completely_unknown_combo() -> None:
    hint = resolve_hint(
        hresult=None,
        iface_method="IUnknown.Method",
        feature_type="unknown_type",
    )
    assert hint is None


def test_resolve_hint_hresult_takes_precedence_over_feature() -> None:
    # Both could match; HRESULT is the primary key per spec §3.4
    hint = resolve_hint(
        hresult="0x80004005",
        iface_method="IFeatureManager.FeatureExtrusion2",
        feature_type="boss_extrude_blind",
    )
    assert hint is not None
    assert hint.key == "face_no_longer_exists"


def test_every_hresult_mapped_entry_is_reachable() -> None:
    # Each registered HRESULT entry must produce its catalog hint
    from ai_sw_bridge.errors.hints import _IFACE_HRESULT_MAP

    for (iface, hresult), expected_key in _IFACE_HRESULT_MAP.items():
        hint = resolve_hint(hresult=hresult, iface_method=iface)
        assert hint is not None, f"unreachable HRESULT entry: ({iface}, {hresult})"
        assert hint.key == expected_key


def test_every_feature_mapped_entry_is_reachable() -> None:
    from ai_sw_bridge.errors.hints import _IFACE_FEATURE_MAP

    for (iface, ftype), expected_key in _IFACE_FEATURE_MAP.items():
        hint = resolve_hint(hresult=None, iface_method=iface, feature_type=ftype)
        assert hint is not None, f"unreachable feature entry: ({iface}, {ftype})"
        assert hint.key == expected_key


def test_default_hint_is_distinct_and_well_formed() -> None:
    d = default_hint()
    assert isinstance(d, Hint)
    assert d.key == "unknown_failure"
    assert d.summary
    assert d.remedy
    assert d.ref_doc
    # default hint is NOT in the catalog (it's a sentinel)
    assert d.key not in HINT_CATALOG
