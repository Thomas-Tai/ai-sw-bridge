"""v0.18 Strangler-slice PAE — class-based API boundary on the hot seat.

Proves the Observer/URDF vertical slice end-to-end:

  A cli_clean   : ai-sw-observe `inertia` (SolidWorksClient().observe.get_inertia)
                  returns ok=True with a real inertia tensor AND emits NO
                  PendingDeprecationWarning internally (internal tools bypass
                  the legacy shim). Run under warnings-as-errors to prove it.
  B shim_warns  : the legacy free function sw_get_inertia STILL emits
                  PendingDeprecationWarning for external scripts (back-compat).
  C data_sane   : the routed inertia payload is physically sane (CoM present,
                  non-zero diagonal tensor) for a known cube.
  D urdf_clean  : ai-sw-urdf export (SolidWorksClient().urdf.export, which uses
                  the _impl core for mass props) runs flawlessly with NO
                  PendingDeprecationWarning internally.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_v018_slice_pae.py
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

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.cli import observe as cli_observe  # noqa: E402
from ai_sw_bridge.cli.urdf import _run_export  # noqa: E402
from ai_sw_bridge.observe_inertia import sw_get_inertia  # noqa: E402
from ai_sw_bridge.sw_com import get_active_doc, get_sw_app  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "v018_slice_pae.json"
results: dict[str, Any] = {"pae": "v018_strangler_slice", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(g["ok"] for g in results["gates"].values())
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
        # ── Build a cube part; it becomes the active document ─────────────
        cube = P._build("v018_cube", P._cube("v018_cube", 20.0))
        if "error" in cube:
            gate("fixture", False, cube["error"])
            raise SystemExit(_finish())
        active = get_active_doc(get_sw_app())
        gate("fixture", active is not None, f"cube={cube.get('path')}")

        # ── A: inertia CLI routes through the client with NO warning ──────
        with warnings.catch_warnings():
            warnings.simplefilter("error", PendingDeprecationWarning)
            try:
                rep = cli_observe._run_inertia(argparse.Namespace())
                clean = True
                why = ""
            except PendingDeprecationWarning as exc:  # noqa: BLE001
                rep = {"ok": False}
                clean = False
                why = f"internal PendingDeprecationWarning leaked: {exc}"
        results["inertia_report"] = rep
        gate("cli_clean", clean and bool(rep.get("ok")),
             why or f"ok={rep.get('ok')} (class-routed, no deprecation warning)")

        # ── C: the routed payload is physically sane for a cube ───────────
        tensor = rep.get("inertia_tensor_kg_m2")
        com = rep.get("center_of_mass_mm")
        diag_ok = (isinstance(tensor, (list, tuple)) and len(tensor) == 3
                   and all(float(tensor[i][i]) > 0 for i in range(3)))
        gate("data_sane", com is not None and diag_ok,
             f"com_mm={com} tensor_diag="
             f"{[tensor[i][i] for i in range(3)] if diag_ok else tensor}")

        # ── B: the legacy free function STILL warns (external back-compat) ─
        doc = get_active_doc(get_sw_app())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            legacy = sw_get_inertia(doc)
        warned = any(issubclass(w.category, PendingDeprecationWarning) for w in caught)
        gate("shim_warns",
             warned and bool(legacy.get("ok"))
             and legacy.get("inertia_tensor_kg_m2") == tensor,
             f"legacy warned={warned}, same_payload={legacy.get('inertia_tensor_kg_m2') == tensor}")

        # ── D: URDF CLI routes through client.urdf, internal _impl, no warn ─
        base = P._build("v018_base", P._plate("v018_base"))
        arm = P._build("v018_arm", P._cube("v018_arm", 20.0))
        for x in (base, arm):
            if "error" in x:
                gate("urdf_clean", False, x["error"])
                raise SystemExit(_finish())
        comps = [
            {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "arm", "part": arm["path"], "transform": {"xyz_mm": [30, 0, 20]}},
        ]
        asm, _placed, err = P._place(sw, mod, comps)
        if err:
            gate("urdf_clean", False, err)
            raise SystemExit(_finish())
        asm_path = str(Path(t1._results_tmp(), f"v018_urdf_{os.getpid()}.SLDASM"))
        typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        sw.CloseAllDocuments(True)
        out_dir = str(Path(t1._results_tmp(), f"v018_urdfout_{os.getpid()}"))
        ns = argparse.Namespace(
            assembly=asm_path, output_dir=out_dir,
            robot_name="sorter", ascii_stl=False)
        with warnings.catch_warnings():
            warnings.simplefilter("error", PendingDeprecationWarning)
            try:
                urep = _run_export(ns)
                uclean = True
                uwhy = ""
            except PendingDeprecationWarning as exc:  # noqa: BLE001
                urep = {"ok": False}
                uclean = False
                uwhy = f"internal PendingDeprecationWarning leaked: {exc}"
        results["urdf_report_ok"] = bool(urep.get("ok"))
        gate("urdf_clean", uclean and bool(urep.get("ok")),
             uwhy or f"ok={urep.get('ok')} (client.urdf routed, no deprecation warning)")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
