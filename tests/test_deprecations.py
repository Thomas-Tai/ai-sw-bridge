"""Gate for the cross-surface deprecation registry + grace validator.

Synthetic fixtures exercise the pure validator with an empty production
registry. A structural guard checks that any production entry's id is
well-formed (``<surface_class>:<name>``); the live-membership cross-check —
asserting ``<name>`` exists in the real CLI/MCP/facade registries — wires in
with the first real entry (deferred, like the MCP deprecation plumbing, since
there is nothing to check against at v1.7.0). The production DEPRECATIONS tuple
is never mutated.
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


def test_stable_removal_skipping_a_major_violates():
    # deprecated in 1.8 -> the only legal removal is 2.0; 3.0 skips the boundary.
    e = _entry(surface_class="facade", deprecated_in="1.8", remove_in="3.0")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "boundary" in v[0].reason


def test_patch_suffix_is_ignored_in_parsing():
    # "1.8.2" -> (1, 8) and "2.0.0" -> (2, 0): a stable entry carrying patch
    # suffixes must still validate cleanly (the patch component is ignored).
    e = _entry(surface_class="facade", deprecated_in="1.8.2", remove_in="2.0.0")
    assert validate_registry([e], "1.9") == []


# --- structural guard on production entries (live-membership check deferred) -


def test_production_entries_have_wellformed_ids():
    """Every production entry id is '<surface_class>:<name>' with the prefix
    matching surface_class and a non-empty name.

    Structural guard today (registry is empty). The live-membership cross-check
    — asserting <name> exists in the real CLI/MCP/facade registries — wires in
    with the first real entry.
    """
    known = {
        "stable_cli",
        "mcp_tool",
        "facade",
        "experimental_cli",
        "spec_handler",
    }
    for e in DEPRECATIONS:
        prefix, sep, name = e.id.partition(":")
        assert sep == ":", f"{e.id!r}: id must be '<surface_class>:<name>'"
        assert prefix == e.surface_class, (
            f"{e.id!r}: id prefix {prefix!r} must match surface_class "
            f"{e.surface_class!r}"
        )
        assert e.surface_class in known, f"{e.id!r}: unknown surface_class"
        assert name, f"{e.id!r}: empty surface name"
