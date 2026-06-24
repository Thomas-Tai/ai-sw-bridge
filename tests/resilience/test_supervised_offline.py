"""Offline gauntlet for SupervisedSession — the state machine, no seat, no sleep.

Implements cases 1-6 of docs/supervised_session_test_spec.md §4. Every collaborator
is a fake; both measured death signatures are reconstructed as plain objects; the
clock is fake so the respawn-budget / cap / poison logic runs in microseconds.
"""

from __future__ import annotations

from typing import Any

from ai_sw_bridge.resilience.session import (
    SeatRespawnTimeout,
    SupervisedSession,
)

# Both measured fault signatures, as plain objects (no seat needed).
RPC_DEAD = None
try:
    import pywintypes

    RPC_DEAD = pywintypes.com_error(
        -2147023174, "The RPC server is unavailable.", None, None
    )  # 0x800706BA
except Exception:  # pragma: no cover - pywin32 always present on the target
    RPC_DEAD = OSError("RPC server unavailable")
DYN_DEAD = AttributeError("SldWorks.Application.RevisionNumber")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleep_calls: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:  # pragma: no cover - envelope never calls
        self.sleep_calls.append(seconds)
        self.t += seconds

    def advance(self, dt: float) -> None:
        self.t += dt


class FakeSeat:
    """is_alive() yields scripted booleans; respawn() bumps pid (+ optional clock)."""

    def __init__(
        self,
        alive_script: list[bool],
        *,
        clock: FakeClock | None = None,
        respawn_cost_s: float = 0.0,
        respawn_raises: bool = False,
    ) -> None:
        self._alive = list(alive_script)
        self._pid = 1000
        self.respawn_calls = 0
        self._clock = clock
        self._cost = respawn_cost_s
        self._raises = respawn_raises

    @property
    def pid(self) -> int | None:
        return self._pid

    def is_alive(self) -> bool:
        return self._alive.pop(0) if self._alive else True

    def respawn(self) -> None:
        self.respawn_calls += 1
        if self._raises:
            raise SeatRespawnTimeout("fake respawn timeout")
        self._pid += 1
        if self._clock and self._cost:
            self._clock.advance(self._cost)


class FakeSnapshotter:
    def __init__(self) -> None:
        self.snapshots = 0
        self.restores = 0
        self.discards = 0

    def snapshot(self, doc_path: str) -> str:
        self.snapshots += 1
        return f"token::{doc_path}"

    def restore(self, token: Any) -> None:
        self.restores += 1

    def discard(self, token: Any) -> None:
        self.discards += 1


