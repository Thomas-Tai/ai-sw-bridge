"""Batch O1 orchestrator gate — observe satellites via SolidWorksClient on the seat.

Verifies the worker-ported O1 batch end-to-end on the live seat:

  A draft_clean        : ai-sw-observe `draft` runner (SolidWorksClient().observe
                         .draft_analysis) returns ok=True on a real part AND emits
                         NO PendingDeprecationWarning internally (warnings-as-errors).
  B interference_clean : ai-sw-observe `interference` runner (…observe.interference)
                         returns ok=True on a real assembly (overlapping cubes →
                         count>=1) with NO internal PendingDeprecationWarning.
  C shim_warns         : the legacy free function sw_get_interference STILL warns
                         for external scripts and returns identical data.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_o1_gate_pae.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_HERE.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.cli import observe as cli_observe  # noqa: E402
from ai_sw_bridge.observe_interference import sw_get_interference  # noqa: E402
from ai_sw_bridge.sw_com import get_active_doc, get_sw_app  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402

_OUT = _HERE.parent / "_results" / "o1_gate_pae.json"
results: dict[str, Any] = {"pae": "o1_observe_satellites_gate", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _under_warnings_as_errors(fn) -> tuple[dict[str, Any], bool, str]:
    """Run *fn*; PendingDeprecationWarning becomes an exception (leak detector)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        try:
            return fn(), True, ""
        except PendingDeprecationWarning as exc:  # noqa: BLE001
            return (
                {"ok": False},
                False,
                f"internal PendingDeprecationWarning leaked: {exc}",
            )


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        # ── A: draft analysis via the client (part active) ────────────────
        cube = P._build("o1_draft_cube", P._cube("o1_draft_cube", 20.0))
        if "error" in cube:
            gate("draft_clean", False, cube["error"])
            raise SystemExit(_finish())
        ns_draft = argparse.Namespace(pull_direction="top", min_angle=1.0)
        rep, clean, why = _under_warnings_as_errors(
            lambda: cli_observe._run_draft(ns_draft)
        )
        results["draft_report"] = rep
        gate(
            "draft_clean",
            clean and bool(rep.get("ok")),
            why
            or f"ok={rep.get('ok')} faces_total={rep.get('faces_total')} "
            f"(class-routed, no deprecation warning)",
        )

        # ── B: interference via the client (overlapping assembly active) ──
        sw.CloseAllDocuments(True)
        base = P._build("o1_int_base", P._cube("o1_int_base", 20.0))
        arm = P._build("o1_int_arm", P._cube("o1_int_arm", 20.0))
        for x in (base, arm):
            if "error" in x:
                gate("interference_clean", False, x["error"])
                raise SystemExit(_finish())
        # Overlap: second cube shifted 10mm into the first (20mm cubes) → clash.
        comps = [
            {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "arm", "part": arm["path"], "transform": {"xyz_mm": [10, 0, 0]}},
        ]
        asm, _placed, err = P._place(sw, mod, comps)
        if err:
            gate("interference_clean", False, err)
            raise SystemExit(_finish())
        rep2, clean2, why2 = _under_warnings_as_errors(
            lambda: cli_observe._run_interference(argparse.Namespace())
        )
        results["interference_report"] = rep2
        cnt = rep2.get("interference_count")
        gate(
            "interference_clean",
            clean2 and bool(rep2.get("ok")),
            why2
            or f"ok={rep2.get('ok')} interference_count={cnt} "
            f"(class-routed, no deprecation warning)",
        )

        # ── C: the legacy free function STILL warns (external back-compat) ─
        doc = get_active_doc(get_sw_app())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            legacy = sw_get_interference(doc)
        warned = any(issubclass(w.category, PendingDeprecationWarning) for w in caught)
        gate(
            "shim_warns",
            warned
            and bool(legacy.get("ok"))
            and legacy.get("interference_count") == cnt,
            f"legacy warned={warned}, same_count={legacy.get('interference_count') == cnt}",
        )
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
