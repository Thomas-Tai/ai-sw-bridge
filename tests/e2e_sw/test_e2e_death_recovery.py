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

pytestmark = pytest.mark.solidworks_only


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


def test_e2e_death_recovery_via_sw_reconnect(live_tools) -> None:
    """Baseline call works -> kill SW -> next call errors -> reconnect -> recovers."""
    # Step 1 — baseline. Either ok=True or a benign "no_active_doc" — both
    # prove SW responded.
    baseline = live_tools["sw_active_doc"].fn()
    assert baseline.get("ok") in (
        True,
        False,
    ), f"baseline call did not return a well-formed payload: {baseline}"

    # Step 2 — kill the SW process.
    assert _sw_alive(), "expected SW to be alive at test start"
    _kill_sw()
    assert not _sw_alive(), "SW survived Stop-Process -Force"

    # Step 3 — call against dead dispatch. Expect the dispatch-failed
    # error surfaced into the observe payload (not a raised exception
    # — observe.* wraps the AttributeError into result.error).
    dead = live_tools["sw_active_doc"].fn()
    assert (
        dead.get("error") is not None
    ), f"expected dispatch-failed error, got clean payload: {dead}"
    assert (
        "dispatch failed" in str(dead["error"]).lower()
        or "no_active_doc" in str(dead["error"]).lower()
    ), f"unexpected error shape: {dead['error']}"

    # Step 4 — sw_reconnect. Should clear the stale dispatch cache
    # (W5.6 fix in commit 5069866) and auto-launch fresh SW via COM.
    rec = live_tools["sw_reconnect"].fn()
    assert rec["ok"] is True, f"sw_reconnect failed: {rec}"
    assert rec["executor_alive"] is True

    # Step 5 — call after reconnect. The cached dispatch was cleared
    # by runtime.reconnect(), and pywin32 auto-launched a fresh SW
    # (no active doc — that's expected). Recovery payload should NOT
    # contain "dispatch failed".
    recovered = live_tools["sw_active_doc"].fn()
    assert (
        recovered.get("ok") is True
    ), f"sw_active_doc did not recover after reconnect: {recovered}"
    # Either no_active_doc (likely — fresh SW) or a real doc (if
    # pywin32 happened to attach to an existing instance). Both are
    # acceptable recoveries.
    err = recovered.get("error")
    if err is not None:
        assert (
            "dispatch failed" not in str(err).lower()
        ), f"sw_active_doc still reporting stale dispatch after reconnect: {err}"
