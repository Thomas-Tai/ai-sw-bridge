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

import pytest

import ai_sw_bridge.observe as _observe_mod

from ai_sw_bridge.client import (
    SolidWorksClient,
    SolidWorksObserverFacade,
    UrdfFacade,
)
from ai_sw_bridge.observe_bbox import (
    _sw_get_assembly_bbox_from_doc_impl,
    _sw_get_bbox_from_doc_impl,
    sw_get_assembly_bbox_from_doc,
    sw_get_bbox_from_doc,
)
from ai_sw_bridge.observe_clearance import (
    _sw_analyze_stackup_impl,
    _sw_get_clearance_impl,
    _sw_get_face_clearance_impl,
    sw_analyze_stackup,
    sw_get_clearance,
    sw_get_face_clearance,
)
from ai_sw_bridge.observe_draft import _sw_get_draft_analysis_impl, sw_get_draft_analysis
from ai_sw_bridge.observe_inertia import _sw_get_inertia_impl, sw_get_inertia
from ai_sw_bridge.observe_interference import (
    _sw_get_interference_impl,
    sw_get_interference,
)
from ai_sw_bridge.observe_section import _sw_get_section_props_impl, sw_get_section_props
from ai_sw_bridge.observe_selection import _sw_get_selection_impl, sw_get_selection
from ai_sw_bridge.observe_measure import (
    _sw_get_measure_from_doc_impl,
    _sw_get_measure_durable_pair_impl,
    _sw_get_measure_angle_from_doc_impl,
    _sw_get_measure_area_from_doc_impl,
    sw_get_measure_from_doc,
    sw_get_measure_durable_pair,
    sw_get_measure_angle_from_doc,
    sw_get_measure_area_from_doc,
)
from ai_sw_bridge.observe import (
    # Batch O2 _impl cores
    _sw_get_active_doc_impl,
    _sw_get_feature_errors_impl,
    _sw_get_equations_impl,
    _sw_get_bbox_impl,
    _sw_get_volume_impl,
    _sw_get_feature_statistics_impl,
    _sw_screenshot_impl,
    _sw_get_mate_errors_impl,
    _sw_get_custom_props_impl,
    _sw_measure_impl,
    _sw_undercut_faces_impl,
    _sw_min_wall_thickness_impl,
    _sw_get_enabled_addins_impl,
    # Batch O2 shims
    sw_get_active_doc,
    sw_get_feature_errors,
    sw_get_equations,
    sw_get_bbox,
    sw_get_volume,
    sw_get_feature_statistics,
    sw_screenshot,
    sw_get_mate_errors,
    sw_get_custom_props,
    sw_measure,
    sw_undercut_faces,
    sw_min_wall_thickness,
    sw_get_enabled_addins,
)


class _PartDoc:
    """Fake non-assembly doc: drives the stackup assembly-guard error path."""

    def GetType(self):
        return 1  # swDocPART


class _AsmDoc:
    """Fake assembly doc (GetType=2): drives non-part error paths."""

    def GetType(self):
        return 2  # swDocASSEMBLY


# ── Deprecation shims: warn + delegate to identical data ────────────────────

def test_sw_get_inertia_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="get_inertia"):
        shim = sw_get_inertia(object())
    impl = _sw_get_inertia_impl(object())
    assert shim == impl                # identical payload
    assert shim["ok"] is False         # object() has no .Extension -> typed error


def test_sw_analyze_stackup_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="analyze_stackup"):
        shim = sw_analyze_stackup(_PartDoc(), ["a-1", "b-1"])
    impl = _sw_analyze_stackup_impl(_PartDoc(), ["a-1", "b-1"])
    assert shim == impl
    assert shim["ok"] is False and "assembly" in shim["error"]


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
def test_sw_get_interference_shim_warns_and_delegates():
    doc = _PartDoc()  # GetType=1 (part) → "interference detection requires assembly"
    with pytest.warns(PendingDeprecationWarning, match="sw_get_interference"):
        shim = sw_get_interference(doc)
    impl = _sw_get_interference_impl(doc)
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_interference_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.interference(doc=_PartDoc())
    assert res["ok"] is False  # type-guard fires, not a warning


