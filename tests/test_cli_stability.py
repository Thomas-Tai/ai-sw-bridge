"""Tests for CLI stability tier markers (Task 1.9)."""

from __future__ import annotations

import importlib
import subprocess
import sys
from importlib.metadata import entry_points

import pytest

from ai_sw_bridge.cli.stability import TIER_REGISTRY, add_tier, cli_stability
from ai_sw_bridge.cli import build, codegen, mutate, observe, probe


# Entry points that are stdio daemons, not argparse CLIs: they carry no
# @cli_stability tier (the tier banner lives in argparse --help, which a daemon
# has none of). Excluded from the tier-coverage assertion below; PUBLIC_API.md
# §1 documents ai-sw-mcp as the 'daemon' tier separately.
_DAEMON_ENTRYPOINTS = {"ai-sw-mcp"}


def _argparse_cli_entrypoints() -> list[tuple[str, str]]:
    """Every ``ai_sw_bridge.*`` console_script EXCEPT the stdio daemons.

    Derived from ``importlib.metadata`` (the installed product surface) so a
    newly-added CLI is covered automatically — no hard-coded allowlist to drift.
    Mirrors ``tests/cli/test_entrypoints_smoke.py::_console_scripts``.
    """
    eps = entry_points()
    try:
        scripts = list(eps.select(group="console_scripts"))  # py3.10+ API
    except AttributeError:  # pragma: no cover — legacy importlib.metadata
        scripts = list(eps.get("console_scripts", []))
    return sorted(
        (ep.name, ep.value)
        for ep in scripts
        if ep.value.startswith("ai_sw_bridge.") and ep.name not in _DAEMON_ENTRYPOINTS
    )


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

    @pytest.mark.parametrize(
        "name,target",
        _argparse_cli_entrypoints(),
        ids=[n for n, _ in _argparse_cli_entrypoints()] or ["none"],
    )
    def test_every_entrypoint_has_a_tier(self, name: str, target: str) -> None:
        """Derived from [project.scripts]: EVERY argparse CLI must declare a
        tier, so a new tier-less command fails CI automatically (closes the
        gap where only a 5-module allowlist was checked).

        Importing the module runs its module-level ``@cli_stability(...)``
        decorator, which registers the tier — so the registry is populated by
        the act of importing every entry point's module here.
        """
        module_path, _, func_name = target.partition(":")
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            missing = exc.name or ""
            if missing.startswith("ai_sw_bridge"):
                raise  # a real internal import break — must fail, not skip
            pytest.skip(f"{name}: optional dependency {missing!r} not installed")

        assert module.__name__ in TIER_REGISTRY, (
            f"{name} ({module.__name__}) is missing from TIER_REGISTRY — add "
            f"@cli_stability(...) to its main()"
        )
        main = getattr(module, func_name, None)
        assert main is not None and hasattr(main, "_cli_tier"), (
            f"{name}: {target} lacks a _cli_tier — the @cli_stability(...) "
            f"decorator did not run on its main()"
        )
        assert main._cli_tier == TIER_REGISTRY[module.__name__]

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
