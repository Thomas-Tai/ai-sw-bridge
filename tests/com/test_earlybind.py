"""Tests for ai_sw_bridge.com.earlybind.

The module's load-bearing function, ``typed()``, constructs an early-bound
interface wrapper directly from a dispatch's raw ``_oleobj_`` — the proven
S-EARLYBIND escape hatch for OUT-param / Callout marshaling. These tests run
without pywin32 or SOLIDWORKS by passing a fake gen_py module (interface
classes that record the raw handle they were constructed from), so the wrap
contract is exercised in isolation from COM.
"""

from __future__ import annotations

import sys
import types

import pytest

from ai_sw_bridge.com import earlybind as eb
from ai_sw_bridge.com.earlybind import EarlyBindError


# ---------------------------------------------------------------------------
# Fakes: a gen_py-like module whose interface classes capture the raw handle.
# ---------------------------------------------------------------------------


class _FakeRaw:
    """Stand-in for a PyIDispatch (the thing real ``_oleobj_`` returns)."""


class _FakeTyped:
    """Stand-in for a makepy typed wrapper; records what it wrapped."""

    def __init__(self, raw: object) -> None:
        self.raw = raw


def _fake_module() -> types.ModuleType:
    mod = types.ModuleType("win32com.gen_py.fake_sw")
    mod.IModelDocExtension = _FakeTyped  # type: ignore[attr-defined]
    mod.IEntity = _FakeTyped  # type: ignore[attr-defined]
    return mod


class _FakeDispatch:
    """A late-bound dispatch: has a ``_oleobj_`` raw handle."""

    def __init__(self) -> None:
        self._oleobj_ = _FakeRaw()


# ---------------------------------------------------------------------------
# typed()
# ---------------------------------------------------------------------------


class TestTyped:
    def test_wraps_raw_oleobj_with_explicit_module(self) -> None:
        obj = _FakeDispatch()
        wrapped = eb.typed(obj, "IModelDocExtension", module=_fake_module())
        assert isinstance(wrapped, _FakeTyped)
        # The wrapper is built from the RAW handle, not the dispatch itself.
        assert wrapped.raw is obj._oleobj_

    def test_uses_shared_wrapper_module_when_not_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _fake_module()
        monkeypatch.setattr(eb, "wrapper_module", lambda: mod)
        obj = _FakeDispatch()
        wrapped = eb.typed(obj, "IEntity")
        assert isinstance(wrapped, _FakeTyped)
        assert wrapped.raw is obj._oleobj_

    def test_none_obj_raises(self) -> None:
        with pytest.raises(EarlyBindError, match="None"):
            eb.typed(None, "IEntity", module=_fake_module())

    def test_unavailable_module_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(eb, "wrapper_module", lambda: None)
        with pytest.raises(EarlyBindError, match="gen_py wrapper unavailable"):
            eb.typed(_FakeDispatch(), "IEntity")

    def test_unknown_interface_raises(self) -> None:
        with pytest.raises(EarlyBindError, match="not found"):
            eb.typed(_FakeDispatch(), "INotAnInterface", module=_fake_module())

    def test_object_without_oleobj_raises(self) -> None:
        class _Bare:
            pass

        with pytest.raises(EarlyBindError, match="_oleobj_"):
            eb.typed(_Bare(), "IEntity", module=_fake_module())


# ---------------------------------------------------------------------------
# typed_qi() — QI-validated wrap (pywin32-free via an injected fake pythoncom)
# ---------------------------------------------------------------------------


_IID_IDISPATCH = object()  # sentinel standing in for pythoncom.IID_IDispatch
E_NOINTERFACE_SIGNED = -2147467262  # 0x80004002 as a signed 32-bit int


class _FakeComError(Exception):
    """Stand-in for pythoncom.com_error: args[0] is the (signed) hresult."""


def _fake_pythoncom() -> types.ModuleType:
    mod = types.ModuleType("pythoncom")
    mod.IID_IDispatch = _IID_IDISPATCH  # type: ignore[attr-defined]
    mod.com_error = _FakeComError  # type: ignore[attr-defined]
    return mod


class _QIRaw:
    """A raw _oleobj_ whose QueryInterface is driven by a supplied behaviour."""

    def __init__(self, behaviour) -> None:
        self._behaviour = behaviour
        self.calls: list[tuple] = []

    def QueryInterface(self, iid, iface_hint):  # noqa: N802 — COM signature
        self.calls.append((iid, iface_hint))
        return self._behaviour(iid, iface_hint)


class _QIDispatch:
    def __init__(self, behaviour) -> None:
        self._oleobj_ = _QIRaw(behaviour)


