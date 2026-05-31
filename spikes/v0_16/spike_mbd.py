"""
Spike v0.16 / S-MBD — IDimXpertManager annotation round-trip.
[authored seat-free; RUN ON A LIVE SEAT]

Probes the SOLIDWORKS MBD / DimXpert API surface out-of-process:
  - Locate and load the DimXpert type library (dimxpert.tlb / swdimxpert.tlb)
  - IModelDoc2.GetDimXpertManager(configName) -> IDimXpertManager
  - Enumerate annotations: GetAnnotationCount / GetAnnotations
  - Probe annotation sub-interfaces: IDimXpertDatumFeature,
    IDimXpertGeometricTolerance, IDimXpertAnnotation
  - Probe creation methods (if reachable): datum, geometric tolerance, dimension

The goal is to map the DimXpert API surface — what is reachable out-of-process
via late/early binding, what marshaling walls exist — before building the
MBD handler layer (P2.2 tolerances + P2.3 DimXpert annotations).

Background
----------
Phase 2 (spec.md section 7.2) declares two MBD paths:

  (a) Tolerances as first-class fields on model dimensions
      (IDimension.Tolerance / IDisplayDimension) — model-item import carries
      them to the drawing for free.  S-MBD probes whether IDimension.Tolerance
      is reachable out-of-process.

  (b) DimXpert / MBD annotations (drawingless definition) — a separate pass
      through IDimXpertManager.  FR-2-04.

The DimXpert interfaces live in a **separate type library** (typically
dimxpert.tlb or swdimxpert.tlb, installed alongside sldworks.tlb).  This
means the gen_py makepy module from sldworks.tlb alone may not contain
DimXpert interface classes — the spike probes both the late-bound path
(dynamic dispatch, no typelib needed) and the early-bound path (separate
typelib load + EnsureModule).

Risks: DimXpert type-library location, annotation creation OUT-param
marshaling (the same class that bit S-PERSIST), SAFEARRAY-of-dispatch
annotation arrays.

Verdict
-------
PASS    : DimXpertManager obtained, annotations enumerable, >=1 creation
          method reachable — build the handler.
PARTIAL : DimXpertManager obtained but creation methods fail or typelib
          not loadable — narrow the binding path; run --mode vba to isolate.
FAIL    : GetDimXpertManager unreachable or DimXpert type library absent —
          defer or route B/C.

Prereq: SOLIDWORKS running with a blank Part active (or let the harness
build one). Non-destructive.

Usage
-----
    python spikes/v0_16/spike_mbd.py --out report.json
    python spikes/v0_16/spike_mbd.py --mode vba
    python spikes/v0_16/spike_mbd.py --skip-build   # probe existing part
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import winreg
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402
import pywintypes  # noqa: E402
from win32com.client import gencache, dynamic  # noqa: E402

from spike_persist_reference import build_single_box  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DOC_PART = 1


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _capture(fn: Any, label: str = "") -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "_val": val,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except pywintypes.com_error as e:
        return {
            "status": "COM_ERROR",
            "hresult": (
                f"{e.hresult:#010x}"
                if hasattr(e, "hresult") and e.hresult
                else None
            ),
            "description": getattr(e, "strerror", str(e))[:200],
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except Exception as e:
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


# ---------------------------------------------------------------------------
# DimXpert type-library discovery
# ---------------------------------------------------------------------------

_DIMXPERT_TLB_CANDIDATES = [
    "dimxpert.tlb",
    "swdimxpert.tlb",
    "swDimXpert.tlb",
    "DimXpert.tlb",
]


def _find_sw_install_dir() -> str | None:
    """Locate the SOLIDWORKS install directory from the registry."""
    for key_path in [
        r"SOFTWARE\SolidWorks\SOLIDWORKS Application",
        r"SOFTWARE\SolidWorks\SldWorks",
    ]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                return winreg.QueryValueEx(key, "SolidWorks Folder")[0]
        except (FileNotFoundError, OSError):
            continue
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Classes\TypeLib"
            r"\{83AD3F01-0160-11D2-8023-080009DBCB24}\32.0\0\win64",
        ) as key:
            tlb_path = winreg.QueryValue(key)
            if tlb_path:
                return str(Path(tlb_path).parent)
    except (FileNotFoundError, OSError):
        pass
    return None


def _find_dimxpert_tlb() -> dict[str, Any]:
    """Search for the DimXpert type library on disk."""
    sw_dir = _find_sw_install_dir()
    result: dict[str, Any] = {"sw_install_dir": sw_dir}
    if not sw_dir:
        result["status"] = "SW_DIR_NOT_FOUND"
        return result

    search_dirs = [
        Path(sw_dir),
        Path(sw_dir) / "api" / "redist",
        Path(sw_dir) / "api" / "redist64",
        Path(sw_dir) / "redist",
        Path(sw_dir) / "redist64",
    ]

    for d in search_dirs:
        if not d.is_dir():
            continue
        for candidate in _DIMXPERT_TLB_CANDIDATES:
            p = d / candidate
            if p.is_file():
                result["status"] = "FOUND"
                result["tlb_path"] = str(p)
                return result
        try:
            for f in d.iterdir():
                if "dimxpert" in f.name.lower() and f.suffix.lower() == ".tlb":
                    result["status"] = "FOUND"
                    result["tlb_path"] = str(f)
                    return result
        except PermissionError:
            continue

    result["status"] = "NOT_FOUND"
    result["searched"] = [str(d) for d in search_dirs if d.is_dir()]
    return result


def _load_dimxpert_typelib(tlb_path: str) -> dict[str, Any]:
    """Load the DimXpert typelib and enumerate its interfaces."""
    result: dict[str, Any] = {"tlb_path": tlb_path}
    t0 = time.perf_counter()
    try:
        tlb = pythoncom.LoadTypeLib(tlb_path)
    except Exception as e:
        result["status"] = "LOAD_FAILED"
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    la = tlb.GetLibAttr()
    lib_name, lib_doc, _, _ = tlb.GetDocumentation(-1)
    result.update({
        "status": "LOADED",
        "lib_name": lib_name,
        "lib_doc": lib_doc,
        "libid": str(la[0]),
        "lcid": la[1],
        "major": la[3],
        "minor": la[4],
        "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
    })

    TYPEKIND_NAMES = {
        0: "ENUM", 1: "RECORD", 2: "MODULE", 3: "INTERFACE",
        4: "DISPATCH", 5: "COCLASS", 6: "ALIAS", 7: "UNION",
    }

    interfaces: list[dict[str, Any]] = []
    n = tlb.GetTypeInfoCount()
    for i in range(n):
        info = tlb.GetTypeInfo(i)
        name, doc, _, _ = tlb.GetDocumentation(i)
        ta = info.GetTypeAttr()
        members: list[str] = []
        for f_idx in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f_idx)
                names = info.GetNames(fd.memid)
                if names:
                    members.append(names[0])
            except Exception:
                pass
        for p_idx in range(ta.cVars):
            try:
                vd = info.GetVarDesc(p_idx)
                names = info.GetNames(vd.memid)
                if names:
                    members.append(names[0])
            except Exception:
                pass

        if "dimxpert" in name.lower() or "DimXpert" in name:
            interfaces.append({
                "name": name,
                "doc": doc,
                "typekind": TYPEKIND_NAMES.get(ta.typekind, str(ta.typekind)),
                "member_count": len(members),
                "members": members,
            })

    result["total_type_infos"] = n
    result["dimxpert_interfaces"] = interfaces
    return result


def _ensure_dimxpert_module(
    lib_info: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    """Generate the makepy module for the DimXpert typelib."""
    info: dict[str, Any] = {}
    try:
        mod = gencache.EnsureModule(
            lib_info["libid"], lib_info["lcid"],
            lib_info["major"], lib_info["minor"],
        )
        if mod is None:
            info["status"] = "EnsureModule returned None"
            return None, info
        info["status"] = "OK"
        info["module"] = mod.__name__
        return mod, info
    except Exception as e:
        info["status"] = f"EXCEPTION: {type(e).__name__}: {e}"
        return None, info


# ---------------------------------------------------------------------------
# DimXpertManager probe
# ---------------------------------------------------------------------------

def _get_dimxpert_manager(doc: Any) -> dict[str, Any]:
    """Probe IModelDoc2.GetDimXpertManager across invocation forms."""
    probes: list[dict[str, Any]] = []

    forms = [
        ("GetDimXpertManager('')", lambda: doc.GetDimXpertManager("")),
        ("GetDimXpertManager('Default')",
         lambda: doc.GetDimXpertManager("Default")),
    ]

    mgr = None
    for label, fn in forms:
        cap = _capture(fn, label)
        probes.append({"form": label, **{k: v for k, v in cap.items() if k != "_val"}})
        if cap["status"] == "OK" and cap.get("_val") is not None:
            mgr = cap["_val"]
            break

    return {"manager": mgr, "probes": probes}


def _probe_manager_interface(mgr: Any) -> dict[str, Any]:
    """Enumerate the reachable members of IDimXpertManager."""
    result: dict[str, Any] = {"python_type": _tag(mgr)}

    expected_members = [
        "GetAnnotationCount",
        "GetAnnotations",
        "IGetAnnotations",
        "GetDatum",
        "GetGeometricTolerance",
        "GetFeature",
        "GetFeatureCount",
        "GetAnnotation",
        "AddDatum",
        "AddGeometricTolerance",
        "AddAnnotation",
        "CreateDatum",
        "CreateGeometricTolerance",
        "Count",
        "AnnotationCount",
    ]

    member_check: dict[str, dict[str, Any]] = {}
    for name in expected_members:
        cap = _capture(lambda n=name: getattr(mgr, n))
        entry = {k: v for k, v in cap.items() if k != "_val"}
        if cap["status"] == "OK":
            val = cap.get("_val")
            if callable(val):
                entry["is_callable"] = True
            elif val is not None:
                entry["value"] = repr(val)[:100]
        member_check[name] = entry

    result["member_check"] = member_check

    dynamic_members: list[str] = []
    try:
        if hasattr(mgr, "_oleobj_"):
            type_info = mgr._oleobj_.GetTypeInfo()
            type_attr = type_info.GetTypeAttr()
            for i in range(type_attr.cFuncs):
                try:
                    fd = type_info.GetFuncDesc(i)
                    names = type_info.GetNames(fd.memid)
                    if names:
                        dynamic_members.append(names[0])
                except Exception:
                    pass
            for i in range(type_attr.cVars):
                try:
                    vd = type_info.GetVarDesc(i)
                    names = type_info.GetNames(vd.memid)
                    if names:
                        dynamic_members.append(names[0])
                except Exception:
                    pass
    except Exception:
        pass
    result["dynamic_members"] = dynamic_members

    return result


def _probe_annotation_enumeration(mgr: Any) -> dict[str, Any]:
    """Try to enumerate annotations via IDimXpertManager."""
    result: dict[str, Any] = {}

    count_cap = _capture(lambda: mgr.GetAnnotationCount())
    result["GetAnnotationCount"] = {
        k: v for k, v in count_cap.items() if k != "_val"
    }

    annots_cap = _capture(lambda: mgr.GetAnnotations())
    result["GetAnnotations"] = {
        k: v for k, v in annots_cap.items() if k != "_val"
    }

    annotations: list[dict[str, Any]] = []
    annots = annots_cap.get("_val")
    if annots is not None:
        items = annots if isinstance(annots, (list, tuple)) else [annots]
        for i, annot in enumerate(items[:5]):
            entry: dict[str, Any] = {"index": i, "type": _tag(annot)}
            for attr in [
                "Type", "Name", "GetID", "GetFeature", "GetAnnotationType",
            ]:
                cap = _capture(lambda a=annot, at=attr: getattr(a, at))
                if cap["status"] == "OK":
                    val = cap.get("_val")
                    entry[attr] = (
                        repr(val)[:80] if not callable(val)
                        else f"<method {attr}>"
                    )
            annotations.append(entry)
    result["annotations"] = annotations
    return result


def _probe_dimxpert_on_dimension(doc: Any) -> dict[str, Any]:
    """Probe IDimension.Tolerance / IDisplayDimension on a model dimension.

    This tests path (a) from the background: tolerances as first-class fields
    on model dimensions, which model-item import carries to drawings for free.
    """
    result: dict[str, Any] = {}

    fm = doc.FeatureManager
    feat_cap = _capture(lambda: fm.GetFeatures(True))
    result["GetFeatures"] = {k: v for k, v in feat_cap.items() if k != "_val"}

    feats = feat_cap.get("_val")
    if feats is None or not isinstance(feats, (list, tuple)):
        result["status"] = "NO_FEATURES"
        return result

    dim_found = False
    for feat in feats:
        try:
            fname = feat.Name
        except Exception:
            continue

        disp_dim_cap = _capture(lambda f=feat: f.GetFirstDisplayDimension())
        if disp_dim_cap["status"] != "OK" or disp_dim_cap.get("_val") is None:
            continue

        dim_found = True
        disp_dim = disp_dim_cap["_val"]
        dd: dict[str, Any] = {
            "feature_name": fname,
            "type": _tag(disp_dim),
        }

        for attr in [
            "GetDimension", "Tolerance", "SetTolerance",
            "GetToleranceType", "SetToleranceType",
            "GetToleranceValue", "SetToleranceValue",
            "GetMaxValue", "GetMinValue",
        ]:
            cap = _capture(lambda d=disp_dim, a=attr: getattr(d, a))
            if cap["status"] == "OK":
                val = cap.get("_val")
                dd[attr] = (
                    repr(val)[:80] if not callable(val)
                    else f"<method {attr}>"
                )
            else:
                dd[attr] = cap["status"]

        dim_cap = _capture(lambda d=disp_dim: d.GetDimension(None))
        dd["GetDimension(None)"] = {
            k: v for k, v in dim_cap.items() if k != "_val"
        }
        if dim_cap.get("_val") is not None:
            dim = dim_cap["_val"]
            if isinstance(dim, (tuple, list)):
                dim = dim[0]
            idim: dict[str, Any] = {"type": _tag(dim)}
            for attr in [
                "Tolerance", "SetTolerance", "GetSystemValue",
                "GetUserValueIn", "SystemValue", "Value",
            ]:
                cap = _capture(lambda d=dim, a=attr: getattr(d, a))
                if cap["status"] == "OK":
                    val = cap.get("_val")
                    idim[attr] = (
                        repr(val)[:80] if not callable(val) else "<method>"
                    )
            dd["IDimension"] = idim

        result["first_display_dimension"] = dd
        break

    if not dim_found:
        result["status"] = "NO_DISPLAY_DIMENSIONS"
    return result


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

def run(skip_build: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid (late + optional early)"}

    # --- 1. DimXpert typelib discovery + load --------------------------------
    tlb_search = _find_dimxpert_tlb()
    result["typelib_search"] = tlb_search

    if tlb_search.get("status") == "FOUND":
        lib_info = _load_dimxpert_typelib(tlb_search["tlb_path"])
        result["typelib_info"] = lib_info
        if lib_info.get("status") == "LOADED":
            mod, mod_info = _ensure_dimxpert_module(lib_info)
            result["makepy_module"] = mod_info

    # --- 2. Connect to SW + build test part ----------------------------------
    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    doc = sw.ActiveDoc
    if doc is None:
        return {
            **result, "overall": "FAIL",
            "reason": "no active document",
        }
    if doc.GetType != SW_DOC_PART:
        return {
            **result, "overall": "FAIL",
            "reason": f"active doc not a Part (GetType={doc.GetType})",
        }

    if not skip_build:
        build = build_single_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {
                **result, "overall": "FAIL",
                "reason": "test part did not build",
            }

    # --- 3. GetDimXpertManager -----------------------------------------------
    mgr_result = _get_dimxpert_manager(doc)
    result["manager_acquisition"] = {
        k: v for k, v in mgr_result.items() if k != "manager"
    }
    mgr = mgr_result["manager"]
    if mgr is None:
        result["overall"] = "FAIL"
        result["reason"] = "GetDimXpertManager returned None in all forms"
        result["interpretation"] = (
            "DimXpertManager unreachable — API may need a saved doc, "
            "or DimXpert add-in may not be loaded. Run --mode vba to isolate."
        )
        return result

    # --- 4. Probe IDimXpertManager interface ---------------------------------
    iface_probe = _probe_manager_interface(mgr)
    result["manager_interface"] = iface_probe

    # --- 5. Enumerate annotations --------------------------------------------
    annot_probe = _probe_annotation_enumeration(mgr)
    result["annotation_enumeration"] = annot_probe

    # --- 6. Probe tolerance on a dimension (path a) --------------------------
    tol_probe = _probe_dimxpert_on_dimension(doc)
    result["dimension_tolerance"] = tol_probe

    # --- 7. Verdict ----------------------------------------------------------
    has_manager = mgr is not None
    annot_count_ok = (
        annot_probe.get("GetAnnotationCount", {}).get("status") == "OK"
    )
    has_dynamic_members = bool(iface_probe.get("dynamic_members"))
    has_dim_tol = tol_probe.get("first_display_dimension") is not None

    if has_manager and (annot_count_ok or has_dynamic_members):
        overall = "PASS"
        interp = (
            "DimXpertManager obtained + annotation surface reachable "
            "-> build the MBD handler"
        )
    elif has_manager:
        overall = "PARTIAL"
        interp = (
            "DimXpertManager obtained but enumeration/creation surface "
            "unclear -> narrow via --mode vba; check DimXpert add-in loaded"
        )
    else:
        overall = "FAIL"
        interp = "GetDimXpertManager unreachable -> defer or route B/C"

    if has_dim_tol:
        result["dimension_tolerance_note"] = (
            "IDimension.Tolerance surface reachable — path (a) tolerances "
            "on model dims may be independently viable"
        )

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba() -> str:
    return (
        "' Spike v0.16 S-MBD VBA oracle.\n"
        "' Paste into a Part document module, press F5.\n"
        "' Tests DimXpertManager access + annotation enumeration in early binding.\n"
        "Option Explicit\n"
        "Sub ProbeDimXpert()\n"
        "    Dim swApp     As SldWorks.SldWorks\n"
        "    Dim Part      As SldWorks.ModelDoc2\n"
        "    Dim mgr       As Object\n"
        "    Dim annotCount As Long\n"
        "    Dim annotations As Variant\n"
        "    Set swApp = Application.SldWorks\n"
        "    Set Part  = swApp.ActiveDoc\n"
        "\n"
        "    ' 1. Get the DimXpertManager\n"
        '    Set mgr = Part.GetDimXpertManager("")\n'
        "    If mgr Is Nothing Then\n"
        '        Set mgr = Part.GetDimXpertManager("Default")\n'
        "    End If\n"
        "    If mgr Is Nothing Then\n"
        '        MsgBox "GetDimXpertManager returned Nothing"\n'
        "        Exit Sub\n"
        "    End If\n"
        "\n"
        "    ' 2. Enumerate annotations\n"
        "    annotCount = mgr.GetAnnotationCount\n"
        "    If annotCount > 0 Then\n"
        "        annotations = mgr.GetAnnotations\n"
        '        MsgBox "DimXpertManager OK, " & annotCount & " annotations"\n'
        "    Else\n"
        '        MsgBox "DimXpertManager OK, 0 annotations (no MBD on this part)"\n'
        "    End If\n"
        "\n"
        "    ' 3. Probe tolerance on a display dimension (if the part has dims)\n"
        "    Dim feat  As SldWorks.Feature\n"
        "    Dim dDim  As SldWorks.DisplayDimension\n"
        "    Set feat = Part.FirstFeature\n"
        "    Do While Not feat Is Nothing\n"
        "        Set dDim = feat.GetFirstDisplayDimension\n"
        "        If Not dDim Is Nothing Then\n"
        '            MsgBox "DisplayDim found on " & feat.Name & _\n'
        '                   ", Tolerance type: " & dDim.GetToleranceType\n'
        "            Exit Do\n"
        "        End If\n"
        "        Set feat = feat.GetNextFeature\n"
        "    Loop\n"
        "End Sub\n"
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument(
        "--skip-build", action="store_true",
        help="Probe the active part without building a test box.",
    )
    p.add_argument(
        "--out", type=Path, default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_mbd.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run(args.skip_build)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
