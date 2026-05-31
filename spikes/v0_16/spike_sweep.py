"""
Spike v0.16 / S-SWEEP — sweep and loft feature creation via COM.
[authored seat-free; RUN ON A LIVE SEAT]

Probes the SOLIDWORKS sweep/loft API out-of-process using the proven
CreateDefinition -> typed feature-data -> CreateFeature pipeline:

  - CreateDefinition(swFmSweep) -> ISweepFeatureData
  - CreateDefinition(swFmLoft)  -> ILoftFeatureData
  - typed_qi wrap the feature-data interface
  - Set profile + path selections, CreateFeature

The swFmSweep / swFmLoft constants are unknown — scan 0..127 to discover
(same technique as spike_wizhole.py found swFmHoleWzd).

Background
----------
Sweep and Loft are roadmap features (P2.x). Both require:
  1. A profile sketch (closed contour)
  2. A path sketch (open or closed curve)
  3. FeatureManager.CreateDefinition(swFm*) to get the data object
  4. typed_qi wrap to ISweepFeatureData / ILoftFeatureData
  5. Set profile/path entity references on the data object
  6. CreateFeature to materialize

Risks: profile/path selection marshaling, feature-data interface
discovery (the makepy module may not expose ISweepFeatureData).

Verdict
-------
PASS    : sweep materializes on a profile+path — build the handler.
PARTIAL : data object reachable but CreateFeature does not materialize —
          narrow selection or interface name; run --mode vba.
FAIL    : CreateDefinition(swFm*) returns None for all scanned values —
          sweep/loft unreachable via CreateDefinition pipeline.

Prereq: SOLIDWORKS running. Creates own part with profile+path sketches
(non-destructive; never touches the user's open documents).

Usage
-----
    python spikes/v0_16/spike_sweep.py --out report.json
    python spikes/v0_16/spike_sweep.py --mode vba
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_DOC_PART = 1

# Known feature-definition constants (from SW API + prior spikes)
SW_FM_EXTRUDE = 0
SW_FM_FILLET = 1
SW_FM_REVOLVE = 5
# Sweep/Loft constants: unknown, scan to discover
_SWEEP_SCAN_RANGE = range(0, 64)


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:  # noqa: BLE001
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass


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
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


def _build_sweep_geometry(doc: Any) -> dict[str, Any]:
    """Create a circle profile on Front Plane and a line path on Right Plane.

    Returns dict with profile_sketch and path_sketch names if successful.
    """
    result: dict[str, Any] = {}

    # Profile: circle on Front Plane
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCircleByRadius(0.0, 0.0, 0.0, 0.005)  # 5mm radius
        doc.SketchManager.InsertSketch(True)
        result["profile_sketch"] = "Sketch1"
    except Exception as e:  # noqa: BLE001
        result["profile_error"] = f"{type(e).__name__}: {e}"
        return result

    # Path: vertical line on Right Plane
    try:
        doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateLine(0.0, 0.0, 0.0, 0.0, 0.05, 0.0)  # 50mm line
        doc.SketchManager.InsertSketch(True)
        result["path_sketch"] = "Sketch2"
    except Exception as e:  # noqa: BLE001
        result["path_error"] = f"{type(e).__name__}: {e}"

    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass

    return result


def _scan_create_definition(fm: Any, scan_range: range) -> dict[int, str]:
    """Scan CreateDefinition(i) to find sweep/loft feature-data objects."""
    results: dict[int, str] = {}
    for i in scan_range:
        try:
            data = fm.CreateDefinition(i)
            if data is not None and not isinstance(data, int):
                type_name = _tag(data)
                iface = None
                for attr in ("GetTypeName", "GetTypeName2"):
                    try:
                        m = getattr(data, attr)
                        iface = str(m() if callable(m) else m)
                        break
                    except Exception:  # noqa: BLE001
                        continue
                results[i] = f"{type_name}({iface})" if iface else type_name
            else:
                results[i] = f"None/int({data})"
        except Exception as e:  # noqa: BLE001
            results[i] = f"EXCEPTION: {type(e).__name__}"
    return results


def _try_qi_interfaces(data: Any, mod: Any) -> dict[str, Any]:
    """Try typed_qi against candidate sweep/loft interfaces."""
    candidates = [
        "ISweepFeatureData",
        "ILoftFeatureData",
        "IChamferFeatureData",
        "ISimpleFilletFeatureData2",
    ]
    results: dict[str, str] = {}
    for iface in candidates:
        try:
            wrapped = typed_qi(data, iface, module=mod)
            results[iface] = f"OK({_tag(wrapped)})"
        except Exception as e:  # noqa: BLE001
            hresult = f"{e.args[0]:#010x}" if hasattr(e, "args") and e.args else "?"
            results[iface] = f"FAIL({type(e).__name__}: {hresult})"
    return results


def run(keep_file: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind pattern)"}

    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module (LoadTypeLib fallback)"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    part_path = tmp_dir / "spike_sweep.sldprt"
    if part_path.exists():
        try:
            part_path.unlink()
        except OSError:
            pass

    # --- 1. Build part with sweep geometry ----------------------------------
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    geom = _build_sweep_geometry(doc)
    result["geometry"] = geom

    if "profile_error" in geom:
        _try_close(sw, doc)
        return {**result, "overall": "FAIL", "reason": f"profile sketch failed: {geom['profile_error']}"}

    # --- 2. Scan CreateDefinition for sweep/loft constants --------------------
    fm = doc.FeatureManager
    scan = _scan_create_definition(fm, _SWEEP_SCAN_RANGE)
    result["create_definition_scan"] = scan

    # Find candidate sweep/loft entries (non-None, non-exception)
    candidates = {
        k: v
        for k, v in scan.items()
        if "None" not in v and "EXCEPTION" not in v
    }
    result["non_null_definitions"] = candidates

    # --- 3. Try typed_qi on each candidate -----------------------------------
    qi_results: dict[int, dict[str, str]] = {}
    sweep_candidates = []
    for idx in candidates:
        try:
            data = fm.CreateDefinition(idx)
            qi = _try_qi_interfaces(data, mod)
            qi_results[idx] = qi
            if any("OK" in v for v in qi.values()):
                sweep_candidates.append(idx)
        except Exception:  # noqa: BLE001
            pass
    result["qi_results"] = qi_results
    result["sweep_candidates"] = sweep_candidates

    # --- 4. Attempt sweep creation on best candidate --------------------------
    sweep_result: dict[str, Any] = {}
    if sweep_candidates:
        idx = sweep_candidates[0]
        try:
            data = fm.CreateDefinition(idx)
            # Try ISweepFeatureData first
            try:
                fd = typed_qi(data, "ISweepFeatureData", module=mod)
                sweep_result["interface"] = "ISweepFeatureData"
            except Exception:  # noqa: BLE001
                fd = data
                sweep_result["interface"] = "raw"

            # Select profile and path — typed Extension for marked selects
            # (D4: IModelDocExtension.SelectByID2 marshals mark + Callout
            # correctly; IModelDoc2 late-bound SelectByID has no mark param).
            profile_name = geom.get("profile_sketch", "Sketch1")
            path_name = geom.get("path_sketch", "Sketch2")
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)

            sel_profile = _capture(
                lambda: ext.SelectByID2(doc, profile_name, "SKETCH", 0, 0, 0, False, 1, None, 0),
                "select_profile",
            )
            sel_path = _capture(
                lambda: ext.SelectByID2(doc, path_name, "SKETCH", 0, 0, 0, True, 4, None, 0),
                "select_path",
            )
            sweep_result["select_profile"] = sel_profile
            sweep_result["select_path"] = sel_path

            feat = fm.CreateFeature(fd)
            sweep_result["create_feature_type"] = _tag(feat)
            sweep_result["materialized"] = _materialized(feat)
            if _materialized(feat):
                sweep_result["type_name"] = _type_name(feat)
        except Exception as e:  # noqa: BLE001
            sweep_result["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    else:
        sweep_result["error"] = "no sweep/loft candidate found in CreateDefinition scan"
    result["sweep_attempt"] = sweep_result

    # --- Cleanup -------------------------------------------------------------
    _try_close(sw, doc)
    if not keep_file:
        try:
            part_path.unlink()
        except OSError:
            pass
        result["cleanup"] = "closed doc + removed temp file"
    else:
        result["cleanup"] = f"kept file at {part_path}"

    # --- Verdict -------------------------------------------------------------
    mat = sweep_result.get("materialized", False)
    if mat:
        overall = "PASS"
        interp = "sweep materializes out-of-process -> build the handler"
    elif sweep_candidates:
        overall = "PARTIAL"
        interp = (
            "feature-data interface reachable but CreateFeature did not materialize "
            "-> run --mode vba to isolate the marshaler"
        )
    elif candidates:
        overall = "PARTIAL"
        interp = (
            "CreateDefinition returns objects but no typed QI match "
            "-> scan wider range or check makepy module coverage"
        )
    else:
        overall = "FAIL"
        interp = "no sweep/loft CreateDefinition found in scan range -> defer"

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba() -> str:
    return r"""' Spike v0.16 S-SWEEP VBA oracle.
' Paste into a Part with a circle profile (Sketch1) and line path (Sketch2).
Option Explicit
Sub ProbeSweep()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As Object
    Dim Feat  As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager
    ' Try CreateDefinition for sweep (constant TBD from Python scan)
    Set fd = fm.CreateDefinition(7)  ' <-- replace 7 with scan result
    If fd Is Nothing Then
        MsgBox "CreateDefinition returned Nothing"
        Exit Sub
    End If
    ' Select profile + path
    Part.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 1, Nothing, 0
    Part.SelectByID2 "Sketch2", "SKETCH", 0, 0, 0, True, 4, Nothing, 0
    Set Feat = fm.CreateFeature(fd)
    If Feat Is Nothing Then
        MsgBox "CreateFeature returned Nothing"
    Else
        MsgBox "Sweep created: " & Feat.Name
    End If
End Sub
"""


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--keep-file", action="store_true")
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_sweep.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
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
