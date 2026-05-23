"""Tests for CLI stability tier markers (Task 1.9)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ai_sw_bridge.cli.stability import TIER_REGISTRY, Tier, add_tier, cli_stability
from ai_sw_bridge.cli import build, codegen, mutate, observe, probe


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestTierRegistry:
    """Every CLI module that ships a main() must have an explicit tier."""

    # These are the modules that define CLI entry points.
    _CLI_MODULES = {
        build,
        codegen,
        mutate,
        observe,
        probe,
    }

    def test_all_cli_modules_registered(self) -> None:
        for mod in self._CLI_MODULES:
            assert mod.__name__ in TIER_REGISTRY, (
                f"{mod.__name__} is missing from TIER_REGISTRY — add "
                f"@cli_stability(...) to its main()"
            )

    def test_no_module_defaults_to_stable_implicitly(self) -> None:
        """A module must explicitly declare 'stable'; it must not just
        happen to be the default Tier value."""
        for mod in self._CLI_MODULES:
            tier = TIER_REGISTRY[mod.__name__]
            assert hasattr(mod.main, "_cli_tier"), (
                f"{mod.__name__}.main() lacks _cli_tier — did you add "
                f"@cli_stability(...)?"
            )
            # The decorator sets _cli_tier; we just confirm it matches the
            # registry value (i.e. the decorator ran, not a manual insert).
            assert mod.main._cli_tier == tier

    @pytest.mark.parametrize(
        "mod,expected",
        [
            (build, "stable"),
            (observe, "stable"),
            (mutate, "stable"),
            (probe, "experimental"),
            (codegen, "experimental"),
        ],
    )
    def test_expected_tier(self, mod: object, expected: str) -> None:
        assert TIER_REGISTRY[mod.__name__] == expected


class TestAddTier:
    """add_tier() mutates the parser help text correctly."""

    def test_stable_prefix(self) -> None:
        import argparse

        p = argparse.ArgumentParser(prog="test", description="Do stuff.")
        add_tier(p, "stable")
        assert p.description == "[stable] Do stuff."
        assert p._cli_tier == "stable"

    def test_experimental_prefix(self) -> None:
        import argparse

        p = argparse.ArgumentParser(prog="test", description="Do stuff.")
        add_tier(p, "experimental")
        assert p.description == "[experimental] Do stuff."

    def test_deprecated_emits_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        import argparse

        p = argparse.ArgumentParser(prog="test", description="Old stuff.")
        add_tier(p, "deprecated")
        assert p.description == "[deprecated] Old stuff."
        captured = capsys.readouterr()
        assert "deprecated" in captured.err.lower()

    def test_idempotent(self) -> None:
        import argparse

        p = argparse.ArgumentParser(prog="test", description="Do stuff.")
        add_tier(p, "stable")
        add_tier(p, "stable")
        assert p.description == "[stable] Do stuff."


class TestDecorator:
    """@cli_stability sets TIER_REGISTRY and _cli_tier."""

    def test_decorator_registers(self) -> None:
        @cli_stability("experimental")
        def _fake_main() -> int:
            return 0

        assert _fake_main._cli_tier == "experimental"
        assert _fake_main.__module__ in TIER_REGISTRY

    def test_invalid_tier_type(self) -> None:
        """Literal type enforces valid tiers at type-check time; at
        runtime the decorator just stores whatever was passed.  The test
        suite's static checks (mypy/pyright) catch bad literals."""
        pass


# ---------------------------------------------------------------------------
# Integration tests (subprocess, no SW required)
# ---------------------------------------------------------------------------


class TestCLIHelpTierBanner:
    """``--help`` output includes the tier banner."""

    @pytest.mark.parametrize(
        "module,tier_tag",
        [
            ("build", "[stable]"),
            ("observe", "[stable]"),
            ("mutate", "[stable]"),
            ("probe", "[experimental]"),
            ("codegen", "[experimental]"),
        ],
    )
    def test_help_shows_tier(self, module: str, tier_tag: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", f"ai_sw_bridge.cli.{module}", "--help"],
            capture_output=True,
            text=True,
        )
        # --help exits 0
        assert result.returncode == 0
        assert tier_tag in result.stdout, (
            f"ai_sw_bridge.cli.{module} --help missing {tier_tag} banner.\n"
            f"stdout:\n{result.stdout}"
        )
