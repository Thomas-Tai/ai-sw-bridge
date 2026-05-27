"""Tests for the uniform --quiet flag (UIUX §2.2, §3.3).

Every CLI registered in pyproject.toml [project.scripts] must support
``--quiet``. The flag silences stderr without touching stdout; the
two-stream contract (UIUX §2.1) is invariant.
"""

from __future__ import annotations

import argparse
import os
import sys

import pytest

from ai_sw_bridge.cli.streams import add_quiet_flag, apply_quiet


CLI_MODULES = [
    "ai_sw_bridge.cli.probe",
    "ai_sw_bridge.cli.build",
    "ai_sw_bridge.cli.observe",
    "ai_sw_bridge.cli.mutate",
    "ai_sw_bridge.cli.codegen",
    "ai_sw_bridge.cli.apidoc",
    "ai_sw_bridge.cli.history",
]


def test_add_quiet_flag_adds_quiet_attribute() -> None:
    parser = argparse.ArgumentParser()
    add_quiet_flag(parser)
    args = parser.parse_args(["--quiet"])
    assert args.quiet is True


def test_quiet_defaults_false() -> None:
    parser = argparse.ArgumentParser()
    add_quiet_flag(parser)
    args = parser.parse_args([])
    assert args.quiet is False


def test_apply_quiet_redirects_stderr_when_set() -> None:
    parser = argparse.ArgumentParser()
    add_quiet_flag(parser)
    args = parser.parse_args(["--quiet"])
    original = apply_quiet(args)
    try:
        assert original is sys.stderr or original is not None
        # sys.stderr should now point at devnull
        assert sys.stderr.name == os.devnull
    finally:
        if original is not None:
            sys.stderr.close()
            sys.stderr = original


def test_apply_quiet_noop_when_flag_absent() -> None:
    parser = argparse.ArgumentParser()
    add_quiet_flag(parser)
    args = parser.parse_args([])
    original_stderr = sys.stderr
    result = apply_quiet(args)
    assert result is None
    assert sys.stderr is original_stderr


@pytest.mark.parametrize("module_name", CLI_MODULES)
def test_every_cli_supports_quiet_in_help(module_name: str) -> None:
    """Every CLI's --help mentions --quiet (UIUX §3.3 invariant)."""
    import importlib
    import io
    from contextlib import redirect_stdout

    module = importlib.import_module(module_name)
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            module.main(["--help"])
        except SystemExit:
            pass  # argparse exits after --help
        except TypeError:
            # main() that doesn't accept argv — fall back to monkeypatch
            old_argv = sys.argv
            try:
                sys.argv = [module_name, "--help"]
                try:
                    module.main()
                except SystemExit:
                    pass
            finally:
                sys.argv = old_argv

    help_text = buf.getvalue()
    assert "--quiet" in help_text, (
        f"{module_name}: --help output missing --quiet flag.\n"
        f"Got:\n{help_text}"
    )
