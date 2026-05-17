"""
Spike H pre-probe - enumerate top-level windows to find the SOLIDWORKS HWND.

Spike H assumed window class "SldWorks"; FindWindowW returned 0. This
probe walks all visible top-level windows and reports class + title for
each. The user (or us) picks the SW one by inspecting the output.
"""

from __future__ import annotations

import ctypes
import json
from ctypes import wintypes


def main() -> int:
    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    IsWindowVisible = user32.IsWindowVisible
    GetWindowTextW = user32.GetWindowTextW
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    GetClassNameW = user32.GetClassNameW

    results = []

    def cb(hwnd, _lparam):
        if not IsWindowVisible(hwnd):
            return True
        tlen = GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(tlen + 1)
        GetWindowTextW(hwnd, buf, tlen + 1)
        title = buf.value
        clsbuf = ctypes.create_unicode_buffer(256)
        GetClassNameW(hwnd, clsbuf, 256)
        cls = clsbuf.value
        if title or "Sld" in cls or "SW" in cls or "SOLID" in cls.upper():
            results.append({"hwnd": int(hwnd), "class": cls, "title": title})
        return True

    EnumWindows(EnumWindowsProc(cb), 0)

    # Filter: anything mentioning SOLIDWORKS in title or class containing "Sld"
    candidates = [
        r
        for r in results
        if "SOLIDWORKS" in r["title"].upper() or "SLD" in r["class"].upper()
    ]

    print(
        json.dumps(
            {
                "candidates": candidates,
                "all_visible_with_title": results,
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