# sw_get_draft_analysis — assembly doc drives the non-part type-guard error path
def test_sw_get_draft_analysis_shim_warns_and_delegates():
    doc = _AsmDoc()  # GetType=2 → "draft analysis requires part document"
    with pytest.warns(PendingDeprecationWarning, match="sw_get_draft_analysis"):
        shim = sw_get_draft_analysis(doc, "top")
    impl = _sw_get_draft_analysis_impl(doc, "top")
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_draft_analysis_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.draft_analysis("top", doc=_AsmDoc())
    assert res["ok"] is False  # type-guard fires, not a warning


# sw_get_section_props — bare object() has no .Extension → typed error path
def test_sw_get_section_props_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="sw_get_section_props"):
        shim = sw_get_section_props(object())
    impl = _sw_get_section_props_impl(object())
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_section_props_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.section_props(doc=object())
    assert res["ok"] is False  # no .Extension on object(), no warning raised


# sw_get_selection — bare object() fails typed(IModelDoc2) → errors → ok=False
def test_sw_get_selection_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="sw_get_selection"):
        shim = sw_get_selection(object())
    impl = _sw_get_selection_impl(object())
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_selection_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.selection(doc=object())
    assert res["ok"] is False  # typed() fails on object(), no warning raised


# sw_get_bbox_from_doc — assembly doc drives the non-part type-guard error path
def test_sw_get_bbox_from_doc_shim_warns_and_delegates():
    doc = _AsmDoc()  # GetType=2 → "bounding-box requires part document"
    with pytest.warns(PendingDeprecationWarning, match="sw_get_bbox_from_doc"):
        shim = sw_get_bbox_from_doc(doc)
    impl = _sw_get_bbox_from_doc_impl(doc)
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_bbox_from_doc_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.bbox_from_doc(doc=_AsmDoc())
    assert res["ok"] is False  # type-guard fires, not a warning


# sw_get_assembly_bbox_from_doc — part doc drives the non-assembly type-guard
def test_sw_get_assembly_bbox_from_doc_shim_warns_and_delegates():
    doc = _PartDoc()  # GetType=1 → "assembly bounding-box requires assembly document"
    with pytest.warns(PendingDeprecationWarning, match="sw_get_assembly_bbox_from_doc"):
        shim = sw_get_assembly_bbox_from_doc(doc)
    impl = _sw_get_assembly_bbox_from_doc_impl(doc)
    assert shim == impl
    assert shim["ok"] is False


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
def test_sw_get_active_doc_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_get_active_doc"):
            shim = sw_get_active_doc()
        impl = _sw_get_active_doc_impl()
    assert shim == impl
    assert shim["ok"] is True   # active_doc returns ok=True even on no_active_doc


def test_client_facade_active_doc_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.active_doc()
    assert res["ok"] is True  # no_active_doc returns ok=True with error set


# sw_get_feature_errors / feature_errors
def test_sw_get_feature_errors_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_get_feature_errors"):
            shim = sw_get_feature_errors()
        impl = _sw_get_feature_errors_impl()
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_feature_errors_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.feature_errors()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_equations / equations
def test_sw_get_equations_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_get_equations"):
            shim = sw_get_equations()
        impl = _sw_get_equations_impl()
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_equations_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.equations()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_bbox / bbox (no-arg legacy form)
def test_sw_get_bbox_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_get_bbox"):
            shim = sw_get_bbox()
        impl = _sw_get_bbox_impl()
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_bbox_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.bbox()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_volume / volume
def test_sw_get_volume_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_get_volume"):
            shim = sw_get_volume()
        impl = _sw_get_volume_impl()
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_volume_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.volume()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_feature_statistics / feature_statistics
def test_sw_get_feature_statistics_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_get_feature_statistics"):
            shim = sw_get_feature_statistics()
        impl = _sw_get_feature_statistics_impl()
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_feature_statistics_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.feature_statistics()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_screenshot / screenshot
def test_sw_screenshot_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_screenshot"):
            shim = sw_screenshot(width=320, height=240)
        impl = _sw_screenshot_impl(width=320, height=240)
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_screenshot_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.screenshot(width=320, height=240)
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_mate_errors / mate_errors
def test_sw_get_mate_errors_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_get_mate_errors"):
            shim = sw_get_mate_errors()
        impl = _sw_get_mate_errors_impl()
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_mate_errors_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.mate_errors()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_get_custom_props / custom_props
def test_sw_get_custom_props_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_get_custom_props"):
            shim = sw_get_custom_props()
        impl = _sw_get_custom_props_impl()
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_custom_props_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.custom_props()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_measure / measure
def test_sw_measure_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_measure"):
            shim = sw_measure()
        impl = _sw_measure_impl()
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_measure_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.measure()
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_undercut_faces / undercut_faces
def test_sw_undercut_faces_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_undercut_faces"):
            shim = sw_undercut_faces(pull_x=0.0, pull_y=1.0, pull_z=0.0)
        impl = _sw_undercut_faces_impl(pull_x=0.0, pull_y=1.0, pull_z=0.0)
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


