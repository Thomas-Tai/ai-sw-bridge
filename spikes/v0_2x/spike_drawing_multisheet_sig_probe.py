"""W23 S1 signature probe — focused NewSheet* arity discovery.

The main spike walled on all NewSheet* candidates with Type mismatch /
Parameter not optional. The typed IDrawingDoc reports a specific 1-based
arg index per method — the errors suggest one of the later args has the
wrong VARIANT type (probably a BOOL marshalled as Python bool rather than
I4, or a LONG where pywin32 sent VT_I2).

This probe tries the most common signature permutations explicitly so the
spike JSON can record which one actually works on SW 2024 SP1.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_multisheet_sig_probe.json"
)


def main() -> None:
    import tempfile
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    drwdots = sorted(
        set(
            glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT")
            + glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot")
        )
    )
    template_path = drwdots[0]

    doc_raw = typed(sw, "ISldWorks", module=mod).NewDocument(
        template_path, 0, 0.420, 0.297
    )
    drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)

    results: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "attempts": [],
    }

    def try_call(label: str, fn: Any, args: tuple) -> None:
        try:
            ok = fn(*args)
            results["attempts"].append(
                {
                    "label": label,
                    "args": list(args),
                    "ok": bool(ok),
                    "returned": type(ok).__name__ if ok is not None else "None",
                    "error": None,
                }
            )
        except Exception as e:
            results["attempts"].append(
                {
                    "label": label,
                    "args": list(args),
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    # --- NewSheet(name) variants ---
    try_call("NewSheet(name)", drawing_doc.NewSheet, ("SigProbeA",))
    try_call("NewSheet(name) via raw", doc_raw.NewSheet, ("SigProbeA_raw",))

    # --- NewSheet2 variants (Name, TemplateIn, PaperSizeIn, Scale1, Scale2, FirstAngle) ---
    try_call(
        "NewSheet2(name, 1, 0, 1.0, 1.0, True)",
        drawing_doc.NewSheet2,
        ("SigProbeB", 1, 0, 1.0, 1.0, True),
    )
    try_call(
        "NewSheet2(name, 0, 8, 1.0, 1.0, True)  # papersize 8=swDwgPaperAsize",
        drawing_doc.NewSheet2,
        ("SigProbeC", 0, 8, 1.0, 1.0, True),
    )
    try_call(
        "NewSheet2(name, 1, 8, 1, 1, 1)  # all ints",
        drawing_doc.NewSheet2,
        ("SigProbeD", 1, 8, 1, 1, 1),
    )
    try_call(
        "NewSheet2(name, 1, 8, 1.0, 1.0, 1)  # firstangle as int",
        drawing_doc.NewSheet2,
        ("SigProbeE", 1, 8, 1.0, 1.0, 1),
    )

    # --- NewSheet3 (Name, TemplateIn, PaperSizeIn, Width, Height, Scale1, Scale2, FirstAngle) ---
    try_call(
        "NewSheet3(name, 1, 8, 0.210, 0.297, 1.0, 1.0, 1)",
        drawing_doc.NewSheet3,
        ("SigProbeF", 1, 8, 0.210, 0.297, 1.0, 1.0, 1),
    )
    try_call(
        "NewSheet3(name, 1, 8, 0.210, 0.297, 1, 1, 1)  # scales as int",
        drawing_doc.NewSheet3,
        ("SigProbeG", 1, 8, 0.210, 0.297, 1, 1, 1),
    )
    try_call(
        "NewSheet3(name, 1, 8, 210.0, 297.0, 1.0, 1.0, 1)  # mm not m",
        drawing_doc.NewSheet3,
        ("SigProbeH", 1, 8, 210.0, 297.0, 1.0, 1.0, 1),
    )
    try_call(
        "NewSheet3(name, 1, 0, 0.210, 0.297, 1.0, 1.0, 1)  # paper=0",
        drawing_doc.NewSheet3,
        ("SigProbeI", 1, 0, 0.210, 0.297, 1.0, 1.0, 1),
    )

    # --- NewSheet4 (Name, TemplateIn, PaperSizeIn, Scale1, Scale2, FirstAngle, TemplateFeatureIn, NumPropertyViews) ---
    try_call(
        "NewSheet4(name, 1, 8, 1.0, 1.0, 1, None, 0)",
        drawing_doc.NewSheet4,
        ("SigProbeJ", 1, 8, 1.0, 1.0, 1, None, 0),
    )
    try_call(
        "NewSheet4(name, 1, 8, 1.0, 1.0, 1, 0, 0)",
        drawing_doc.NewSheet4,
        ("SigProbeK", 1, 8, 1.0, 1.0, 1, 0, 0),
    )

    # --- SetupSheet5 + Sheet() alternative path ---
    try:
        # SetupSheet5 is on IDrawingDoc (CHM); then Sheet() might add it
        try_call(
            "SetupSheet5(name, ...)",
            drawing_doc.SetupSheet5,
            ("SigProbeSetup", 1, 8, 1.0, 1.0, 1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    except Exception as e:
        results["attempts"].append(
            {
                "label": "SetupSheet5(attr)",
                "error": f"{type(e).__name__}: {e}",
            }
        )

    # Close
    try:
        t = doc_raw.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

    # Tally
    ok_count = sum(1 for a in results["attempts"] if a["ok"])
    print(f"OK: {ok_count}/{len(results['attempts'])}")
    for a in results["attempts"]:
        print(
            f"  {'PASS' if a['ok'] else 'FAIL'} {a['label']}: {a.get('error') or ('ok=' + str(a.get('ok')))}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
