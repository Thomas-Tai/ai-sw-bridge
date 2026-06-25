"""Seat-respawn UI-BLOCKER probe (Resilience epoch, measure-first).

Extends the murder-spike (spike_seat_death_recovery.py) with the one question the
supervised-respawn sequence must answer before we trust the ~8-9s budget: after an
UNSAVED-WORK crash, does the respawned SOLIDWORKS pop a blocking Document-Recovery
pane / "encountered a problem" dialog that WEDGES the COM bridge (turning 8-9s into
an infinite hang)?

Method:
  1. Bind/spawn SW; locate the auto-recover dir; snapshot its contents.
  2. Open a fixture part, make a TRIVIAL UNSAVED change (a 3D-sketch line — no plane
     SelectByID2, so no callout wall), confirm dirty via GetSaveFlag.
  3. taskkill /F /PID the dirty instance (simulates an unsaved-work crash).
  4. RESPAWN via Dispatch; run the readiness probe on a WATCHDOG TIMER —
     HANG = a modal blocked the bridge; RETURN = clean.
  5. Witness post-respawn: ActiveDoc auto-loaded? recovery files written? Visible?
  6. SUPPRESSION: clear the auto-recover dir (binding-independent) + try the
     auto-recover toggle/interval; re-confirm a clean respawn.

Telemetry -> spikes/_results/seat_recovery_ui.json (untracked).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

RESULTS_PATH = Path(__file__).resolve().parent / "_results" / "seat_recovery_ui.json"
AUTORECOVER_DIR = Path(
    os.path.expandvars(r"%APPDATA%\SOLIDWORKS\SOLIDWORKS 2024\swxauto")
)
FIXTURE = None  # resolved at runtime from captures/

results: dict[str, Any] = {"probe": "seat_recovery_ui", "phases": {}}


def log(m: str) -> None:
    print(f"  {m}", flush=True)


def describe_exc(e: BaseException) -> dict[str, Any]:
    import pywintypes

    d: dict[str, Any] = {"type": type(e).__name__, "str": str(e)[:200]}
    if isinstance(e, pywintypes.com_error):
        try:
            hr = int(e.args[0])
            d["hresult_hex"] = hex(hr & 0xFFFFFFFF)
        except Exception:  # noqa: BLE001
            pass
    return d


def _rev(sw: Any) -> Any:
    v = sw.RevisionNumber
    return v() if callable(v) else v


def guarded(label: str, fn: Callable[[], Any], timeout: float = 20.0) -> dict[str, Any]:
    """Main-thread invoke + watchdog timer. Hang past *timeout* => a modal is
    blocking the bridge: flush telemetry and force-exit (cannot interrupt a
    blocked COM call otherwise)."""
    done = threading.Event()

    def watchdog() -> None:
        if not done.wait(timeout):
            results["_BLOCKED_at"] = label
            try:
                RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
                RESULTS_PATH.write_text(
                    json.dumps(results, indent=2, default=str), encoding="utf-8"
                )
            except Exception:  # noqa: BLE001
                pass
            print(
                f"  [{label}] *** BLOCKED/HUNG {timeout}s — a modal wedged the bridge ***"
            )
            os._exit(3)

    threading.Thread(target=watchdog, daemon=True).start()
    t0 = time.time()
    try:
        v = fn()
        out: dict[str, Any] = {"ok": True, "value": repr(v)[:100]}
    except BaseException as e:  # noqa: BLE001
        out = {"ok": False, "exc": describe_exc(e)}
    out["dt_s"] = round(time.time() - t0, 2)
    done.set()
    log(f"[{label}] {'ok' if out.get('ok') else 'FAULT'} in {out['dt_s']}s")
    return out


def find_sw_pid() -> int | None:
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


def recover_dir_state() -> dict[str, Any]:
    try:
        if AUTORECOVER_DIR.is_dir():
            files = [p.name for p in AUTORECOVER_DIR.iterdir()]
            return {"exists": True, "count": len(files), "files": files[:10]}
        return {"exists": False}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def make_dirty(doc: Any) -> dict[str, Any]:
    """Trivial unsaved change: a 3D-sketch line (no plane select => no callout)."""
    info: dict[str, Any] = {}
    try:
        sm = doc.SketchManager
        sm.Insert3DSketch(True)
        sm.CreateLine(0.0, 0.0, 0.0, 0.05, 0.0, 0.0)
        sm.Insert3DSketch(True)  # exit
        flag = doc.GetSaveFlag
        info["dirty"] = bool(flag() if callable(flag) else flag)
    except Exception as e:  # noqa: BLE001
        info["err"] = describe_exc(e)
    return info


def respawn_and_witness(label: str, dead_pid: int | None) -> dict[str, Any]:
    import pythoncom
    import win32com.client as w32

    from ai_sw_bridge.sw_com import release_sw_app

    release_sw_app()
    pythoncom.CoUninitialize()
    pythoncom.CoInitialize()
    t_kill = time.time()
    phase: dict[str, Any] = {}
    # readiness probe under the watchdog — the decisive block-vs-clean signal
    sw2 = w32.Dispatch("SldWorks.Application")
    phase["readiness"] = guarded(f"{label} readiness RevisionNumber", lambda: _rev(sw2))
    phase["seconds_to_ready"] = round(time.time() - t_kill, 2)
    phase["new_pid"] = find_sw_pid()
    phase["pid_changed"] = phase["new_pid"] != dead_pid
    # did a recovery doc auto-load? is a frame shown?
    phase["active_doc"] = guarded(f"{label} ActiveDoc", lambda: sw2.ActiveDoc)
    phase["recover_dir_after"] = recover_dir_state()
    try:
        sw2.Visible = False
    except Exception:  # noqa: BLE001
        pass
    return phase


def run() -> None:
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.sw_com import get_sw_app

    global FIXTURE
    cands = list(
        (Path(__file__).resolve().parent.parent / "captures").rglob("*.SLDPRT")
    )
    if not cands:
        results["error"] = "no .SLDPRT fixture under captures/"
        return
    FIXTURE = str(cands[0])
    results["fixture"] = FIXTURE
    results["autorecover_dir"] = str(AUTORECOVER_DIR)
    results["phases"]["0_recover_dir_initial"] = recover_dir_state()

    # ---- Phase A: BASELINE — dirty crash, default settings ----
    sw = get_sw_app()
    mod = wrapper_module()
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(FIXTURE, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    results["phases"]["A_dirty"] = (
        make_dirty(doc) if doc is not None else {"open": "FAIL"}
    )
    pid = find_sw_pid()
    results["phases"]["A_recover_dir_before_kill"] = recover_dir_state()
    subprocess.run(
        ["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True, timeout=20
    )
    log(f"killed dirty PID {pid}")
    time.sleep(1.5)
    results["phases"]["A_recover_dir_after_kill"] = recover_dir_state()
    results["phases"]["A_respawn"] = respawn_and_witness("A", pid)

    # ---- Phase B: SUPPRESSED — clear auto-recover dir, then dirty crash again ----
    sw_b = get_sw_app()
    # binding-independent suppression: wipe any recovery snapshots
    cleared = False
    try:
        if AUTORECOVER_DIR.is_dir():
            shutil.rmtree(AUTORECOVER_DIR, ignore_errors=True)
            cleared = True
    except Exception:  # noqa: BLE001
        pass
    # also TRY the toggle/interval (constant resolved dynamically if present)
    toggle_set: dict[str, Any] = {}
    try:
        c = w32.constants
        for name in ("swAutoRecoverInterval", "swBackupSaveAutoRecoverInfo"):
            try:
                val = getattr(c, name)
                toggle_set[name] = val
            except Exception:  # noqa: BLE001
                toggle_set[name] = "unresolved"
    except Exception as e:  # noqa: BLE001
        toggle_set["constants_err"] = repr(e)
    results["phases"]["B_suppression"] = {"dir_cleared": cleared, "toggles": toggle_set}

    tsw_b = typed(sw_b, "ISldWorks", module=mod)
    ret2 = tsw_b.OpenDoc6(FIXTURE, 1, 1, "", 0, 0)
    doc2 = ret2[0] if isinstance(ret2, tuple) else ret2
    results["phases"]["B_dirty"] = (
        make_dirty(doc2) if doc2 is not None else {"open": "FAIL"}
    )
    pid2 = find_sw_pid()
    subprocess.run(
        ["taskkill", "/F", "/PID", str(pid2)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    log(f"killed dirty PID {pid2} (suppressed)")
    time.sleep(1.5)
    results["phases"]["B_respawn"] = respawn_and_witness("B", pid2)


def main() -> int:
    import pythoncom

    pythoncom.CoInitialize()
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        import traceback

        results["fatal"] = f"{type(exc).__name__}: {exc}"
        results["traceback"] = traceback.format_exc()
        print(traceback.format_exc())
    finally:
        try:
            import win32com.client as w32

            w32.Dispatch("SldWorks.Application").CloseAllDocuments(True)
        except Exception:  # noqa: BLE001
            pass
        try:
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
