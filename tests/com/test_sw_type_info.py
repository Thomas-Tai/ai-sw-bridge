"""Tests for ai_sw_bridge.com.sw_type_info (W5.3).

The module wraps pywin32 type-library introspection. Tests run without
pywin32 by injecting fake ``win32com.client`` components into the module
namespace and resetting module-level state between tests.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from ai_sw_bridge.com import sw_type_info as mod


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch: pytest.MonkeyPatch):
    """Reset module-level caches and inject fake pywin32 before each test."""
    fake_mod = types.ModuleType("win32com.client")
    fake_gencache = MagicMock()
    fake_mod.gencache = fake_gencache  # type: ignore[attr-defined]

    monkeypatch.setattr(mod, "win32com", types.ModuleType("win32com"), raising=False)
    win32com_mod = mod.win32com  # type: ignore[attr-defined]
    monkeypatch.setattr(win32com_mod, "client", fake_mod, raising=False)
    monkeypatch.setattr(mod, "gencache", fake_gencache, raising=False)
    monkeypatch.setattr(mod, "PYWIN32_AVAILABLE", True)

    mod._wrapper_module = types.ModuleType("fake_wrapper")
    mod._interface_methods.clear()
    mod._flag_cache.clear()
    mod.invalidate_flag_cache()

    yield

    mod._wrapper_module = None
    mod._interface_methods.clear()
    mod._flag_cache.clear()


# ---------------------------------------------------------------------------
# flag_methods
# ---------------------------------------------------------------------------


class TestFlagMethods:
    def test_flags_single_interface(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(
            ["GetTitle", "GetType", "GetPathName"]
        )

        obj = MagicMock()
        count = mod.flag_methods(obj, "IModelDoc2")
        assert count == 3
        obj._FlagAsMethod.assert_any_call("GetTitle")
        obj._FlagAsMethod.assert_any_call("GetType")
        obj._FlagAsMethod.assert_any_call("GetPathName")

    def test_idempotent_second_call_returns_zero(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle", "GetType"])

        obj = MagicMock()
        first = mod.flag_methods(obj, "IModelDoc2")
        second = mod.flag_methods(obj, "IModelDoc2")
        assert first == 2
        assert second == 0
        assert obj._FlagAsMethod.call_count == 2

    def test_incremental_new_interface_adds(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        mod._interface_methods["IPartDoc"] = frozenset(["GetBendState"])

        obj = MagicMock()
        mod.flag_methods(obj, "IModelDoc2")
        count = mod.flag_methods(obj, "IPartDoc")
        assert count == 1
        obj._FlagAsMethod.assert_called_with("GetBendState")

    def test_none_obj_returns_zero(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        assert mod.flag_methods(None, "IModelDoc2") == 0

    def test_unknown_interface_returns_zero(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        obj = MagicMock()
        assert mod.flag_methods(obj, "IUnknown") == 0

    def test_flagasmethod_exception_skipped(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle", "BadMethod"])
        obj = MagicMock()
        obj._FlagAsMethod.side_effect = lambda n: (
            (_ for _ in ()).throw(RuntimeError("nope")) if n == "BadMethod" else None
        )
        count = mod.flag_methods(obj, "IModelDoc2")
        assert count == 1

    def test_no_wrapper_loaded_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mod, "PYWIN32_AVAILABLE", False)
        mod._wrapper_module = None
        mod._interface_methods.clear()
        obj = MagicMock()
        assert mod.flag_methods(obj, "IModelDoc2") == 0


# ---------------------------------------------------------------------------
# flagged
# ---------------------------------------------------------------------------


class TestFlagged:
    def test_returns_same_object(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        obj = MagicMock()
        result = mod.flagged(obj, "IModelDoc2")
        assert result is obj

    def test_none_passthrough(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        assert mod.flagged(None, "IModelDoc2") is None


# ---------------------------------------------------------------------------
# flag_doc
# ---------------------------------------------------------------------------


class TestFlagDoc:
    def test_part_flags_modeldoc2_and_partdoc(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        mod._interface_methods["IPartDoc"] = frozenset(["GetBendState"])
        obj = MagicMock()
        count = mod.flag_doc(obj, 1)
        assert count == 2

    def test_assembly_flags_modeldoc2_and_assemblydoc(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        mod._interface_methods["IAssemblyDoc"] = frozenset(["GetComponents"])
        obj = MagicMock()
        count = mod.flag_doc(obj, 2)
        assert count == 2

    def test_drawing_flags_modeldoc2_and_drawingdoc(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        mod._interface_methods["IDrawingDoc"] = frozenset(["GetSheets"])
        obj = MagicMock()
        count = mod.flag_doc(obj, 3)
        assert count == 2

    def test_unknown_type_falls_back_to_modeldoc2(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        obj = MagicMock()
        count = mod.flag_doc(obj, 99)
        assert count == 1


# ---------------------------------------------------------------------------
# invalidate_flag_cache
# ---------------------------------------------------------------------------


class TestInvalidateFlagCache:
    def test_invalidate_specific_object(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        obj = MagicMock()
        mod.flag_methods(obj, "IModelDoc2")
        assert mod.flag_methods(obj, "IModelDoc2") == 0

        mod.invalidate_flag_cache(obj)
        count = mod.flag_methods(obj, "IModelDoc2")
        assert count == 1

    def test_invalidate_all(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle"])
        obj1, obj2 = MagicMock(), MagicMock()
        mod.flag_methods(obj1, "IModelDoc2")
        mod.flag_methods(obj2, "IModelDoc2")

        mod.invalidate_flag_cache()
        assert mod.flag_methods(obj1, "IModelDoc2") == 1
        assert mod.flag_methods(obj2, "IModelDoc2") == 1


# ---------------------------------------------------------------------------
# interface_method_names
# ---------------------------------------------------------------------------


class TestInterfaceMethodNames:
    def test_known_interface(self) -> None:
        mod._interface_methods["IModelDoc2"] = frozenset(["GetTitle", "GetType"])
        names = mod.interface_method_names("IModelDoc2")
        assert names == frozenset(["GetTitle", "GetType"])

    def test_unknown_interface_returns_empty(self) -> None:
        assert mod.interface_method_names("INonExistent") == frozenset()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_doc_type_to_interfaces(self) -> None:
        assert mod.DOC_TYPE_TO_INTERFACES[1] == ("IModelDoc2", "IPartDoc")
        assert mod.DOC_TYPE_TO_INTERFACES[2] == ("IModelDoc2", "IAssemblyDoc")
        assert mod.DOC_TYPE_TO_INTERFACES[3] == ("IModelDoc2", "IDrawingDoc")

    def test_sw_tlb_iid_format(self) -> None:
        assert mod.SW_TLB_IID.startswith("{")
        assert mod.SW_TLB_IID.endswith("}")


# ---------------------------------------------------------------------------
# Fallback when pywin32 unavailable
# ---------------------------------------------------------------------------


class TestNoPywin32:
    def test_no_load_when_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "PYWIN32_AVAILABLE", False)
        mod._wrapper_module = None
        mod._interface_methods.clear()
        # Should not attempt to load and should return empty
        assert mod.interface_method_names("IModelDoc2") == frozenset()
        obj = MagicMock()
        assert mod.flag_methods(obj, "IModelDoc2") == 0