def test_client_facade_undercut_faces_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        with _no_doc_patches()[0], _no_doc_patches()[1]:
            res = client.observe.undercut_faces(pull_x=0.0, pull_y=1.0, pull_z=0.0)
    assert res["ok"] is False and res["error"] == "no_active_doc"


# sw_min_wall_thickness / min_wall_thickness
def test_sw_min_wall_thickness_shim_warns_and_delegates():
    with _no_doc_patches()[0], _no_doc_patches()[1]:
        with pytest.warns(PendingDeprecationWarning, match="sw_min_wall_thickness"):
            shim = sw_min_wall_thickness(samples_per_face=2)
        impl = _sw_min_wall_thickness_impl(samples_per_face=2)
    assert shim == impl
    assert shim["ok"] is False and shim["error"] == "no_active_doc"


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
def test_sw_get_enabled_addins_shim_warns_and_delegates():
    with patch.object(_observe_mod, "get_sw_app", return_value=object()):
        with pytest.warns(PendingDeprecationWarning, match="sw_get_enabled_addins"):
            shim = sw_get_enabled_addins()
        impl = _sw_get_enabled_addins_impl()
    assert shim == impl
    assert shim["ok"] is True and shim["error"] == "api_not_present"


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
def test_sw_get_measure_from_doc_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="sw_get_measure_from_doc"):
        shim = sw_get_measure_from_doc(object())
    impl = _sw_get_measure_from_doc_impl(object())
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_measure_selection_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.measure_selection(doc=object())
    assert res["ok"] is False


# sw_get_measure_durable_pair / measure_durable_pair — bare object() fails in durable-ref resolution
def test_sw_get_measure_durable_pair_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="sw_get_measure_durable_pair"):
        shim = sw_get_measure_durable_pair(object(), "ref_a", "ref_b")
    impl = _sw_get_measure_durable_pair_impl(object(), "ref_a", "ref_b")
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_measure_durable_pair_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.measure_durable_pair("ref_a", "ref_b", doc=object())
    assert res["ok"] is False


# sw_get_measure_angle_from_doc / measure_angle — bare object() has no SelectionManager
def test_sw_get_measure_angle_from_doc_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="sw_get_measure_angle_from_doc"):
        shim = sw_get_measure_angle_from_doc(object())
    impl = _sw_get_measure_angle_from_doc_impl(object())
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_measure_angle_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.measure_angle(doc=object())
    assert res["ok"] is False


# sw_get_measure_area_from_doc / measure_area — bare object() has no SelectionManager
def test_sw_get_measure_area_from_doc_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="sw_get_measure_area_from_doc"):
        shim = sw_get_measure_area_from_doc(object())
    impl = _sw_get_measure_area_from_doc_impl(object())
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_measure_area_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.measure_area(doc=object())
    assert res["ok"] is False


# sw_get_clearance / clearance — bare object() has no GetType → typed error
def test_sw_get_clearance_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="sw_get_clearance"):
        shim = sw_get_clearance(object(), "a", "b")
    impl = _sw_get_clearance_impl(object(), "a", "b")
    assert shim == impl
    assert shim["ok"] is False


def test_client_facade_clearance_routes_without_warning():
    client = SolidWorksClient(app=object(), mod=object())
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        res = client.observe.clearance("a", "b", doc=object())
    assert res["ok"] is False


# sw_get_face_clearance / face_clearance — bare object() fails typed(IModelDoc2)
def test_sw_get_face_clearance_shim_warns_and_delegates():
    with pytest.warns(PendingDeprecationWarning, match="sw_get_face_clearance"):
        shim = sw_get_face_clearance(object(), "Face<1>", "Face<2>")
    impl = _sw_get_face_clearance_impl(object(), "Face<1>", "Face<2>")
    assert shim == impl
    assert shim["ok"] is False


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
