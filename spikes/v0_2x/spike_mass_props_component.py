"""W78 Phase-1 confirmation — per-component mass properties in-assembly.

The URDF orchestrator needs each LINK's (component's) mass, CoM, and inertia
tensor in the component's OWN frame. This confirms the shipped sw_get_inertia
(+ a direct IMassProperty2.Mass read) extracts isolated per-component mass
properties via IComponent2.GetModelDoc2() WITHOUT any isolate/open-part
maneuver — operating purely on the component's part-doc handle.

Fixture: two cubes of DIFFERENT size (20mm, 30mm) placed in one assembly.
Witness:
  - both components return mass>0 and a non-zero inertia tensor
  - mass ratio b/a ~ 27/8 = 3.375 (volume ratio; density cancels) — proves the
    read DISCRIMINATES per component, not a single shared/active-doc answer
  - per-part CoM is in the component's own frame: z ~ 10mm vs ~15mm (the cubes
    are centered in X/Y on Front and extruded +Z by their side) — distinct

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_mass_props_component.py
"""

from __future__ import annotations

import json
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
from ai_sw_bridge.observe_inertia import sw_get_inertia  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402

_OUT = _HERE.parent / "_results" / "mass_props_component.json"
results: dict[str, Any] = {
    "probe": "w78_mass_props_component",
    "gates": {},
    "links": {},
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _model_doc_of(comp: Any, mod: Any) -> Any | None:
    """IComponent2.GetModelDoc2 — late-bound first, typed fallback (W52-B)."""
    try:
        return comp.GetModelDoc2()
    except Exception:
        try:
            return typed(comp, "IComponent2", module=mod).GetModelDoc2()
        except Exception:
            return None


def _mass_of(part_doc: Any, mod: Any) -> tuple[float | None, float | None]:
    """Read Mass (kg) + Density (kg/m^3) off the part-doc's IMassProperty2."""
    try:
        ext = part_doc.Extension
        mp = typed(ext, "IModelDocExtension", module=mod).CreateMassProperty
        if callable(mp):
            mp = mp()
        if mp is None:
            return None, None
        return float(resolve(mp, "Mass")), float(resolve(mp, "Density"))
    except Exception:
        return None, None


def _link_props(comp: Any, mod: Any) -> dict[str, Any]:
    part_doc = _model_doc_of(comp, mod)
    if part_doc is None:
        return {"error": "GetModelDoc2 returned None"}
    inert = sw_get_inertia(part_doc)
    mass, density = _mass_of(part_doc, mod)
    return {
        "ok": bool(inert.get("ok")) and mass is not None,
        "mass_kg": mass,
        "density_kg_m3": density,
        "center_of_mass_mm": inert.get("center_of_mass_mm"),
        "inertia_tensor_kg_m2": inert.get("inertia_tensor_kg_m2"),
        "error": inert.get("error"),
    }


def _trace(t: Any) -> float:
    try:
        return abs(t[0][0]) + abs(t[1][1]) + abs(t[2][2])
    except Exception:
        return 0.0


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
        a = P._build("mp_a", P._cube("mp_a", 20.0))
        b = P._build("mp_b", P._cube("mp_b", 30.0))
        for x in (a, b):
            if "error" in x:
                gate("fixture", False, x["error"])
                raise SystemExit(_finish())
        comps = [
            {"id": "a", "part": a["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": b["path"], "transform": {"xyz_mm": [60, 0, 0]}},
        ]
        asm, placed, err = P._place(sw, mod, comps)
        if err:
            gate("fixture", False, err)
            raise SystemExit(_finish())
        gate("fixture", len(placed) == 2, f"placed={list(placed.keys())}")

        la = _link_props(placed["a"], mod)
        lb = _link_props(placed["b"], mod)
        results["links"] = {"a": la, "b": lb}

        gate(
            "per_component_mass",
            bool(la.get("ok"))
            and bool(lb.get("ok"))
            and (la.get("mass_kg") or 0) > 0
            and (lb.get("mass_kg") or 0) > 0,
            f"mass_a={la.get('mass_kg')} mass_b={lb.get('mass_kg')} "
            f"errA={la.get('error')} errB={lb.get('error')}",
        )

        # Volume ratio 30^3 / 20^3 = 3.375 — density cancels, proves the read is
        # per-component, not a shared/active-doc answer.
        ratio = None
        if la.get("mass_kg") and lb.get("mass_kg"):
            ratio = lb["mass_kg"] / la["mass_kg"]
        gate(
            "mass_discriminates",
            ratio is not None and abs(ratio - 3.375) < 0.05,
            f"mass_b/mass_a={ratio} (expect 3.375)",
        )

        gate(
            "inertia_nonzero",
            _trace(la.get("inertia_tensor_kg_m2")) > 0
            and _trace(lb.get("inertia_tensor_kg_m2")) > 0,
            f"trA={_trace(la.get('inertia_tensor_kg_m2')):.3e} "
            f"trB={_trace(lb.get('inertia_tensor_kg_m2')):.3e}",
        )

        # Each component's CoM is in its OWN frame: centered in X/Y, z = side/2.
        cza = (la.get("center_of_mass_mm") or [0, 0, 0])[2]
        czb = (lb.get("center_of_mass_mm") or [0, 0, 0])[2]
        gate(
            "com_per_part_frame",
            abs(cza - 10.0) < 0.5 and abs(czb - 15.0) < 0.5,
            f"com_z_a={cza} (expect 10) com_z_b={czb} (expect 15)",
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
