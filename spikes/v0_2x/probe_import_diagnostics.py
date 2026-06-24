"""MEASURE-FIRST probe — import-diagnostics observe lane.

Discover what the diagnostic COM endpoints actually return, and whether they
yield JSON-serializable, actionable metrics (gap/fault counts, decoded topology
error codes) for a read-only observe lane.

DLL-validated reconnaissance (docs/sw_api_full.md, build 32.1.0.123):
  * IPartDoc.ImportDiagnosis(CloseAllGaps, RemoveFaces, FixFaces, Options:Int32)
      -> Int32.  The 3 bools are REPAIR actions — for a READ-ONLY lane we pass
      all False and read the Int32 (meaning unknown → discover here).
  * IModelDoc2.CheckModel  — DOES NOT EXIST in this DLL (the directive named it,
      but it is absent — like CreateEquationCurve2). The model-fault API is
      IBody2.Check3 -> IFaultEntity (Count, Entity[i], ErrorCode[i]); ErrorCode
      decodes via swFaultEntityErrorCode_e.  (check_geometry W59 used this but
      was never wired into the observe facade.)

Probe matrix (one seat fire):
  1. native block          — baseline: does ImportDiagnosis run on a non-imported
                             part? Check3 fault count on a healthy solid (expect 0).
  2. IGES round-trip KNIT  — healthy imported solid: ImportDiagnosis + Check3.
  3. IGES round-trip NOKNIT— faulty import (unstitched surfaces via AttemptKnitting
                             =False): ImportDiagnosis (expect gaps) + Check3.

Witness questions:
  - What int does ImportDiagnosis return, and does it differ healthy vs faulty?
  - Does ImportDiagnosis(all False) MUTATE? (guard: body count before/after.)
  - Does Check3 yield Count + decodable ErrorCode[]? Are surface bodies the
    unstitched-import signal?

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/probe_import_diagnostics.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
import win32com.client.dynamic as w32dyn  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_WORK = _HERE.parent / "_results" / "import_diag_work"
_OUT = _HERE.parent / "_results" / "probe_import_diagnostics.json"
out: dict[str, Any] = {"probe": "import_diagnostics"}

# swFaultEntityErrorCode_e — partial decode (the gap/face/body classes most
# relevant to imported geometry).
_FAULT_CODES = {
    1: "swBodyCorrupt",
    2: "swBodyInvalidIdentifiers",
    3: "swBodyInsideOut",
    4: "swBodyRegionsInconsistent",
    16: "swFaceBadVertex",
    17: "swFaceBadEdge",
    18: "swFaceBadEdgeOrder",
    19: "swFaceNoAccomVertex",
    20: "swFaceBadLoops",
    21: "swFaceSelfIntersecting",
    22: "swFaceBadWireframe",
    23: "swFaceCheckerFailure",
}


def _resolve(obj: Any, attr: str) -> Any:
    v = getattr(obj, attr)
    return v() if callable(v) else v


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _build_block(sw: Any, path: str | None) -> Any:
    """40x30x10 solid block via the proven fixture (re-selects Sketch1 before
    FeatureExtrusion2 — the step my hand-rolled version omitted). Save to *path*
    if given. Returns the late-bound doc."""
    doc = fx.build_block(sw)
    doc.ForceRebuild3(False)
    if path:
        doc.SaveAs3(path, 0, 0)
    return doc


def _bodies(part_ld: Any) -> list[Any]:
    try:
        bs = part_ld.GetBodies2(-1, False)  # swAllBodies
    except Exception:
        return []
    if bs is None:
        return []
    return list(bs) if isinstance(bs, (list, tuple)) else [bs]


def _body_summary(part_ld: Any) -> dict[str, Any]:
    mod = wrapper_module()
    solid = sheet = other = 0
    faults: list[dict[str, Any]] = []
    bodies = _bodies(part_ld)
    for b in bodies:
        try:
            tb = typed(b, "IBody2", module=mod)
        except Exception:
            tb = b
        # body type: IBody2.GetType() -> swBodyType_e (0 solid, 1 sheet)
        try:
            bt = _resolve(tb, "GetType")
            bt = int(bt)
        except Exception:
            bt = None
        if bt == 0:
            solid += 1
        elif bt == 1:
            sheet += 1
        else:
            other += 1
        # Check3 -> IFaultEntity
        try:
            fault = _resolve(tb, "Check3")
            if fault is not None:
                cnt = int(_resolve(fault, "Count"))
                codes = []
                for i in range(cnt):
                    try:
                        ec = int(fault.ErrorCode(i))
                    except Exception:
                        try:
                            ec = int(fault.ErrorCode[i])
                        except Exception:
                            ec = None
                    codes.append(
                        {"code": ec, "name": _FAULT_CODES.get(ec, f"code_{ec}")}
                    )
                if cnt:
                    faults.append({"body_type": bt, "count": cnt, "codes": codes})
        except Exception as e:  # noqa: BLE001
            faults.append({"check3_exc": repr(e)})
    return {
        "body_count": len(bodies),
        "solid": solid,
        "sheet": sheet,
        "other": other,
        "faults": faults,
    }


def _import_diagnosis(part_ld: Any) -> dict[str, Any]:
    """Read-only ImportDiagnosis: all repair flags False. Guard mutation by body
    count before/after."""
    before = len(_bodies(part_ld))
    r: dict[str, Any] = {"bodies_before": before}
    try:
        ret = part_ld.ImportDiagnosis(False, False, False, 0)
        r["return"] = ret
        r["return_type"] = type(ret).__name__
    except Exception as e:  # noqa: BLE001
        r["exc"] = repr(e)
    r["bodies_after"] = len(_bodies(part_ld))
    r["mutated"] = r.get("bodies_after") != before
    return r


def _import_iges(sw: Any, tsw: Any, igs: str, *, knit: bool) -> Any:
    """Import *igs* with surface-knitting on/off. Returns the imported doc (late
    bound) or None. AttemptKnitting=False -> unstitched surface bodies."""
    _close_all(sw)
    # Try to set knit on the import-data object and via SetIgesInfo (belt+braces).
    try:
        sw.SetIgesInfo("", 0.0, knit)
    except Exception:
        pass
    try:
        import_data = tsw.GetImportFileData(str(igs))
    except Exception:
        import_data = None
    if import_data is not None:
        for prop in ("AttemptKnitting", "KnitSurfaces", "Knit"):
            try:
                setattr(import_data, prop, knit)
            except Exception:
                continue
    try:
        result = tsw.LoadFile4(str(igs), "r", import_data, 0)
    except Exception as e:  # noqa: BLE001
        return None, repr(e)
    doc = result[0] if isinstance(result, tuple) else result
    return (w32dyn.Dispatch(doc) if doc is not None else None), None


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    tsw = typed(sw, "ISldWorks", module=wrapper_module())
    _close_all(sw)
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    try:
        # 1. native block baseline
        try:
            seed = str(_WORK / "block.SLDPRT")
            doc = _build_block(sw, seed)
            part_ld = w32dyn.Dispatch(doc)
            out["native"] = {
                "import_diagnosis": _import_diagnosis(part_ld),
                "bodies": _body_summary(part_ld),
            }
            igs = str(_WORK / "block.IGS")
            try:
                doc.SaveAs3(igs, 0, 0)
                out["iges_saved"] = os.path.isfile(igs)
            except Exception as e:  # noqa: BLE001
                out["iges_save_exc"] = repr(e)
        except Exception as e:  # noqa: BLE001
            out["native_exc"] = repr(e)

        # 2. IGES round-trip, KNIT ON (healthy imported solid)
        try:
            ld, err = _import_iges(sw, tsw, igs, knit=True)
            if ld is None:
                out["iges_knit"] = {"import_error": err}
            else:
                out["iges_knit"] = {
                    "import_diagnosis": _import_diagnosis(ld),
                    "bodies": _body_summary(ld),
                }
        except Exception as e:  # noqa: BLE001
            out["iges_knit_exc"] = repr(e)

        # 3. IGES round-trip, KNIT OFF (faulty unstitched surfaces)
        try:
            ld, err = _import_iges(sw, tsw, igs, knit=False)
            if ld is None:
                out["iges_noknit"] = {"import_error": err}
            else:
                out["iges_noknit"] = {
                    "import_diagnosis": _import_diagnosis(ld),
                    "bodies": _body_summary(ld),
                }
        except Exception as e:  # noqa: BLE001
            out["iges_noknit_exc"] = repr(e)
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"\n(wrote {_OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
