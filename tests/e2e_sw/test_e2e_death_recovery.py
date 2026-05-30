"""End-to-end death-recovery test (Wave 5 Phase 2.5 codified).

Verifies the fix from commit ``5069866``: after SW is killed mid-
session, ``sw_reconnect`` clears the ``sw_com._CACHED_SW_APP`` global
so subsequent observe calls re-Dispatch against a fresh SW process
instead of reusing the stale dead handle.

This test is destructive — it kills the SW process and (via pywin32
COM auto-launch) spawns a fresh one. Run only on a workstation where
losing the active SW session is acceptable.

Run with::

    pytest -m solidworks_only tests/e2e_sw/test_e2e_death_recovery.py -v
"""

from __future__ import annotations

import subprocess
import time

import pytest

pytestmark = [pytest.mark.solidworks_only, pytest.mark.destructive_sw]


def _sw_alive() -> bool:
    r = subprocess.run(
        [
            "powershell",
            "-Command",
            "if (Get-Process -Name SLDWORKS -ErrorAction SilentlyContinue) "
            "{ 'yes' } else { 'no' }",
        ],
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() == "yes"


def _kill_sw() -> None:
    subprocess.run(
        [
            "powershell",
            "-Command",
            "Stop-Process -Name SLDWORKS -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        text=True,
    )
    # Give Windows a beat to actually release the process.
    time.sleep(2)


def test_e2e_death_recovery_via_sw_reconnect(live_runtime, live_tools) -> None:
    """Baseline call works -> kill SW -> next call errors AND flips
    is_sw_dead -> follow-up call short-circuits -> reconnect -> recover."""
    # Step 1 — baseline. Either ok=True or a benign "no_active_doc" — both
    # prove SW responded.
    baseline = live_tools["sw_active_doc"].fn()
    assert baseline.get("ok") in (
        True,
        False,
    ), f"baseline call did not return a well-formed payload: {baseline}"
    assert (
        live_runtime.executor.is_sw_dead is False
    ), "is_sw_dead set before kill — fixture is leaking state"

    # Step 2 — kill the SW process.
    assert _sw_alive(), "expected SW to be alive at test start"
    _kill_sw()
    assert not _sw_alive(), "SW survived Stop-Process -Force"

    # Step 3 — call against dead dispatch. observe.* swallows the
    # AttributeError into result['error']; the v0.13.0 @com_tool
    # post-hoc detector flips is_sw_dead based on the wrapped pattern.
    dead = live_tools["sw_active_doc"].fn()
    assert (
        dead.get("error") is not None
    ), f"expected dispatch-failed error, got clean payload: {dead}"
    assert (
        "dispatch failed" in str(dead["error"]).lower()
        or "no_active_doc" in str(dead["error"]).lower()
    ), f"unexpected error shape: {dead['error']}"
    # The is_sw_dead flag must have flipped if the error was the SW
    # death pattern (not just no_active_doc against a respawned SW).
    if "sldworks." in str(dead["error"]).lower():
        assert live_runtime.executor.is_sw_dead is True, (
            "@com_tool did not flip is_sw_dead on dead-dispatch payload — "
            "v0.13.0 A.1 fix is not active"
        )

    # Step 3b — follow-up call must short-circuit with the reconnect
    # hint instead of repeating the dispatch-failed error.
    if live_runtime.executor.is_sw_dead:
        import pytest

        with pytest.raises(RuntimeError, match="sw_reconnect"):
            live_tools["sw_active_doc"].fn()

    # Step 4 — sw_reconnect. Should clear the stale dispatch cache
    # (W5.6 fix in commit 5069866), auto-launch fresh SW via COM,
    # and reset is_sw_dead.
    rec = live_tools["sw_reconnect"].fn()
    assert rec["ok"] is True, f"sw_reconnect failed: {rec}"
    assert rec["executor_alive"] is True
    assert (
        live_runtime.executor.is_sw_dead is False
    ), "is_sw_dead did not clear on reconnect"

    # Step 5 — call after reconnect. The cached dispatch was cleared
    # by runtime.reconnect(), and pywin32 auto-launched a fresh SW
    # (no active doc — that's expected). Recovery payload should NOT
    # contain "dispatch failed".
    recovered = live_tools["sw_active_doc"].fn()
    assert (
        recovered.get("ok") is True
    ), f"sw_active_doc did not recover after reconnect: {recovered}"
    err = recovered.get("error")
    if err is not None:
        assert (
            "dispatch failed" not in str(err).lower()
        ), f"sw_active_doc still reporting stale dispatch after reconnect: {err}"
