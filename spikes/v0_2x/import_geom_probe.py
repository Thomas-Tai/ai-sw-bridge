"""W40 S1 probe: STEP/IGES import via ISldWorks.LoadFile4 + GetImportFileData.

Ground-truth signatures (CSDN telemetry + typelib reverse, confirmed before
authoring):

    ISldWorks.GetImportFileData(FileName: BSTR) -> IDispatch
        Extension-based dispatch (parses .step/.stp/.iges/.igs internally).

    ISldWorks.LoadFile4(FileName: BSTR, ArgString: BSTR, ImportData: IDispatch,
                        ByRef Errors: I4) -> ModelDoc2
        ArgString: "" (empty) when 3D Interconnect enabled, "r" for standard
        native B-rep import. We use "r" to force dumb-solid import.
        Errors is an [out] ByRef int — the late-binding trap.

Two call paths are characterized in parallel:
    A) typed early-bound call via ``typed(sw, "ISldWorks").LoadFile4(...)`` —
       expected to work because makepy handles ByRef I4 as a tuple-return.
    B) raw InvokeTypes — the W34 SaveAs escape hatch — as fallback if (A)
       drops the errors out-param or raises DISP_E_TYPEMISMATCH.

Verification (inverted verify-the-bytes, the load-bearing gate):
    - IPartDoc.GetBodies2(0, True) → ≥1 solid body
    - CreateMassProperty.Volume ≈ 24000 mm³ for the round-tripped 20×30×40 box
    - Face count > 0 (rejects the E4 bodyless-Reference-feature trap)

Fixture: we *export our own* 20×30×40 box via the proven W34 route
(``doc.SaveAs3(path, 0, 0)`` with extension-based dispatch) — same recipe
as ``export_3d_pae.py`` — then re-import the resulting .step file.

Outputs:
    - ``spikes/v0_2x/_results/import_geom_probe.json``
    - ``examples/import_box_20_30_40/spec.json`` (fixture spec for S2/S3)
    - ``examples/import_box_20_30_40/box.step``       (fixture bytes)
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import traceback
from pathlib import Path

src_path = Path(__file__).resolve().parents[2] / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

import pythoncom

from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.sw_com import get_sw_app


# ---------------------------------------------------------------------------
# typelib introspection — pin the literal dispids before any InvokeTypes call
# ---------------------------------------------------------------------------

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"


def _dump_isldworks_members(targets: tuple[str, ...]) -> dict[str, dict]:
    """Return {method_name: {memid, cParams, ret_vt, param_vts}} for targets."""
    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    out: dict[str, dict] = {}
    for i in range(tlb.GetTypeInfoCount()):
        name, _doc, _ctx, _f = tlb.GetDocumentation(i)
        if name != "ISldWorks":
            continue
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        for f in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f)
                names = info.GetNames(fd.memid)
                if not names:
                    continue
                mname = names[0]
                if mname not in targets:
                    continue
                ret_vt = fd.elemdescFunc.tdesc.vt if fd.elemdescFunc.tdesc else None
                param_vts = []
                for p in range(fd.cParams):
                    try:
                        param_vts.append(fd.GetElemDesc(p).tdesc.vt)
                    except Exception:
                        param_vts.append(None)
                out[mname] = {
                    "memid": fd.memid,
                    "cParams": fd.cParams,
                    "ret_vt": ret_vt,
                    "param_vts": param_vts,
                    "invkind": fd.invkind,
                    "flags": fd.wFuncFlags,
                }
            except Exception:
                continue
    return out


# ---------------------------------------------------------------------------
# fixture: build the 20×30×40 box + export to STEP (W34 proven path)
# ---------------------------------------------------------------------------

def _make_box_and_export_step(sw_app, temp_dir: Path) -> tuple[Path, Path]:
    """Build a centered 20×30×40 mm box, save .SLDPRT + .step. Returns both paths.

    SW API uses *meters*: 20 mm = 0.020 m, 30 mm = 0.030 m, 40 mm = 0.040 m.
    Volume = 24000 mm³ — this is the round-trip invariant we assert against.
    """
    template = sw_app.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
    doc = sw_app.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        raise RuntimeError("NewDocument returned None")

    # SK_Box: 20×30 mm rectangle centered on Front Plane
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    # CreateCenterRectangle takes HALF-extents in meters: 0.010 × 0.015
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, 0.010, 0.015, 0.0)
    sm.InsertSketch(True)

    # EX_Box: 40 mm blind extrude (0.040 m)
    feat = doc.FeatureManager.FeatureExtrusion2(
        True, False, False,
        0, 0,
        0.040, 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False,
        True, True, True,
        0, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("FeatureExtrusion2 failed")

    prt_path = temp_dir / "w40_box_20_30_40.SLDPRT"
    err = doc.SaveAs3(str(prt_path), 0, 0)
    if err:
        raise RuntimeError(f"SaveAs3(.SLDPRT) returned {err}")

    step_path = temp_dir / "w40_box_20_30_40.step"
    err = doc.SaveAs3(str(step_path), 0, 0)  # extension dispatches to STEP exporter
    if err:
        raise RuntimeError(f"SaveAs3(.step) returned {err}")

    if not step_path.exists() or step_path.stat().st_size == 0:
        raise RuntimeError("STEP export produced no bytes")

    # Close the doc so the import side starts clean
    sw_app.CloseDoc("w40_box_20_30_40.SLDPRT")
    return prt_path, step_path


# ---------------------------------------------------------------------------
# verification — the load-bearing gate
# ---------------------------------------------------------------------------

def _verify_imported(doc, expected_volume_mm3: float = 24000.0,
                     rel_tol: float = 0.01) -> dict:
    """Confirm real B-rep landed: ≥1 body, volume ≈ expected, faces > 0."""
    from ai_sw_bridge.com.earlybind import typed_qi

    out: dict = {
        "bodies_count": 0,
        "face_count": 0,
        "volume_mm3": None,
        "volume_match": False,
        "verdict": "FAIL",
        "errors": [],
    }

    # QI to IPartDoc (W37 lesson — the doc returned is IModelDoc2-shaped)
    try:
        pdoc = typed_qi(doc, "IPartDoc")
    except Exception as exc:
        out["errors"].append(f"IPartDoc QI failed: {exc!r}")
        return out

    try:
        bodies = pdoc.GetBodies2(0, True)  # swSolidBody=0, True=all
    except Exception as exc:
        out["errors"].append(f"GetBodies2 raised: {exc!r}")
        return out

    if bodies is None:
        out["errors"].append("GetBodies2 returned None — bodyless import (E4 trap)")
        return out
    if not isinstance(bodies, (list, tuple)):
        bodies = (bodies,)
    out["bodies_count"] = len(bodies)
    if len(bodies) == 0:
        out["errors"].append("zero solid bodies (E4 trap)")
        return out

    total_faces = 0
    for b in bodies:
        try:
            fc = b.GetFaceCount
            if callable(fc):
                fc = fc()
            total_faces += int(fc or 0)
        except Exception:
            pass
    out["face_count"] = total_faces
    if total_faces == 0:
        out["errors"].append("zero faces across all bodies (Reference-feature trap)")
        return out

    # Volume via Extension.CreateMassProperty (observe.py:586 pattern).
    # mp.Volume is in m³; convert to mm³ (×1e9).
    try:
        ext = pdoc.Extension
        mp = ext.CreateMassProperty
        if callable(mp):
            mp = mp()
        if mp is None:
            out["errors"].append("Extension.CreateMassProperty returned None")
            return out
        vol_m3 = mp.Volume
        if callable(vol_m3):
            vol_m3 = vol_m3()
        if vol_m3 is None:
            out["errors"].append("MassProperty.Volume is None")
            return out
        vol_mm3 = float(vol_m3) * 1.0e9
        out["volume_mm3"] = vol_mm3
        if abs(vol_mm3 - expected_volume_mm3) <= rel_tol * expected_volume_mm3:
            out["volume_match"] = True
            out["verdict"] = "PASS"
        else:
            out["errors"].append(
                f"volume {vol_mm3:.2f} mm³ outside ±{rel_tol*100:.0f}% "
                f"of expected {expected_volume_mm3} mm³"
            )
    except Exception as exc:
        out["errors"].append(f"CreateMassProperty raised: {exc!r}")

    return out


# ---------------------------------------------------------------------------
# import call paths — A) early-bound via typed(); B) raw InvokeTypes
# ---------------------------------------------------------------------------

def _import_path_A(sw_app, step_path: Path, import_data) -> tuple:
    """Early-bound path: typed(sw, 'ISldWorks').LoadFile4(...).

    makepy turns ByRef I4 into a trailing tuple element on return.
    Expected: (ModelDoc2_dispatch, errors_int).
    """
    mod = wrapper_module()
    tsw = typed(sw_app, "ISldWorks", module=mod)
    t0 = time.perf_counter()
    try:
        result = tsw.LoadFile4(str(step_path), "r", import_data, 0)
    except Exception as exc:
        return None, None, time.perf_counter() - t0, f"{type(exc).__name__}: {exc}"
    dt = time.perf_counter() - t0
    if isinstance(result, tuple) and len(result) >= 2:
        doc, errors = result[0], result[1]
    else:
        doc, errors = result, None
    return doc, errors, dt, None


def _import_path_B(sw_app, step_path: Path, import_data) -> tuple:
    """Raw InvokeTypes path (W34 SaveAs escape hatch).

    dispid is resolved once by _dump_isldworks_members; we pass it in.
    """
    from ai_sw_bridge.com.earlybind import typed as _typed_wrap

    mod = wrapper_module()
    tsw = _typed_wrap(sw_app, "ISldWorks", module=mod)
    dispid = _LOADFILE4_MEMID
    if dispid is None:
        return None, None, 0.0, "LoadFile4 dispid unknown"

    # VT_DISPATCH=9, VT_BSTR=8, VT_I4=3, VT_BYREF=0x4000
    VT_BSTR = 8
    VT_I4 = 3
    VT_DISPATCH = 9
    VT_BYREF = 0x4000
    ret_type = (VT_DISPATCH, 0)
    arg_types = (
        (VT_BSTR, 1),
        (VT_BSTR, 1),
        (VT_DISPATCH, 1),
        (VT_I4 | VT_BYREF, 2),
    )
    raw_import = getattr(import_data, "_oleobj_", import_data)

    t0 = time.perf_counter()
    try:
        result = sw_app._oleobj_.InvokeTypes(
            dispid, 0, pythoncom.DISPATCH_METHOD,
            ret_type, arg_types,
            str(step_path), "r", raw_import, 0,
        )
    except Exception as exc:
        return None, None, time.perf_counter() - t0, f"{type(exc).__name__}: {exc}"
    dt = time.perf_counter() - t0

    # InvokeTypes with a ByRef tail returns (retval, out1, ...) as tuple
    doc_disp = None
    errors = None
    if isinstance(result, tuple):
        if len(result) >= 2:
            doc_disp, errors = result[0], result[1]
        else:
            doc_disp = result[0]
    else:
        doc_disp = result

    # Wrap the raw IDispatch into a pywin32 dispatch if needed
    doc = None
    if doc_disp is not None:
        import win32com.client
        try:
            doc = win32com.client.Dispatch(doc_disp)
        except Exception:
            doc = doc_disp

    return doc, errors, dt, None


_LOADFILE4_MEMID = None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> dict:
    print("=== W40 S1 probe: STEP import via LoadFile4 + GetImportFileData ===")

    temp_dir = Path(tempfile.mkdtemp(prefix="W40_import_"))
    print(f"Temp dir: {temp_dir}")

    results: dict = {
        "wave": "W40",
        "stage": "S1_probe",
        "seat": None,
        "dispid_dump": {},
        "fixture": {},
        "import_A_earlybound": {},
        "import_B_invoketypes": {},
        "verdict": "FAIL",
        "errors": [],
    }

    try:
        sw_app = get_sw_app()
        rev = sw_app.RevisionNumber()
        results["seat"] = f"SW {rev}"
        print(f"Seat: SW {rev}")

        # ---- dispid dump for LoadFile4 + GetImportFileData ----
        print("Dumping ISldWorks member dispids...")
        members = _dump_isldworks_members(("LoadFile4", "GetImportFileData"))
        results["dispid_dump"] = members
        global _LOADFILE4_MEMID
        if "LoadFile4" in members:
            _LOADFILE4_MEMID = members["LoadFile4"]["memid"]
        print(f"  LoadFile4:         {members.get('LoadFile4')}")
        print(f"  GetImportFileData: {members.get('GetImportFileData')}")

        if not members:
            results["errors"].append("typelib dump returned no members")
            return results

        # ---- build fixture + export STEP (W34 route) ----
        print("Building 20×30×40 box and exporting to STEP...")
        prt_path, step_path = _make_box_and_export_step(sw_app, temp_dir)
        results["fixture"] = {
            "sldprt": str(prt_path),
            "step": str(step_path),
            "step_size_bytes": step_path.stat().st_size,
            "expected_volume_mm3": 24000.0,
        }
        print(f"  STEP: {step_path} ({step_path.stat().st_size} bytes)")

        # ---- GetImportFileData: extension dispatch ----
        print("Calling GetImportFileData(step_path)...")
        import_data = sw_app.GetImportFileData(str(step_path))
        if import_data is None:
            results["errors"].append("GetImportFileData returned None for .step")
            return results
        results["import_data_type"] = type(import_data).__name__
        print(f"  import_data type: {type(import_data).__name__}")

        # ---- path A: early-bound typed() ----
        print("Path A: typed(sw).LoadFile4(...)...")
        doc_a, err_a, dt_a, exc_a = _import_path_A(sw_app, step_path, import_data)
        results["import_A_earlybound"] = {
            "doc_acquired": doc_a is not None,
            "errors_out": err_a,
            "duration_s": round(dt_a, 4),
            "exception": exc_a,
        }
        if doc_a is not None:
            verify_a = _verify_imported(doc_a)
            results["import_A_earlybound"]["verify"] = verify_a
            try:
                sw_app.CloseDoc(doc_a.GetTitle())
            except Exception:
                pass

        # ---- path B: raw InvokeTypes ----
        # GetImportFileData is stateful per call — fetch a fresh one
        import_data_b = sw_app.GetImportFileData(str(step_path))
        print("Path B: InvokeTypes(dispid, ..., ByRef I4)...")
        doc_b, err_b, dt_b, exc_b = _import_path_B(sw_app, step_path, import_data_b)
        results["import_B_invoketypes"] = {
            "doc_acquired": doc_b is not None,
            "errors_out": err_b,
            "duration_s": round(dt_b, 4),
            "exception": exc_b,
        }
        if doc_b is not None:
            verify_b = _verify_imported(doc_b)
            results["import_B_invoketypes"]["verify"] = verify_b
            try:
                sw_app.CloseDoc(doc_b.GetTitle())
            except Exception:
                pass

        # ---- overall verdict: ship whichever path yields real bodies ----
        a_ok = (
            results["import_A_earlybound"].get("doc_acquired")
            and results["import_A_earlybound"].get("verify", {}).get("verdict") == "PASS"
        )
        b_ok = (
            results["import_B_invoketypes"].get("doc_acquired")
            and results["import_B_invoketypes"].get("verify", {}).get("verdict") == "PASS"
        )
        if a_ok or b_ok:
            results["verdict"] = "PASS"
            results["chosen_path"] = "A" if a_ok else "B"
        else:
            results["verdict"] = "FAIL"
            results["chosen_path"] = None

    except Exception as exc:
        results["errors"].append(f"probe crashed: {type(exc).__name__}: {exc}")
        results["traceback"] = traceback.format_exc()

    # ---- persist + print ----
    out_path = Path(__file__).parent / "_results" / "import_geom_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults: {out_path}")

    print("\n=== VERDICT ===")
    print(f"  A (early-bound): {results['import_A_earlybound']}")
    print(f"  B (InvokeTypes): {results['import_B_invoketypes']}")
    print(f"  chosen: {results.get('chosen_path')}")
    print(f"  overall: {results['verdict']}")

    return results


if __name__ == "__main__":
    main()
