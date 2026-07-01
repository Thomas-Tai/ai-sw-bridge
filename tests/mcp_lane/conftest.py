"""Fixtures for the MCP lane tests.

These tests use a mock adapter but still start the real ``ComExecutor``
background thread (``[SolidWorks-MCP-COM]``). The tool implementations
call real COM functions; the mock only covers adapter.connect().

If the SW dispatch handle goes stale mid-suite, the worker thread
triggers a Windows structured exception (SEH, e.g. ``0x8001010E``)
that crashes the entire pytest process. Mark all tests here as
``destructive_sw`` so they run only in isolation::

    pytest -m destructive_sw tests/mcp_lane/ -v
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items):
    """Mark every test in this directory as destructive_sw and mcp_lane_live.

    ``destructive_sw`` keeps the existing blanket skip (SEH-crash risk, must
    run isolated). ``mcp_lane_live`` is the finer marker: it lets a future CI
    job select ``-m mcp_lane_live`` to run this directory's live MCP
    write-gate lane specifically, without pulling in every other
    seat-killing ``destructive_sw`` test elsewhere in the suite.

    ``test_registration.py`` is exempt: it is a pure stdlib/tmp_path unit
    test for the MCP-client registrar (no ComExecutor, no server, no COM
    touch at all) and must run in the normal seat-safe suite.
    """
    for item in items:
        if "mcp_lane" in str(item.fspath) and "test_registration.py" not in str(
            item.fspath
        ):
            item.add_marker(pytest.mark.destructive_sw)
            item.add_marker(pytest.mark.mcp_lane_live)
