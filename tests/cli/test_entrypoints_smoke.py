"""Smoke test: every console_script entry point resolves and ``--help`` exits 0.

Guards the *installed product surface* — the 22 ``[project.scripts]`` entry
points in pyproject.toml. A packaging/import break in any CLI (a stale
``module:func``, a missing ``main``, or a ``--help`` that crashes) is caught
here in CI rather than by a user after ``pip install``.

Derived dynamically from ``importlib.metadata`` so new CLIs are covered
automatically (no hard-coded list to drift). Requires the package to be
installed (``pip install -e .``), which CI guarantees.
"""

from __future__ import annotations

import importlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import entry_points

import pytest


def _console_scripts() -> list[tuple[str, str]]:
    eps = entry_points()
    try:
        scripts = list(eps.select(group="console_scripts"))  # py3.10+ API
    except AttributeError:  # pragma: no cover - legacy importlib.metadata
        scripts = list(eps.get("console_scripts", []))
    return sorted(
        (ep.name, ep.value) for ep in scripts if ep.value.startswith("ai_sw_bridge.")
    )


_SCRIPTS = _console_scripts()

# Entry points that are stdio daemons, not argparse CLIs: ``main()`` takes no
# argv and blocks on a transport loop, so ``--help`` is N/A (and calling it
# would hang). They still get the import + callable-main smoke below.
_DAEMON_ENTRYPOINTS = {"ai-sw-mcp"}


def test_all_console_scripts_discovered() -> None:
    """pyproject declares 22 console_scripts; metadata must see them all."""
    assert len(_SCRIPTS) >= 22, (
        f"expected >= 22 ai_sw_bridge console_scripts, got "
        f"{len(_SCRIPTS)}: {[s[0] for s in _SCRIPTS]}"
    )


@pytest.mark.parametrize(
    "name,target", _SCRIPTS, ids=[s[0] for s in _SCRIPTS] or ["none"]
)
def test_entrypoint_imports_and_help_exits_zero(name: str, target: str) -> None:
    """The target ``module:func`` imports, ``func`` is callable, ``--help`` exits 0."""
    module_path, _, func_name = target.partition(":")
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing.startswith("ai_sw_bridge"):
            raise  # a real internal import break — must fail, not skip
        pytest.skip(f"{name}: optional dependency {missing!r} not installed")
    main = getattr(module, func_name, None)
    assert callable(main), f"{name}: {target} has no callable {func_name!r}"

    if name in _DAEMON_ENTRYPOINTS:
        # Daemon: main() blocks and has no --help; import + callable is its smoke.
        return

    buf_out, buf_err = io.StringIO(), io.StringIO()
    rc: object = None
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        try:
            rc = main(["--help"])
        except SystemExit as exc:  # argparse exits after --help
            rc = exc.code
        except TypeError:
            # main() that doesn't accept argv — fall back to sys.argv
            old_argv = sys.argv
            sys.argv = [name, "--help"]
            try:
                rc = main()
            except SystemExit as exc:
                rc = exc.code
            finally:
                sys.argv = old_argv

    assert rc in (0, None), (
        f"{name}: `--help` exited with {rc!r}; expected 0.\n"
        f"stderr:\n{buf_err.getvalue()}"
    )
