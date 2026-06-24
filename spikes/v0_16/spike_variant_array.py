"""Spike v0.16 - Epic A: VARIANT-array marshaling for E1 inertia tensor.

Probes IMassProperty2 / IMassProperty on a live box to crack the
VARIANT(VT_ARRAY|VT_R8, [x,y,z]) marshaling wall.

Usage:
    python spikes/v0_16/spike_variant_array.py --out spikes/v0_16/_results/variant_array.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parent
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module

from spike_earlybind_persist import connect_running_sw, ensure_sw_module


SW_DEFAULT_TEMPLATE_PART = 8
TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"


def _title(doc):
    t = doc.GetTitle
    return t() if callable(t) else t


def _try_close(sw, doc):
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _capture(fn):
    try:
        result = fn()
        return {"status": "OK"}, result
    except Exception as exc:
        return {
            "status": "ERR",
            "type": type(exc).__name__,
            "message": str(exc)[:200],
        }, None


_VT_NAMES = {
    0: "VT_EMPTY",
    1: "VT_NULL",
    2: "VT_I2",
    3: "VT_I4",
    4: "VT_R4",
    5: "VT_R8",
    6: "VT_CY",
    7: "VT_DATE",
    8: "VT_BSTR",
    9: "VT_DISPATCH",
    10: "VT_ERROR",
    11: "VT_BOOL",
    12: "VT_VARIANT",
    13: "VT_UNKNOWN",
    14: "VT_DECIMAL",
    16: "VT_I1",
    17: "VT_UI1",
    18: "VT_UI2",
    19: "VT_UI4",
    20: "VT_I8",
    21: "VT_UI8",
    22: "VT_INT",
    23: "VT_UINT",
    24: "VT_VOID",
    25: "VT_HRESULT",
    26: "VT_PTR",
    27: "VT_SAFEARRAY",
    29: "VT_USERDEFINED",
}


def _vt_name(vt):
    base = vt & 0xFFF
    array = bool(vt & 0x2000)
    byref = bool(vt & 0x4000)
    name = _VT_NAMES.get(base, f"VT_{base}")
    if array:
        name = f"VT_ARRAY|{name}"
    if byref:
        name = f"{name}*"
    return name


def _dump_typelib_members():
    out = {}
    try:
        tlb = pythoncom.LoadTypeLib(TLB_PATH)
    except Exception as exc:
        out["error"] = f"LoadTypeLib failed: {exc!r}"
        return out
    n = tlb.GetTypeInfoCount()
    focus = {"IMassProperty", "IMassProperty2"}
    for i in range(n):
        info = tlb.GetTypeInfo(i)
        name = tlb.GetDocumentation(i)[0]
        if name not in focus:
            continue
        ta = info.GetTypeAttr()
        members = []
        for f in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f)
                names = info.GetNames(fd.memid)
                mem_name = names[0] if names else f"dispid_{fd.memid}"
                arg_names = names[1:] if len(names) > 1 else []
                args_info = []
                for ai, elem in enumerate(fd.args):
                    vt_type = elem[0]
                    flags = elem[1]
                    default = elem[2] if len(elem) > 2 else None
                    flag_parts = []
                    if flags & 1:
                        flag_parts.append("in")
                    if flags & 2:
                        flag_parts.append("out")
                    if flags & 8:
                        flag_parts.append("retval")
                    if flags & 0x40:
                        flag_parts.append("optional")
                    arg_info = {
                        "name": arg_names[ai] if ai < len(arg_names) else f"arg{ai}",
                        "vt": _vt_name(vt_type),
                        "vt_raw": vt_type,
                        "flags": "|".join(flag_parts) or f"0x{flags:x}",
                    }
                    if default is not None:
                        arg_info["default"] = str(default)
                    args_info.append(arg_info)
                ret_vt = _vt_name(fd.retType)
                inv_kind = {
                    1: "method",
                    2: "propget",
                    4: "propput",
                    8: "propputref",
                }.get(fd.invkind, str(fd.invkind))
                members.append(
                    {
                        "name": mem_name,
                        "invkind": inv_kind,
                        "return_vt": ret_vt,
                        "args": args_info,
                        "dispid": fd.memid,
                    }
                )
            except Exception as exc:
                members.append({"error": str(exc)[:100], "func_index": f})
        for v in range(ta.cVars):
            try:
                vd = info.GetVarDesc(v)
                names = info.GetNames(vd.memid)
                var_name = names[0] if names else f"var_{vd.memid}"
                members.append(
                    {
                        "name": var_name,
                        "kind": "variable",
                        "vt": _vt_name(vd.varkind),
                        "dispid": vd.memid,
                    }
                )
            except Exception:
                pass
        out[name] = members
    return out


def _build_box(sw):
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument returned None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateLine(-0.02, -0.02, 0, 0.02, -0.02, 0)
    sk.CreateLine(0.02, -0.02, 0, 0.02, 0.02, 0)
    sk.CreateLine(0.02, 0.02, 0, -0.02, 0.02, 0)
    sk.CreateLine(-0.02, 0.02, 0, -0.02, -0.02, 0)
    doc.InsertSketch2(False)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(
        True,
        False,
        False,
        0,
        0,
        0.02,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0,
        False,
    )
    doc.ClearSelection2(True)
    return doc


def _get_mass_property(doc, mod):
    info = {}
    ext = doc.Extension
    text = typed(ext, "IModelDocExtension", module=mod)
    mp = text.CreateMassProperty
    if callable(mp):
        mp = mp()
    if mp is None:
        info["error"] = "CreateMassProperty returned None"
        return None, None, info
    mp_typed = None
    rec, mp_typed = _capture(lambda: typed(mp, "IMassProperty2", module=mod))
    if mp_typed is None:
        info["typed_IMassProperty2"] = rec
        rec2, mp_typed = _capture(lambda: typed(mp, "IMassProperty", module=mod))
        if mp_typed is None:
            info["typed_IMassProperty"] = rec2
        else:
            info["typed_iface"] = "IMassProperty"
    else:
        info["typed_iface"] = "IMassProperty2"
    return mp, mp_typed, info


def _probe_scalar_reads(mp):
    out = {}
    for prop in ("Volume", "SurfaceArea", "Mass", "Density", "CenterOfMass"):
        rec, val = _capture(lambda p=prop: getattr(mp, p))
        rec["value"] = val
        out[prop] = rec
    return out


def _probe_member_enum(mp, mp_typed):
    out = {"late_bound": [], "typed": []}
    probe_names = (
        "PrincipalAxesOfInertia",
        "GetMomentOfInertia",
        "Moments",
        "RadiusOfGyration",
        "MomentOfInertia",
        "GetPrincipalAxesOfInertia",
        "GetPrincipalMomentsOfInertia",
        "GetRadiiOfGyration",
    )
    for name in probe_names:
        rec, val = _capture(lambda n=name: getattr(mp, n))
        entry = {"name": name}
        if rec["status"] == "OK":
            entry.update({"callable": callable(val), "type": type(val).__name__})
        else:
            entry.update(rec)
        out["late_bound"].append(entry)
    if mp_typed is not None:
        for name in probe_names:
            rec, val = _capture(lambda n=name: getattr(mp_typed, n))
            entry = {"name": name}
            if rec["status"] == "OK":
                entry.update({"callable": callable(val), "type": type(val).__name__})
            else:
                entry.update(rec)
            out["typed"].append(entry)
    return out


def _preview(val):
    if val is None:
        return "None"
    if isinstance(val, (int, float, bool, str)):
        return repr(val)
    if isinstance(val, (tuple, list)):
        items = []
        for v in val[:12]:
            if isinstance(v, float):
                items.append(f"{v:.6g}")
            else:
                items.append(repr(v))
        suffix = f"... ({len(val)} total)" if len(val) > 12 else ""
        return "[" + ", ".join(items) + "]" + suffix
    return f"<{type(val).__name__}>"


def _probe_marshaling(mp, mp_typed, com_center):
    results = []
    targets = [("late_bound", mp)]
    if mp_typed is not None:
        targets.append(("typed", mp_typed))
    METHODS = ("PrincipalAxesOfInertia", "GetMomentOfInertia")
    for tn, t in targets:
        for mn in METHODS:
            rec, val = _capture(lambda t=t, m=mn: getattr(t, m)(com_center))
            results.append(
                {
                    "variant": "plain_list",
                    "target": tn,
                    "method": mn,
                    **rec,
                    "value_preview": _preview(val),
                }
            )
    tup = tuple(com_center)
    for tn, t in targets:
        for mn in METHODS:
            rec, val = _capture(lambda t=t, m=mn: getattr(t, m)(tup))
            results.append(
                {
                    "variant": "plain_tuple",
                    "target": tn,
                    "method": mn,
                    **rec,
                    "value_preview": _preview(val),
                }
            )
    try:
        var_arr = w32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, com_center)
        for tn, t in targets:
            for mn in METHODS:
                rec, val = _capture(lambda t=t, m=mn, v=var_arr: getattr(t, m)(v))
                results.append(
                    {
                        "variant": "VARIANT(VT_ARRAY|VT_R8,list)",
                        "target": tn,
                        "method": mn,
                        **rec,
                        "value_preview": _preview(val),
                    }
                )
    except Exception as exc:
        results.append(
            {
                "variant": "VARIANT(VT_ARRAY|VT_R8,list)",
                "construction_error": f"{type(exc).__name__}: {exc}"[:200],
            }
        )
    try:
        inner = [w32.VARIANT(pythoncom.VT_R8, v) for v in com_center]
        var_varr = w32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, inner)
        for tn, t in targets:
            for mn in METHODS:
                rec, val = _capture(lambda t=t, m=mn, v=var_varr: getattr(t, m)(v))
                results.append(
                    {
                        "variant": "VARIANT(VT_ARRAY|VT_VARIANT,[VT_R8])",
                        "target": tn,
                        "method": mn,
                        **rec,
                        "value_preview": _preview(val),
                    }
                )
    except Exception as exc:
        results.append(
            {
                "variant": "VARIANT(VT_ARRAY|VT_VARIANT,[VT_R8])",
                "construction_error": f"{type(exc).__name__}: {exc}"[:200],
            }
        )
    for tn, t in targets:
        for mn in METHODS:
            c = list(com_center)
            rec, val = _capture(lambda t=t, m=mn, c=c: getattr(t, m)(c[0], c[1], c[2]))
            results.append(
                {
                    "variant": "3_separate_floats",
                    "target": tn,
                    "method": mn,
                    **rec,
                    "value_preview": _preview(val),
                }
            )
    try:
        v0 = w32.VARIANT(pythoncom.VT_R8, com_center[0])
        v1 = w32.VARIANT(pythoncom.VT_R8, com_center[1])
        v2 = w32.VARIANT(pythoncom.VT_R8, com_center[2])
        for tn, t in targets:
            for mn in METHODS:
                rec, val = _capture(lambda t=t, m=mn: getattr(t, m)(v0, v1, v2))
                results.append(
                    {
                        "variant": "3_separate_VARIANT(VT_R8)",
                        "target": tn,
                        "method": mn,
                        **rec,
                        "value_preview": _preview(val),
                    }
                )
    except Exception as exc:
        results.append(
            {
                "variant": "3_separate_VARIANT(VT_R8)",
                "construction_error": f"{type(exc).__name__}: {exc}"[:200],
            }
        )
    try:
        sa = pythoncom.SafeArrayCreate(pythoncom.VT_R8, 1, (0, 2))
        if sa is not None:
            for i, v in enumerate(com_center):
                sa[i] = v
            for tn, t in targets:
                for mn in METHODS:
                    rec, val = _capture(lambda t=t, m=mn, s=sa: getattr(t, m)(s))
                    results.append(
                        {
                            "variant": "SafeArray(VT_R8)",
                            "target": tn,
                            "method": mn,
                            **rec,
                            "value_preview": _preview(val),
                        }
                    )
        else:
            results.append(
                {
                    "variant": "SafeArray(VT_R8)",
                    "construction_error": "SafeArrayCreate returned None",
                }
            )
    except Exception as exc:
        results.append(
            {
                "variant": "SafeArray(VT_R8)",
                "construction_error": f"{type(exc).__name__}: {exc}"[:200],
            }
        )
    PROP_NAMES = METHODS + ("Moments", "RadiusOfGyration", "MomentOfInertia")
    for tn, t in targets:
        for pn in PROP_NAMES:
            rec, val = _capture(lambda t=t, p=pn: getattr(t, p))
            results.append(
                {
                    "variant": "property_get_no_args",
                    "target": tn,
                    "property": pn,
                    **rec,
                    "value_type": type(val).__name__ if val is not None else "None",
                    "value_preview": _preview(val),
                }
            )
    try:
        var_tup = w32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(com_center))
        for tn, t in targets:
            for mn in METHODS:
                rec, val = _capture(lambda t=t, m=mn, v=var_tup: getattr(t, m)(v))
                results.append(
                    {
                        "variant": "VARIANT(VT_ARRAY|VT_R8,tuple)",
                        "target": tn,
                        "method": mn,
                        **rec,
                        "value_preview": _preview(val),
                    }
                )
    except Exception as exc:
        results.append(
            {
                "variant": "VARIANT(VT_ARRAY|VT_R8,tuple)",
                "construction_error": f"{type(exc).__name__}: {exc}"[:200],
            }
        )
    try:
        VT_BR = pythoncom.VT_ARRAY | pythoncom.VT_R8 | pythoncom.VT_BYREF
        var_br = w32.VARIANT(VT_BR, com_center)
        for tn, t in targets:
            for mn in METHODS:
                rec, val = _capture(lambda t=t, m=mn, v=var_br: getattr(t, m)(v))
                results.append(
                    {
                        "variant": "VARIANT(VT_ARRAY|VT_R8|VT_BYREF)",
                        "target": tn,
                        "method": mn,
                        **rec,
                        "value_preview": _preview(val),
                    }
                )
    except Exception as exc:
        results.append(
            {
                "variant": "VARIANT(VT_ARRAY|VT_R8|VT_BYREF)",
                "construction_error": f"{type(exc).__name__}: {exc}"[:200],
            }
        )
    return results


def run():
    result = {"spike": "variant_array_epic_A"}
    print("[spike] Phase 1: typelib characterization...")
    result["typelib"] = _dump_typelib_members()
    print("[spike] Phase 2: connecting to running SW...")
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))
    sw = connect_running_sw()
    print("[spike] building box...")
    doc = _build_box(sw)
    title = _title(doc)
    print(f"[spike] box built: {title}")
    try:
        print("[spike] acquiring IMassProperty...")
        mp, mp_typed, mp_info = _get_mass_property(doc, mod)
        result["mass_property_acquisition"] = mp_info
        if mp is None:
            result["overall"] = "FAIL"
            result["reason"] = "Could not acquire IMassProperty"
            return result
        print("[spike] scalar baseline reads...")
        result["scalar_reads"] = _probe_scalar_reads(mp)
        print("[spike] member enumeration...")
        result["member_enum"] = _probe_member_enum(mp, mp_typed)
        com = [0.0, 0.0, 0.0]
        try:
            com_raw = mp.CenterOfMass
            if com_raw is not None and len(com_raw) >= 3:
                com = [float(com_raw[i]) for i in range(3)]
        except Exception:
            pass
        result["center_of_rotation_m"] = com
        print("[spike] marshaling probes (10 variants)...")
        result["marshaling_probes"] = _probe_marshaling(mp, mp_typed, com)
        greens = [
            p
            for p in result["marshaling_probes"]
            if p.get("status") == "OK" and p.get("value_preview") != "None"
        ]
        result["green_count"] = len(greens)
        result["green_variants"] = [
            {
                "variant": p["variant"],
                "target": p.get("target"),
                "method": p.get("method", p.get("property", "?")),
                "preview": p["value_preview"],
            }
            for p in greens
        ]
        if greens:
            result["overall"] = "GREEN"
            n = len(greens)
            result["interpretation"] = (
                f"{n} marshaling variant(s) returned data. W0 can wire tensor reads."
            )
        else:
            result["overall"] = "WALL"
            result["interpretation"] = (
                "No marshaling variant succeeded. VARIANT(VT_ARRAY|VT_R8) wall persists."
            )
    finally:
        _try_close(sw, doc)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"GREEN": 0, "WALL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
