# tests/test_preflight_hints.py
from ai_sw_bridge.errors.hints import HINT_CATALOG, resolve_hint


def test_empty_air_cut_hint_exists():
    assert "empty_air_cut" in HINT_CATALOG
    h = HINT_CATALOG["empty_air_cut"]
    assert (
        "coordinate_conventions.md" in h.remedy or "coordinate_conventions" in h.ref_doc
    )


def test_empty_air_cut_resolves_by_feature_type():
    h = resolve_hint(None, "IFeatureManager.FeatureCut4", "empty_air_cut")
    assert h is not None and h.key == "empty_air_cut"
