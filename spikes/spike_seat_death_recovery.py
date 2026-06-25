"""Seat-death / COM-recovery MURDER-SPIKE (Resilience epoch, measure-first).

Maps the exact physics of an unexpected SOLIDWORKS death so the future
supervised-session layer can be built on real fault signatures, not guesses.
Throwaway probe — classification only, builds no recovery logic.

Sequence:
  1. BIND to the live seat, capture its PID, read a baseline property.
  2. ASSASSINATE by PID (taskkill /F /PID <pid> — targeted, never /IM so we can't
     nuke an unrelated instance) while holding the COM reference.
  3. WITNESS the held-reference fault: exact exception type + HRESULT, and whether
     the call faults IMMEDIATELY or HANGS (every post-kill invoke is run on a
     watchdog thread with a join-timeout to detect a hang vs a clean throw).
  4. RE-BIND: respawn via Dispatch and poll until the new instance answers
     RevisionNumber(); record the cooldown. Probe whether a CoUninitialize/
     CoInitialize cache-cycle is needed for the re-bind to take.

Prereq: a live SOLIDWORKS seat with NO unsaved work (this kills it).
Telemetry -> spikes/_results/seat_death_recovery.json (untracked).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

RESULTS_PATH = Path(__file__).resolve().parent / "_results" / "seat_death_recovery.json"
results: dict[str, Any] = {
    "probe": "seat_death_recovery",
    "phases": {},
    "rebind": {},
}


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def describe_exc(e: BaseException) -> dict[str, Any]:
    """Decode a COM/Python exception into a stable fault signature."""
    import pywintypes  # noqa: WPS433

    d: dict[str, Any] = {"type": type(e).__name__, "str": str(e)[:300]}
    if isinstance(e, pywintypes.com_error):
        hr = None
        # com_error.args = (hresult, strerror, excepinfo, argerror)
        try:
            hr = int(e.args[0])
        except Exception:  # noqa: BLE001
            hr = getattr(e, "hresult", None)
        if hr is not None:
            d["hresult"] = hr
            d["hresult_hex"] = hex(hr & 0xFFFFFFFF)
        try:
            d["strerror"] = str(e.args[1])
        except Exception:  # noqa: BLE001
            pass
    return d


def _rev(sw: Any) -> Any:
    """RevisionNumber resolves as a PROPERTY (str) under dynamic dispatch, but as
    a callable under early binding — read it either way."""
    v = sw.RevisionNumber
    return v() if callable(v) else v


def guarded_invoke(
    label: str, fn: Callable[[], Any], timeout: float = 12.0
) -> dict[str, Any]:
    """Run *fn* ON THE MAIN THREAD (correct COM apartment — no cross-thread
    marshaling / CoInitialize artifact) while a watchdog TIMER classifies hang.

    Common case: fn faults/returns fast -> we record the real HRESULT. Hang case:
    fn blocks on a wedged dead-server dispatch past *timeout* -> the watchdog
    flushes partial telemetry and force-exits (a blocked COM call cannot be
    interrupted from Python any other way)."""
    done = threading.Event()

    def watchdog() -> None:
        if not done.wait(timeout):
            results["_hung_at"] = label
            try:
                RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
                RESULTS_PATH.write_text(
                    json.dumps(results, indent=2, default=str), encoding="utf-8"
                )
            except Exception:  # noqa: BLE001
                pass
            print(
                f"  [{label}] HUNG ({timeout}s) — dispatch wedged on dead server; force-exit"
            )
            os._exit(2)

    threading.Thread(target=watchdog, daemon=True).start()
    t0 = time.time()
    try:
        v = fn()
        out = {"ok": True, "value": repr(v)[:120]}
    except BaseException as e:  # noqa: BLE001
        out = {"ok": False, "exc": describe_exc(e)}
    out["dt_s"] = round(time.time() - t0, 3)
    done.set()
    tag = "ok" if out.get("ok") else f"FAULT {out.get('exc', {}).get('hresult_hex')}"
    log(f"[{label}] {tag} in {out.get('dt_s')}s")
    return out


def find_sw_pid() -> int | None:
    """First SLDWORKS.exe PID via tasklist CSV (no display-formatting ambiguity)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:  # noqa: BLE001
        return None
    for line in out.splitlines():
        if "SLDWORKS.EXE" in line.upper():
            parts = [p.strip('" ') for p in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
    return None


def run() -> None:
    import pythoncom
    import win32com.client as w32

    pythoncom.CoInitialize()

    # ---- Phase 1: BIND (both binding modes) + baseline ----
    # DYNAMIC (late-bound) dispatch — what a naive caller gets.
    try:
        sw = w32.GetActiveObject("SldWorks.Application")
    except Exception:  # noqa: BLE001
        sw = w32.Dispatch("SldWorks.Application")
    # EARLY-BOUND via the PRODUCTION bridge path: get_sw_app() returns a dynamic
    # dispatch (EnsureDispatch fails on SldWorks — "can not automate makepy"),
    # which the bridge wraps with typed(obj, "ISldWorks", pre-generated makepy
    # module). That typed/vtable object is the reference production code holds —
    # its post-kill fault (a real com_error + HRESULT) is what the resilience
    # layer will actually catch.
    sw_eb = None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from ai_sw_bridge.com.earlybind import typed
        from ai_sw_bridge.com.sw_type_info import wrapper_module
        from ai_sw_bridge.sw_com import get_sw_app

        sw_eb = typed(get_sw_app(), "ISldWorks", module=wrapper_module())
    except Exception as e:  # noqa: BLE001
        results["phases"]["earlybound_bind_err"] = describe_exc(e)
    pid = find_sw_pid()
    base = guarded_invoke("baseline RevisionNumber (dynamic)", lambda: _rev(sw))
    base_eb = (
        guarded_invoke("baseline RevisionNumber (early-bound)", lambda: _rev(sw_eb))
        if sw_eb is not None
        else None
    )
    results["phases"]["1_bind"] = {
        "pid": pid,
        "baseline_dynamic": base,
        "baseline_earlybound": base_eb,
    }
    if pid is None:
        results["error"] = "no SLDWORKS pid found — aborting before kill"
        return
    log(f"bound to PID {pid}")

    # ---- Phase 2: ASSASSINATE by PID (targeted, not /IM) ----
    t_kill = time.time()
    kill = subprocess.run(
        ["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True, timeout=20
    )
    results["phases"]["2_kill"] = {
        "cmd": f"taskkill /F /PID {pid}",
        "returncode": kill.returncode,
        "stdout": kill.stdout.strip()[:200],
        "stderr": kill.stderr.strip()[:200],
    }
    log(f"taskkill rc={kill.returncode}: {kill.stdout.strip()[:80]}")
    # brief settle so the process is actually gone before we poke the corpse
    time.sleep(1.0)

    # ---- Phase 3: WITNESS the held-reference fault (immediate vs hang) ----
    witness = {
        "dynamic_RevisionNumber": guarded_invoke(
            "post-kill RevisionNumber (dynamic)", lambda: _rev(sw)
        ),
        "dynamic_ActiveDoc": guarded_invoke(
            "post-kill ActiveDoc (dynamic)", lambda: sw.ActiveDoc
        ),
    }
    if sw_eb is not None:
        witness["earlybound_RevisionNumber"] = guarded_invoke(
            "post-kill RevisionNumber (early-bound)", lambda: _rev(sw_eb)
        )
        witness["earlybound_ActiveDoc"] = guarded_invoke(
            "post-kill ActiveDoc (early-bound)", lambda: sw_eb.ActiveDoc
        )
        witness["earlybound_OpenDoc6"] = guarded_invoke(
            "post-kill OpenDoc6 (early-bound)",
            lambda: sw_eb.OpenDoc6("C:/nonexistent.SLDPRT", 1, 1, "", 0, 0),
        )
    results["phases"]["3_held_ref_fault"] = witness

    # ---- Phase 4: RE-BIND + cooldown timing ----
    # Drop the dead dispatch + COM apartment; a stale proxy can poison re-bind.
    try:
        del sw
    except Exception:  # noqa: BLE001
        pass
    pythoncom.CoUninitialize()
    pythoncom.CoInitialize()

    rebind: dict[str, Any] = {"attempts": [], "recovered": False}
    deadline = time.time() + 150.0  # SW cold start can be slow
    attempt = 0
    new_pid = None
    while time.time() < deadline:
        attempt += 1
        t0 = time.time()
        try:
            sw2 = w32.Dispatch("SldWorks.Application")
            rev = _rev(sw2)  # the real "accepts commands" gate (property-safe)
            new_pid = find_sw_pid()
            elapsed = round(time.time() - t_kill, 2)
            rebind["recovered"] = True
            rebind["seconds_from_kill_to_ready"] = elapsed
            rebind["new_pid"] = new_pid
            rebind["pid_changed"] = new_pid != pid
            rebind["revision"] = repr(rev)[:60]
            rebind["dispatch_attempts"] = attempt
            log(f"RE-BIND OK after {elapsed}s, attempt {attempt}, new PID {new_pid}")
            # leave the recovered seat headless to avoid a UI popup lingering
            try:
                sw2.Visible = False
            except Exception:  # noqa: BLE001
                pass
            break
        except Exception as e:  # noqa: BLE001
            rebind["attempts"].append(
                {
                    "n": attempt,
                    "dt_s": round(time.time() - t0, 2),
                    "exc": describe_exc(e),
                }
            )
            time.sleep(3.0)
    if not rebind["recovered"]:
        log("RE-BIND FAILED within deadline")
    results["rebind"] = rebind


def main() -> int:
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        import traceback

        results["fatal"] = f"{type(exc).__name__}: {exc}"
        results["traceback"] = traceback.format_exc()
        print(traceback.format_exc())
    finally:
        try:
            import pythoncom

            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nWrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