def _qi_module() -> types.ModuleType:
    """gen_py-like module whose interface classes carry a CLSID + capture wraps."""
    mod = types.ModuleType("win32com.gen_py.fake_sw_qi")

    class _IShell(_FakeTyped):
        CLSID = "{SHELL-IID}"

    class _IDraft(_FakeTyped):
        CLSID = "{DRAFT-IID}"

    class _INoIID(_FakeTyped):
        pass  # deliberately no CLSID

    mod.IShellFeatureData = _IShell  # type: ignore[attr-defined]
    mod.IDraftFeatureData2 = _IDraft  # type: ignore[attr-defined]
    mod.INoIID = _INoIID  # type: ignore[attr-defined]
    return mod


class TestTypedQi:
    def test_qi_success_wraps_validated_dispatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "pythoncom", _fake_pythoncom())
        validated = _FakeRaw()  # the pointer QI hands back
        obj = _QIDispatch(lambda iid, hint: validated)
        wrapped = eb.typed_qi(obj, "IShellFeatureData", module=_qi_module())
        assert isinstance(wrapped, _FakeTyped)
        assert wrapped.raw is validated
        # IID came from the class CLSID and the IDispatch hint was passed.
        assert obj._oleobj_.calls == [("{SHELL-IID}", _IID_IDISPATCH)]

    def test_qi_e_nointerface_raises_earlybind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "pythoncom", _fake_pythoncom())

        def _reject(iid, hint):
            raise _FakeComError(E_NOINTERFACE_SIGNED, "No such interface")

        obj = _QIDispatch(_reject)
        with pytest.raises(EarlyBindError, match="E_NOINTERFACE"):
            eb.typed_qi(obj, "IDraftFeatureData2", module=_qi_module())

    def test_qi_other_hresult_raises_without_nointerface(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "pythoncom", _fake_pythoncom())

        def _fail(iid, hint):
            raise _FakeComError(-2147024891, "Access denied")  # 0x80070005

        obj = _QIDispatch(_fail)
        with pytest.raises(EarlyBindError) as ei:
            eb.typed_qi(obj, "IShellFeatureData", module=_qi_module())
        assert "E_NOINTERFACE" not in str(ei.value)
        assert "0x80070005" in str(ei.value)

    def test_interface_without_clsid_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "pythoncom", _fake_pythoncom())
        obj = _QIDispatch(lambda iid, hint: _FakeRaw())
        with pytest.raises(EarlyBindError, match="no CLSID"):
            eb.typed_qi(obj, "INoIID", module=_qi_module())

    def test_none_obj_raises(self) -> None:
        with pytest.raises(EarlyBindError, match="None"):
            eb.typed_qi(None, "IShellFeatureData", module=_qi_module())

    def test_unknown_interface_raises(self) -> None:
        obj = _QIDispatch(lambda iid, hint: _FakeRaw())
        with pytest.raises(EarlyBindError, match="not found"):
            eb.typed_qi(obj, "INotReal", module=_qi_module())

    def test_object_without_oleobj_raises(self) -> None:
        class _Bare:
            pass

        with pytest.raises(EarlyBindError, match="_oleobj_"):
            eb.typed_qi(_Bare(), "IShellFeatureData", module=_qi_module())

    def test_unavailable_module_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(eb, "wrapper_module", lambda: None)
        obj = _QIDispatch(lambda iid, hint: _FakeRaw())
        with pytest.raises(EarlyBindError, match="unavailable"):
            eb.typed_qi(obj, "IShellFeatureData")


# ---------------------------------------------------------------------------
# typed_extension()
# ---------------------------------------------------------------------------


class TestTypedExtension:
    def test_wraps_doc_extension(self) -> None:
        ext = _FakeDispatch()
        doc = types.SimpleNamespace(Extension=ext)
        wrapped = eb.typed_extension(doc, module=_fake_module())
        assert isinstance(wrapped, _FakeTyped)
        assert wrapped.raw is ext._oleobj_

    def test_none_doc_raises(self) -> None:
        with pytest.raises(EarlyBindError, match="None doc"):
            eb.typed_extension(None, module=_fake_module())


# ---------------------------------------------------------------------------
# is_early_bound()
# ---------------------------------------------------------------------------


class TestIsEarlyBound:
    def test_true_for_gen_py_module(self) -> None:
        # Emulate a real makepy wrapper: a class whose __module__ lives under
        # the win32com.gen_py namespace (where EnsureModule generates them).
        gen_py_cls = type(
            "ITyped",
            (),
            {"__module__": "win32com.gen_py.83A33D31x0x32x0"},
        )
        assert eb.is_early_bound(gen_py_cls()) is True

    def test_false_for_late_bound(self) -> None:
        assert eb.is_early_bound(_FakeDispatch()) is False


# ---------------------------------------------------------------------------
# Package re-exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_symbols_exported_from_com_package(self) -> None:
        from ai_sw_bridge import com

        assert com.typed is eb.typed
        assert com.typed_extension is eb.typed_extension
        assert com.typed_qi is eb.typed_qi
        assert com.is_early_bound is eb.is_early_bound
        assert com.EarlyBindError is EarlyBindError
