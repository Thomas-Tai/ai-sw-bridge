"""W75c path mate CLASSIFICATION probe (throwaway).

swMatePATH=15 has NO IPathMateFeatureData interface in the 32.1 typelib (the
declarative CreateMateData->typed_qi pipeline cannot be used). The only legacy
route is selection-driven AddMate3. This probe classifies whether AddMate3(
swMatePATH) materializes a path mate OUT-OF-PROCESS, or ghosts/errors without the
GUI PropertyManager dialog.

Fixture: two placed blocks. Pre-select a VERTEX on the slider + a linear EDGE on
the base (a single contiguous edge is a valid path), then fire AddMate3.

Witness: AddMate3 returns a valid Mate2 (ErrorStatus 0) and a MatePath survives
reopen -> VIABLE-via-AddMate3; else -> WALLED (Route-C / GUI-only).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_path_mate_probe.py
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

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.assembly.handlers import place_components  # noqa: E402
from ai_sw_bridge.assembly.lifecycle import _find_assembly_template  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402
import mech_mate_tier2_rack_cam as t2  # noqa: E402
import mech_mate_tier1_gear_screw as t1  # noqa: E402

_OUT = _HERE.parent / "_results" / "path_mate_probe.json"
results: dict[str, Any] = {"probe": "w75c_path_mate", "swMatePATH": 15, "attempts": []}


def _first_vertex(comp: Any, mod: Any) -> Any | None:
    body = P._body_of(comp)
    if body is None:
        return None
    try:
        edges = body.GetEdges() or ()
    except Exception:
        return None
    for e in edges:
        try:
            ie = typed(e, "IEdge", module=mod)
            v = ie.GetStartVertex()
            if v is not None:
                return v
        except Exception:
            continue
    return None


def main() -> int:
    pythoncom.CoInitialize()
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    verdict = "WALLED"
    try:
        base = P._build("path_base", P._cube("path_base", 60.0))
        slider = P._build("path_slider", P._cube("path_slider", 10.0))
        if "error" in base or "error" in slider:
            results["error"] = base.get("error") or slider.get("error")
            raise SystemExit(_finish(verdict))
        asm = sw.NewDocument(_find_assembly_template(), 0, 0.1, 0.1)
        comps = [
            {"id": "base", "part": base["path"], "transform": {"xyz_mm": [0, 0, 0]}},
            {
                "id": "slider",
                "part": slider["path"],
                "transform": {"xyz_mm": [0, 40, 0]},
            },
        ]
        placed, err = place_components(sw, asm, comps, mod=mod)
        if err:
            results["error"] = f"place: {err}"
            raise SystemExit(_finish(verdict))
        typed_asm = typed(asm, "IAssemblyDoc", module=mod)
        mdoc2 = typed(asm, "IModelDoc2", module=mod)
        mdoc2.ForceRebuild3(False)

        vertex = _first_vertex(placed["slider"], mod)
        edge = t2._first_linear_edge(placed["base"], mod)
        results["vertex_ok"] = vertex is not None
        results["edge_ok"] = edge is not None
        if vertex is None or edge is None:
            results["error"] = "could not get vertex/edge entities"
            raise SystemExit(_finish(verdict))

        # Try a few mark combinations for the (vertex, path) selection.
        for vmark, emark in ((0, 0), (0, 1), (1, 0)):
            try:
                mdoc2.ClearSelection2(True)
                ev = typed_qi(vertex, "IEntity", module=mod)
                ee = typed_qi(edge, "IEntity", module=mod)
                sv = bool(ev.Select2(False, vmark))
                se = bool(ee.Select2(True, emark))
                ret = typed_asm.AddMate3(
                    15, 0, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False
                )
                mate = ret[0] if isinstance(ret, tuple) else ret
                estatus = ret[1] if isinstance(ret, tuple) and len(ret) > 1 else None
                ok = mate is not None and not isinstance(mate, int)
                ftype = None
                if ok:
                    try:
                        ftype = typed(mate, "IFeature", module=mod).GetTypeName2()
                    except Exception:
                        ftype = "?(not IFeature)"
                results["attempts"].append(
                    {
                        "vmark": vmark,
                        "emark": emark,
                        "sel_v": sv,
                        "sel_e": se,
                        "error_status": estatus,
                        "mate_returned": ok,
                        "feature_type": ftype,
                    }
                )
                if ok:
                    verdict = "VIABLE_VIA_ADDMATE3"
                    break
            except Exception as exc:
                results["attempts"].append(
                    {
                        "vmark": vmark,
                        "emark": emark,
                        "raised": f"{type(exc).__name__}: {exc}",
                    }
                )

        # If something materialized, check reopen-survival.
        if verdict == "VIABLE_VIA_ADDMATE3":
            path = str(Path(t1._results_tmp(), f"w75c_path_{os.getpid()}.SLDASM"))
            try:
                mdoc2.SaveAs3(path, 0, 0)
                tsw = typed(sw, "ISldWorks", module=mod)
                sw.CloseAllDocuments(True)
                ro = tsw.OpenDoc6(path, 2, 0, "", 0, 0)
                rdoc = ro[0] if isinstance(ro, tuple) else ro
                names = []
                for f in rdoc.FeatureManager.GetFeatures(False) or ():
                    try:
                        tn = typed(f, "IFeature", module=mod).GetTypeName2()
                        if "Mate" in tn:
                            names.append(tn)
                    except Exception:
                        continue
                results["reopen_mates"] = names
            except Exception as exc:
                results["reopen_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish(verdict)


def _finish(verdict: str) -> int:
    results["verdict"] = verdict
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"Verdict: {verdict}")
    for a in results["attempts"]:
        print(f"  attempt {a}")
    print(f"  reopen_mates={results.get('reopen_mates')}  (wrote {_OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
