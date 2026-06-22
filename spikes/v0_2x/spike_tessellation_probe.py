"""W78 diagnostic #2 — active-document tessellation context unlocks STL.

The lightweight hypothesis was FALSIFIED (spike_lightweight_resolution.py):
components reopen FullyResolved (GetSuppression()==2, unchanged by
ResolveAllLightWeightComponents), yet SaveAs3-STL still writes 0 bytes. The
B-rep is in the kernel (mass props read clean) — what's missing is a TESSELLATION
context. SaveAs3-STL tessellates through the active document's view; a silent,
background, windowless doc has no view -> 0-byte ghost while returning NoError.

This probe tests the active-document fix on the SAME part, three ways:

  A. standalone open SILENT (options=1), no activate     -> expect 0 (reproduce ghost)
  B. standalone open NON-SILENT (options=0) + ActivateDoc3 + ForceRebuild3
                                                          -> expect >0 (the fix)
  C. re-export the SAME activated doc                     -> expect >0 (stable)

If B/C are >0, the production fix for _export_component_stl is: open non-silent,
ActivateDoc3 the part to the foreground, ForceRebuild3, THEN SaveAs3-STL.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_tessellation_probe.py
"""
from __future__ import annotations

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
from ai_sw_bridge.sw_com import resolve  # noqa: E402
from ai_sw_bridge.export.dispatch import ExportRequest, export_all  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "tessellation_probe.json"
results: dict[str, Any] = {"probe": "w78_tessellation_context", "gates": {}, "log": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _export_stl(doc: Any, name: str, out_dir: Path, binary: bool = True) -> int:
    reqs = [ExportRequest(format="stl", output_dir=out_dir, filename=name, binary=binary)]
    try:
        export_all(doc, reqs, name)
    except Exception as exc:  # noqa: BLE001
        results["log"].setdefault("export_errors", {})[name] = repr(exc)
    p = out_dir / f"{name}.stl"
    return p.stat().st_size if p.exists() else 0


def _unwrap(ret: Any) -> Any:
    return ret[0] if isinstance(ret, tuple) else ret


def _finish() -> int:
    # GREEN requires the fix (B + C) to fire; A is the control (ghost expected).
    needed = ("ghost_control", "activate_open", "activated_export", "reexport_stable")
    all_pass = all(results["gates"].get(n, {}).get("ok") for n in needed)
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    tsw = typed(sw, "ISldWorks", module=mod)
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        # ── Build + save a 2-component assembly, then CLOSE (force disk) ──
        base = P._build("tess_base", P._plate("tess_base"))
        arm = P._build("tess_arm", P._cube("tess_arm", 20.0))
        for x in (base, arm):
            if "error" in x:
                gate("fixture", False, x["error"])
                raise SystemExit(_finish())
        comps_spec = [
            {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "arm", "part": arm["path"], "transform": {"xyz_mm": [30, 0, 20]}},
        ]
        asm, _placed, err = P._place(sw, mod, comps_spec)
        if err:
            gate("fixture", False, err)
            raise SystemExit(_finish())
        asm_path = str(Path(t1._results_tmp(), f"w78_tess_{os.getpid()}.SLDASM"))
        typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        sw.CloseAllDocuments(True)
        gate("fixture", Path(asm_path).exists(), asm_path)

        # The base part's own file path — that is our STL target.
        part_path = str(base["path"])
        out_dir = Path(t1._results_tmp(), f"w78_tessout_{os.getpid()}")
        out_dir.mkdir(parents=True, exist_ok=True)
        results["log"]["part_path"] = part_path

        # ── A. CONTROL: standalone SILENT open, no activate -> ghost ──────
        so = tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)   # swDocPART, Silent
        sdoc = _unwrap(so)
        bytes_silent = _export_stl(sdoc, "A_silent", out_dir) if sdoc is not None else -1
        results["log"]["stl_bytes_silent"] = bytes_silent
        gate("ghost_control", bytes_silent == 0,
             f"silent-open STL = {bytes_silent} bytes (expect 0 ghost)")
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

        # ── B. THE FIX: NON-SILENT open + ActivateDoc3 + ForceRebuild3 ────
        no = tsw.OpenDoc6(part_path, 1, 0, "", 0, 0)   # swDocPART, options=0 (non-silent)
        ndoc = _unwrap(no)
        open_ok = ndoc is not None
        title = resolve(ndoc, "GetTitle") if open_ok else None
        title = title() if callable(title) else title
        results["log"]["title"] = str(title)

        # Foreground the doc so the tessellation/view context initialises.
        adoc = None
        try:
            ar = tsw.ActivateDoc3(str(title), False, 0)
            adoc = _unwrap(ar)
            activate_ok = True
        except Exception as exc:  # noqa: BLE001
            activate_ok = False
            results["log"]["activate_error"] = repr(exc)
        # Prefer the freshly-activated pointer if returned, else the opened one.
        active_doc = adoc if adoc is not None else ndoc
        gate("activate_open", open_ok and activate_ok,
             f"non-silent open + ActivateDoc3('{title}') ok={open_ok and activate_ok}")

        # Force graphics triangles to be computed.
        try:
            typed(active_doc, "IModelDoc2", module=mod).ForceRebuild3(False)
            results["log"]["force_rebuild"] = "ok"
        except Exception as exc:  # noqa: BLE001
            results["log"]["force_rebuild"] = repr(exc)

        bytes_activated = _export_stl(active_doc, "B_activated", out_dir) \
            if active_doc is not None else -1
        results["log"]["stl_bytes_activated"] = bytes_activated
        gate("activated_export", bytes_activated > 0,
             f"activated STL = {bytes_activated} bytes (expect >0)")

        # ── C. STABILITY: re-export the same activated doc ────────────────
        bytes_reexport = _export_stl(active_doc, "C_reexport", out_dir) \
            if active_doc is not None else -1
        results["log"]["stl_bytes_reexport"] = bytes_reexport
        gate("reexport_stable", bytes_reexport > 0,
             f"re-export STL = {bytes_reexport} bytes (expect >0)")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
