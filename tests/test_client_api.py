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
"""
from __future__ import annotations

import warnings

import pytest

from ai_sw_bridge.client import (
    SolidWorksClient,
    SolidWorksObserverFacade,
    UrdfFacade,
)
from ai_sw_bridge.observe_clearance import (
    _sw_analyze_stackup_impl,
    sw_analyze_stackup,
)
from ai_sw_bridge.observe_inertia import _sw_get_inertia_impl, sw_get_inertia


class _PartDoc:
    """Fake non-assembly doc: drives the stackup assembly-guard error path."""

    def GetType(self):
        return 1  # swDocPART


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
