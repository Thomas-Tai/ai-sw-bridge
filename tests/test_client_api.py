"""Offline tests for the v0.18 class-based API boundary (SolidWorksClient).

Pins the Strangler-slice contract without a SW seat:
  - the legacy ``sw_*`` free functions emit ``PendingDeprecationWarning`` and
    still return identical data (delegating to the ``_impl`` core);
  - the new ``SolidWorksClient`` facades route to the SAME core WITHOUT any
    deprecation warning (internal tools bypass the shims);
  - the client taxonomy (domain facades, cached, lazy connection state).

COM is never touched: a bare ``object()`` has no ``.Extension`` (drives the
inertia typed-error path) and a fake part-doc drives the stackup assembly-guard,
so both ``_impl`` cores return their typed error dicts immediately.

Batch O1 additions: interference, draft_analysis, section_props, selection,
bbox_from_doc, assembly_bbox — same pattern as the pilot slice.

Batch O2 additions: the 13 active-doc verbs from observe.py —
active_doc, feature_errors, equations, bbox, volume, feature_statistics,
screenshot, mate_errors, custom_props, measure, undercut_faces,
min_wall_thickness, enabled_addins.  All self-resolve the active doc, so
we monkeypatch observe.get_sw_app / observe.get_active_doc to return None,
driving the no_active_doc typed-error path without any COM touch.
"""

from __future__ import annotations

import warnings
from unittest.mock import patch


import ai_sw_bridge.observe as _observe_mod

from ai_sw_bridge.client import (
    SolidWorksClient,
    SolidWorksMutatorFacade,
    SolidWorksObserverFacade,
    UrdfFacade,
)
from ai_sw_bridge.mutate import ProposalStore


class _PartDoc:
    """Fake non-assembly doc: drives the stackup assembly-guard error path."""

    def GetType(self):
        return 1  # swDocPART


class _AsmDoc:
    """Fake assembly doc (GetType=2): drives non-part error paths."""

    def GetType(self):
        return 2  # swDocASSEMBLY


# ── Deprecation shims: warn + delegate to identical data ────────────────────


# ── Client facades route to the core WITHOUT a deprecation warning ──────────


def test_client_facade_inertia_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.get_inertia(doc=object())
    assert res["ok"] is False  # reached _impl (no .Extension), no warning raised


def test_client_facade_stackup_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.analyze_stackup(["a-1", "b-1"], doc=_PartDoc())
    assert res["ok"] is False and "assembly" in res["error"]


# ── Taxonomy: domain facades on one stateful client, cached, lazy ───────────


def test_client_taxonomy_and_caching():
    client = SolidWorksClient(app=object(), mod=object())
    assert isinstance(client.observe, SolidWorksObserverFacade)
    assert isinstance(client.urdf, UrdfFacade)
    # facades are cached — the same instance across reads (shared client context)
    assert client.observe is client.observe
    assert client.urdf is client.urdf


def test_client_facade_no_active_doc_guard():
    client = SolidWorksClient(app=object(), mod=object())
    client.active_doc = lambda: None  # type: ignore[method-assign]
    assert client.observe.get_inertia()["error"] == "no_active_doc"
    assert client.observe.analyze_stackup(["a-1", "b-1"])["error"] == "no_active_doc"


def test_client_connection_state_lazy_and_injectable():
    # Injected app/mod are used verbatim; no COM acquisition on construction.
    sentinel_app, sentinel_mod = object(), object()
    client = SolidWorksClient(app=sentinel_app, mod=sentinel_mod)
    assert client.app is sentinel_app
    assert client.mod is sentinel_mod


# ── Batch O1: interference, draft_analysis, section_props, selection, ──────
#              bbox_from_doc, assembly_bbox — shim warns + delegates;
#              facade routes without warning.
# ────────────────────────────────────────────────────────────────────────────

# sw_get_interference — non-assembly doc drives the type-guard error path


def test_client_facade_interference_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.interference(doc=_PartDoc())
    assert res["ok"] is False  # type-guard fires, not a warning


# sw_get_draft_analysis — assembly doc drives the non-part type-guard error path


def test_client_facade_draft_analysis_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.draft_analysis("top", doc=_AsmDoc())
    assert res["ok"] is False  # type-guard fires, not a warning


# sw_get_section_props — bare object() has no .Extension → typed error path


def test_client_facade_section_props_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.section_props(doc=object())
    assert res["ok"] is False  # no .Extension on object(), no warning raised


# sw_get_selection — bare object() fails typed(IModelDoc2) → errors → ok=False


def test_client_facade_selection_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.selection(doc=object())
    assert res["ok"] is False  # typed() fails on object(), no warning raised


