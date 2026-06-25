"""SupervisedSession against the DURABLE SQLite journal (TransactionStoreJournal).

Proves the state machine holds with the real persistence layer substituted for
the in-memory journal, and that the PENDING|COMMITTED boundary lands correctly
on disk — including the crash anchor: a fatal/unrecovered run leaves the row
PENDING (the resume queue), a recovered run flips it to COMMITTED.
"""

from __future__ import annotations

import json
from typing import Any

from ai_sw_bridge.checkpoint import TransactionStatus, TransactionStore
from ai_sw_bridge.resilience import TransactionStoreJournal
from ai_sw_bridge.resilience.session import SupervisedSession

PROPOSALS = [
    {"feature": {"type": "fillet"}, "target": {"edge": f"E{i}"}} for i in range(3)
]


# --- minimal fakes (self-contained; the seat/clock never sleep) -------------


class FakeClock:
    def now(self) -> float:
        return 0.0

    def sleep(self, seconds: float) -> None:  # pragma: no cover
        pass


class FakeSeat:
    def __init__(self, alive_script: list[bool]) -> None:
        self._alive = list(alive_script)
        self.respawn_calls = 0

    @property
    def pid(self) -> int | None:
        return 1000

    def is_alive(self) -> bool:
        return self._alive.pop(0) if self._alive else True

    def respawn(self) -> None:
        self.respawn_calls += 1


class FakeSnapshotter:
    def snapshot(self, doc_path: str) -> str:
        return f"tok::{doc_path}"

    def restore(self, token: Any) -> None:
        pass

    def discard(self, token: Any) -> None:
        pass


class ScriptedRunner:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, doc_path, proposals, *, strict=False):
        self.calls += 1
        out = self._outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


def _ok():
    return {
        "ok": True,
        "doc_path": "p",
        "committed": [{"index": i} for i in range(3)],
        "fault": None,
    }


def _fault(stage, index):
    return {
        "ok": False,
        "doc_path": "p",
        "committed": [],
        "fault": {"index": index, "stage": stage, "error": "down"},
    }


def _session(runner, seat, journal):
    return SupervisedSession(
        batch_runner=runner,
        seat=seat,
        journal=journal,
        snapshotter=FakeSnapshotter(),
        clock=FakeClock(),
    )


def _journal(tmp_path):
    return TransactionStoreJournal(TransactionStore(root=tmp_path))


# --- the integration proofs -------------------------------------------------


def test_clean_success_commits_durably(tmp_path):
    store = TransactionStore(root=tmp_path)
    j = TransactionStoreJournal(store)
    out = _session(ScriptedRunner([_ok()]), FakeSeat([]), j).execute("doc", PROPOSALS)
    assert out["ok"] is True
    assert store.get_pending_transactions() == []  # nothing left dangling
    rows = _all_rows(store)
    assert len(rows) == 1
    assert rows[0].status is TransactionStatus.COMMITTED
    assert rows[0].doc_path == "doc"
    assert json.loads(rows[0].intent_payload) == PROPOSALS


def test_tier1_recovery_commits_and_payload_is_the_intent(tmp_path):
    store = TransactionStore(root=tmp_path)
    j = TransactionStoreJournal(store)
    runner = ScriptedRunner([_fault("apply", 2), _ok()])
    out = _session(runner, FakeSeat([False]), j).execute("doc", PROPOSALS)
    assert out["ok"] is True and out["recovery"]["tier"] == 1

    # one transaction, now COMMITTED, with the proposal list as intent payload.
    assert store.get_pending_transactions() == []
    # dig the row out by listing all (no pending) -> query committed via a fresh
    # connection: reopen and confirm persistence + payload.
    store2 = TransactionStore(root=tmp_path)
    # the only row should be committed; reconstruct it via get on the id we know
    # is the single row — fetch through a direct status check.
    committed = _all_rows(store2)
    assert len(committed) == 1
    row = committed[0]
    assert row.status is TransactionStatus.COMMITTED
    assert json.loads(row.intent_payload) == PROPOSALS


def test_tier1_recovery_persists_recovery_summary(tmp_path):
    """A caught death -> the committed row carries the recovery summary
    (tier/replays/deaths) so sw_session_health can report it durably."""
    store = TransactionStore(root=tmp_path)
    j = TransactionStoreJournal(store)
    runner = ScriptedRunner([_fault("apply", 2), _ok()])
    out = _session(runner, FakeSeat([False]), j).execute("doc", PROPOSALS)
    assert out["ok"] is True

    lr = store.last_recovered()
    assert lr is not None
    rec = json.loads(lr.recovery_json)
    assert rec["tier"] == 1 and rec["replays"] == 1
    assert len(rec["deaths"]) == 1


def test_clean_success_persists_no_recovery_summary(tmp_path):
    """A non-recovered (clean) commit leaves recovery_json NULL."""
    store = TransactionStore(root=tmp_path)
    j = TransactionStoreJournal(store)
    _session(ScriptedRunner([_ok()]), FakeSeat([]), j).execute("doc", PROPOSALS)
    assert store.last_recovered() is None  # nothing carried a recovery summary


def test_fatal_poison_leaves_row_pending_as_resume_anchor(tmp_path):
    """Same proposal dies twice -> poison-fatal. The session does NOT commit,
    so the durable row stays PENDING — the host-crash/resume anchor."""
    store = TransactionStore(root=tmp_path)
    j = TransactionStoreJournal(store)
    runner = ScriptedRunner([_fault("apply", 2), _fault("apply", 2)])
    out = _session(runner, FakeSeat([False, False]), j).execute("doc", PROPOSALS)
    assert out["ok"] is False
    assert out["recovery"]["poison_proposal"] == 2

    pending = store.get_pending_transactions()
    assert len(pending) == 1  # the unfinished transaction is still discoverable
    assert pending[0].status is TransactionStatus.PENDING
    assert json.loads(pending[0].intent_payload) == PROPOSALS  # full replay intent


def _all_rows(store: TransactionStore):
    """Test helper: every row regardless of status (the store exposes only
    pending + get-by-id, so reach through the connection for the assertion)."""
    conn = store._connect()  # noqa: SLF001 — test-only introspection
    ids = [r[0] for r in conn.execute("SELECT id FROM transactions").fetchall()]
    return [store.get(i) for i in ids]
