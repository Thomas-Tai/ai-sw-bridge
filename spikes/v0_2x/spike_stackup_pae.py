"""W77 production PAE — analyze_stackup through ai-sw-observe.

Builds a real 1D component stack and audits it with the SHIPPED orchestration
verb on the hot seat:

    base(20mm cube) | 2mm gap | spacer(20mm cube) | 3mm gap | top(20mm cube)

Three 20mm cubes are centered on origin (X in [-10,10] in their own frame) and
placed at X = 0, 22, 45 mm, so consecutive nearest-face gaps are exactly 2.0mm
and 3.0mm and the direct base<->top span is 25mm (= 2 + 20(spacer body) + 3).

Gates:
  A fixture   : assembly built, 3 components placed, Name2 captured
  B gaps      : consecutive pairs measure 2.0mm and 3.0mm, accumulated 5.0mm,
                ok=True / accumulation_complete=True  (direct module call)
  C endpoint  : endpoint_span 25mm, intervening_span 20mm, linear_consistent
  D cli_entry : the same analysis through the CLI runner (_run_analyze_stackup,
                active-doc path) returns the same 5.0mm accumulation headlessly

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_stackup_pae.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
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

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.observe_clearance import sw_analyze_stackup  # noqa: E402
from ai_sw_bridge.cli.observe import _run_analyze_stackup  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "stackup_pae.json"
results: dict[str, Any] = {"pae": "w77_analyze_stackup", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _name2(comp: Any) -> str | None:
    try:
        nm = comp.Name2
        return str(nm() if callable(nm) else nm)
    except Exception:
        return None


def _near(val: Any, target: float, tol: float = 0.05) -> bool:
    return val is not None and abs(float(val) - target) <= tol


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values())
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
        # ── Build three 20mm cubes ───────────────────────────────────────
        base = P._build("stk_base", P._cube("stk_base", 20.0))
        spacer = P._build("stk_spacer", P._cube("stk_spacer", 20.0))
        top = P._build("stk_top", P._cube("stk_top", 20.0))
        for x in (base, spacer, top):
            if "error" in x:
                gate("fixture", False, x["error"])
                raise SystemExit(_finish())

        # Place along +X: base@0, spacer@22 (gap 2mm), top@45 (gap 3mm).
        comps = [
            {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "spacer", "part": spacer["path"], "transform": {"xyz_mm": [22, 0, 0]}},
            {"id": "top", "part": top["path"], "transform": {"xyz_mm": [45, 0, 0]}},
        ]
        asm, placed, err = P._place(sw, mod, comps)
        if err:
            gate("fixture", False, err)
            raise SystemExit(_finish())
        names = [_name2(placed["base"]), _name2(placed["spacer"]), _name2(placed["top"])]
        gate("fixture", all(names) and len(placed) == 3,
             f"components={names}")
        if not all(names):
            raise SystemExit(_finish())

        # Save so the active-doc CLI path has a stable on-disk model.
        asm_path = str(Path(t1._results_tmp(), f"w77_stackup_{os.getpid()}.SLDASM"))
        typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)

        # ── Gate B/C: direct module call on the known assembly doc ───────
        rep = sw_analyze_stackup(asm, names, check_endpoints=True)
        results["report"] = rep
        gaps = [p.get("gap_mm") for p in rep.get("pairs", [])]
        gate("gaps",
             rep.get("ok") is True and rep.get("accumulation_complete") is True
             and len(gaps) == 2 and _near(gaps[0], 2.0) and _near(gaps[1], 3.0)
             and _near(rep.get("accumulated_gap_mm"), 5.0),
             f"ok={rep.get('ok')} gaps={gaps} "
             f"accumulated={rep.get('accumulated_gap_mm')} err={rep.get('error')}")
        gate("endpoint",
             _near(rep.get("endpoint_span_mm"), 25.0)
             and _near(rep.get("intervening_span_mm"), 20.0)
             and rep.get("linear_consistent") is True
             and not rep.get("warnings"),
             f"endpoint_span={rep.get('endpoint_span_mm')} "
             f"intervening={rep.get('intervening_span_mm')} "
             f"linear={rep.get('linear_consistent')} warn={rep.get('warnings')}")

        # ── Gate D: the same audit through the CLI runner (active doc) ────
        ns = argparse.Namespace(components=names, no_endpoints=False)
        cli_rep = _run_analyze_stackup(ns)
        results["cli_report"] = cli_rep
        gate("cli_entry",
             cli_rep.get("ok") is True
             and _near(cli_rep.get("accumulated_gap_mm"), 5.0),
             f"ok={cli_rep.get('ok')} accumulated={cli_rep.get('accumulated_gap_mm')} "
             f"err={cli_rep.get('error')}")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
