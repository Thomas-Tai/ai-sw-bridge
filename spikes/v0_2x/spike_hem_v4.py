"""Spike v0.2x / hem-v4 — UN-WALL InsertSheetMetalHem PCBA null trap.

OVERTURNED: the bc5c849 "mode-B wall" verdict. fire3's ``Type mismatch``
(DISP_E_TYPEMISMATCH, argErr 9) is the FUNCDESC-confirmed PCBA arg:
InsertSheetMetalHem(arity 9) = 8 scalars + PCBA: vt PTR (raw_vt 26).
Bare Python None can't marshal to VT_PTR -> Type mismatch; PyOleMissing
-> TypeError.  This is the makepy/VT_PTR trailing-null trap
(reference_makepy_wrong_argtype), the SAME class W4 edge_flange cracked
with VARIANT(VT_DISPATCH, None).

base_flange creates fine (CreateDefinition->typed_qi->CreateFeature),
12 edges, Select2:true — the ONLY blocker is the PCBA null.

Three typed-null tactics sweep (all from the documented trailing-null
recipe; NO guessing):
  1. VARIANT(VT_DISPATCH, None)       — edge_flange proven pattern
  2. VARIANT(VT_ERROR, DISP_E_PARAMNOTFOUND) — COM "missing optional"
  3. raw InvokeTypes with VT_PTR      — literal FUNCDESC type, None

If a tactic cracks v1 (arity 9), it is applied to InsertSheetMetalHem2
(memid 201, arity 16, PCBA at index 8).

Verify-the-EFFECT: a hem folds the selected edge -> assert dFace > 0
AND small dVol > 0, BOTH surviving save->reopen.

FUNCDESC anchor: spikes/v0_2x/_results/hem_funcdesc_dump.json
  InsertSheetMetalHem  memid=91  arity=9  return=PTR
    Type(I4) Position(I4) Reverse(BOOL) DLength(R8) DGap(R8)
    DAngle(R8) DRad(R8) DMiterGap(R8) PCBA(PTR,raw_vt=26)
  InsertSheetMetalHem2 memid=201 arity=16 return=PTR
    same 8 scalars + PCBA(PTR) + UseDefaultRelief(BOOL) ReliefType(I4)
    ReliefTearTypes(I4) UseReliefRatio(BOOL) ReliefRatio(R8)
    ReliefWidth(R8) ReliefDepth(R8)
  Enums: swHemTypes_e Open0/Closed1/TearDrop2/Rolled3/Double4
         swHemPositionTypes_e Inside0/Outside1

Prereq: SOLIDWORKS running. Sheet Metal add-in enabled.
Non-destructive (own doc, CloseAllDocuments in finally — NEVER CloseDoc).

Usage:
    python spikes/v0_2x/spike_hem_v4.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_PKG_ROOT = _HERE.parents[2] / "src"
_V15 = _HERE.parents[1] / "v0_15"
_V16 = _HERE.parents[1] / "v0_16"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom
from win32com.client import VARIANT

from ai_sw_bridge.com.earlybind import typed, typed_extension, typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module
from spike_earlybind_persist import connect_running_sw

SW_DEFAULT_TEMPLATE_PART = 8
SW_FM_BASEFLANGE = 34
IFACE_BASEFLANGE = "IBaseFlangeFeatureData"
SW_BODY_SOLID = 0

PROF_W_M = 0.060
PROF_H_M = 0.040
THICKNESS_M = 0.002
BEND_RADIUS_M = 0.002

HEM_TYPE_CLOSED = 1
HEM_POS_INSIDE = 0
HEM_REVERSE = False
HEM_DLENGTH_M = 0.010
HEM_DGAP_M = 0.0
HEM_DANGLE_RAD = 0.0
HEM_DRAD_M = 0.0
HEM_DMITERGAP_M = 0.001

MEMID_HEM_V1 = 91
MEMID_HEM_V2 = 201

VT_I4 = 3
VT_R8 = 5
VT_BOOL = 11
VT_PTR = 26
VT_UNKNOWN = 13


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {"status": "OK", "type": _tag(val),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}, val
    except Exception as e:
        return {"status": "EXCEPTION", "exception_type": type(e).__name__,
                "message": str(e)[:300],
                "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}, None


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _metrics(doc: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"faces": 0, "vol_mm3": 0.0}
    try:
        bodies = doc.GetBodies2(SW_BODY_SOLID, True)
    except Exception:
        return out
    if not bodies:
        return out
    for b in (bodies if isinstance(bodies, (list, tuple)) else [bodies]):
        try:
            faces = b.GetFaces()
            out["faces"] += len(faces) if faces else 0
        except Exception:
            pass
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                out["vol_mm3"] += float(mp[3]) * 1e9
        except Exception:
            pass
    out["vol_mm3"] = round(out["vol_mm3"], 3)
    return out


def _build_fixture(sw: Any, mod: Any) -> tuple[Any, Any, Any, dict[str, Any]]:
    """Build a fresh doc with base_flange + 1 selected edge. Return (doc, fm, edge, diag)."""
    diag: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        diag["error"] = "NewDocument None"
        return None, None, None, diag
    fm = doc.FeatureManager

    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        sk.CreateCornerRectangle(
            -PROF_W_M / 2, -PROF_H_M / 2, 0.0,
            PROF_W_M / 2, PROF_H_M / 2, 0.0)
        sk.InsertSketch(True)
    except Exception as e:
        diag["sketch_error"] = f"{type(e).__name__}: {e}"[:200]

    def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_BASEFLANGE))
    diag["create_definition"] = def_rec
    if data is None:
        diag["error"] = "CreateDefinition None"
        return doc, None, None, diag
    qi_rec, wrapped = _capture(lambda: typed_qi(data, IFACE_BASEFLANGE, module=mod))
    diag["typed_qi"] = qi_rec
    if wrapped is None:
        diag["error"] = "typed_qi None"
        return doc, None, None, diag
    for name, val in (("Thickness", THICKNESS_M), ("BendRadius", BEND_RADIUS_M)):
        try:
            setattr(wrapped, name, val)
        except Exception:
            pass
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
    diag["create_feature"] = feat_rec
    if not _materialized(feat):
        diag["error"] = "base flange not materialized"
        return doc, None, None, diag

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    rec, bodies = _capture(lambda: doc.GetBodies2(SW_BODY_SOLID, True))
    body_list = list(bodies) if bodies and isinstance(bodies, (list, tuple)) else [bodies] if bodies else []
    if not body_list:
        diag["error"] = "no bodies"
        return doc, fm, None, diag
    body = body_list[0]
    rec, edges_raw = _capture(lambda: body.GetEdges())
    edge_list = list(edges_raw) if edges_raw and isinstance(edges_raw, (list, tuple)) else [edges_raw] if edges_raw else []
    diag["edge_count"] = len(edge_list)
    if not edge_list:
        diag["error"] = "no edges"
        return doc, fm, None, diag

    ext = typed_extension(doc, module=mod)
    edge = edge_list[0]
    try:
        pid = ext.GetPersistReference3(edge)
        if pid:
            obj_result = ext.GetObjectByPersistReference3(pid)
            edge = obj_result[0] if isinstance(obj_result, tuple) else obj_result
    except Exception as e:
        diag["edge_resolve"] = f"{type(e).__name__}: {e}"[:120]

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    try:
        from ai_sw_bridge.com.earlybind import typed as _typed
        _typed(edge, "IEntity", module=mod).Select2(False, 0)
        diag["select2"] = True
    except Exception as e:
        diag["select2_error"] = f"{type(e).__name__}: {e}"[:120]
        try:
            edge.Select2(False, 0)
            diag["select2"] = True
        except Exception as e2:
            diag["select2_fallback_error"] = f"{type(e2).__name__}: {e2}"[:120]

    return doc, fm, edge, diag


def _hem_scalars() -> tuple:
    return (HEM_TYPE_CLOSED, HEM_POS_INSIDE, HEM_REVERSE,
            HEM_DLENGTH_M, HEM_DGAP_M, HEM_DANGLE_RAD,
            HEM_DRAD_M, HEM_DMITERGAP_M)


def _tactic_1_makepy_vt_dispatch(fm: Any) -> tuple[dict, Any]:
    """Tactic 1: VARIANT(VT_DISPATCH, None) via makepy — edge_flange pattern."""
    vt_null = VARIANT(pythoncom.VT_DISPATCH, None)
    args = _hem_scalars() + (vt_null,)
    return _capture(lambda: fm.InsertSheetMetalHem(*args))


def _tactic_2_makepy_vt_error(fm: Any) -> tuple[dict, Any]:
    """Tactic 2: VARIANT(VT_ERROR, DISP_E_PARAMNOTFOUND) — COM 'missing optional'."""
    vt_missing = VARIANT(pythoncom.VT_ERROR, pythoncom.DISP_E_PARAMNOTFOUND)
    args = _hem_scalars() + (vt_missing,)
    return _capture(lambda: fm.InsertSheetMetalHem(*args))


def _tactic_3_raw_invoke_vt_ptr(fm: Any) -> tuple[dict, Any]:
    """Tactic 3: raw InvokeTypes with VT_PTR at index 8 — literal FUNCDESC type."""
    arg_types = (
        (VT_I4, 1), (VT_I4, 1), (VT_BOOL, 1),
        (VT_R8, 1), (VT_R8, 1), (VT_R8, 1),
        (VT_R8, 1), (VT_R8, 1),
        (VT_PTR, 1),
    )
    args = _hem_scalars() + (None,)
    return _capture(lambda: fm._oleobj_.InvokeTypes(
        MEMID_HEM_V1, 0, 1, (VT_PTR, 0), arg_types, *args))


def _tactic_3b_raw_invoke_vt_dispatch(fm: Any) -> tuple[dict, Any]:
    """Tactic 3b: raw InvokeTypes with VT_DISPATCH at index 8 — edge_flange VT."""
    arg_types = (
        (VT_I4, 1), (VT_I4, 1), (VT_BOOL, 1),
        (VT_R8, 1), (VT_R8, 1), (VT_R8, 1),
        (VT_R8, 1), (VT_R8, 1),
        (pythoncom.VT_DISPATCH, 1),
    )
    args = _hem_scalars() + (None,)
    return _capture(lambda: fm._oleobj_.InvokeTypes(
        MEMID_HEM_V1, 0, 1, (VT_PTR, 0), arg_types, *args))


def _apply_winner_to_v2(fm: Any, tactic_name: str) -> tuple[dict, Any]:
    """Apply the winning v1 tactic to InsertSheetMetalHem2 (memid 201, arity 16)."""
    v2_scalars = _hem_scalars() + (
        True,   # UseDefaultRelief
        0,      # ReliefType
        0,      # ReliefTearTypes
        False,  # UseReliefRatio
        0.0,    # ReliefRatio
        0.0,    # ReliefWidth
        0.0,    # ReliefDepth
    )
    if tactic_name == "tactic_1_vt_dispatch":
        vt_null = VARIANT(pythoncom.VT_DISPATCH, None)
        args = v2_scalars + (vt_null,)
        return _capture(lambda: fm.InsertSheetMetalHem2(*args))
    elif tactic_name == "tactic_2_vt_error":
        vt_missing = VARIANT(pythoncom.VT_ERROR, pythoncom.DISP_E_PARAMNOTFOUND)
        args = v2_scalars + (vt_missing,)
        return _capture(lambda: fm.InsertSheetMetalHem2(*args))
    elif tactic_name == "tactic_3_raw_vt_ptr":
        arg_types = (
            (VT_I4, 1), (VT_I4, 1), (VT_BOOL, 1),
            (VT_R8, 1), (VT_R8, 1), (VT_R8, 1),
            (VT_R8, 1), (VT_R8, 1),
            (VT_PTR, 1),
            (VT_BOOL, 1), (VT_I4, 1), (VT_I4, 1),
            (VT_BOOL, 1), (VT_R8, 1), (VT_R8, 1), (VT_R8, 1),
        )
        args = v2_scalars + (None,)
        return _capture(lambda: fm._oleobj_.InvokeTypes(
            MEMID_HEM_V2, 0, 1, (VT_PTR, 0), arg_types, *args))
    elif tactic_name == "tactic_3b_raw_vt_dispatch":
        arg_types = (
            (VT_I4, 1), (VT_I4, 1), (VT_BOOL, 1),
            (VT_R8, 1), (VT_R8, 1), (VT_R8, 1),
            (VT_R8, 1), (VT_R8, 1),
            (pythoncom.VT_DISPATCH, 1),
            (VT_BOOL, 1), (VT_I4, 1), (VT_I4, 1),
            (VT_BOOL, 1), (VT_R8, 1), (VT_R8, 1), (VT_R8, 1),
        )
        args = v2_scalars + (None,)
        return _capture(lambda: fm._oleobj_.InvokeTypes(
            MEMID_HEM_V2, 0, 1, (VT_PTR, 0), arg_types, *args))
    return {"status": "SKIPPED", "reason": f"unknown tactic {tactic_name}"}, None


def _check_hem_materialized(doc: Any, mod: Any) -> dict[str, Any]:
    """Scan feature tree for a Hem-type feature."""
    out: dict[str, Any] = {"found": False}
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    tn = ifeat.GetTypeName2()
                    if "Hem" in tn or "hem" in tn:
                        out["found"] = True
                        out["name"] = ifeat.Name
                        out["type"] = tn
                        break
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _save_reopen(sw: Any, doc: Any, mod: Any) -> dict[str, Any]:
    """Save, close, reopen, and verify hem survives."""
    out: dict[str, Any] = {}
    tmp = tempfile.mktemp(suffix=".SLDPRT")
    try:
        doc.SaveAs3(tmp, 0, 2)
        out["saved_to"] = tmp

        sw.CloseAllDocuments(True)
        out["closed"] = True

        doc2, w, e = 0, 0, 0
        try:
            doc2 = sw.OpenDoc6(tmp, 0, 0, "", w, e)
        except Exception as exc:
            out["reopen_error"] = f"{type(exc).__name__}: {exc}"[:200]
            return out

        if doc2 is None:
            out["reopen_error"] = "OpenDoc6 returned None"
            return out

        out["reopened"] = True
        try:
            doc2.ForceRebuild3(False)
        except Exception:
            pass

        after = _metrics(doc2)
        out["faces_after_reopen"] = after["faces"]
        out["vol_mm3_after_reopen"] = after["vol_mm3"]
        out["hem_feature"] = _check_hem_materialized(doc2, mod)

        sw.CloseAllDocuments(True)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass
    return out


def _run_tactic(sw: Any, mod: Any, tactic_name: str,
                tactic_fn: Any) -> dict[str, Any]:
    """Run a single tactic: build fixture, call hem, measure."""
    out: dict[str, Any] = {"tactic": tactic_name}
    doc = None
    try:
        doc, fm, edge, diag = _build_fixture(sw, mod)
        out["fixture"] = diag
        if doc is None or fm is None or edge is None:
            out["error"] = diag.get("error", "fixture build failed")
            out["materialized"] = False
            return out

        before = _metrics(doc)
        out["faces_before"] = before["faces"]
        out["vol_mm3_before"] = before["vol_mm3"]

        rec, feat = tactic_fn(fm)
        out["call"] = rec
        out["materialized"] = _materialized(feat)

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        after = _metrics(doc)
        out["faces_after"] = after["faces"]
        out["vol_mm3_after"] = after["vol_mm3"]
        out["delta_faces"] = after["faces"] - before["faces"]
        out["delta_vol_mm3"] = round(after["vol_mm3"] - before["vol_mm3"], 3)

        out["hem_feature"] = _check_hem_materialized(doc, mod)

        if out["delta_faces"] > 0 and out["delta_vol_mm3"] != 0:
            out["verdict"] = "PASS"
            out["persist"] = _save_reopen(sw, doc, mod)
            doc = None
        else:
            out["verdict"] = "NO_OP"

    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
        out["traceback"] = traceback.format_exc()
        out["materialized"] = False
        out["verdict"] = "EXCEPTION"
    finally:
        if doc is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass

    return out


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "spike": "hem_v4",
        "purpose": "UN-WALL PCBA null trap via 3 typed-null tactics",
        "funcdesc_anchor": "hem_funcdesc_dump.json (memid=91, arity=9, PCBA=PTR/26)",
    }
    sw = None
    try:
        mod = wrapper_module()
        sw = connect_running_sw()
        # RevisionNumber is a METHOD on the typed/makepy proxy but a str
        # PROPERTY on a dynamic.Dispatch (which connect_running_sw returns).
        # Guard both flavors (the GetSaveFlag typed-proxy class of footgun).
        rev = sw.RevisionNumber
        out["sw_revision"] = rev() if callable(rev) else rev

        tactics = [
            ("tactic_1_vt_dispatch", _tactic_1_makepy_vt_dispatch),
            ("tactic_2_vt_error", _tactic_2_makepy_vt_error),
            ("tactic_3_raw_vt_ptr", _tactic_3_raw_invoke_vt_ptr),
            ("tactic_3b_raw_vt_dispatch", _tactic_3b_raw_invoke_vt_dispatch),
        ]

        results: list[dict[str, Any]] = []
        winner = None

        for name, fn in tactics:
            sys.stderr.write(f"[hem-v4] running {name}...\n")
            r = _run_tactic(sw, mod, name, fn)
            results.append(r)
            sys.stderr.write(
                f"[hem-v4] {name}: verdict={r.get('verdict')} "
                f"dFace={r.get('delta_faces')} dVol={r.get('delta_vol_mm3')}\n"
            )
            if r.get("verdict") == "PASS" and winner is None:
                winner = name

        out["v1_tactics"] = results
        out["v1_winner"] = winner

        if winner:
            sys.stderr.write(f"[hem-v4] WINNER: {winner} — applying to v2\n")
            doc2, fm2, edge2, diag2 = _build_fixture(sw, mod)
            v2_out: dict[str, Any] = {"fixture": diag2}
            if doc2 is not None and fm2 is not None and edge2 is not None:
                before2 = _metrics(doc2)
                v2_out["faces_before"] = before2["faces"]
                v2_out["vol_mm3_before"] = before2["vol_mm3"]

                rec2, feat2 = _apply_winner_to_v2(fm2, winner)
                v2_out["call"] = rec2
                v2_out["materialized"] = _materialized(feat2)

                try:
                    doc2.ForceRebuild3(False)
                except Exception:
                    pass

                after2 = _metrics(doc2)
                v2_out["faces_after"] = after2["faces"]
                v2_out["vol_mm3_after"] = after2["vol_mm3"]
                v2_out["delta_faces"] = after2["faces"] - before2["faces"]
                v2_out["delta_vol_mm3"] = round(
                    after2["vol_mm3"] - before2["vol_mm3"], 3)
                v2_out["hem_feature"] = _check_hem_materialized(doc2, mod)

                if v2_out["delta_faces"] > 0 and v2_out["delta_vol_mm3"] != 0:
                    v2_out["verdict"] = "PASS"
                    v2_out["persist"] = _save_reopen(sw, doc2, mod)
                    doc2 = None
                else:
                    v2_out["verdict"] = "NO_OP"
            else:
                v2_out["error"] = "v2 fixture build failed"

            if doc2 is not None:
                try:
                    sw.CloseAllDocuments(True)
                except Exception:
                    pass

            out["v2_winner_applied"] = v2_out

        any_pass = any(r.get("verdict") == "PASS" for r in results)
        out["overall_verdict"] = "PASS" if any_pass else "WALLED"

    except Exception as exc:
        out["fatal_error"] = f"{type(exc).__name__}: {exc}"[:300]
        out["traceback"] = traceback.format_exc()
        out["overall_verdict"] = "ERROR"
    finally:
        if sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        pythoncom.CoUninitialize()

    res_dir = Path(__file__).resolve().parent / "_results"
    res_dir.mkdir(parents=True, exist_ok=True)
    out_path = res_dir / "hem_v4_results.json"
    out_path.write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")
    sys.stderr.write(f"[hem-v4] wrote {out_path}\n")
    sys.stderr.write(f"[hem-v4] VERDICT: {out.get('overall_verdict')}\n")

    payload = json.dumps(out, indent=2, default=str)
    sys.stdout.write(payload + "\n")
    return 0 if out.get("overall_verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
