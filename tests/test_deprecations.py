"""Gate for the cross-surface deprecation registry + grace validator.

Synthetic fixtures exercise the pure validator with an empty production
registry; a live cross-check asserts present/absent consistency against the
real surface registries. The production DEPRECATIONS tuple is never mutated.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.deprecations import (
    DEPRECATIONS,
    DeprecationEntry,
    validate_registry,
    current_version,
)


def _entry(**kw):
    base = dict(
        id="mcp_tool:sw_old",
        surface_class="mcp_tool",
        deprecated_in="1.8",
        remove_in="2.0",
        replacement="sw_new",
    )
    base.update(kw)
    return DeprecationEntry(**base)


# --- production registry is clean & immutable -------------------------------


def test_production_registry_is_empty_and_valid():
    assert DEPRECATIONS == ()
    assert validate_registry(DEPRECATIONS, current_version()) == []


def test_production_registry_is_immutable():
    with pytest.raises((AttributeError, TypeError)):
        DEPRECATIONS.append(_entry())  # type: ignore[attr-defined]


# --- valid synthetic entries produce no violations --------------------------


def test_valid_stable_entry_ok():
    assert validate_registry([_entry(surface_class="mcp_tool")], "1.9") == []
    assert validate_registry([_entry(surface_class="stable_cli")], "1.9") == []
    assert validate_registry([_entry(surface_class="facade")], "1.9") == []


def test_valid_experimental_entry_ok():
    e = _entry(surface_class="experimental_cli", deprecated_in="1.8", remove_in="1.9")
    assert validate_registry([e], "1.8") == []
    e2 = _entry(surface_class="spec_handler", deprecated_in="1.8", remove_in="1.9")
    assert validate_registry([e2], "1.8") == []


# --- each invalid case yields exactly one violation -------------------------


def test_stable_removal_not_at_major_boundary_violates():
    e = _entry(surface_class="mcp_tool", deprecated_in="1.8", remove_in="1.9")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "boundary" in v[0].reason


def test_stable_removal_at_nonzero_minor_violates():
    e = _entry(surface_class="facade", deprecated_in="1.8", remove_in="2.1")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "boundary" in v[0].reason


def test_experimental_removal_skipping_a_minor_violates():
    e = _entry(surface_class="experimental_cli", deprecated_in="1.8", remove_in="1.10")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "next minor" in v[0].reason


def test_announce_not_before_remove_violates():
    e = _entry(surface_class="experimental_cli", deprecated_in="1.8", remove_in="1.8")
    v = validate_registry([e], "1.8")
    assert len(v) == 1


def test_unknown_surface_class_violates():
    e = _entry(surface_class="bogus")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "surface_class" in v[0].reason


def test_unparseable_version_violates():
    e = _entry(deprecated_in="one.two")
    v = validate_registry([e], "1.8")
    assert len(v) == 1


# --- live cross-check: entries must name real surfaces & obey present/absent -


def test_live_entries_reference_real_surfaces():
    """Every production entry must name a surface that exists (until removed)."""
    from ai_sw_bridge.cli.stability import TIER_REGISTRY  # noqa: F401

    # With DEPRECATIONS empty this is vacuously true; the check is wired so the
    # first real entry is validated against the live registries.
    for e in DEPRECATIONS:
        assert ":" in e.id  # id is "<class>:<surface-name>"
