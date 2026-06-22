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
"""
from __future__ import annotations

import warnings

import pytest

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
    sw_analyze_stackup,
)
from ai_sw_bridge.observe_draft import _sw_get_draft_analysis_impl, sw_get_draft_analysis
from ai_sw_bridge.observe_inertia import _sw_get_inertia_impl, sw_get_inertia
from ai_sw_bridge.observe_interference import (
    _sw_get_interference_impl,
    sw_get_interference,
)
from ai_sw_bridge.observe_section import _sw_get_section_props_impl, sw_get_section_props
from ai_sw_bridge.observe_selection import _sw_get_selection_impl, sw_get_selection


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
