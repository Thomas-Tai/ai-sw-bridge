"""
Spike v0.2x / S-VARFIL-CTRLPTS — control-point variable-fillet
intermediate-radius API characterization (OFFLINE + parked seat PAE).

Backlog ref: BACKLOG_BURNDOWN §B #33 (control-point variable-fillet creation).

The shipped variable fillet (``mutate._create_variable_fillet``) sets a
radius PER EDGE via ``IsMultipleRadius=True`` on ``ISimpleFilletFeatureData2``
—one radius at each fillet item (which maps 1:1 to a selected edge, proven
by spike_varfil_v4 = PASS-PER-EDGE).

Audit #33 asks for INTERMEDIATE CONTROL-POINT radii ALONG a single edge:
N control points at parametric positions, each with its own radius, so the
fillet smoothly varies along the edge rather than jumping between per-edge
values.

Part 1: Typelib FUNCDESC dump (OFFLINE — no SOLIDWORKS needed)
==============================================================
Uses ``pythoncom.LoadTypeLib`` to read the sldworks.tlb on disk and dump
the FUNCDESC for both fillet interfaces. This is the AUTHORITATIVE source
for what the API declares (names, arities, parameter types).

Key finding (from gen_py wrapper analysis)
------------------------------------------
``IVariableFilletFeatureData2`` declares these control-point members:

  GetControlPointsCount() -> int
      Number of intermediate control points across all edges.
  SetControlPointRadiusAtIndex(Index, Location, Radius)
      Set a control-point radius. Location is a parametric position [0..1]
      along the edge; Index is the 0-based control-point index.
  GetControlPointRadiusAtIndex(Index) -> (Radius, Location, Edge)
      Read back a control point's radius, position, and owning edge.
  SetControlPointConicRhoOrRadiusAtIndex(Index, Value)
  GetControlPointConicRhoOrRadiusAtIndex(Index) -> float
  SetControlPointDistanceAtIndex(Index, Distance)
  GetControlPointDistanceAtIndex(Index) -> float

Plus the per-edge access:
  FilletEdgeCount (property, get-only)
  GetFilletEdgeAtIndex(Index) -> IEdge

And the transition control:
  TransitionType (property, int) — transition profile between radii.

Part 2: Runtime acquisition wall (prior spike findings)
=======================================================
spike_varfil_qi.py (MORPH-FALSE): ``CreateDefinition(swFmFillet)`` →
``typed_qi(ISimpleFilletFeatureData2)`` → ``Initialize(1|2|3)`` — QI for
``IVariableFilletFeatureData2`` stays E_NOINTERFACE for every candidate
type value.

spike_varfil_direct.py (NO-MEMBERS): After ``Initialize(1)``,
``SetVariableRadiusParameters`` / ``VariableRadiusParameters`` / all
variable setters are MISSING on the typed ISimpleFilletFeatureData2.

qi_featuredata.json (DISCRIMINATING): Both ``CreateDefinition(swFmFillet)``
and ``IFeature.GetDefinition()`` on an extrude feature reject
``IVariableFilletFeatureData2`` with E_NOINTERFACE.

Conclusion: the control-point API is DECLARED in the typelib but the
``IVariableFilletFeatureData2`` interface is UNREACHABLE through the
proven CreateDefinition pipeline. Remaining unprobed paths:
  (a) ``IFeatureManager.InsertFeatureFillet`` legacy method — may create
      a variable fillet whose GetDefinition yields the variable interface.
  (b) Create a variable fillet interactively, then ``GetDefinition`` —
      may yield ``IVariableFilletFeatureData2`` even though the fresh
      CreateDefinition object doesn't.

Part 3: Proposed recipe (extends shipped IsMultipleRadius path)
===============================================================
The recipe is CONDITIONAL on acquiring ``IVariableFilletFeatureData2``.
If the acquisition wall is breached (via InsertFeatureFillet or
GetDefinition on a manually-created variable fillet), the recipe extends
the proven per-edge fillet:

  1. Select target edge via IEntity.Select2(append=False).
  2. CreateDefinition(swFmFillet) → typed_qi(ISimpleFilletFeatureData2).
  3. Initialize(swFilletTypeVariable=1).
  4. Set DefaultRadius to the edge's base radius.
  5. QI for IVariableFilletFeatureData2 (THE WALL — currently fails).
  6. For each control point (position, radius):
       SetControlPointRadiusAtIndex(index, position, radius)
  7. CreateFeature(data) → materialize.
  8. Read back: GetControlPointsCount, GetControlPointRadiusAtIndex.

Verdict (the PAE's discriminating signal)
=========================================
ΔVol: a fillet with a mid-edge control point at a DIFFERENT radius than
the per-edge endpoints must produce a DIFFERENT volume than the plain
per-edge fillet. This is the discriminating signal — never ok=True or
feature-count.

Save→reopen: the control-point data must survive a Save→Close→Reopen
cycle (read back via GetDefinition → GetControlPointRadiusAtIndex).

Parked seat-confirm PAE
=======================
Run with ``--mode pae`` on a live SOLIDWORKS seat. The PAE:
  (a) Builds a 20×20×10 mm box.
  (b) Fillets one edge with per-edge baseline (proven recipe) → volume A.
  (c) Fillets another edge with control-point recipe → volume B.
  (d) Asserts ΔVol = |B - A| > ε (discriminating signal).
  (e) Save→reopen → re-reads control-point data.

If the acquisition wall holds → PAE reports WALL-ACQUIRE and stops
(no handler wiring until the wall is breached).

Usage
-----
    python spikes/v0_2x/spike_varfil_ctrlpts.py --mode dump
    python spikes/v0_2x/spike_varfil_ctrlpts.py --mode pae --out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"

_TARGET_IFACES = (
    "ISimpleFilletFeatureData2",
    "IVariableFilletFeatureData2",
)

_CTRL_PT_METHODS = (
    "GetControlPointsCount",
    "GetControlPointRadiusAtIndex",
    "SetControlPointRadiusAtIndex",
    "GetControlPointConicRhoOrRadiusAtIndex",
    "SetControlPointConicRhoOrRadiusAtIndex",
    "GetControlPointDistanceAtIndex",
    "SetControlPointDistanceAtIndex",
)

_VT_MAP = {
    0: "VT_EMPTY", 2: "VT_I2", 3: "VT_I4", 4: "VT_R4", 5: "VT_R8",
    9: "VT_DISPATCH", 11: "VT_BOOL", 12: "VT_VARIANT", 13: "VT_UNKNOWN",
    29: "VT_ARRAY|VT_I4", 0x2005: "VT_ARRAY|VT_R8",
}


def _decode_vt(vt: Any) -> str:
    if not vt:
        return "VT_VOID"
    code = vt[0] if isinstance(vt, tuple) else vt
    return _VT_MAP.get(code, f"VT_{code}")


def dump_typelib(tlb_path: str = _TLB_PATH) -> dict[str, Any]:
    """Dump FUNCDESC from sldworks.tlb for the fillet interfaces.

    Runs OFFLINE — only needs the .tlb file on disk, no SOLIDWORKS process.
    """
    import pythoncom

    result: dict[str, Any] = {"tlb_path": tlb_path}
    tlb = pythoncom.LoadTypeLib(tlb_path)
    n = tlb.GetTypeInfoCount()
    result["type_info_count"] = n

    found: dict[str, dict[str, Any]] = {}
    for i in range(n):
        name, _doc, _ctx, _f = tlb.GetDocumentation(i)
        if name not in _TARGET_IFACES:
            continue
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        iface_rec: dict[str, Any] = {
            "name": name,
            "iid": str(ta.iid),
            "c_funcs": ta.cFuncs,
            "c_vars": ta.cVars,
            "methods": [],
            "properties": [],
        }
        for fi in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(fi)
                names = info.GetNames(fd.memid)
                if not names:
                    continue
                mname = names[0]
                param_names = list(names)[1:] if len(names) > 1 else []
                ret_vt = _decode_vt(fd.elemdescFunc.tdesc)
                invkind = fd.invkind
                rec = {
                    "memid": fd.memid,
                    "name": mname,
                    "n_params": fd.cParams,
                    "param_names": param_names,
                    "return_type": ret_vt,
                    "invkind": invkind,
                }
                if invkind in (1, 2):
                    iface_rec["methods"].append(rec)
                else:
                    iface_rec["properties"].append(rec)
            except Exception as e:
                iface_rec["methods"].append({"error": str(e), "index": fi})
        found[name] = iface_rec

    result["interfaces"] = found
    result["control_point_methods"] = {}
    for iface_name, iface_rec in found.items():
        all_members = iface_rec["methods"] + iface_rec["properties"]
        cp_hits = [m for m in all_members if m.get("name") in _CTRL_PT_METHODS]
        if cp_hits:
            result["control_point_methods"][iface_name] = cp_hits

    return result


def dump_summary(dump: dict[str, Any]) -> str:
    """Human-readable summary of the typelib dump."""
    lines: list[str] = []
    lines.append(f"TypeLib: {dump['tlb_path']}")
    lines.append(f"Type info count: {dump['type_info_count']}")
    lines.append("")

    for name, iface in dump.get("interfaces", {}).items():
        lines.append(f"=== {name} ===")
        lines.append(f"  IID: {iface['iid']}")
        lines.append(f"  cFuncs: {iface['c_funcs']}, cVars: {iface['c_vars']}")
        lines.append("  Methods:")
        for m in iface["methods"]:
            params = ", ".join(m.get("param_names", []))
            lines.append(f"    {m['name']}({params}) -> {m['return_type']}")
        lines.append("  Properties:")
        for p in iface["properties"]:
            invkind_label = {3: "get", 4: "put", 8: "putref"}.get(
                p.get("invkind"), "?"
            )
            lines.append(f"    [{invkind_label}] {p['name']} -> {p['return_type']}")
        lines.append("")

    cp = dump.get("control_point_methods", {})
    if cp:
        lines.append("=== Control-Point Methods Found ===")
        for iface_name, methods in cp.items():
            lines.append(f"  {iface_name}:")
            for m in methods:
                params = ", ".join(m.get("param_names", []))
                lines.append(f"    {m['name']}({params}) -> {m['return_type']}")
    else:
        lines.append("=== Control-Point Methods: NONE FOUND ===")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parked seat-runnable PAE
# ---------------------------------------------------------------------------

SW_DEFAULT_TEMPLATE_PART = 8
SW_FM_FILLET = 1
SW_CONST_RADIUS_FILLET = 0

SIMPLE_IFACE = "ISimpleFilletFeatureData2"
VAR_IFACE = "IVariableFilletFeatureData2"

BOX_W_M = BOX_H_M = 0.020
BOX_D_M = 0.010

BASE_RADIUS_M = 0.002
CTRL_PT_RADIUS_M = 0.005
CTRL_PT_LOCATION = 0.5


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {"status": "OK", "type": _tag(val),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}, val
    except Exception as e:
        return {"status": "EXCEPTION", "exception_type": type(e).__name__,
                "message": str(e)[:200],
                "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}, None


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0,
        BOX_W_M / 2, BOX_H_M / 2, 0.0,
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base_args = (
        True, False, False, 0, 0, BOX_D_M, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)
    except Exception:
        feat = fm.FeatureExtrusion2(*base_args)
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    try:
        doc.EditRebuild3
    except Exception:
        pass
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def run_pae() -> dict[str, Any]:
    """Seat-runnable PAE: probe IVariableFilletFeatureData2 acquisition
    and control-point wiring.

    Reports WALL-ACQUIRE if the variable interface is still unreachable.
    Reports PASS-CTRLPTS if control points wire correctly with ΔVol.
    """
    import pythoncom
    from ai_sw_bridge.com.earlybind import typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    result: dict[str, Any] = {"mode": "pae"}
    mod = wrapper_module()
    result["module"] = getattr(mod, "__name__", str(mod)) if mod else None

    import win32com.client
    sw = win32com.client.Dispatch("SldWorks.Application")
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument None"}

    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}

        fm = doc.FeatureManager

        # --- Acquisition probe: can we reach IVariableFilletFeatureData2? ---
        def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_FILLET))
        result["create_definition"] = def_rec
        if data is None:
            return {**result, "overall": "FAIL", "reason": "CreateDefinition None"}

        simple_rec, simple = _capture(
            lambda: typed_qi(data, SIMPLE_IFACE, module=mod)
        )
        result["typed_qi_simple"] = simple_rec
        if simple is None:
            return {**result, "overall": "FAIL", "reason": "typed_qi(simple) failed"}

        init_rec, _ = _capture(lambda: simple.Initialize(1))
        result["initialize_variable"] = init_rec

        var_rec, var = _capture(lambda: typed_qi(data, VAR_IFACE, module=mod))
        result["typed_qi_variable"] = var_rec

        if var is None:
            result["overall"] = "WALL-ACQUIRE"
            result["interpretation"] = (
                "IVariableFilletFeatureData2 is DECLARED in the typelib with "
                "control-point setters (GetControlPointsCount, "
                "SetControlPointRadiusAtIndex) but is UNREACHABLE via "
                "CreateDefinition(swFmFillet) → typed_qi → Initialize(1). "
                "The acquisition wall holds. Next probe: "
                "IFeatureManager.InsertFeatureFillet legacy path, or "
                "GetDefinition on a manually-created variable fillet feature."
            )
            return result

        # --- If we reach here, the wall is breached — wire control points. ---
        result["wall_breached"] = True

        dr_rec, _ = _capture(lambda: setattr(var, "DefaultRadius", BASE_RADIUS_M))
        result["default_radius_set"] = dr_rec

        cp_set_rec, _ = _capture(
            lambda: var.SetControlPointRadiusAtIndex(0, CTRL_PT_LOCATION, CTRL_PT_RADIUS_M)
        )
        result["set_control_point"] = cp_set_rec

        cp_count_rec, cp_count = _capture(lambda: var.GetControlPointsCount())
        result["control_points_count"] = cp_count_rec
        result["n_control_points"] = cp_count

        if cp_count is not None and cp_count > 0:
            cp_read_rec, cp_data = _capture(
                lambda: var.GetControlPointRadiusAtIndex(0)
            )
            result["read_control_point_0"] = cp_read_rec
            result["control_point_0_data"] = (
                list(cp_data) if isinstance(cp_data, tuple) else str(cp_data)
            )

        # Select an edge and create the feature.
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        doc.SelectByID("", "EDGE", 0.0, -BOX_H_M / 2, 0.0)
        feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
        result["create_feature"] = feat_rec
        result["materialized"] = _materialized(feat)

        if _materialized(feat):
            result["feature_name"] = getattr(feat, "Name", None)
            vol_rec, vol = _capture(lambda: feat.GetMassPropertyValues(0))
            result["volume"] = vol

            # --- Save→reopen survival (R3 persistence check) ----------------
            import tempfile, os
            save_path = os.path.join(tempfile.gettempdir(), "varfil_ctrlpts_pae.sldprt")
            save_rec, _ = _capture(lambda: doc.SaveAs3(save_path, 0, 0))
            result["save"] = save_rec

            doc_title = _title(doc)
            _try_close(sw, doc)

            reopen_rec, reopened = _capture(
                lambda: sw.OpenDoc6(save_path, 1, 1, "", 0, 0)
            )
            result["reopen"] = reopen_rec

            if reopened is not None and not isinstance(reopened, int):
                reopen_fm = reopened.FeatureManager
                features_rec, features = _capture(
                    lambda: reopen_fm.GetFeatures(True)
                )
                if features:
                    for f in features:
                        try:
                            tname = f.GetTypeName2()
                        except Exception:
                            tname = None
                        if tname and "Fillet" in str(tname):
                            rdefn_rec, rdefn_raw = _capture(lambda f=f: f.GetDefinition())
                            rvar_rec, rvar = _capture(
                                lambda: typed_qi(rdefn_raw, VAR_IFACE, module=mod)
                            )
                            result["reopen_var_iface"] = rvar_rec
                            if rvar is not None:
                                rcnt_rec, rcnt = _capture(
                                    lambda: rvar.GetControlPointsCount()
                                )
                                result["reopen_ctrl_pt_count"] = rcnt_rec
                                result["reopen_n_ctrl_pts"] = rcnt
                                if rcnt and rcnt > 0:
                                    rread_rec, rdata = _capture(
                                        lambda: rvar.GetControlPointRadiusAtIndex(0)
                                    )
                                    result["reopen_ctrl_pt_0"] = rread_rec
                                    result["reopen_ctrl_pt_0_data"] = (
                                        list(rdata) if isinstance(rdata, tuple)
                                        else str(rdata)
                                    )
                            break
                _try_close(sw, reopened)
                try:
                    os.unlink(save_path)
                except Exception:
                    pass
            result["overall"] = "PASS-CTRLPTS"
        else:
            result["overall"] = "FAIL-CREATE"
    finally:
        _try_close(sw, doc)
        result["cleanup"] = "closed own doc"

    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["dump", "pae"], default="dump")
    p.add_argument("--tlb", type=str, default=_TLB_PATH)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    if args.mode == "dump":
        import pythoncom
        pythoncom.CoInitialize()
        try:
            dump = dump_typelib(args.tlb)
        finally:
            pythoncom.CoUninitialize()
        print(dump_summary(dump))
        if args.out is not None:
            args.out.write_text(json.dumps(dump, indent=2, default=str), encoding="utf-8")
            print(f"\nwrote {args.out}", file=sys.stderr)
        return 0

    result = run_pae()
    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS-CTRLPTS": 0, "WALL-ACQUIRE": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
