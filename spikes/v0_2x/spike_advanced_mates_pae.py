"""W75 production PAE — symmetric + profile_center through create_mate.

Exercises the ACTUAL shipped production handler ``assembly.handlers.create_mate``
(the same per-mate function commit_assembly calls) with declarative mate specs
for the two new advanced types, then save -> close -> reopen and verifies the
mate persists (no over-defined / suppressed feature).

  symmetric: {type:"symmetric", a:{normal±X}, b:{normal±X},
              symmetry_plane:"Right Plane"} -> MateSymmetric, survives reopen.
  profile_center: {type:"profile_center", a:{normal Z}, b:{normal Z},
              offset_mm, lock_rotation} -> MateProfileCenter, survives reopen.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_advanced_mates_pae.py
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

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.assembly.handlers import create_mate, place_components  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import _find_assembly_template  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "advanced_mates_pae.json"
results: dict[str, Any] = {"pae": "w75_advanced_mates", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _place(sw: Any, mod: Any, comps: list[dict]) -> Any:
    asm = sw.NewDocument(_find_assembly_template(), 0, 0.1, 0.1)
    if asm is None:
        return {"error": "ASM_NEWDOC_NONE"}
    placed, err = place_components(sw, asm, comps, mod=mod)
    if err is not None:
        return {"error": f"PLACE_FAILED: {err}"}
    typed(asm, "IModelDoc2", module=mod).ForceRebuild3(False)
    return {"asm": asm, "placed": placed}


def _reopen_mate_names(sw: Any, mod: Any, path: str) -> list[str]:
    out = []
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        sw.CloseAllDocuments(True)
        ro = tsw.OpenDoc6(path, 2, 0, "", 0, 0)
        rdoc = ro[0] if isinstance(ro, tuple) else ro
        if rdoc is None:
            return out
        typed(rdoc, "IModelDoc2", module=mod).ForceRebuild3(False)
        for f in rdoc.FeatureManager.GetFeatures(False) or ():
            try:
                tn = typed(f, "IFeature", module=mod).GetTypeName2()
                if "Mate" in tn:
                    out.append(tn)
            except Exception:
                continue
    except Exception:
        pass
    return out


def _leg(sw: Any, mod: Any, *, name: str, comps: list[dict], mate: dict,
         expect_type: str) -> None:
    ctx = _place(sw, mod, comps)
    if "error" in ctx:
        gate(f"{name}_place", False, ctx["error"])
        return
    gate(f"{name}_place", True, f"placed {len(comps)} comps")
    asm, placed = ctx["asm"], ctx["placed"]
    feat, err = create_mate(asm, placed, mate, mod=mod)
    if feat is None:
        gate(f"{name}_create_mate", False, str(err))
        return
    try:
        ft = typed(feat, "IFeature", module=mod).GetTypeName2()
    except Exception:
        ft = "?"
    gate(f"{name}_create_mate", expect_type in ft, f"feature_type={ft}")
    path = str(Path(t1._results_tmp(), f"w75pae_{name}_{os.getpid()}.SLDASM"))
    try:
        typed(asm, "IModelDoc2", module=mod).SaveAs3(path, 0, 0)
        saved = True
    except Exception as exc:
        saved = False
        gate(f"{name}_save", False, repr(exc))
    if saved:
        names = _reopen_mate_names(sw, mod, path)
        gate(f"{name}_reopen_persists", expect_type in " ".join(names),
             f"reopen_mates={names}")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        # --- symmetric: two cubes, symmetry about the assembly Right Plane ---
        a = P._build("pae_sym_a", P._cube("pae_sym_a", 10.0))
        b = P._build("pae_sym_b", P._cube("pae_sym_b", 10.0))
        if "error" not in a and "error" not in b:
            _leg(
                sw, mod, name="symmetric",
                comps=[
                    {"id": "a", "part": a["path"], "transform": {"xyz_mm": [-50, 0, 0]}},
                    {"id": "b", "part": b["path"], "transform": {"xyz_mm": [50, 30, 0]}},
                ],
                mate={
                    "type": "symmetric",
                    "a": {"component": "a", "face_ref": {"normal": [1, 0, 0]}},
                    "b": {"component": "b", "face_ref": {"normal": [1, 0, 0]}},
                    "symmetry_plane": "Right Plane",
                },
                expect_type="MateSymmetric",
            )
        else:
            gate("symmetric_fixture", False, a.get("error") or b.get("error"))

        # --- profile_center: two plates, centered profiles ---
        pa = P._build("pae_pc_a", P._plate("pae_pc_a"))
        pb = P._build("pae_pc_b", P._plate("pae_pc_b"))
        if "error" not in pa and "error" not in pb:
            _leg(
                sw, mod, name="profile_center",
                comps=[
                    {"id": "a", "part": pa["path"], "transform": {"xyz_mm": [0, 0, 0]}},
                    {"id": "b", "part": pb["path"], "transform": {"xyz_mm": [0, 0, 40]}},
                ],
                mate={
                    "type": "profile_center",
                    "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
                    "b": {"component": "b", "face_ref": {"normal": [0, 0, 1]}},
                    "offset_mm": 0.0, "lock_rotation": False,
                },
                expect_type="MateProfileCenter",
            )
        else:
            gate("profile_center_fixture", False, pa.get("error") or pb.get("error"))
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()

    all_pass = all(g["ok"] for g in results["gates"].values())
    gate("OVERALL", all_pass,
         f"{sum(1 for g in results['gates'].values() if g['ok'])}/"
         f"{len(results['gates'])}")
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
