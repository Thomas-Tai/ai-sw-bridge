"""Fixtures for the unified end-to-end SW test suite.

Tests in this directory all carry ``@pytest.mark.solidworks_only`` so
the root conftest's auto-skip hook handles CI gating. Fixtures here
provide:

* paths to canonical sample specs from ``examples/``
* a per-test ``ServerRuntime`` builder with the real (non-mock)
  adapter — so observe.* calls actually hit the live SW process
* a temporary checkpoint root that gets cleaned between tests so the
  history/checkpoint tests don't share state

The fixtures intentionally do NOT open or save any specific SW
document — tests own their document lifecycle. The runtime's executor
+ adapter are started in the fixture and torn down on yield exit.

All tests also carry ``@pytest.mark.destructive_sw``: the live COM
executor's worker thread can trigger a Windows structured exception
(SEH, e.g. ``0x800401FD``) when the SW dispatch handle goes stale,
which crashes the entire pytest process. Run in isolation::

    pytest -m destructive_sw tests/e2e_sw/ -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest


def pytest_collection_modifyitems(items):
    """Mark every test in this directory as destructive_sw."""
    for item in items:
        if "e2e_sw" in str(item.fspath):
            item.add_marker(pytest.mark.destructive_sw)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES_ROOT = REPO_ROOT / "examples"


@pytest.fixture
def minimal_cylinder_spec_path() -> Path:
    """Path to the smallest reversible spec — 2 features, no external deps."""
    return EXAMPLES_ROOT / "minimal_cylinder" / "spec.json"


@pytest.fixture
def chamfered_box_spec_path() -> Path:
    """Path to a multi-feature spec exercising sketch + extrude + chamfer."""
    return EXAMPLES_ROOT / "chamfered_box" / "spec.json"


@pytest.fixture
def e2e_checkpoint_root(tmp_path: Path) -> Path:
    """Per-test checkpoint directory under pytest's tmp_path.

    Avoids the real ``.checkpoints/`` so concurrent runs / leftover
    state from prior runs don't contaminate the test.
    """
    root = tmp_path / "checkpoints"
    root.mkdir()
    return root


@pytest.fixture
def live_runtime() -> Iterator[Any]:
    """A ServerRuntime backed by the real (pywin32) adapter.

    Started + stopped per test. The adapter.connect() may auto-launch
    SOLIDWORKS if no process is running — that's COM's default
    behavior and is acceptable for E2E setup.
    """
    from ai_sw_bridge.mcp.runtime import ServerRuntime
    import ai_sw_bridge.sw_com as sw_com

    # Drop any process-global cached dispatch left over from a previous
    # test — fixes the cross-test STA-thread cache-leak finding from
    # Wave 5 Phase 2.5 audit.
    sw_com.release_sw_app()

    runtime = ServerRuntime.create()
    runtime.adapter.connect()
    runtime.executor.start()
    try:
        yield runtime
    finally:
        runtime.shutdown()


@pytest.fixture
def live_mcp(live_runtime) -> Any:
    """A live FastMCP server wrapped around live_runtime — for direct
    tool-call tests that bypass the JSON-RPC wire layer.
    """
    from ai_sw_bridge.mcp.server import create_server

    return create_server(live_runtime)


@pytest.fixture
def live_tools(live_mcp) -> dict[str, Any]:
    """Dict of {tool_name: tool_record} — convenient for calling
    ``live_tools['sw_bbox'].fn()`` instead of walking iter_tools().
    """
    return {t.name: t for t in live_mcp.iter_tools()}


@pytest.fixture
def ai_sw_mcp_exe() -> str:
    """Resolve the path to the ai-sw-mcp console script.

    Tests that spawn the MCP server as a subprocess (the proper wire-
    level E2E check) use this rather than ``sys.executable -m`` so
    they exercise the entry point users actually invoke.
    """
    import shutil

    exe = shutil.which("ai-sw-mcp")
    if exe is None:
        # Fall back to the Python-module form; this still tests the
        # server but bypasses the entry-point wiring.
        import sys

        return f'"{sys.executable}" -m ai_sw_bridge.mcp.server'
    return exe
