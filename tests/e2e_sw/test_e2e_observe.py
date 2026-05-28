"""End-to-end observe.* tests against a live SW session.

Each ``observe.sw_*`` function is called via its MCP tool wrapper
against whatever part is currently active. The tests are written to
tolerate any active document state — they assert on shape and value
ranges rather than specific values. Tests that REQUIRE a specific
document state (e.g., an assembly for sw_mate_errors) build that
state themselves.

Run with::

    pytest -m solidworks_only tests/e2e_sw/test_e2e_observe.py -v
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.solidworks_only


def _ensure_part(live_tools, minimal_cylinder_spec_path) -> None:
    """Build the minimal_cylinder if no part is active.

    Idempotent — if sw_active_doc reports a Part already, this is a no-op.
    """
    active = live_tools["sw_active_doc"].fn()
    if active.get("ok") and active.get("type") == "Part":
        return
    live_tools["sw_build"].fn(spec_path=str(minimal_cylinder_spec_path), mode="no_dim")


def test_e2e_active_doc_reports_part(live_tools, minimal_cylinder_spec_path) -> None:
    _ensure_part(live_tools, minimal_cylinder_spec_path)
    result = live_tools["sw_active_doc"].fn()
    assert result["ok"] is True
    assert result["type"] == "Part"
    assert isinstance(result["title"], str) and result["title"]
    assert isinstance(result["type_id"], int) and result["type_id"] == 1


def test_e2e_bbox_returns_geometry(live_tools, minimal_cylinder_spec_path) -> None:
    _ensure_part(live_tools, minimal_cylinder_spec_path)
    result = live_tools["sw_bbox"].fn()
    assert result["ok"] is True
    # Minimal cylinder is 25mm diameter, 80mm tall. Span tolerances are
    # generous because the active doc might be a different part.
    assert isinstance(result["x_span_mm"], float)
    assert result["x_span_mm"] > 0
    assert isinstance(result["z_span_mm"], float)
    assert result["z_span_mm"] > 0


def test_e2e_volume_returns_mass_properties(
    live_tools, minimal_cylinder_spec_path
) -> None:
    _ensure_part(live_tools, minimal_cylinder_spec_path)
    result = live_tools["sw_volume"].fn()
    assert result["ok"] is True
    # SW's GetMassProperties returns volume in m^3 from the Mass
    # Properties API; observe converts to a documented unit. We don't
    # pin specific values (material density is configurable in SW),
    # only the field set and their types.
    for key in ("volume_mm3", "surface_area_mm2"):
        assert key in result, f"sw_volume payload missing {key}"
        assert isinstance(
            result[key], (int, float)
        ), f"{key} should be numeric, got {type(result[key]).__name__}"


def test_e2e_enabled_addins_returns_list(live_tools) -> None:
    """sw_enabled_addins works on any SW state (no active doc required)."""
    result = live_tools["sw_enabled_addins"].fn()
    assert result["ok"] is True
    assert isinstance(result["addins"], list)
    assert isinstance(result["known_problematic"], list)
    # Every entry in addins should be a dict with name + enabled fields
    # (or whatever the contract is — verified once against live SW).
    for addin in result["addins"]:
        assert isinstance(addin, dict)


def test_e2e_feature_errors_walks_tree(live_tools, minimal_cylinder_spec_path) -> None:
    _ensure_part(live_tools, minimal_cylinder_spec_path)
    result = live_tools["sw_feature_errors"].fn()
    assert result["ok"] is True
    # observe.sw_get_feature_errors emits ``total_features`` (the full
    # feature-tree row count, including origin planes) plus a list
    # in ``features`` of any non-OK rows.
    assert result.get("total_features", 0) > 0


def test_e2e_custom_props_returns_dict(live_tools, minimal_cylinder_spec_path) -> None:
    _ensure_part(live_tools, minimal_cylinder_spec_path)
    result = live_tools["sw_custom_props"].fn()
    # observe.sw_get_custom_props emits ``properties`` (dict of name ->
    # value) and ``count`` (its length). New parts have no props; the
    # contract is that the shape is well-formed regardless.
    assert result["ok"] is True
    assert "properties" in result
    assert isinstance(result["properties"], dict)
    assert result.get("count") == len(result["properties"])
