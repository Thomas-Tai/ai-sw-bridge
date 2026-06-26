"""Offline suite for ``sw_build`` — the elicitation-gated single-part build tool.

Write-gate unification (2026-06-25 audit Option 3): ``sw_build`` must NOT run
the irreversible build (or ``SaveAs3``) over MCP without an explicit in-chat
approval. This suite is the contract guard for that invariant — it asserts the
COM ``build`` callable is invoked EXACTLY when the human approves, and NEVER on
any non-approval path:

    client state          build() COM calls   doc_saved / outcome
    --------------------   ----------------    -------------------
    approve (yes)          1                   build manifest, approved=True
    accept form, no        0                   aborted, declined_in_form
    decline                0                   aborted, declined
    cancel                 0                   aborted, cancelled
    timeout (walk away)    0                   aborted, elicit_timeout
    elicitation unsupported 0                  refused -> ai-sw-build CLI

The COM dispatch (``run_on_executor``) is stubbed to a direct call — there is no
live SOLIDWORKS here — and ``ctx.elicit`` is driven through the REAL SDK
``elicit_with_validation`` against a fake session, so both the SDK's
accept/decline/cancel routing AND the tool's gate are exercised. Mirrors
``tests/mcp_lane/test_batch_execute.py``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

# Gate the whole module on the optional `mcp` SDK (anyio rides along).
pytest.importorskip("mcp", reason="requires `ai-sw-bridge[mcp]` extra")

import mcp.types as types  # noqa: E402
from mcp.server.elicitation import elicit_with_validation  # noqa: E402

from ai_sw_bridge.mcp import _tool_build as mod  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: a minimal valid-shaped spec written to a temp file
# ---------------------------------------------------------------------------

SPEC = {
    "part_name": "widget",
    "features": [
        {"name": "Base", "type": "boss_extrude"},
        {"name": "Hole1", "type": "simple_hole"},
    ],
}


class _FakeBuildResult:
    """Stand-in for spec.builder.BuildResult — only to_dict() is used."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def to_dict(self) -> dict:
        return dict(self._payload)


# ---------------------------------------------------------------------------
# Test doubles (FakeSession / FakeContext mirror test_batch_execute.py)
# ---------------------------------------------------------------------------