class ScriptedRunner:
    """Returns/raises a scripted sequence of batch outcomes, one per call."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, doc_path: str, proposals: list, *, strict: bool = False) -> dict:
        self.calls += 1
        out = self._outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


def manifest_ok(committed_idx: list[int]) -> dict:
    return {
        "ok": True,
        "doc_path": "p",
        "doc_saved": True,
        "committed": [{"index": i, "kind": "fillet"} for i in committed_idx],
        "fault": None,
    }


def manifest_fault(
    stage: str, index: int | None, *, committed_idx: list[int] = ()
) -> dict:
    return {
        "ok": False,
        "doc_path": "p",
        "doc_saved": False,
        "committed": [{"index": i, "kind": "fillet"} for i in committed_idx],
        "fault": {
            "index": index,
            "kind": "fillet",
            "stage": stage,
            "error": (
                "AttributeError: face not found" if stage == "apply" else "RPC down"
            ),
            "feature": {"type": "fillet"},
            "target": {"edge": "Edge1"},
        },
    }


def _session(runner, seat, *, snap=None, clock=None, **kw) -> SupervisedSession:
    return SupervisedSession(
        batch_runner=runner,
        seat=seat,
        snapshotter=snap or FakeSnapshotter(),
        clock=clock or FakeClock(),
        **kw,
    )


PROPOSALS = [
    {"feature": {"type": "fillet"}, "target": {"edge": f"E{i}"}} for i in range(3)
]


# ---------------------------------------------------------------------------
# Case 1 — the liveness oracle (the safety-critical disambiguation)
# ---------------------------------------------------------------------------


def test_benign_fault_seat_alive_is_NOT_a_respawn():
    """Handler AttributeError + LIVE seat = genuine geometric fault -> propagate."""
    runner = ScriptedRunner([manifest_fault("apply", 1)])
    seat = FakeSeat([True])  # seat alive
    snap = FakeSnapshotter()
    out = _session(runner, seat, snap=snap).execute("p", PROPOSALS)

    assert out["ok"] is False  # the genuine fault is preserved
    assert out["fault"]["index"] == 1
    assert out["recovery"]["deaths"] == []  # no death recorded
    assert seat.respawn_calls == 0  # NO respawn
    assert snap.restores == 0
    assert runner.calls == 1  # NOT replayed


def test_fault_seat_dead_triggers_tier1_respawn_and_recovers():
    """Same fault shape but seat DEAD -> reclassify as death -> respawn -> replay."""
    runner = ScriptedRunner([manifest_fault("apply", 2), manifest_ok([0, 1, 2])])
    seat = FakeSeat([False])  # dead on the faulted attempt
    snap = FakeSnapshotter()
    out = _session(runner, seat, snap=snap).execute("p", PROPOSALS)

    assert out["ok"] is True
    rec = out["recovery"]
    assert rec["recovered"] is True
    assert rec["replays"] == 1
    assert rec["tier"] == 1
    assert len(rec["deaths"]) == 1
    assert rec["deaths"][0]["proposal_index"] == 2
    assert seat.respawn_calls == 1
    assert snap.restores == 0  # Tier 1 never restores
    assert runner.calls == 2


def test_raised_com_error_seat_dead_is_recovered():
    """An escaped com_error 0x800706BA with a dead seat is a death, not a crash."""
    runner = ScriptedRunner([RPC_DEAD, manifest_ok([0, 1, 2])])
    seat = FakeSeat([False])
    out = _session(runner, seat).execute("p", PROPOSALS)
    assert out["ok"] is True
    assert out["recovery"]["recovered"] is True
    assert out["recovery"]["deaths"][0]["phase"] == "raised"
    assert "0x800706ba" in out["recovery"]["deaths"][0]["fault"]


def test_raised_error_seat_alive_is_wrapped_not_respawned():
    runner = ScriptedRunner([DYN_DEAD])
    seat = FakeSeat([True])  # alive -> genuine unexpected error
    out = _session(runner, seat).execute("p", PROPOSALS)
    assert out["ok"] is False
    assert "seat alive" in out["error"]
    assert seat.respawn_calls == 0
    assert out["recovery"]["deaths"] == []


# ---------------------------------------------------------------------------
# Case 2 & 3 — full replay (Tier 1) and snapshot-restore (Tier 2)
# ---------------------------------------------------------------------------


def test_tier1_full_pristine_replay_committed_matches():
    runner = ScriptedRunner([manifest_fault("apply", 2), manifest_ok([0, 1, 2])])
    out = _session(runner, FakeSeat([False])).execute("p", PROPOSALS)
    # the FULL list replayed (not a partial resume from index 2)
    assert [c["index"] for c in out["committed"]] == [0, 1, 2]


def test_tier2_save_death_restores_snapshot_then_replays():
    runner = ScriptedRunner([manifest_fault("save", None), manifest_ok([0, 1, 2])])
    seat = FakeSeat([False])
    snap = FakeSnapshotter()
    out = _session(runner, seat, snap=snap).execute("p", PROPOSALS)
    assert out["ok"] is True
    assert out["recovery"]["tier"] == 2
    assert snap.restores == 1  # the corrupt-save window -> restore pristine
    assert snap.snapshots == 1 and snap.discards == 1


# ---------------------------------------------------------------------------
# Case 4 & 5 — the caps (anti-infinite-loop)
# ---------------------------------------------------------------------------


def test_global_retry_cap_fatal_after_two_replays():
    # DIFFERENT indices so poison-detection does not fire first.
    runner = ScriptedRunner(
        [
            manifest_fault("apply", 0),
            manifest_fault("apply", 1),
            manifest_fault("apply", 2),
        ]
    )
    seat = FakeSeat([False, False, False])
    out = _session(runner, seat).execute("p", PROPOSALS)
    assert out["ok"] is False
    assert out["recovery"]["recovered"] is False
    assert "max respawn-replays" in out["recovery"]["fatal_reason"]
    assert out["recovery"]["poison_proposal"] is None
    assert seat.respawn_calls == 2  # 1 original + 2 replays = 3 attempts
    assert runner.calls == 3


def test_poison_proposal_quarantined_before_cap():
    # SAME index dies twice -> poison, abort before exhausting the global cap.
    runner = ScriptedRunner([manifest_fault("apply", 2), manifest_fault("apply", 2)])
    seat = FakeSeat([False, False])
    out = _session(runner, seat).execute("p", PROPOSALS)
    assert out["ok"] is False
    assert out["recovery"]["poison_proposal"] == 2
    assert "reproducible seat death" in out["recovery"]["fatal_reason"]
    assert runner.calls == 2  # bounded — not 3
    assert seat.respawn_calls == 1


def test_respawn_timeout_is_fatal_not_a_hang():
    runner = ScriptedRunner([manifest_fault("apply", 1)])
    seat = FakeSeat([False], respawn_raises=True)
    out = _session(runner, seat).execute("p", PROPOSALS)
    assert out["ok"] is False
    assert "respawn failed" in out["recovery"]["fatal_reason"]


# ---------------------------------------------------------------------------
# Case 6 — faked clock: wall-clock backstop, zero real sleep
# ---------------------------------------------------------------------------


def test_wall_clock_backstop_with_faked_clock_no_real_sleep():
    clock = FakeClock()
    # each respawn "costs" 10s of fake time; budget 15s; high cap so the
    # WALL-CLOCK guard (not the replay cap) is what fires. Distinct indices.
    runner = ScriptedRunner(
        [
            manifest_fault("apply", 0),
            manifest_fault("apply", 1),
            manifest_fault("apply", 2),
        ]
    )
    seat = FakeSeat([False, False, False], clock=clock, respawn_cost_s=10.0)
    out = _session(
        runner, seat, clock=clock, max_replays=99, recovery_budget_s=15.0
    ).execute("p", PROPOSALS)
    assert out["ok"] is False
    assert "wall-clock budget" in out["recovery"]["fatal_reason"]
    assert clock.sleep_calls == []  # the envelope never paid a real sleep


def test_clean_success_no_death_no_respawn():
    runner = ScriptedRunner([manifest_ok([0, 1, 2])])
    seat = FakeSeat([])  # is_alive never consulted on a clean run
    snap = FakeSnapshotter()
    out = _session(runner, seat, snap=snap).execute("p", PROPOSALS)
    assert out["ok"] is True
    assert out["recovery"]["recovered"] is True
    assert out["recovery"]["deaths"] == []
    assert seat.respawn_calls == 0
    assert snap.snapshots == 1 and snap.discards == 1  # snapshot taken + cleaned up
