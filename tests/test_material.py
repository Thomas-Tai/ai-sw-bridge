"""Tests for the material module (SW-free, mock doc)."""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.material import (
    MATERIAL_PROP_NAME,
    SW_CUSTOM_INFO_TEXT,
    SW_CUSTOM_PROP_REPLACE,
    apply_material,
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


class TestApplyMaterial:
    def test_no_material_in_spec_returns_none(self) -> None:
        cpm = _FakeCPM()
        doc = _FakeDoc(cpm)
        assert apply_material(doc, {"name": "TestPart"}) is None
        assert len(cpm.add3_calls) == 0

    def test_material_in_spec_sets_prop(self) -> None:
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
