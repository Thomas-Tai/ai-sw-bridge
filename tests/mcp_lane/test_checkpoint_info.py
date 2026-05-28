"""Regression: ``sw_checkpoint_info`` against a real encrypted DB.

The W5.5 snapshot fixture exercises only the "DB not found" branch,
so it didn't catch a real bug found by Wave 5 audit: the MCP tool
queried ``SELECT key, value FROM _meta`` against a column-per-field
``_meta`` table (schema in checkpoint/store.py:90). Every encrypted
DB would have raised ``OperationalError``.

This test creates a real encrypted CheckpointStore, runs the MCP
tool against it, and asserts the payload mirrors the CLI surface
(cli/checkpoint.py:60). It is the live-DB counterpart to the
snapshot fixture's empty-path coverage.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.checkpoint.crypto import KeySource, generate_key
from ai_sw_bridge.checkpoint.store import CheckpointStore
from ai_sw_bridge.mcp.runtime import ServerRuntime
from ai_sw_bridge.mcp.server import create_server


@pytest.fixture
def mcp_server():
    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.adapter.connect()
    runtime.executor.start()
    mcp = create_server(runtime)
    try:
        yield mcp
    finally:
        runtime.shutdown()


def _call_tool(mcp, name: str, **kwargs):
    tool = next(t for t in mcp.iter_tools() if t.name == name)
    return tool.fn(**kwargs)


def test_sw_checkpoint_info_against_encrypted_db(
    mcp_server, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sw_checkpoint_info reads the real ``_meta`` column schema."""
    key = generate_key().decode()
    monkeypatch.setenv("AI_SW_TEST_KEY", key)
    src = KeySource.parse("env:AI_SW_TEST_KEY")
    store = CheckpointStore("part_x", root=tmp_path, key_source=src)
    store.insert_pending(
        feature_index=0,
        feature_name="x",
        feature_type="sketch",
        locals_snapshot="{}",
        spec_hash="0" * 64,
        pre_tree_hash="1" * 64,
        build_mode="deferred-dim",
    )
    store.close()

    payload = _call_tool(
        mcp_server,
        "sw_checkpoint_info",
        part_name="part_x",
        root=str(tmp_path),
    )

    assert payload["ok"] is True
    assert payload["part"] == "part_x"
    assert payload["encrypted"] is True
    assert payload["encryption_algo"] == "fernet-v1"
    assert isinstance(payload["key_fingerprint"], str)
    assert payload["encrypted_columns"] == ["locals_snapshot", "com_call_log"]


def test_sw_checkpoint_info_against_plain_db(mcp_server, tmp_path) -> None:
    """Plain (unencrypted) DB returns encrypted=False with full key set."""
    store = CheckpointStore("part_y", root=tmp_path)
    store.insert_pending(
        feature_index=0,
        feature_name="y",
        feature_type="sketch",
        locals_snapshot="{}",
        spec_hash="0" * 64,
        pre_tree_hash="1" * 64,
        build_mode="deferred-dim",
    )
    store.close()

    payload = _call_tool(
        mcp_server,
        "sw_checkpoint_info",
        part_name="part_y",
        root=str(tmp_path),
    )

    assert payload["ok"] is True
    assert payload["part"] == "part_y"
    assert payload["encrypted"] is False
    assert payload["encryption_algo"] is None
    assert payload["key_fingerprint"] is None
    assert payload["encrypted_columns"] == []
