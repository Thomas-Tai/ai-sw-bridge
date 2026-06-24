"""W67 Track-2 / Route-C FEASIBILITY — does in-process execution break the W66
FeatureBossThicken wall?

** LIVE SEAT ONLY. ** Orchestrates an in-process C# VSTA payload
(route_c/RouteCThicken_*.dll) via ISldWorks.RunMacro2 and measures whether the
surface->solid thicken that GHOSTS out-of-process materialises when the SAME
7-arg call runs inside SOLIDWORKS' own process.

Feedback channel = a FILE in %TEMP% (route_c_sentinel.txt) the C# macro writes
as its first action, independent of the swApp pointer — so a null-app early
bail is still diagnosable (custom props can't be the channel; they need the
doc, which needs swApp, the thing under test). The DLL is uniquely named per
build to defeat VSTA assembly caching across RunMacro2 calls in one session.

VERDICTS:
  ROUTE_C_PROVEN   — in-process thicken materialised (INPROC_PASS=1). The W66
                     wall WAS the COM boundary; Route-C is the architecture.
  GHOST_IN_PROCESS — macro ran in-process with a live app pointer, thicken
                     still added nothing. W66 is a TRUE kernel wall, not a
                     marshaling artifact.
  MACRO_EXCEPTION  — the macro reached SW but threw (ERR=... in the sentinel).
  NO_APP_IN_PROC   — Main ran but could not obtain swApp (no VSTA injection AND
                     GetActiveObject failed) — vehicle wiring gap.
  MAIN_NOT_RUN     — RunMacro2 returned but no sentinel file -> Main never
                     executed (assembly cache / wrong module name / macro
                     security).
  VEHICLE_FAILED   — RunMacro2 refused the DLL for every module form (error
                     code reported).
  ERROR            — fixture / connect fault.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pythoncom
from win32com.client import VARIANT

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

_ROUTE_C = Path(__file__).resolve().parent / "route_c"
_SENTINEL = Path(tempfile.gettempdir()) / "route_c_sentinel.txt"
_SW_DEFAULT_TEMPLATE_PART = 8
_SHEET, _SOLID = 1, 0  # swBodyType_e
_MODULE_CANDIDATES = ["SolidWorksMacro", "RouteCThicken.SolidWorksMacro"]
_RUNMACRO_ERR = {
    0: "NoError",
    1: "InvalidArg",
    2: "MacrosAreDisabled",
    3: "NotInDesignMode",
    4: "OnlyCodeModules",
    5: "OutOfMemory",
    6: "InvalidProcname",
}


def _newest_dll() -> Path | None:
    dlls = sorted(_ROUTE_C.glob("RouteCThicken*.dll"), key=lambda p: p.stat().st_mtime)
    return dlls[-1] if dlls else None


def _null() -> Any:
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _bodies(doc: Any, btype: int) -> list[Any]:
    try:
        b = doc.GetBodies2(btype, True)
    except Exception:
        return []
    return list(b) if isinstance(b, (list, tuple)) else ([b] if b else [])


def _solids(doc: Any) -> int:
    return len(_bodies(doc, _SOLID))


def _vol_mm3(doc: Any) -> float:
    v = 0.0
    for b in _bodies(doc, _SOLID):
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                v += float(mp[3]) * 1e9
        except Exception:
            pass
    return v


def _build_standalone_surface(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(_SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return None
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(0.0, 0.0, 0.0, 0.04, 0.03, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    doc.Extension.SelectByID2("Sketch1", "SKETCH", 0, 0, 0, False, 0, _null(), 0)
    ips = doc.InsertPlanarRefSurface
    if callable(ips):
        ips()
    doc.ForceRebuild3(False)
    if len(_bodies(doc, _SHEET)) < 1 or _solids(doc) != 0:
        return None
    return doc


def _preselect_sheet(doc: Any) -> int:
    doc.ClearSelection2(True)
    sheets = _bodies(doc, _SHEET)
    if sheets:
        try:
            sheets[0].Select2(False, 0)
        except Exception:
            pass
    try:
        return int(doc.SelectionManager.GetSelectedObjectCount2(-1))
    except Exception:
        return -1


def _run_macro(sw: Any, dll: str, module: str) -> dict[str, Any]:
    try:
        res = sw.RunMacro2(dll, module, "Main", 0)
    except Exception as e:
        return {
            "module": module,
            "called": False,
            "exc": f"{type(e).__name__}: {e}"[:160],
        }
    ran, err = None, None
    if isinstance(res, (list, tuple)):
        ran = bool(res[0])
        if len(res) > 1:
            err = res[1]
    else:
        ran = bool(res)
    return {
        "module": module,
        "called": True,
        "ran": ran,
        "error_code": err,
        "error_name": _RUNMACRO_ERR.get(err, str(err)),
    }


def _parse_sentinel() -> dict[str, str]:
    if not _SENTINEL.is_file():
        return {}
    d: dict[str, str] = {}
    for line in _SENTINEL.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            d[k.strip()] = v.strip()
    return d


def run() -> dict[str, Any]:
    out: dict[str, Any] = {"spike": "route_c_thicken"}
    dll = _newest_dll()
    if dll is None:
        return {**out, "verdict": "ERROR", "reason": "no RouteCThicken*.dll built"}
    out["dll"] = str(dll)

    sw = get_sw_app()
    if sw is None:
        return {**out, "verdict": "ERROR", "reason": "get_sw_app() returned None"}
    try:
        rev = sw.RevisionNumber
        out["sw_revision"] = rev() if callable(rev) else rev
    except Exception:
        out["sw_revision"] = "<unreadable>"

    # Delete any stale sentinel so we never read a previous fire's result.
    try:
        _SENTINEL.unlink(missing_ok=True)
    except Exception:
        pass

    doc = _build_standalone_surface(sw)
    if doc is None:
        return {
            **out,
            "verdict": "ERROR",
            "reason": "standalone surface fixture failed",
        }

    out["solids_before"] = _solids(doc)
    out["vol_before_mm3"] = _vol_mm3(doc)
    out["preselect_count_oop"] = _preselect_sheet(doc)

    attempts, winner = [], None
    for module in _MODULE_CANDIDATES:
        a = _run_macro(sw, str(dll), module)
        attempts.append(a)
        if a.get("ran"):
            winner = a
            break
        # If the sentinel appeared even on a "ran=False", Main still executed.
        if _SENTINEL.is_file():
            winner = a
            break
    out["runmacro_attempts"] = attempts

    sentinel = _parse_sentinel()
    out["sentinel"] = sentinel
    out["sentinel_path"] = str(_SENTINEL)

    out["solids_after_oop"] = _solids(doc)
    out["vol_after_mm3_oop"] = _vol_mm3(doc)
    out["dvol_mm3_oop"] = out["vol_after_mm3_oop"] - out["vol_before_mm3"]

    main_ran = sentinel.get("MAIN_ENTERED") == "1"
    has_app = main_ran and sentinel.get("SWAPP_NULL") == "False"
    if not main_ran:
        out["verdict"] = "MAIN_NOT_RUN" if winner is not None else "VEHICLE_FAILED"
    elif not has_app:
        out["verdict"] = "NO_APP_IN_PROC"
    elif sentinel.get("ERR"):
        out["verdict"] = "MACRO_EXCEPTION"
    elif sentinel.get("INPROC_PASS") == "1":
        out["verdict"] = "ROUTE_C_PROVEN"
    else:
        out["verdict"] = "GHOST_IN_PROCESS"
    return out


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {}
    try:
        out = run()
    finally:
        try:
            sw = get_sw_app()
            if sw is not None:
                sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    res_dir = Path(__file__).resolve().parent / "_results"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "route_c_thicken.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(out, indent=2, default=str))
    sys.stderr.write(f"\n[route-c] VERDICT: {out.get('verdict')}\n")
    return 0 if out.get("verdict") == "ROUTE_C_PROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