# sw_get_bbox_from_doc — assembly doc drives the non-part type-guard error path


def test_client_facade_bbox_from_doc_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.bbox_from_doc(doc=_AsmDoc())
    assert res["ok"] is False  # type-guard fires, not a warning


# sw_get_assembly_bbox_from_doc — part doc drives the non-assembly type-guard


def test_client_facade_assembly_bbox_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.assembly_bbox(doc=_PartDoc())
    assert res["ok"] is False  # type-guard fires, not a warning


# ── Batch O2: active-doc verbs from observe.py ──────────────────────────────
#
# All 13 self-resolve the active doc via get_sw_app / get_active_doc internally.
# We monkeypatch both to drive the no_active_doc typed-error path without COM.
# _sw_get_enabled_addins_impl is the exception: it calls get_sw_app() and then
# uses getattr(sw, "GetEnabledAddIns", None); returning object() → api_not_present.
#
# Pattern per function:
#   shim_warns:  call sw_*() under the same patches, assert warns + impl == shim
#   facade_clean: call client.observe.<method>() under warnings-as-errors, no raise
# ─────────────────────────────────────────────────────────────────────────────

_FAKE_SW = object()  # a sw app object that has no COM members


def _no_doc_patches():
    """Context manager that patches observe.get_sw_app / get_active_doc to simulate
    no active document, driving the no_active_doc typed-error path."""
    return (
        patch.object(_observe_mod, "get_sw_app", return_value=_FAKE_SW),
        patch.object(_observe_mod, "get_active_doc", return_value=None),
    )


# sw_get_active_doc / active_doc


def test_client_facade_active_doc_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.active_doc()
    assert res["ok"] is True  # no_active_doc returns ok=True with error set


# sw_get_feature_errors / feature_errors


def test_client_facade_feature_errors_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.feature_errors()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_equations / equations


def test_client_facade_equations_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.equations()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_bbox / bbox (no-arg legacy form)


def test_client_facade_bbox_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.bbox()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_volume / volume


def test_client_facade_volume_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.volume()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_feature_statistics / feature_statistics


def test_client_facade_feature_statistics_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.feature_statistics()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_screenshot / screenshot


def test_client_facade_screenshot_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.screenshot(width=320, height=240)
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_mate_errors / mate_errors


def test_client_facade_mate_errors_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.mate_errors()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_custom_props / custom_props


def test_client_facade_custom_props_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.custom_props()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_measure / measure


def test_client_facade_measure_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.measure()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_undercut_faces / undercut_faces


def test_client_facade_undercut_faces_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.undercut_faces(pull_x=0.0, pull_y=1.0, pull_z=0.0)
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_min_wall_thickness / min_wall_thickness


def test_client_facade_min_wall_thickness_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.min_wall_thickness(samples_per_face=2)
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_enabled_addins / enabled_addins
# enabled_addins calls get_sw_app() directly (no get_active_doc); returning
# object() (no GetEnabledAddIns attr) → ok=True, error="api_not_present".


def test_client_facade_enabled_addins_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with patch.object(_observe_mod, "get_sw_app", return_value=object()):
            res = client.observe.enabled_addins()
    assert res["ok"] is True and res["error"] == "api_not_present"


# ── Batch O3: observe_measure + observe_clearance verbs ─────────────────────
#
# sw_get_measure_from_doc, sw_get_measure_durable_pair,
# sw_get_measure_angle_from_doc, sw_get_measure_area_from_doc,
# sw_get_clearance, sw_get_face_clearance — shim warns + delegates;
# facade routes without warning.
# ─────────────────────────────────────────────────────────────────────────────

# sw_get_measure_from_doc / measure_selection — bare object() has no SelectionManager


def test_client_facade_measure_selection_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.measure_selection(doc=object())
    assert res["ok"] is False


# sw_get_measure_durable_pair / measure_durable_pair — bare object() fails in durable-ref resolution


def test_client_facade_measure_durable_pair_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.measure_durable_pair("ref_a", "ref_b", doc=object())
    assert res["ok"] is False


# sw_get_measure_angle_from_doc / measure_angle — bare object() has no SelectionManager


def test_client_facade_measure_angle_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.measure_angle(doc=object())
    assert res["ok"] is False


# sw_get_measure_area_from_doc / measure_area — bare object() has no SelectionManager


def test_client_facade_measure_area_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.measure_area(doc=object())
    assert res["ok"] is False


# sw_get_clearance / clearance — bare object() has no GetType → typed error


def test_client_facade_clearance_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.clearance("a", "b", doc=object())
    assert res["ok"] is False


