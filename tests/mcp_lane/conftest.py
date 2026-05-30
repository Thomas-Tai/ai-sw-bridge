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
    """Mark every test in this directory as destructive_sw."""
    for item in items:
        if "mcp_lane" in str(item.fspath):
            item.add_marker(pytest.mark.destructive_sw)
