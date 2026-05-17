"""
Spike H - auto-dismiss the Modify Dimension popup via background SendKeys.

Approach:
- A background thread waits N ms, then sends ENTER to the SOLIDWORKS
  foreground window. The ENTER accepts the popup (equivalent to clicking
  the green check), unblocking the COM AddDimension2 call.
- Tested in isolation: open blank Part, add one dim with the auto-dismiss
  thread armed. Verify the dim appears with the expected value and the
  COM call completes without manual interaction.

Why SendKeys: GetUserPreferenceToggle(8) for swInputDimValOnCreate does
not actually suppress the popup on this SW build (Spike F confirmed:
popup still blocks). Rather than hunt the right preference ID, we accept
the popup and dismiss it programmatically.

We use the ctypes Win32 API directly (SetForegroundWindow + keybd_event)
to avoid a pywin32-extra import. ENTER key VK code is 0x0D.

If this works, the production version in builder.py will wrap
AddDimension2 in a helper that arms the dismisser before each call.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import threading
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402

VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002


def _find_sw_window() -> int:
    """Return HWND of the SOLIDWORKS main window, or 0 if not found.

    SW 2024 uses an Afx:* class name (not "SldWorks"), so we enumerate
    visible top-level windows and pick the one whose title starts with
    "SOLIDWORKS".
    """
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    found = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.upper().startswith("SOLIDWORKS"):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else 0


def _send_key_to_window(hwnd: int, vk: int) -> None:
    """Focus the SW window and synthesize a keystroke via Win32 keybd_event.

    Used as fallback when sw.SendKeys is not available via late-binding.
    """
    user32 = ctypes.windll.user32
    if hwnd:
        user32.SetForegroundWindow(hwnd)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _arm_dismisser(
    hwnd: int,
    delay_ms: int,
    method: str = "ctypes_enter",
    sw_app=None,
) -> threading.Thread:
    """Start a thread that sleeps `delay_ms` then dismisses the popup.

    `method`:
      - "ctypes_enter":      keybd_event ENTER, after SetForegroundWindow(hwnd)
      - "ctypes_enter_blind": keybd_event ENTER only (no focus change). Relies
                              on the modal popup having focus by default.
      - "ctypes_esc":        keybd_event ESC, after SetForegroundWindow(hwnd)
      - "ctypes_esc_blind":  keybd_event ESC only (no focus change)
      - "sw_sendkeys_enter": sw.SendKeys "{ENTER}"
      - "sw_sendkeys_esc":   sw.SendKeys "{ESC}"
    """

    def _go():
        time.sleep(delay_ms / 1000.0)
        try:
            if method == "ctypes_enter":
                _send_key_to_window(hwnd, VK_RETURN)
            elif method == "ctypes_enter_blind":
                user32 = ctypes.windll.user32
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            elif method == "ctypes_esc":
                _send_key_to_window(hwnd, 0x1B)
            elif method == "ctypes_esc_blind":
                user32 = ctypes.windll.user32
                user32.keybd_event(0x1B, 0, 0, 0)
                user32.keybd_event(0x1B, 0, KEYEVENTF_KEYUP, 0)
            elif method == "ctypes_enter_blind_double":
                # First ENTER: dismiss Modify popup.
                # Wait 250ms for PM pane to settle, then ENTER again to
                # confirm the PM pane (equivalent of clicking green-check).
                user32 = ctypes.windll.user32
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.25)
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            elif method == "ctypes_enter_then_esc":
                # ENTER for Modify popup, ESC for PM pane (cancel keeps
                # the dim, doesn't open edit-value field).
                user32 = ctypes.windll.user32
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.25)
                user32.keybd_event(0x1B, 0, 0, 0)
                user32.keybd_event(0x1B, 0, KEYEVENTF_KEYUP, 0)
            elif method == "sw_sendkeys_enter" and sw_app is not None:
                sw_app.SendKeys("{ENTER}")
            elif method == "sw_sendkeys_esc" and sw_app is not None:
                sw_app.SendKeys("{ESC}")
        except Exception:
            pass

    t = threading.Thread(target=_go, daemon=True)
    t.start()
    return t


def run(delay_ms: int, method: str) -> dict:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        return {"status": "FAIL", "error": "no active doc; open blank part first"}

    fc = doc.GetFeatureCount
    if fc > 17:
        return {
            "status": "FAIL",
            "error": f"doc not blank: {fc} features. File > New > Part first.",
        }

    hwnd = _find_sw_window()
    if hwnd == 0 and method.startswith("ctypes"):
        return {
            "status": "FAIL",
            "error": "could not find SOLIDWORKS window for ctypes method",
        }

    # Build a sketch with one circle and add a diameter dim, with the
    # dismisser armed in the background.
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"status": "FAIL", "error": "could not select Front Plane"}
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)  # 10mm dia circle

    doc.ClearSelection2(True)
    if not doc.SelectByID("", "SKETCHSEGMENT", 0.005, 0.0, 0.0):
        return {"status": "FAIL", "error": "could not select circle for dim"}

    # Arm the dismisser. AddDimension2 will block; the thread will fire
    # the chosen keystroke after delay_ms and unblock us.
    t_start = time.time()
    dismisser = _arm_dismisser(hwnd, delay_ms, method=method, sw_app=sw)
    try:
        dim = doc.AddDimension2(0.010, 0.005, 0.0)
    except Exception as e:
        return {
            "status": "FAIL",
            "error": f"AddDimension2 raised: {e!r}",
            "method": method,
        }
    finally:
        dismisser.join(timeout=2.0)
    elapsed = time.time() - t_start

    if dim is None:
        return {
            "status": "FAIL",
            "error": "AddDimension2 returned None",
            "elapsed_s": round(elapsed, 3),
            "method": method,
        }

    # Close sketch and rename
    sm.InsertSketch(True)
    sketch = doc.FeatureByPositionReverse(0)
    sketch.Name = f"SpikeH_{method}"

    # Verify the dim
    d1 = doc.Parameter(f"D1@SpikeH_{method}")
    d1_mm = (d1.SystemValue * 1000.0) if d1 else None

    return {
        "status": "PASS" if d1 is not None else "FAIL",
        "method": method,
        "elapsed_s": round(elapsed, 3),
        "delay_ms": delay_ms,
        "D1_mm": d1_mm,
        "expected_mm": 10.0,
        "auto_dismissed": elapsed < (delay_ms / 1000.0 + 5.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=300,
        help="ms to wait before sending key (default 300)",
    )
    parser.add_argument(
        "--method",
        choices=[
            "sw_sendkeys_enter",
            "sw_sendkeys_esc",
            "ctypes_enter",
            "ctypes_esc",
            "ctypes_enter_blind",
            "ctypes_esc_blind",
            "ctypes_enter_blind_double",
            "ctypes_enter_then_esc",
        ],
        default="ctypes_enter_blind_double",
        help="how to dismiss the popup (default: ctypes_enter_blind_double)",
    )
    args = parser.parse_args()
    out = run(args.delay_ms, args.method)
    print(json.dumps(out, indent=2))
    return 0 if out.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
