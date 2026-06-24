"""Offline unit tests for the W76 autonomous clearance solver.

The seat PAE (spikes/v0_2x/spike_solver_pae.py) proves the live COM path; these
tests pin the loop's CONTROL LOGIC — input validation, the already-clear short
circuit, monotonic resolution, the fail-closed revert contract, the
wrong-direction guard, and drive-failure handling — with the sense (interference)
and act (mate drive) calls mocked, so no SOLIDWORKS seat is required.
"""

from __future__ import annotations

from unittest.mock import patch

import ai_sw_bridge.solver as S


def _intf(count: int, vol_mm3: float) -> dict:
    """A sw_get_interference-shaped reading."""
    return {
        "ok": True,
        "interference_count": count,
        "interferences": ([{"interference_volume_mm3": vol_mm3}] if vol_mm3 else []),
    }


def _run(sense_seq, *, read_val=0.010, drive_side=None, **kwargs):
    """Drive resolve_clearance with mocked sense/act. ``sense_seq`` is a list of
    (count, volume_mm3) tuples consumed one per loop iteration."""
    senses = [_intf(c, v) for (c, v) in sense_seq]
    drive = drive_side if drive_side is not None else (lambda *a, **k: "parameter")
    with (
        patch.object(S, "wrapper_module", return_value=object()),
        patch.object(S, "read_mate_value_si", return_value=read_val),
        patch.object(S, "sw_get_interference", side_effect=senses) as sense_m,
        patch.object(S, "drive_mate_value_si", side_effect=drive) as drive_m,
    ):
        res = S.resolve_clearance(object(), "Distance1", **kwargs)
    return res, drive_m, sense_m


# ── Input validation (fails fast, before any seat mutation) ─────────────────


def test_rejects_empty_mate_name():
    # mate_name "" is rejected before any read/drive.
    res = S.resolve_clearance(object(), "", step_mm=2.0)
    assert res["ok"] is False and "mate_name" in res["error"]


def test_rejects_nonpositive_step():
    res = S.resolve_clearance(object(), "M", step_mm=0)
    assert res["ok"] is False and "step_mm" in res["error"]
    res = S.resolve_clearance(object(), "M", step_mm=-1)
    assert res["ok"] is False and "step_mm" in res["error"]


def test_rejects_bad_max_iters():
    res = S.resolve_clearance(object(), "M", max_iters=0)
    assert res["ok"] is False and "max_iters" in res["error"]


def test_rejects_bad_direction():
    res = S.resolve_clearance(object(), "M", direction="sideways")
    assert res["ok"] is False and "direction" in res["error"]


def test_no_driving_dimension_is_explicit():
    # read_mate_value_si returns None -> not a distance mate.
    res, _, _ = _run([], read_val=None)
    assert res["ok"] is False
    assert "driving dimension" in res["error"] and "distance mate" in res["error"]


# ── Resolution behaviour ────────────────────────────────────────────────────


def test_already_clear_zero_drives():
    # First sense is clash-free -> resolved at the initial value, no drive.
    res, drive_m, _ = _run([(0, 0.0)], read_val=0.010)
    assert res["ok"] is True and res["resolved"] is True
    assert res["resolved_mm"] == 10.0
    assert res["iterations"] == 1
    assert drive_m.call_count == 0  # never touched the mate


def test_resolves_after_monotonic_steps():
    # 10mm(4000) -> 12mm(3200) -> 14mm(clear). Two drives, resolved at 14mm.
    res, drive_m, _ = _run(
        [(1, 4000.0), (1, 3200.0), (0, 0.0)], read_val=0.010, step_mm=2.0
    )
    assert res["ok"] is True and res["resolved_mm"] == 14.0
    assert res["iterations"] == 3
    assert drive_m.call_count == 2
    # Last in-loop drive moved the mate to 14mm = 0.014m.
    assert abs(drive_m.call_args_list[-1].args[2] - 0.014) < 1e-9


def test_fail_closed_reverts_to_original():
    # Never clears within the budget -> revert to the original 10mm.
    res, drive_m, _ = _run(
        [(1, 4000.0), (1, 3800.0), (1, 3600.0)],
        read_val=0.010,
        step_mm=2.0,
        max_iters=3,
    )
    assert res["ok"] is False and res["resolved"] is False
    assert res["reverted"] is True
    assert "max_iters" in res["error"]
    # The final drive call restores the original value (the revert).
    assert abs(drive_m.call_args_list[-1].args[2] - 0.010) < 1e-9
    # Best-effort telemetry: closest it got was the tightest volume seen.
    assert res["best_state"]["volume_mm3"] == 3600.0


def test_wrong_direction_guard_trips_and_reverts():
    # A step that INCREASES interference means we are driving them together.
    res, drive_m, _ = _run(
        [(1, 4000.0), (1, 4500.0)], read_val=0.010, step_mm=2.0, max_iters=10
    )
    assert res["ok"] is False
    assert "direction='in'" in res["error"]
    assert res["reverted"] is True
    assert abs(drive_m.call_args_list[-1].args[2] - 0.010) < 1e-9


def test_drive_failure_is_surfaced_and_reverted():
    calls = {"n": 0}

    def flaky(*_a, **_k):
        calls["n"] += 1
        return "FAIL:boom" if calls["n"] == 1 else "parameter"

    res, drive_m, _ = _run([(1, 4000.0)], read_val=0.010, step_mm=2.0, drive_side=flaky)
    assert res["ok"] is False
    assert "drive_failed" in res["error"]
    assert res["reverted"] is True  # second (revert) drive succeeds


def test_direction_in_uses_negative_step():
    # direction='in' drives the value DOWN.
    res, drive_m, _ = _run(
        [(1, 4000.0), (0, 0.0)], read_val=0.010, step_mm=2.0, direction="in"
    )
    assert res["ok"] is True
    assert abs(drive_m.call_args_list[0].args[2] - 0.008) < 1e-9  # 10 - 2 = 8mm