# sw_get_face_clearance / face_clearance — bare object() fails typed(IModelDoc2)


def test_client_facade_face_clearance_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.face_clearance("Face<1>", "Face<2>", doc=object())
    assert res["ok"] is False


# ── Batch O3: no_active_doc guard for all 6 O3 facade methods ──────────────


def test_client_facade_o3_no_active_doc_guard():
    client = SolidWorksClient(app=object(), mod=object())
    client.active_doc = lambda: None  # type: ignore[method-assign]
    assert client.observe.measure_selection()["error"] == "no_active_doc"
    assert client.observe.measure_durable_pair("a", "b")["error"] == "no_active_doc"
    assert client.observe.measure_angle()["error"] == "no_active_doc"
    assert client.observe.measure_area()["error"] == "no_active_doc"
    assert client.observe.clearance("a", "b")["error"] == "no_active_doc"
    assert client.observe.face_clearance("a", "b")["error"] == "no_active_doc"


# ── Batch M1: mutate Local + Feature transaction triads ────────────────────
#
# sw_propose_local_change, sw_dry_run, sw_commit, sw_undo_last_commit,
# sw_propose_feature_add, sw_dry_run_feature_add, sw_commit_feature_add —
# shim warns + delegates; facade routes without warning; ProposalStore
# (v0.14 legacy facade) does not leak deprecation warnings.
# ─────────────────────────────────────────────────────────────────────────────

# sw_propose_local_change — the _impl resolves active doc internally, returns error dict


def test_client_facade_propose_local_change_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.propose_local_change("x", "1")
    assert res["ok"] is False


# sw_dry_run — _impl loads proposal from disk (nonexistent id -> error)


def test_client_facade_dry_run_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.dry_run("nonexistent_id")
    assert res["ok"] is False
    assert "not found" in res["error"]


# sw_commit — _impl loads proposal from disk (nonexistent id -> error)


def test_client_facade_commit_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.commit("nonexistent_id")
    assert res["ok"] is False
    assert "not found" in res["error"]


# sw_undo_last_commit — _impl scans proposals dir (empty -> error)


def test_client_facade_undo_last_commit_routes_without_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path / "proposals"))
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.undo_last_commit()
    assert res["ok"] is False
    assert "no committed proposal" in res["error"]


# sw_propose_feature_add — _impl validates offline (no doc_path -> error)


def test_client_facade_propose_feature_add_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.propose_feature_add(
            "/no/such.sldprt",
            {"type": "fillet_constant_radius", "radius_mm": 2},
            {"edges": [{"ref": {"persist_id": "AA"}, "radius_mm": 2}]},
        )
    assert res["ok"] is False


# sw_dry_run_feature_add — _impl loads proposal from disk (nonexistent id -> error)


def test_client_facade_dry_run_feature_add_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.dry_run_feature_add("nonexistent_id")
    assert res["ok"] is False
    assert "not found" in res["error"]


# sw_commit_feature_add — _impl loads proposal from disk (nonexistent id -> error)


def test_client_facade_commit_feature_add_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.commit_feature_add("nonexistent_id")
    assert res["ok"] is False
    assert "not found" in res["error"]


# ── Batch M1: ProposalStore (v0.14 legacy facade) must not leak warnings ────


def test_proposal_store_no_deprecation_warning(tmp_path, monkeypatch):
    """ProposalStore routes to _impl cores — no PendingDeprecationWarning."""
    monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path / "proposals"))
    store = ProposalStore()
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = store.propose("x", "1")
    assert res["ok"] is False

    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = store.dry_run("nonexistent_id")
    assert res["ok"] is False

    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = store.commit("nonexistent_id")
    assert res["ok"] is False

    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = store.undo_last()
    assert res["ok"] is False

    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = store.propose_feature_add(
            "/no/such.sldprt",
            {"type": "fillet_constant_radius", "radius_mm": 2},
            {"edges": [{"ref": {"persist_id": "AA"}, "radius_mm": 2}]},
        )
    assert res["ok"] is False

    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = store.dry_run_feature_add("nonexistent_id")
    assert res["ok"] is False

    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = store.commit_feature_add("nonexistent_id")
    assert res["ok"] is False


# ── Batch M1: facade is the right type and cached ────────────────────────────


def test_client_mutate_facade_type_and_cached():
    client = SolidWorksClient(app=object(), mod=object())
    assert isinstance(client.mutate, SolidWorksMutatorFacade)
    assert client.mutate is client.mutate  # cached


