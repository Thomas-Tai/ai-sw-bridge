"""W78 diagnostic #3 — kernel ground truth for the component placement frame.

The URDF PAE read the arm's joint origin as [0.03, 0, 0.01] while it was placed
via AddComponent4 at (30, 0, 20)mm. The read translation matched ``placed - CoM``
across both components — but that could be (a) AddComponent4 natively placing by
center-of-mass, or (b) a Python-side URDF serialization offset. This probe
isolates the kernel from any Python math: it dumps the RAW
``IComponent2.Transform2.ArrayData[0..15]`` for each component immediately after
reopen and compares indices [9,10,11] (the translation X/Y/Z) against the exact
AddComponent4 inputs.

  AddComponent4 inputs (metres):
    base : (0.000, 0, 0.000)
    arm  : (0.030, 0, 0.020)

  If ArrayData[9,10,11] == placed            -> serialization bug (fix export_urdf math)
  If ArrayData[9,10,11] == placed - CoM      -> AddComponent4 places by CoM (fix expectation)

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_component_transform_probe.py
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
from ai_sw_bridge.observe_bbox import _read_component_transform  # noqa: E402
from ai_sw_bridge.observe_inertia import sw_get_inertia  # noqa: E402
from ai_sw_bridge.sw_com import resolve  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "component_transform_probe.json"
results: dict[str, Any] = {"probe": "w78_component_transform", "gates": {}, "components": []}

# Exact AddComponent4 placement inputs (metres), keyed by part-name fragment.
_PLACED = {"base": [0.0, 0.0, 0.0], "arm": [0.030, 0.0, 0.020]}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _name2(comp: Any) -> str:
    nm = resolve(comp, "Name2")
    return str(nm() if callable(nm) else nm)


def _raw_arraydata(comp: Any, mod: Any) -> list[float] | None:
    """Read IComponent2.Transform2.ArrayData verbatim (no row-major conversion)."""
    for getter in (lambda: comp.Transform2,
                   lambda: typed(comp, "IComponent2", module=mod).Transform2):
        try:
            t = getter()
            if callable(t):
                t = t()
            if t is None:
                continue
            ad = t.ArrayData
            if callable(ad):
                ad = ad()
            return [float(v) for v in ad]
        except Exception:  # noqa: BLE001
            continue
    return None


def _near(a: float, b: float, tol: float = 5e-4) -> bool:
    return abs(float(a) - float(b)) <= tol


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
        base = P._build("ct_base", P._plate("ct_base"))      # 40x30x5, at origin
        arm = P._build("ct_arm", P._cube("ct_arm", 20.0))     # 20mm cube at (30,0,20)
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
        asm_path = str(Path(t1._results_tmp(), f"w78_ct_{os.getpid()}.SLDASM"))
        typed(asm, "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)
        sw.CloseAllDocuments(True)
        gate("fixture", Path(asm_path).exists(), asm_path)

        # ── Reopen and dump each component's RAW transform ────────────────
        tsw = typed(sw, "ISldWorks", module=mod)
        ro = tsw.OpenDoc6(asm_path, 2, 0, "", 0, 0)
        rdoc = ro[0] if isinstance(ro, tuple) else ro
        asm_typed = typed(rdoc, "IAssemblyDoc", module=mod)
        comps = asm_typed.GetComponents(True)
        comps = list(comps) if isinstance(comps, (list, tuple)) else [comps]

        for comp in comps:
            nm = _name2(comp)
            key = "base" if "base" in nm else ("arm" if "arm" in nm else nm)
            placed = _PLACED.get(key, [None, None, None])

            ad = _raw_arraydata(comp, mod)
            rowmajor = _read_component_transform(comp, mod)
            part_doc = None
            try:
                part_doc = comp.GetModelDoc2()
            except Exception:
                try:
                    part_doc = typed(comp, "IComponent2", module=mod).GetModelDoc2()
                except Exception:
                    part_doc = None
            com_m = None
            if part_doc is not None:
                inert = sw_get_inertia(part_doc)
                com_mm = inert.get("center_of_mass_mm")
                if com_mm:
                    com_m = [float(c) / 1000.0 for c in com_mm]

            trans = ad[9:12] if ad and len(ad) >= 12 else None
            rec = {
                "name": nm, "key": key,
                "placed_m": placed,
                "arraydata_len": (len(ad) if ad else None),
                "arraydata": ad,
                "translation_idx_9_10_11": trans,
                "rowmajor_translation_3_7_11": (
                    [rowmajor[3], rowmajor[7], rowmajor[11]] if rowmajor else None),
                "com_m": com_m,
                "placed_minus_com": (
                    [placed[i] - com_m[i] for i in range(3)]
                    if (com_m and None not in placed) else None),
            }
            results["components"].append(rec)
            print(f"\n  component {nm!r} (key={key})")
            print(f"    placed (AddComponent4)      = {placed}")
            print(f"    ArrayData[9,10,11]          = {trans}")
            print(f"    CoM (part frame)            = {com_m}")
            print(f"    placed - CoM                = {rec['placed_minus_com']}")

            # Decide the hypothesis per component (skip base: placed==origin is
            # ambiguous; the arm is the discriminator).
            if key == "arm" and trans is not None:
                matches_placed = all(_near(trans[i], placed[i]) for i in range(3))
                matches_minus_com = (
                    rec["placed_minus_com"] is not None
                    and all(_near(trans[i], rec["placed_minus_com"][i]) for i in range(3)))
                gate("arm_matches_placed", matches_placed,
                     f"ArrayData[9,10,11]={trans} vs placed={placed}")
                gate("arm_matches_placed_minus_com", matches_minus_com,
                     f"ArrayData[9,10,11]={trans} vs placed-CoM={rec['placed_minus_com']}")
                results["verdict_hint"] = (
                    "SERIALIZATION_BUG (raw==placed)" if matches_placed else
                    "ADDCOMPONENT4_PLACES_BY_COM (raw==placed-CoM)" if matches_minus_com else
                    "NEITHER — investigate rotation/scale")
                print(f"    >>> HYPOTHESIS: {results['verdict_hint']}")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    # This probe is informational: PASS iff exactly one hypothesis matched.
    g = results["gates"]
    one_clear = g.get("fixture", {}).get("ok") and (
        g.get("arm_matches_placed", {}).get("ok")
        != g.get("arm_matches_placed_minus_com", {}).get("ok"))
    results["gates"]["one_clear_hypothesis"] = {
        "ok": bool(one_clear), "detail": results.get("verdict_hint", "?")}
    print(f"  [{'PASS' if one_clear else 'FAIL'}] one_clear_hypothesis: "
          f"{results.get('verdict_hint', '?')}")
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
