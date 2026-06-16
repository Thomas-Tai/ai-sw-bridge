"""Step A — O1 FUNCDESC dump for InsertSheetMetalHem / InsertSheetMetalHem2.

Dumps the **real** signature from sldworks.tlb via pythoncom.LoadTypeLib
(NOT GetTypeInfo on a live dispatch — O1 doctrine).
Also dumps swHemTypes_e / swHemPositionTypes_e from swconst.tlb.

Usage:
    PYTHONPATH=src C:/Python314/python.exe spikes/v0_2x/dump_hem_funcdesc.py
"""

from __future__ import annotations

import json
import sys
import winreg
from pathlib import Path

import pythoncom

SW_LIBID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
SWCONST_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb")

VT_NAMES = {
    pythoncom.VT_I2: "I2",
    pythoncom.VT_I4: "I4",
    pythoncom.VT_R4: "R4",
    pythoncom.VT_R8: "R8",
    pythoncom.VT_BSTR: "BSTR",
    pythoncom.VT_BOOL: "BOOL",
    pythoncom.VT_VARIANT: "VARIANT",
    pythoncom.VT_UNKNOWN: "IUnknown*",
    pythoncom.VT_DISPATCH: "IDispatch*",
    pythoncom.VT_HRESULT: "HRESULT",
    pythoncom.VT_VOID: "VOID",
    pythoncom.VT_UI4: "UI4",
    pythoncom.VT_LPSTR: "LPSTR",
    pythoncom.VT_LPWSTR: "LPWSTR",
    pythoncom.VT_INT: "INT",
    pythoncom.VT_UINT: "UINT",
    pythoncom.VT_CY: "CY",
    pythoncom.VT_DATE: "DATE",
    pythoncom.VT_ERROR: "ERROR",
    pythoncom.VT_PTR: "PTR",
    pythoncom.VT_USERDEFINED: "USERDEFINED",
}


def _sw_tlb_path() -> str | None:
    try:
        libk = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"TypeLib")
        libk = winreg.OpenKey(libk, SW_LIBID)
    except OSError:
        return None
    vers = []
    i = 0
    while True:
        try:
            vers.append(winreg.EnumKey(libk, i))
            i += 1
        except OSError:
            break
    for ver in reversed(vers):
        for arch in ("win64", "win32"):
            try:
                kk = winreg.OpenKey(libk, f"{ver}\\0\\{arch}")
                path, _ = winreg.QueryValueEx(kk, "")
                if path:
                    return path
            except OSError:
                continue
    return None


def _vt_name(vt: int) -> str:
    base = vt & ~pythoncom.VT_BYREF & ~pythoncom.VT_ARRAY
    name = VT_NAMES.get(base, f"VT_{base}")
    if vt & pythoncom.VT_BYREF:
        name += " [byref]"
    if vt & pythoncom.VT_ARRAY:
        name += " [array]"
    return name


def _dump_funcdesc(tlb_path: str, target_iface: str, target_methods: list[str]) -> dict:
    tlb = pythoncom.LoadTypeLib(tlb_path)
    result: dict = {"tlb_path": tlb_path, "iface": target_iface, "methods": {}}

    for i in range(tlb.GetTypeInfoCount()):
        name = tlb.GetDocumentation(i)[0]
        if name != target_iface:
            continue
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()

        for f in range(ta.cFuncs):
            fd = info.GetFuncDesc(f)
            mname = info.GetNames(fd.memid)[0]
            if mname not in target_methods:
                continue

            arg_names = info.GetNames(fd.memid)
            param_names = arg_names[1:] if len(arg_names) > 1 else []

            ret_raw = fd.rettype
            if isinstance(ret_raw, tuple) and len(ret_raw) > 0:
                ret_vt_val = ret_raw[0] if not isinstance(ret_raw[0], tuple) else ret_raw[0][0]
                ret_vt = _vt_name(ret_vt_val)
            else:
                ret_vt = "VOID"

            params = []
            for j, elem in enumerate(fd.args):
                vt_val = elem[0] if not isinstance(elem[0], tuple) else elem[0][0]
                pname = param_names[j] if j < len(param_names) else f"arg{j}"
                params.append({"name": pname, "vt": _vt_name(vt_val), "raw_vt": vt_val})

            result["methods"][mname] = {
                "arity": len(fd.args),
                "return_type": ret_vt,
                "params": params,
                "invkind": fd.invkind,
                "flags": fd.wFuncFlags,
                "memid": fd.memid,
            }
        break

    return result


def _dump_enum(tlb_path: str, target_enums: list[str]) -> dict:
    tlb = pythoncom.LoadTypeLib(tlb_path)
    result: dict = {"tlb_path": str(tlb_path), "enums": {}}

    for i in range(tlb.GetTypeInfoCount()):
        name = tlb.GetDocumentation(i)[0]
        if name not in target_enums:
            continue
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        if ta.typekind != pythoncom.TKIND_ENUM:
            continue
        members = {}
        for v in range(ta.cVars):
            vd = info.GetVarDesc(v)
            mname = info.GetNames(vd.memid)[0]
            members[mname] = vd.value
        result["enums"][name] = members

    return result


def main() -> int:
    pythoncom.CoInitialize()
    try:
        tlb_path = _sw_tlb_path()
        if not tlb_path:
            sys.stderr.write("ERROR: sldworks.tlb not found in registry\n")
            return 1
        sys.stderr.write(f"sldworks.tlb: {tlb_path}\n")

        hem_dump = _dump_funcdesc(
            tlb_path,
            "IFeatureManager",
            ["InsertSheetMetalHem", "InsertSheetMetalHem2"],
        )

        enum_dump = _dump_enum(
            str(SWCONST_TLB),
            ["swHemTypes_e", "swHemPositionTypes_e"],
        )

        report = {
            "sldworks_funcdesc": hem_dump,
            "swconst_enums": enum_dump,
        }

        out_path = Path(__file__).parent / "_results" / "hem_funcdesc_dump.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        sys.stderr.write(f"wrote {out_path}\n")

        sys.stdout.write(json.dumps(report, indent=2, default=str) + "\n")
        return 0

    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