class BuildSpy:
    """Stand-in for ``spec.builder.build``. Records each invocation and returns
    a canned BuildResult so a 'success' looks real to the tool."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, spec, **kwargs) -> _FakeBuildResult:
        self.calls.append({"spec": spec, "kwargs": kwargs})
        return _FakeBuildResult(
            {"ok": True, "doc_saved": kwargs.get("save_as") is not None}
        )


class FakeSession:
    """Drives the elicitation wire: capability + canned elicit_form replies."""

    def __init__(self, supports: bool, behavior: str) -> None:
        self.supports = supports
        self.behavior = behavior  # accept_yes|accept_no|decline|cancel|hang

    def check_client_capability(self, capability) -> bool:
        if capability.elicitation is not None and not self.supports:
            return False
        return True

    async def elicit_form(self, message, requestedSchema, related_request_id=None):
        if self.behavior == "hang":
            await asyncio.Event().wait()  # never resolves → wait_for must fire
            raise AssertionError("unreachable")
        if self.behavior == "accept_yes":
            return types.ElicitResult(action="accept", content={"approve": True})
        if self.behavior == "accept_no":
            return types.ElicitResult(action="accept", content={"approve": False})
        if self.behavior == "decline":
            return types.ElicitResult(action="decline")
        if self.behavior == "cancel":
            return types.ElicitResult(action="cancel")
        raise ValueError(self.behavior)


class FakeContext:
    """Minimal FastMCP Context: ``.session`` + ``.elicit`` through the real SDK."""

    def __init__(self, session: FakeSession) -> None:
        self._session = session
        self.request_id = "test-req-build-1"

    @property
    def session(self) -> FakeSession:
        return self._session

    async def elicit(self, message, schema):
        return await elicit_with_validation(
            session=self._session,
            message=message,
            schema=schema,
            related_request_id=self.request_id,
        )


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _get_tool():
    """Pull the registered ``sw_build`` coroutine via a fake mcp."""
    captured: dict = {}

    class _FakeMCP:
        def tool(self):
            def deco(fn):
                captured["fn"] = fn
                return fn

            return deco

    mod.register(_FakeMCP())
    return captured["fn"]


def _patch(monkeypatch, *, timeout=None) -> BuildSpy:
    spy = BuildSpy()
    monkeypatch.setattr(mod, "build", spy)
    # validate() is pure; force it to pass so the gate under test is the human,
    # not the schema (a separate path has its own coverage).
    monkeypatch.setattr(mod, "validate", lambda spec, spec_path=None: None)
    # Bypass the real STA executor — call the (spied) callable directly.
    monkeypatch.setattr(mod, "run_on_executor", lambda fn, *a, **k: fn(*a, **k))
    if timeout is not None:
        monkeypatch.setattr(mod, "ELICIT_TIMEOUT_S", timeout)
    return spy


def _spec_path(tmp_path: Path) -> str:
    p = tmp_path / "widget.json"
    p.write_text(json.dumps(SPEC), encoding="utf-8")
    return str(p)


def _run(
    behavior,
    *,
    supports=True,
    save_as=None,
    monkeypatch,
    tmp_path,
    timeout=None,
):
    spy = _patch(monkeypatch, timeout=timeout)
    fn = _get_tool()
    ctx = FakeContext(FakeSession(supports, behavior))
    out = asyncio.run(fn(_spec_path(tmp_path), ctx, mode="no_dim", save_as=save_as))
    return out, spy


# ---------------------------------------------------------------------------
# The approval path + the 5 non-approval guards
# ---------------------------------------------------------------------------


def test_approve_builds(monkeypatch, tmp_path) -> None:
    out, spy = _run("accept_yes", monkeypatch=monkeypatch, tmp_path=tmp_path)
    # The ONLY path that fires the irreversible build.
    assert len(spy.calls) == 1
    assert out["ok"] is True
    assert out["approved"] is True
    assert out["mcp_mode"] == "elicited_build"
    assert out.get("aborted") is None


def test_approve_with_save_as_writes(monkeypatch, tmp_path) -> None:
    out, spy = _run(
        "accept_yes",
        save_as="C:/out/widget.sldprt",
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )
    assert len(spy.calls) == 1
    assert spy.calls[0]["kwargs"]["save_as"] == "C:/out/widget.sldprt"
    assert out["doc_saved"] is True


def test_accept_form_but_unapproved_does_not_build(monkeypatch, tmp_path) -> None:
    # Client ACCEPTED the prompt but the human ticked approve=False.
    out, spy = _run("accept_no", monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert spy.calls == []  # build NEVER ran
    assert out["aborted"] is True
    assert out["reason"] == "declined_in_form"
    assert out["doc_saved"] is False


def test_decline_does_not_build(monkeypatch, tmp_path) -> None:
    out, spy = _run("decline", monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert spy.calls == []
    assert out["aborted"] is True
    assert out["reason"] == "declined"


def test_cancel_does_not_build(monkeypatch, tmp_path) -> None:
    out, spy = _run("cancel", monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert spy.calls == []
    assert out["aborted"] is True
    assert out["reason"] == "cancelled"


def test_timeout_walkaway_does_not_build_and_does_not_hang(
    monkeypatch, tmp_path
) -> None:
    # Human walks away: elicit_form never resolves. asyncio.wait_for must fire;
    # the build phase must never run. This IS the regression guard against a
    # missing timeout bound (it would hang the process otherwise).
    out, spy = _run("hang", monkeypatch=monkeypatch, tmp_path=tmp_path, timeout=0.05)
    assert spy.calls == []
    assert out["aborted"] is True
    assert out["reason"] == "elicit_timeout"
    assert out["doc_saved"] is False


def test_elicitation_unsupported_degrades_to_cli(monkeypatch, tmp_path) -> None:
    # No capability → refuse BEFORE any COM, point at the headless CLI.
    out, spy = _run(
        "accept_yes", supports=False, monkeypatch=monkeypatch, tmp_path=tmp_path
    )
    assert spy.calls == []  # build never dispatched
    assert out["ok"] is False
    assert out["aborted"] is True
    assert out["reason"] == "elicitation_unsupported"
    assert "ai-sw-build" in out["next_step"]