# ── Batch M2: assembly verbs ─────────────────────────────────────────────
#
# sw_propose_assembly, sw_dry_run_assembly, sw_commit_assembly,
# sw_edit_assembly — shim warns + delegates; facade routes without warning.
# ─────────────────────────────────────────────────────────────────────────────

# sw_propose_assembly — _impl validates offline (non-dict → error)


def test_client_facade_propose_assembly_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.propose_assembly("not a dict")  # type: ignore[arg-type]
    assert res["ok"] is False


# sw_dry_run_assembly — _impl loads proposal from disk (nonexistent id → error)


def test_client_facade_dry_run_assembly_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.dry_run_assembly("nonexistent_id")
    assert res["ok"] is False
    assert "not found" in res["error"]


# sw_commit_assembly — _impl loads proposal from disk (nonexistent id → error)


def test_client_facade_commit_assembly_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.commit_assembly("nonexistent_id", "/tmp/out.sldasm")
    assert res["ok"] is False
    assert "not found" in res["error"]


# sw_edit_assembly — _impl loads manifest from disk (nonexistent → error)


def test_client_facade_edit_assembly_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.edit_assembly("/no/such.manifest.json", {"op": "bogus"})
    assert res["ok"] is False
    assert "manifest load failed" in res["error"]


# ── Batch M3: drawing + properties verbs ─────────────────────────────────
#
# sw_propose_drawing, sw_dry_run_drawing, sw_commit_drawing,
# sw_propose_properties, sw_dry_run_properties, sw_commit_properties —
# shim warns + delegates; facade routes without warning.
# ─────────────────────────────────────────────────────────────────────────────

# sw_propose_drawing — _impl validates offline (non-dict → schema error)


def test_client_facade_propose_drawing_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.propose_drawing("not a dict")  # type: ignore[arg-type]
    assert res["ok"] is False


# sw_dry_run_drawing — _impl loads proposal from disk (nonexistent id → error)


def test_client_facade_dry_run_drawing_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.dry_run_drawing("nonexistent_id")
    assert res["ok"] is False
    assert "not found" in res["error"]


# sw_commit_drawing — _impl loads proposal from disk (nonexistent id → error)


def test_client_facade_commit_drawing_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.commit_drawing("nonexistent_id", "/tmp/out.SLDDRW")
    assert res["ok"] is False
    assert "not found" in res["error"]


# sw_propose_properties — _impl validates offline (non-dict → schema error)


def test_client_facade_propose_properties_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.propose_properties("not a dict")  # type: ignore[arg-type]
    assert res["ok"] is False


# sw_dry_run_properties — _impl loads proposal from disk (nonexistent id → error)


def test_client_facade_dry_run_properties_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.dry_run_properties("nonexistent_id")
    assert res["ok"] is False
    assert "not found" in res["error"]


# sw_commit_properties — _impl loads proposal from disk (nonexistent id → error)


def test_client_facade_commit_properties_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.mutate.commit_properties("nonexistent_id")
    assert res["ok"] is False
    assert "not found" in res["error"]


# ── Recipe-B: facade-only domains (.export / .features) — no shims ──────────


def test_export_facade_delegates_to_export_all(monkeypatch):
    """client.export.run forwards (doc, requests, part_name) to export.export_all
    verbatim and returns its result. The facade lazy-imports export_all, so we
    patch the name on the ai_sw_bridge.export package the import resolves from."""
    captured = {}

    def fake_export_all(doc, requests, part_name):
        captured["args"] = (doc, requests, part_name)
        return ["EXPORT_RESULT"]

    monkeypatch.setattr("ai_sw_bridge.export.export_all", fake_export_all)
    client = SolidWorksClient(app=object(), mod=object())
    out = client.export.run("DOC", ["req"], "part_stem")
    assert out == ["EXPORT_RESULT"]
    assert captured["args"] == ("DOC", ["req"], "part_stem")


def test_features_facade_introspection():
    """client.features.list_kinds() mirrors the HANDLER_REGISTRY; supports() is
    membership. Read-only — the write path stays on .mutate.propose_feature_add."""
    from ai_sw_bridge.features import HANDLER_REGISTRY

    client = SolidWorksClient(app=object(), mod=object())
    kinds = client.features.list_kinds()
    assert isinstance(kinds, list)
    assert kinds == sorted(HANDLER_REGISTRY)
    assert kinds  # registry is non-empty (seat-proven lanes registered)
    assert client.features.supports(kinds[0]) is True
    assert client.features.supports("__not_a_real_feature_kind__") is False


def test_export_features_facades_cached():
    """.export and .features are cached singletons, like .observe/.mutate/.urdf."""
    client = SolidWorksClient(app=object(), mod=object())
    assert client.export is client.export
    assert client.features is client.features
