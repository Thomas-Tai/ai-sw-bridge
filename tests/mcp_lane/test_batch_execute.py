"""Offline suite for ``sw_batch_execute`` — the elicitation-gated batch tool.

Graduated from the measure-first witness (``scratchpad/elicit_witness.py``).
Asserts that for every client state the tool routes to the correct transaction
and that the underlying engine ``_sw_batch_feature_add_impl`` is invoked exactly
the right number of times with the correct ``dry_run`` flags:

    client state          engine calls (dry_run flags)   doc_saved
    --------------------   ----------------------------   ---------
    approve (yes)          [True, False]  PLAN + COMMIT   True
    accept form, no        [True]         PLAN only       False
    decline                [True]         PLAN only       False
    cancel                 [True]         PLAN only       False
    timeout (walk away)    [True]         PLAN only       False
    elicitation unsupported []            (no plan)       False
    plan invalid           [True]         PLAN only       False

The COM dispatch (``run_on_executor``) is stubbed to a direct call — there is no
live SOLIDWORKS here — and ``ctx.elicit`` is driven through the REAL SDK
``elicit_with_validation`` against a fake session, so both the SDK's
accept/decline/cancel routing AND the tool's transaction routing are exercised.

No pytest-asyncio coupling: each coroutine is driven with ``asyncio.run`` from a
plain sync test, so the suite passes regardless of the project's asyncio_mode.
"""

from __future__ import annotations

import asyncio

import pytest

# Gate the whole module on the optional `mcp` SDK (anyio rides along).
pytest.importorskip("mcp", reason="requires `ai-sw-bridge[mcp]` extra")

import mcp.types as types  # noqa: E402
from mcp.server.elicitation import elicit_with_validation  # noqa: E402

from ai_sw_bridge.mcp import _tool_batch_execute as mod  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: canned manifests + a 2-feature batch
# ---------------------------------------------------------------------------

PROPOSALS = [
    {"feature": {"type": "fillet"}, "target": {"edge": "E1"}},
    {"feature": {"type": "chamfer"}, "target": {"edge": "E2"}},
]

GREEN_PLAN = {
    "ok": True,
    "dry_run": True,
    "doc_saved": False,
    "total": 2,
    "committed": [
        {"index": 0, "kind": "fillet", "note": "2mm"},
        {"index": 1, "kind": "chamfer", "note": "1mm"},
    ],
    "fault": None,
}

GREEN_COMMIT = {
    "ok": True,
    "dry_run": False,
    "doc_saved": True,
    "total": 2,
    "committed": [
        {"index": 0, "kind": "fillet", "note": "2mm"},
        {"index": 1, "kind": "chamfer", "note": "1mm"},
    ],
    "fault": None,
}

BAD_PLAN = {
    "ok": False,
    "dry_run": True,
    "doc_saved": False,
    "total": 2,
    "committed": [{"index": 0, "kind": "fillet", "note": "2mm"}],
    "fault": {
        "index": 1,
        "kind": "chamfer",
        "stage": "apply",
        "error": "handler returned False",
        "feature": {"type": "chamfer"},
        "target": {"edge": "E2"},
    },
}


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class EngineSpy:
    """Stand-in for ``_sw_batch_feature_add_impl``. Records each call's flags
    and returns the canned plan (dry_run=True) or commit (dry_run=False)."""

    def __init__(self, plan: dict, commit: dict | None = None) -> None:
        self.plan = plan
        self.commit = commit
        self.calls: list[dict] = []

    def __call__(self, *, doc_path, proposals, strict, dry_run) -> dict:
        self.calls.append({"dry_run": dry_run, "strict": strict, "doc_path": doc_path})
        return dict(self.plan if dry_run else self.commit)

    @property
    def dry_run_flags(self) -> list[bool]:
        return [c["dry_run"] for c in self.calls]


class FakeSession:
    """Drives the elicitation wire: capability + canned elicit_form replies."""

    def __init__(self, supports: bool, behavior: str) -> None:
        self.supports = supports
        self.behavior = behavior  # accept_yes|accept_no|decline|cancel|hang

    def check_client_capability(self, capability) -> bool:
        # Mirror ServerSession.check_client_capability for the elicitation bit.
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
    """Minimal FastMCP Context stand-in: ``.session`` + ``.elicit`` that routes
    through the real SDK ``elicit_with_validation`` (exactly as the real
    ``Context.elicit`` does)."""

    def __init__(self, session: FakeSession) -> None:
        self._session = session
        self.request_id = "test-req-1"

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
    """Pull the registered ``sw_batch_execute`` coroutine via a fake mcp."""
    captured: dict = {}

    class _FakeMCP:
        def tool(self):
            def deco(fn):
                captured["fn"] = fn
                return fn

            return deco

    mod.register(_FakeMCP())
    return captured["fn"]


