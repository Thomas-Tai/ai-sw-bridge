"""MBD/DimXpert READ-EXTRACTION probe (Phase 2 recon, throwaway).

The W72 write-side probe (spike_mbd_probe.py) returned READABLE_WALL_ON_WRITE:
the DimXpert object graph resolves OOP (manager -> DimXpertPart -> counts) but
AUTHORING walls (AutoDimensionScheme + InsertSizeDimension both ghost, ret=False
/ 0-delta). Consequence: a PMI-bearing fixture cannot be built out-of-process,
so per-annotation value extraction (nominal / upper-lower tol / attached feature
/ datum label) was never reachable -- count stayed 0.

This probe answers the EXTRACTION witness at two levels:

  PART A (no fixture needed): statically dump the swdimxpert.tlb read-interface
  CONTRACT -- for each IDimXpert* interface, every method/property name + member
  id + return VARTYPE + arg VARTYPEs. This tells us EXACTLY which getters exist
  (nominal value, tolerance, datum label, attached feature) and what each
  marshals as, WITHOUT needing a part that has PMI on it.

  PART B (live seat): reconfirm the read graph on the current seat, and -- if a
  PMI-bearing part is supplied via $MBD_FIXTURE -- walk GetFeatures/GetAnnotations
  and attempt to extract each field OOP, recording per-field marshal success vs
  VARIANT/TypeError fault. With no fixture it confirms the empty-schema read path.

Run on the live seat. Telemetry -> _results/mbd_read_extract.json (untracked).
Supply a GUI-authored PMI part:  MBD_FIXTURE=C:\\path\\to\\block_with_pmi.SLDPRT
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_SRC))

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swdimxpert.tlb"
RESULTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "spikes"
    / "v0_2x"
    / "_results"
    / "mbd_read_extract.json"
)

# Interfaces whose read surface we care about for PMI serialization.
READ_IFACES = {
    "IDimXpertPart",
    "IDimXpertFeature",
    "IDimXpertAnnotation",
    "IDimXpertDatumFeature",
    "IDimXpertGeometricTolerance",
    "IDimXpertSizeDimension",
    "IDimXpertLocationDimension",
    "IDimXpertChamferDimension",
    "IDimXpertDatumTargetGroup",
}

# VARTYPE name table (pythoncom VT_* values) for human-readable signature dumps.
VT_NAMES = {
    0: "EMPTY",
    1: "NULL",
    2: "I2",
    3: "I4",
    4: "R4",
    5: "R8",
    6: "CY",
    7: "DATE",
    8: "BSTR",
    9: "DISPATCH",
    10: "ERROR",
    11: "BOOL",
    12: "VARIANT",
    13: "UNKNOWN",
    16: "I1",
    17: "UI1",
    18: "UI2",
    19: "UI4",
    20: "I8",
    21: "UI8",
    22: "INT",
    23: "UINT",
    24: "VOID",
    25: "HRESULT",
    26: "PTR",
    27: "SAFEARRAY",
    28: "CARRAY",
}


def _vt(vt: int) -> str:
    base = vt & 0x0FFF
    name = VT_NAMES.get(base, f"VT{base}")
    if vt & 0x2000:  # VT_ARRAY
        name = f"ARRAY<{name}>"
    if vt & 0x4000:  # VT_BYREF
        name = f"{name}*"
    return name


results: dict[str, Any] = {
    "probe": "mbd_read_extract",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "tlb_contract": {},
    "live": {},
}


def dump_tlb_contract() -> None:
    """PART A: enumerate swdimxpert.tlb read interfaces and their member surface."""
    import pythoncom

    if not os.path.isfile(TLB_PATH):
        results["tlb_contract"]["error"] = f"TLB not found: {TLB_PATH}"
        return
    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    n = tlb.GetTypeInfoCount()
    for i in range(n):
        try:
            name, _doc, _, _ = tlb.GetDocumentation(i)
        except Exception:
            continue
        if not name.startswith("IDimXpert"):
            continue
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        members: list[dict[str, Any]] = []
        for f_idx in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f_idx)
                names = info.GetNames(fd.memid)
                ret_vt = fd.rettype[0] if fd.rettype else 24
                arg_vts = [a[0] for a in fd.args] if fd.args else []
                # invkind: 1=METHOD 2=PROPERTYGET 4=PROPERTYPUT
                members.append(
                    {
                        "name": names[0] if names else f"memid_{fd.memid}",
                        "invkind": fd.invkind,
                        "ret": _vt(ret_vt),
                        "args": [_vt(v) for v in arg_vts],
                        "argnames": list(names[1:]) if len(names) > 1 else [],
                    }
                )
            except Exception:
                continue
        results["tlb_contract"][name] = members
        print(f"[TLB] {name}: {len(members)} members")
        for m in members:
            kind = {1: "M", 2: "get", 4: "put"}.get(m["invkind"], "?")
            sig_args = ", ".join(
                f"{an}:{av}" for an, av in zip(m["argnames"], m["args"])
            ) or ", ".join(m["args"])
            print(f"    [{kind}] {m['name']}({sig_args}) -> {m['ret']}")


def _m(disp: Any, name: str, ret_vt: int = 24, arg_vts: tuple = (), *args: Any) -> Any:
    """Forced-DISPATCH_METHOD invoke by dispid (swdimxpert objects are late-bound)."""
    import pythoncom

    ole = disp._oleobj_ if hasattr(disp, "_oleobj_") else disp
    return ole.InvokeTypes(
        ole.GetIDsOfNames(name),
        0,
        pythoncom.DISPATCH_METHOD,
        (ret_vt, 0),
        arg_vts,
        *args,
    )


def _try(label: str, fn) -> Any:
    try:
        v = fn()
        results["live"][label] = {"ok": True, "value": repr(v)[:200]}
        print(f"  [ok ] {label} = {v!r}"[:160])
        return v
    except Exception as exc:
        results["live"][label] = {"ok": False, "err": f"{type(exc).__name__}: {exc}"}
        print(f"  [ERR] {label}: {type(exc).__name__}: {exc}"[:160])
        return None


def probe_live() -> None:
    """PART B: reconfirm read graph; extract per-annotation fields if PMI present."""
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    fixture = os.environ.get("MBD_FIXTURE", "").strip()
    results["live"]["fixture"] = fixture or "(none — empty-schema read path only)"

    if not fixture:
        # Build a throwaway cube just to confirm the empty-schema read graph.
        import tempfile

        from ai_sw_bridge.spec.builder import build as part_build

        tmp = tempfile.mkdtemp(prefix="mbd_read_")
        fixture = os.path.join(tmp, "ReadCube.SLDPRT")
        part_build(
            {
                "schema_version": 1,
                "name": "ReadCube",
                "features": [
                    {
                        "type": "sketch_rectangle_on_plane",
                        "name": "SK",
                        "plane": "Front",
                        "width": 10.0,
                        "height": 10.0,
                    },
                    {
                        "type": "boss_extrude_blind",
                        "name": "EX",
                        "sketch": "SK",
                        "depth": 10.0,
                    },
                ],
            },
            save_as=fixture,
            save_format="current",
            no_dim=True,
        )

    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(fixture, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        results["live"]["open"] = "FAILED"
        return
    ext = typed(doc, "IModelDoc2", module=mod).Extension
    # A real PMI fixture already carries an authored schema: read it with
    # CreateSchema=False so we don't spin up a fresh EMPTY schema and read 0.
    # A no-PMI part needs CreateSchema=True or DimXpertPart returns None.
    create_schema = not bool(os.environ.get("MBD_FIXTURE", "").strip())
    results["live"]["create_schema"] = create_schema
    mgr = _try(
        "DimXpertManager",
        lambda: ext.DimXpertManager("", create_schema),
    ) or _try("DimXpertManager_bool", lambda: ext.DimXpertManager(create_schema))
    if mgr is None:
        return
    _try("SchemaName", lambda: mgr.SchemaName)
    part = _try("DimXpertPart", lambda: mgr.DimXpertPart)
    if part is None:
        return
    fcount = _try("GetFeatureCount", lambda: int(_m(part, "GetFeatureCount", 3)))
    acount = _try("GetAnnotationCount", lambda: int(_m(part, "GetAnnotationCount", 3)))

    # GetFeatures / GetAnnotations array marshaling (the OOP SAFEARRAY question).
    _try("GetFeatures[array]", lambda: _m(part, "GetFeatures", 12))
    _try("GetAnnotations[array]", lambda: _m(part, "GetAnnotations", 12))

    # ---- helpers for the per-annotation walk ----
    def _g(disp: Any, name: str, ret_vt: int = 8) -> Any:
        """Late-bound PROPERTY-GET by dispid (e.g. Name/Identifier)."""
        import pythoncom

        ole = disp._oleobj_ if hasattr(disp, "_oleobj_") else disp
        return ole.InvokeTypes(
            ole.GetIDsOfNames(name),
            0,
            pythoncom.DISPATCH_PROPERTYGET,
            (ret_vt, 0),
            (),
        )

    def _safe(fn) -> Any:
        try:
            return fn()
        except Exception as exc:
            return f"ERR {type(exc).__name__}: {exc}"

    def _model_feature_name(anno_or_feat: Any) -> Any:
        """GetModelFeature() -> IFeature; return its .Name."""
        try:
            mf = _m(anno_or_feat, "GetModelFeature", 9)  # VT_DISPATCH
            if mf is None:
                return None
            tf = typed_qi(mf, "IFeature", module=mod)
            nm = tf.Name
            return nm() if callable(nm) else nm
        except Exception as exc:
            return f"ERR {type(exc).__name__}: {exc}"

    def _asym_bridge(anno: Any) -> dict[str, Any]:
        """anno.GetDisplayEntity() -> IDisplayDimension -> IDimension.Tolerance
        -> ITolerance.{Get(Min|Max)Value, Type}. The asymmetric +/- deviations
        the DimXpert-native surface does NOT expose."""
        out: dict[str, Any] = {}
        try:
            de = _m(anno, "GetDisplayEntity", 9)  # VT_DISPATCH
            if de is None:
                return {"bridge": "GetDisplayEntity=None"}
            dd = typed_qi(de, "IDisplayDimension", module=mod)
            getdim = (
                dd.GetDimension2 if hasattr(dd, "GetDimension2") else dd.GetDimension
            )
            dim = getdim(0) if callable(getdim) else getdim
            tdim = typed_qi(dim, "IDimension", module=mod)
            tol = tdim.Tolerance
            tol = tol() if callable(tol) else tol
            ttol = typed_qi(tol, "ITolerance", module=mod)
            out["tol_type"] = _safe(
                lambda: ttol.Type if not callable(ttol.Type) else ttol.Type()
            )
            out["min_value"] = _safe(lambda: ttol.GetMinValue())
            out["max_value"] = _safe(lambda: ttol.GetMaxValue())
        except Exception as exc:
            out["bridge_err"] = f"{type(exc).__name__}: {exc}"
        return out

    extractions: list[dict[str, Any]] = []
    annos = _try("GetAnnotations", lambda: _m(part, "GetAnnotations", 12))
    seq = annos if isinstance(annos, (list, tuple)) else []
    for idx, anno in enumerate(seq):
        rec: dict[str, Any] = {"index": idx}
        rec["name"] = _safe(lambda: _g(anno, "Name", 8))
        rec["attached_feature"] = _model_feature_name(anno)
        # Discriminate by which getter the late-bound object answers:
        # IDimXpertDatum.Identifier / IDimXpertDimensionTolerance.GetNominalValue
        # / IDimXpertTolerance.Tolerance + datum-ref arrays.
        ident = _safe(lambda: _g(anno, "Identifier", 8))
        if not str(ident).startswith("ERR"):
            rec["kind"] = "datum"
            rec["identifier"] = ident
        nominal = _safe(lambda: _m(anno, "GetNominalValue", 5))  # VT_R8
        if not str(nominal).startswith("ERR"):
            rec["kind"] = "dimension"
            rec["nominal"] = nominal
            rec["fit_code"] = _safe(lambda: _g(anno, "LimitsAndFitsCode", 8))
            rec["asym"] = _asym_bridge(anno)  # upper/lower deviation witness
        tol = _safe(lambda: _g(anno, "Tolerance", 5))  # VT_R8
        if not str(tol).startswith("ERR"):
            rec.setdefault("kind", "geometric_tolerance")
            rec["tolerance_value"] = tol
            rec["primary_datums"] = _safe(lambda: _m(anno, "GetPrimaryDatums", 12))
            rec["secondary_datums"] = _safe(lambda: _m(anno, "GetSecondaryDatums", 12))
            rec["tertiary_datums"] = _safe(lambda: _m(anno, "GetTertiaryDatums", 12))
        rec.setdefault("kind", "unknown")
        extractions.append(rec)
        print(f"  [anno {idx}] {json.dumps(rec, default=str)[:240]}")

    features: list[dict[str, Any]] = []
    feats = _try("GetFeatures", lambda: _m(part, "GetFeatures", 12))
    fseq = feats if isinstance(feats, (list, tuple)) else []
    for idx, feat in enumerate(fseq):
        frec = {
            "index": idx,
            "name": _safe(lambda: _g(feat, "Name", 8)),
            "model_feature": _model_feature_name(feat),
            "face_count": _safe(lambda: int(_m(feat, "GetFaceCount", 3))),
        }
        features.append(frec)
        print(f"  [feat {idx}] {json.dumps(frec, default=str)[:200]}")

    results["live"]["extractions"] = extractions
    results["live"]["features"] = features
    results["live"]["summary"] = {
        "feature_count": fcount,
        "annotation_count": acount,
        "has_pmi": bool(isinstance(acount, int) and acount > 0),
    }


def main() -> int:
    import pythoncom

    pythoncom.CoInitialize()
    try:
        print("=== PART A: swdimxpert.tlb read-interface contract ===")
        dump_tlb_contract()
        print("\n=== PART B: live-seat read graph ===")
        probe_live()
    except Exception as exc:
        import traceback

        results["fatal"] = f"{type(exc).__name__}: {exc}"
        results["traceback"] = traceback.format_exc()
        print(traceback.format_exc())
    finally:
        try:
            w32 = __import__("win32com.client", fromlist=["client"])
            w32.Dispatch("SldWorks.Application").CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nWrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
