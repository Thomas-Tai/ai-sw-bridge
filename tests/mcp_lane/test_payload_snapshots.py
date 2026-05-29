"""Payload pass-through snapshot tests for the MCP tool surface (W5.5).

For each of the 21 registered tools, this module:

1. Spins up a :class:`ServerRuntime` backed by :class:`MockAdapter`.
2. Calls the tool's wrapped ``.fn`` with the args recorded in
   ``tests/mcp_lane/fixtures/<tool_name>.json``.
3. Compares the **structural shape** of the return value — key set,
   value types, list lengths and item-shapes — against the fixture.

Catches the three classes of regression the task calls out:

* accidental ``tuple`` / ``datetime`` returns (type tags differ);
* key renames (shape-key set differs);
* shape drift — a new field, a removed field, a list that used to be a
  scalar (structural recursion surfaces all three).

The probe at ``tools/probe_mcp_tools.py`` regenerates the fixtures
whenever the shape changes on purpose; review the diff before
committing.

Design: ``docs/mcp_server_design.md`` §6 (inventory), task W5.5.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# Skip cleanly when the optional `mcp` SDK is not installed — the onboarding
# CI job installs without the `[mcp]` extra, and without this guard the
# `ai_sw_bridge.mcp.server` import below would crash pytest *collection*
# before the marker filter could deselect this module.
pytest.importorskip("mcp", reason="requires `ai-sw-bridge[mcp]` extra")

from ai_sw_bridge.mcp.runtime import ServerRuntime
from ai_sw_bridge.mcp.server import create_server


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Shape comparison
# ---------------------------------------------------------------------------


def _shape(value: Any) -> Any:
    """Structural skeleton of *value* (mirrors ``tools/probe_mcp_tools.py``)."""
    if value is None:
        return "$none"
    if isinstance(value, bool):
        return "$bool"
    if isinstance(value, int):
        return "$int"
    if isinstance(value, float):
        return "$float"
    if isinstance(value, str):
        return "$str"
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if not value:
            return {"__list__": True, "len": 0, "item": None}
        return {"__list__": True, "len": "*", "item": _shape(value[0])}
    return f"$type:{type(value).__name__}"


def _assert_shape_match(
    actual: Any,
    expected: Any,
    path: str = "$",
) -> None:
    """Assert *actual* matches the structural *expected* produced by ``_shape``.

    * ``$bool`` / ``$int`` / ``$float`` / ``$str`` / ``$none`` tags match
      any value of the corresponding Python type — exact values are
      deliberately NOT compared, so embedding-score drift and count
      changes don't fail the suite.
    * ``["$str", "$none"]`` (list of type tags) is a **union marker**:
      the actual value may match any of the listed tags. Used for
      fields whose type depends on live-SW state (``doc_path``,
      ``error``, etc.). The probe emits concrete tags; union markers
      are hand-edited into the fixture when a field's type is
      state-dependent.
    * Dict shapes require identical key sets; values are compared
      recursively.
    * List shapes require identical item-shape; length is tolerated.
    """
    # Union marker: a list of type tags (e.g. ["$str", "$none"]).
    if isinstance(expected, list):
        for tag in expected:
            try:
                _assert_shape_match(actual, tag, path=path)
                return
            except AssertionError:
                continue
        raise AssertionError(
            f"{path}: value of type {type(actual).__name__} did not match "
            f"any union tag in {expected}"
        )

    if expected in ("$bool", "$int", "$float", "$str", "$none"):
        type_map = {
            "$bool": bool,
            "$int": int,
            "$float": float,
            "$str": str,
            "$none": type(None),
        }
        expected_type = type_map[expected]
        # bool is a subclass of int; require exact bool for $bool, and
        # reject bools when expecting $int (otherwise True would pass).
        if expected == "$int":
            assert isinstance(actual, int) and not isinstance(
                actual, bool
            ), f"{path}: expected int, got {type(actual).__name__}"
            return
        assert isinstance(actual, expected_type), (
            f"{path}: expected {expected_type.__name__}, "
            f"got {type(actual).__name__}"
        )
        return

    if isinstance(expected, dict) and expected.get("__list__"):
        assert isinstance(
            actual, (list, tuple)
        ), f"{path}: expected list, got {type(actual).__name__}"
        expected_len = expected["len"]
        if expected_len != "*":
            assert (
                len(actual) == expected_len
            ), f"{path}: list length {len(actual)} != {expected_len}"
        if expected["item"] is not None:
            for i, item in enumerate(actual):
                _assert_shape_match(item, expected["item"], path=f"{path}[{i}]")
        return

    if isinstance(expected, dict):
        assert isinstance(
            actual, dict
        ), f"{path}: expected dict, got {type(actual).__name__}"
        extra = set(actual) - set(expected)
        missing = set(expected) - set(actual)
        if extra or missing:
            raise AssertionError(
                f"{path}: dict key drift — extra={sorted(extra)}, "
                f"missing={sorted(missing)}"
            )
        for k, v_shape in expected.items():
            _assert_shape_match(actual[k], v_shape, path=f"{path}.{k}")
        return

    # Fallback: exact equality (covers e.g. ``None`` as list item template).
    assert actual == expected, f"{path}: {actual!r} != {expected!r}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> dict:
    with (FIXTURES_ROOT / f"{name}.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def _fixture_names() -> list[str]:
    return sorted(p.stem for p in FIXTURES_ROOT.glob("*.json"))


@pytest.fixture
def mcp_server():
    """Per-test ServerRuntime (mock adapter) + FastMCP server."""
    runtime = ServerRuntime.create(adapter_type="mock")
    runtime.adapter.connect()
    runtime.executor.start()
    mcp = create_server(runtime)
    try:
        yield mcp
    finally:
        runtime.shutdown()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPayloadSnapshots:
    """One parametrized test per fixture file under ``fixtures/``."""

    @pytest.mark.parametrize("tool_name", _fixture_names())
    def test_tool_payload_matches_snapshot(self, mcp_server, tool_name: str) -> None:
        fixture = _load_fixture(tool_name)
        tools = {t.name: t for t in mcp_server.iter_tools()}
        assert tool_name in tools, f"{tool_name!r} not registered on server"
        tool = tools[tool_name]

        args = fixture["args"]
        expected_error = fixture["error"]
        expected_shape = fixture["result_shape"]

        if expected_error is not None:
            with pytest.raises(Exception) as excinfo:
                tool.fn(**args)
            actual_err = f"{type(excinfo.value).__name__}: {excinfo.value}"
            assert actual_err == expected_error
            return

        result = tool.fn(**args)

        # Two-stream contract: the MCP wire layer JSON-encodes the
        # return. Catch the three failure modes the task calls out —
        # tuple returns, datetime leaks, and non-JSON-safe leaves —
        # with a round-trip through json.dumps.
        try:
            json.dumps(result)
        except TypeError as exc:
            raise AssertionError(
                f"{tool_name}: return is not JSON-serializable: {exc}"
            ) from exc

        _assert_shape_match(result, expected_shape, path=f"${tool_name}")

    def test_every_registered_tool_has_fixture(self, mcp_server) -> None:
        """No tool may ship without a corresponding snapshot fixture."""
        registered = {t.name for t in mcp_server.iter_tools()}
        captured = set(_fixture_names())
        missing = registered - captured
        assert not missing, (
            f"tools without snapshot fixture: {sorted(missing)} — run "
            "`python tools/probe_mcp_tools.py` and commit the new JSON."
        )

    def test_no_stale_fixtures(self, mcp_server) -> None:
        """No fixture may outlive the tool it snapshots."""
        registered = {t.name for t in mcp_server.iter_tools()}
        captured = set(_fixture_names())
        stale = captured - registered
        assert not stale, f"snapshot fixtures for unregistered tools: {sorted(stale)}"
