"""Tests for the material module (SW-free, mock doc)."""

from __future__ import annotations

from typing import Any

import pytest

import ai_sw_bridge.material as material_mod
from ai_sw_bridge.material import (
    MATERIAL_PROP_NAME,
    SW_CUSTOM_INFO_TEXT,
    SW_CUSTOM_PROP_REPLACE,
    apply_material,
    read_library_material_name,
    set_library_material,
    set_material_custom_prop,
)


class _FakeCPM:
    """Mock ICustomPropertyManager."""

    def __init__(self, add3_return: int = 0) -> None:
        self._add3_return = add3_return
        self.add3_calls: list[tuple[str, int, str, int]] = []

    def Add3(self, name: str, type_: int, value: str, options: int) -> int:
        self.add3_calls.append((name, type_, value, options))
        return self._add3_return


class _FakeExtension:
    """Mock IModelDocExtension."""

    def __init__(self, cpm: _FakeCPM) -> None:
        self._cpm = cpm

    def CustomPropertyManager(self, config: str) -> _FakeCPM:
        return self._cpm


class _FakeDoc:
    """Mock IModelDoc2."""

    def __init__(self, cpm: _FakeCPM) -> None:
        self.Extension = _FakeExtension(cpm)


class TestSetMaterialCustomProp:
    def test_success(self) -> None:
        cpm = _FakeCPM(add3_return=0)
        doc = _FakeDoc(cpm)
        assert set_material_custom_prop(doc, "AISI 304") is True
        assert len(cpm.add3_calls) == 1
        name, type_, value, options = cpm.add3_calls[0]
        assert name == MATERIAL_PROP_NAME
        assert type_ == SW_CUSTOM_INFO_TEXT
        assert value == "AISI 304"
        assert options == SW_CUSTOM_PROP_REPLACE

    def test_empty_string_returns_false(self) -> None:
        cpm = _FakeCPM()
        doc = _FakeDoc(cpm)
        assert set_material_custom_prop(doc, "") is False
        assert len(cpm.add3_calls) == 0

    def test_none_returns_false(self) -> None:
        cpm = _FakeCPM()
        doc = _FakeDoc(cpm)
        assert set_material_custom_prop(doc, None) is False  # type: ignore[arg-type]

    def test_add3_nonzero_returns_false(self) -> None:
        cpm = _FakeCPM(add3_return=2)
        doc = _FakeDoc(cpm)
        assert set_material_custom_prop(doc, "6061 Alloy") is False

    def test_add3_exception_returns_false(self) -> None:
        class _RaisingCPM:
            def Add3(self, *args: Any) -> int:
                raise RuntimeError("COM error")

        class _RaisingDoc:
            Extension = _FakeExtension(_RaisingCPM())  # type: ignore[assignment]

        assert set_material_custom_prop(_RaisingDoc(), "test") is False

    def test_extension_exception_returns_false(self) -> None:
        class _NoExtDoc:
            @property
            def Extension(self) -> Any:
                raise RuntimeError("no extension")

        assert set_material_custom_prop(_NoExtDoc(), "test") is False


class _FakePartDoc:
    """Mock IPartDoc that mimics SW's SetMaterialPropertyName2 semantics:
    the material is assigned ONLY if its name is in the install's library
    (``known_materials``); an unknown name is a silent no-op — the v0.15 trap.
    The early-bound read-back shape is the (name, db) tuple.
    """

    def __init__(
        self,
        cpm: _FakeCPM,
        *,
        known_materials: tuple[str, ...] = (),
        readback_raises: bool = False,
    ) -> None:
        self.Extension = _FakeExtension(cpm)
        self._known = set(known_materials)
        self._assigned = ""
        self._readback_raises = readback_raises
        self.set_calls: list[tuple[str, str, str]] = []
        self.rebuilds = 0

    def SetMaterialPropertyName2(self, config: str, db: str, name: str) -> None:
        self.set_calls.append((config, db, name))
        self._assigned = name if name in self._known else ""

    def ForceRebuild3(self, top_only: bool) -> bool:
        self.rebuilds += 1
        return True

    def GetMaterialPropertyName2(self, config: str) -> tuple[str, str]:
        if self._readback_raises:
            raise RuntimeError("Parameter not optional")
        db = "SOLIDWORKS Materials" if self._assigned else ""
        return (self._assigned, db)


