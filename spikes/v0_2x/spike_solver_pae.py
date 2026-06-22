"""W76 production PAE — auto_resolve_clearance through the ai-sw-solver CLI.

Builds a real overlapping-cube assembly (distance mate at 10mm = 4000mm3 clash),
saves it, then exercises the SHIPPED CLI entry (``cli.solver._run_resolve``) end
to end on the hot seat. Three gates:

  A success  : single call -> ok, resolved ~20mm, final trajectory count==0/vol==0
  B re-sense : independently re-poll the resolved in-session doc -> 0 interference
               (proves the success is real, not just the solver's self-report)
  C revert   : a starved call (max_iters=2) -> ok=False, reverted=True, the mate
               back at 10mm and the 4000mm3 clash restored (fail-closed contract)

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_solver_pae.py
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
from ai_sw_bridge.cli.solver import _run_resolve  # noqa: E402
from ai_sw_bridge.motion_audit import read_mate_value_si  # noqa: E402
from ai_sw_bridge.observe_interference import sw_get_interference  # noqa: E402

import spike_autonomous_clearance as AC  # noqa: E402
import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "solver_pae.json"
results: dict[str, Any] = {"pae": "w76_auto_resolve_clearance", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _ns(assembly: str, mate: str, **kw: Any) -> argparse.Namespace:
    return argparse.Namespace(
        assembly=assembly, mate=mate,
        step_mm=kw.get("step_mm", 2.0), max_iters=kw.get("max_iters", 20),
        direction=kw.get("direction", "out"), save=kw.get("save", False),
        output_dir=kw.get("output_dir", str(_HERE.parent / "_results")),
    )


def _vol(intf: dict[str, Any]) -> float:
    return sum(float(i.get("interference_volume_mm3") or 0.0)
               for i in (intf.get("interferences") or []))


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        # ── Build + save a colliding fixture (reuse the W76 spike builder) ──
        a = P._build("solpae_a", P._cube("solpae_a", AC.CUBE_MM))
        b = P._build("solpae_b", P._cube("solpae_b", AC.CUBE_MM))
        if "error" in a or "error" in b:
            gate("fixture_parts", False, a.get("error") or b.get("error"))
            raise SystemExit(_finish())
        fx = None
        for align in (0, 1, 2):
            fx = AC._try_fixture(sw, mod, a["path"], b["path"], align)
            if fx is not None:
                break
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        if fx is None:
            gate("fixture_collides", False, "no colliding init")
            raise SystemExit(_finish())
        mate_name = fx["mate_name"]
        asm_path = str(Path(t1._results_tmp(), f"w76_solver_{os.getpid()}.SLDASM"))
        sret = typed(fx["asm"], "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        gate("fixture_saved", Path(asm_path).exists(),
             f"mate={mate_name} init_vol={_vol(fx['init_intf']):.0f}mm3 "
             f"SaveAs3={sret} exists={Path(asm_path).exists()} path={asm_path}")
        # Flush the in-session doc so the CLI re-opens the colliding disk state.
        sw.CloseAllDocuments(True)

        # ── Gate A: the single CLI call resolves it ─────────────────────────
        ra = _run_resolve(_ns(asm_path, mate_name, step_mm=2.0, max_iters=20))
        results["resolve"] = ra
        final = (ra.get("trajectory") or [{}])[-1]
        gate("resolve_ok",
             bool(ra.get("ok")) and bool(ra.get("resolved"))
             and final.get("count") == 0 and (final.get("volume_mm3") or 0) == 0,
             f"ok={ra.get('ok')} resolved_mm={ra.get('resolved_mm')} "
             f"final={final.get('count')}/{final.get('volume_mm3')} "
             f"err={ra.get('error')}")
        gate("resolve_geometry_sane",
             ra.get("resolved_mm") is not None
             and 19.0 <= float(ra["resolved_mm"]) <= 22.0,
             f"resolved_mm={ra.get('resolved_mm')} (expect ~20)")

        # ── Gate B: independent re-sense of the resolved in-session doc ──────
        active = typed(sw, "ISldWorks", module=mod).ActiveDoc
        intf_b = sw_get_interference(active) if active is not None else {"interference_count": -1}
        gate("independent_zero_interference",
             intf_b.get("interference_count") == 0 and _vol(intf_b) == 0.0,
             f"count={intf_b.get('interference_count')} vol={_vol(intf_b):.1f}")
        sw.CloseAllDocuments(True)  # discard unsaved resolved state

        # ── Gate C: fail-closed revert on a starved budget ──────────────────
        rc = _run_resolve(_ns(asm_path, mate_name, step_mm=2.0, max_iters=2))
        results["revert"] = rc
        active_c = typed(sw, "ISldWorks", module=mod).ActiveDoc
        cur_mm = None
        intf_c = {"interference_count": None}
        if active_c is not None:
            sv = read_mate_value_si(active_c, mate_name)
            cur_mm = round(sv * 1000.0, 3) if sv is not None else None
            intf_c = sw_get_interference(active_c)
        gate("revert_fail_closed",
             rc.get("ok") is False and rc.get("reverted") is True
             and cur_mm is not None and abs(cur_mm - AC.INIT_DIST_MM) < 0.01
             and intf_c.get("interference_count", 0) > 0,
             f"ok={rc.get('ok')} reverted={rc.get('reverted')} "
             f"mate_back_to={cur_mm}mm clash_restored_vol={_vol(intf_c):.0f}mm3 "
             f"best={rc.get('best_state')}")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values())
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