def _patch(monkeypatch, plan, commit=None, timeout=None) -> EngineSpy:
    spy = EngineSpy(plan, commit)
    monkeypatch.setattr(mod, "_sw_batch_feature_add_impl", spy)
    # Bypass the real STA executor — just call the (spied) engine directly.
    monkeypatch.setattr(mod, "run_on_executor", lambda fn, *a, **k: fn(*a, **k))
    if timeout is not None:
        monkeypatch.setattr(mod, "ELICIT_TIMEOUT_S", timeout)
    return spy


def _run(
    behavior,
    *,
    supports=True,
    plan=GREEN_PLAN,
    commit=GREEN_COMMIT,
    monkeypatch,
    timeout=None,
):
    spy = _patch(monkeypatch, plan, commit, timeout)
    fn = _get_tool()
    ctx = FakeContext(FakeSession(supports, behavior))
    out = asyncio.run(fn("C:/parts/widget.sldprt", PROPOSALS, ctx))
    return out, spy


# ---------------------------------------------------------------------------
# The 5 client states + 2 guards
# ---------------------------------------------------------------------------


def test_approve_commits(monkeypatch) -> None:
    out, spy = _run("accept_yes", monkeypatch=monkeypatch)
    # PLAN then COMMIT — the only path that fires the irreversible write.
    assert spy.dry_run_flags == [True, False]
    assert out["doc_saved"] is True
    assert out["ok"] is True
    assert out["approved"] is True
    assert out["mcp_mode"] == "elicited_commit"
    assert out.get("aborted") is None


def test_accept_form_but_unapproved_does_not_commit(monkeypatch) -> None:
    # Subtle: client ACCEPTED the prompt but the human ticked approve=False.
    # Must NOT be mistaken for a commit.
    out, spy = _run("accept_no", monkeypatch=monkeypatch)
    assert spy.dry_run_flags == [True]  # PLAN only, no commit
    assert out["aborted"] is True
    assert out["reason"] == "declined_in_form"
    assert out["doc_saved"] is False


def test_decline_does_not_commit(monkeypatch) -> None:
    out, spy = _run("decline", monkeypatch=monkeypatch)
    assert spy.dry_run_flags == [True]
    assert out["aborted"] is True
    assert out["reason"] == "declined"
    assert out["doc_saved"] is False


def test_cancel_does_not_commit(monkeypatch) -> None:
    out, spy = _run("cancel", monkeypatch=monkeypatch)
    assert spy.dry_run_flags == [True]
    assert out["aborted"] is True
    assert out["reason"] == "cancelled"
    assert out["doc_saved"] is False


def test_timeout_walkaway_does_not_commit_and_does_not_hang(monkeypatch) -> None:
    # Human walks away: elicit_form never resolves. asyncio.wait_for must fire;
    # the commit phase must never run. If the bound were missing this test
    # would hang the process — it IS the regression guard for that.
    out, spy = _run("hang", monkeypatch=monkeypatch, timeout=0.05)
    assert spy.dry_run_flags == [True]  # PLAN only
    assert out["aborted"] is True
    assert out["reason"] == "elicit_timeout"
    assert out["doc_saved"] is False


def test_elicitation_unsupported_degrades_to_cli(monkeypatch) -> None:
    # No capability → refuse BEFORE any COM, point at sw_batch_plan + CLI.
    out, spy = _run("accept_yes", supports=False, monkeypatch=monkeypatch)
    assert spy.calls == []  # not even the dry-run plan dispatched
    assert out["ok"] is False
    assert out["aborted"] is True
    assert out["reason"] == "elicitation_unsupported"
    assert out["doc_saved"] is False
    assert "ai-sw-batch" in out["next_step"]


def test_plan_invalid_aborts_before_elicit(monkeypatch) -> None:
    # A failing dry-run must short-circuit: no elicitation, no commit. The
    # behavior is accept_yes to prove the gate is the PLAN result, not the human.
    out, spy = _run("accept_yes", plan=BAD_PLAN, monkeypatch=monkeypatch)
    assert spy.dry_run_flags == [True]  # PLAN only; commit never dispatched
    assert out["aborted"] is True
    assert out["reason"] == "plan_invalid"
    assert out["doc_saved"] is False
    assert out["fault"]["kind"] == "chamfer"
