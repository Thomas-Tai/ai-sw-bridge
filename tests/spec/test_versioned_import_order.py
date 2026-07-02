"""Guard: importing builder populates the @versioned FeatureCut4 registry.

The extrude relocation (Phase 3 Move 6) risks the version-resolver registry
not being populated if handlers/extrude.py isn't imported before dispatch.
This test fails loudly if either the 2024 or 2025 variant fails to resolve.
COM-clean: import + registry lookup only; no seat, no dispatch.
"""

from __future__ import annotations


def test_featurecut4_versioned_variants_resolve_after_builder_import() -> None:
    import ai_sw_bridge.spec.builder  # noqa: F401  -- triggers handler import + registration
    from ai_sw_bridge.spec._version_resolver import SW_2025_MAJOR, resolve_op

    # running_major=None -> default (2024) variant; =33 -> the 2025 variant.
    assert resolve_op("FeatureCut4", running_major=None) is not None
    assert resolve_op("FeatureCut4", running_major=SW_2025_MAJOR) is not None
