"""Tests for the config dispatch (SW-free, mock doc)."""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.config.dispatch import (
    apply_overrides,
    create_all,
    validate_overrides,
)
from ai_sw_bridge.config.variants import (
    ConfigResult,
    ConfigVariant,
    VariantOverride,
)


BASE_LOCALS = (
    '"WIDTH"          = 25.0\n'
    '"HEIGHT"         = 50.0\n'
    '"WALL_THICKNESS" = 2.0\n'
)


class _MockConfigManager:
    """Minimal ConfigurationManager mock."""

    def __init__(self, fail_on: str | None = None, return_none: bool = False):
        self._fail_on = fail_on
        self._return_none = return_none
        self.calls: list[tuple[str, str, str]] = []

    def AddConfiguration2(
        self, name: str, alternate_name: str, description: str
    ) -> Any:
        self.calls.append((name, alternate_name, description))
        if self._return_none:
            return None
        if self._fail_on and name == self._fail_on:
            return None
        return object()


class _MockDoc:
    """Minimal IModelDoc2 mock with a ConfigurationManager."""

    def __init__(self, cm: _MockConfigManager | None = None):
        self.ConfigurationManager = cm or _MockConfigManager()


# ---------------------------------------------------------------------------
# apply_overrides
# ---------------------------------------------------------------------------


class TestApplyOverrides:
    def test_empty_overrides_returns_base(self) -> None:
        result = apply_overrides(BASE_LOCALS, [])
        assert result == BASE_LOCALS

    def test_replace_existing_variable(self) -> None:
        overrides = [VariantOverride("WIDTH", "99.0")]
        result = apply_overrides(BASE_LOCALS, overrides)
        assert '"WIDTH"' in result
        assert "99.0" in result
        # HEIGHT and WALL_THICKNESS unchanged
        assert "50.0" in result
        assert "2.0" in result

    def test_replace_multiple_variables(self) -> None:
        overrides = [
            VariantOverride("WIDTH", "10.0"),
            VariantOverride("HEIGHT", "20.0"),
        ]
        result = apply_overrides(BASE_LOCALS, overrides)
        assert "10.0" in result
        assert "20.0" in result
        # WALL_THICKNESS unchanged
        assert "2.0" in result

    def test_append_new_variable(self) -> None:
        overrides = [VariantOverride("DEPTH", "15.0")]
        result = apply_overrides(BASE_LOCALS, overrides)
        assert '"DEPTH" = 15.0' in result
        # Base variables still present
        assert "25.0" in result
        assert "50.0" in result

    def test_expression_override(self) -> None:
        overrides = [VariantOverride("WIDTH", '"HEIGHT" / 2')]
        result = apply_overrides(BASE_LOCALS, overrides)
        assert '"HEIGHT" / 2' in result

    def test_preserves_unmodified_lines(self) -> None:
        text = "# comment\n" + BASE_LOCALS
        overrides = [VariantOverride("WIDTH", "10.0")]
        result = apply_overrides(text, overrides)
        assert "# comment" in result


# ---------------------------------------------------------------------------
# validate_overrides
# ---------------------------------------------------------------------------


class TestValidateOverrides:
    def test_all_known_variables(self) -> None:
        variants = [
            ConfigVariant(
                name="V1",
                overrides=[VariantOverride("WIDTH", "10.0")],
            )
        ]
        errors = validate_overrides(BASE_LOCALS, variants)
        assert errors == []

    def test_unknown_variable_reported(self) -> None:
        variants = [
            ConfigVariant(
                name="V1",
                overrides=[VariantOverride("NONEXISTENT", "10.0")],
            )
        ]
        errors = validate_overrides(BASE_LOCALS, variants)
        assert len(errors) == 1
        assert "NONEXISTENT" in errors[0]
        assert "V1" in errors[0]

    def test_mixed_known_and_unknown(self) -> None:
        variants = [
            ConfigVariant(
                name="V1",
                overrides=[
                    VariantOverride("WIDTH", "10.0"),
                    VariantOverride("UNKNOWN", "5.0"),
                ],
            )
        ]
        errors = validate_overrides(BASE_LOCALS, variants)
        assert len(errors) == 1
        assert "UNKNOWN" in errors[0]

    def test_empty_overrides_clean(self) -> None:
        variants = [ConfigVariant(name="Default", overrides=[])]
        errors = validate_overrides(BASE_LOCALS, variants)
        assert errors == []

    def test_multiple_variants_checked(self) -> None:
        variants = [
            ConfigVariant(
                name="V1",
                overrides=[VariantOverride("WIDTH", "10.0")],
            ),
            ConfigVariant(
                name="V2",
                overrides=[VariantOverride("BAD_VAR", "10.0")],
            ),
        ]
        errors = validate_overrides(BASE_LOCALS, variants)
        assert len(errors) == 1
        assert "V2" in errors[0]


# ---------------------------------------------------------------------------
# create_all / _create_one
# ---------------------------------------------------------------------------


class TestCreateAll:
    def test_empty_variants(self) -> None:
        doc = _MockDoc()
        results = create_all(doc, [], BASE_LOCALS)
        assert results == []

    def test_single_variant_success(self) -> None:
        cm = _MockConfigManager()
        doc = _MockDoc(cm)
        variants = [
            ConfigVariant(
                name="Small",
                overrides=[VariantOverride("WIDTH", "20.0")],
                description="Small variant",
            )
        ]
        results = create_all(doc, variants, BASE_LOCALS)
        assert len(results) == 1
        assert results[0].ok is True
        assert results[0].variant == "Small"
        assert len(cm.calls) == 1
        assert cm.calls[0][0] == "Small"
        assert cm.calls[0][2] == "Small variant"

    def test_multiple_variants(self) -> None:
        cm = _MockConfigManager()
        doc = _MockDoc(cm)
        variants = [
            ConfigVariant(name="A"),
            ConfigVariant(name="B"),
        ]
        results = create_all(doc, variants, BASE_LOCALS)
        assert len(results) == 2
        assert all(r.ok for r in results)
        assert len(cm.calls) == 2

    def test_config_creation_failure(self) -> None:
        cm = _MockConfigManager(return_none=True)
        doc = _MockDoc(cm)
        variants = [ConfigVariant(name="Fail")]
        results = create_all(doc, variants, BASE_LOCALS)
        assert len(results) == 1
        assert results[0].ok is False
        assert "None" in (results[0].error or "")

    def test_config_exception_failure(self) -> None:
        cm = _MockConfigManager(fail_on="Explode")
        original = cm.AddConfiguration2

        def raising_add(name: str, alt: str, desc: str) -> Any:
            if name == "Explode":
                raise RuntimeError("COM failure")
            return original(name, alt, desc)

        cm.AddConfiguration2 = raising_add  # type: ignore[assignment]
        doc = _MockDoc(cm)
        variants = [ConfigVariant(name="Explode")]
        results = create_all(doc, variants, BASE_LOCALS)
        assert len(results) == 1
        assert results[0].ok is False
        assert "SEAT-gated" in (results[0].error or "")