@pytest.fixture
def _identity_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the early-bind seam to identity so the fake doc's methods are
    reached directly (mirrors the mutate-handler test pattern)."""
    monkeypatch.setattr(material_mod, "typed", lambda obj, iface, **kw: obj)


class TestReadLibraryMaterialName:
    def test_returns_assigned_name(self, _identity_typed: None) -> None:
        doc = _FakePartDoc(_FakeCPM(), known_materials=("AISI 1020",))
        doc.SetMaterialPropertyName2("", "", "AISI 1020")
        assert read_library_material_name(doc) == "AISI 1020"

    def test_returns_none_when_unassigned(self, _identity_typed: None) -> None:
        doc = _FakePartDoc(_FakeCPM())
        assert read_library_material_name(doc) is None

    def test_readback_exception_returns_none(self, _identity_typed: None) -> None:
        doc = _FakePartDoc(_FakeCPM(), readback_raises=True)
        assert read_library_material_name(doc) is None


class TestSetLibraryMaterial:
    def test_known_material_assigns_and_verifies(self, _identity_typed: None) -> None:
        doc = _FakePartDoc(_FakeCPM(), known_materials=("AISI 1020",))
        assert set_library_material(doc, "AISI 1020") is True
        assert doc.set_calls == [("", "", "AISI 1020")]  # empty db
        assert doc.rebuilds == 1

    def test_unknown_material_returns_false(self, _identity_typed: None) -> None:
        doc = _FakePartDoc(_FakeCPM(), known_materials=("AISI 1020",))
        # The v0.15 trap: SetMaterialPropertyName2 no-ops on an unknown name.
        assert set_library_material(doc, "AISI 1020 Steel (SS)") is False

    def test_empty_name_returns_false(self, _identity_typed: None) -> None:
        doc = _FakePartDoc(_FakeCPM(), known_materials=("AISI 1020",))
        assert set_library_material(doc, "") is False
        assert doc.set_calls == []

    def test_set_exception_returns_false(self, _identity_typed: None) -> None:
        class _RaisingPart:
            def SetMaterialPropertyName2(self, *a: Any) -> None:
                raise RuntimeError("COM error")

        assert set_library_material(_RaisingPart(), "AISI 1020") is False


class TestApplyMaterial:
    def test_no_material_in_spec_returns_none(self) -> None:
        cpm = _FakeCPM()
        doc = _FakeDoc(cpm)
        assert apply_material(doc, {"name": "TestPart"}) is None
        assert len(cpm.add3_calls) == 0

    def test_library_material_takes_honest_path(self, _identity_typed: None) -> None:
        cpm = _FakeCPM(add3_return=0)
        doc = _FakePartDoc(cpm, known_materials=("AISI 1020",))
        result = apply_material(doc, {"name": "P", "material": "AISI 1020"})
        assert result is True
        # Honest library path took — no custom-property fallback needed.
        assert len(cpm.add3_calls) == 0
        assert doc.set_calls == [("", "", "AISI 1020")]

    def test_unknown_material_falls_back_to_custom_prop(
        self, _identity_typed: None
    ) -> None:
        cpm = _FakeCPM(add3_return=0)
        doc = _FakePartDoc(cpm, known_materials=("AISI 1020",))
        result = apply_material(doc, {"name": "P", "material": "Made Up Steel"})
        assert result is True
        # Library no-op → custom-property carries the metadata.
        assert cpm.add3_calls[0][2] == "Made Up Steel"

    def test_material_in_spec_sets_prop(self) -> None:
        # _FakeDoc has no SetMaterialPropertyName2 → library path errors out
        # and degrades to the custom-property path.
        cpm = _FakeCPM(add3_return=0)
        doc = _FakeDoc(cpm)
        result = apply_material(doc, {"name": "TestPart", "material": "AISI 304"})
        assert result is True
        assert cpm.add3_calls[0][2] == "AISI 304"

    def test_non_string_material_returns_false(self) -> None:
        cpm = _FakeCPM()
        doc = _FakeDoc(cpm)
        result = apply_material(doc, {"name": "TestPart", "material": 42})
        assert result is False
        assert len(cpm.add3_calls) == 0
