"""W53 O1 — typelib FUNCDESC probe for IDesignTable / InsertFamilyTableNew.

Offline authoring deliverable: this script introspects the SOLIDWORKS type
library for design-table-related interfaces and dumps their FUNCDESCs
(method signatures, arg types, return types, invoke kinds).

Run on a seat box with pywin32 + SOLIDWORKS installed:

    python spikes/v0_2x/designtable_typelib_probe.py --out _results/designtable_funcdesc.json

The output is the authoritative API map that informs the design-table
handler and seat spike.  No guessing — every method call in the handler
must trace back to a FUNCDESC discovered here (O1 discipline).

Interfaces probed:
  - IDesignTable (the in-file Excel-backed parameter table)
  - IModelDoc2 methods matching *DesignTable* / *FamilyTable*
  - IConfigurationManager (config creation baseline)
  - IConfiguration (per-config property access)

Architecture note: W36 ruled design tables out "by design" due to Excel OLE
modal dialogs/deadlocks.  W53 re-examines: the question is whether
InsertFamilyTableNew (which creates a design table WITHOUT requiring Excel
to be running) can drive N configs from a parameter grid.  The FUNCDESC
dump answers that offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))


VT_NAMES = {
    0: "VT_EMPTY", 1: "VT_NULL", 2: "VT_I2", 3: "VT_I4", 4: "VT_R4",
    5: "VT_R8", 6: "VT_CY", 7: "VT_DATE", 8: "VT_BSTR", 9: "VT_DISPATCH",
    10: "VT_ERROR", 11: "VT_BOOL", 12: "VT_VARIANT", 13: "VT_UNKNOWN",
    14: "VT_DECIMAL", 16: "VT_I1", 17: "VT_UI1", 18: "VT_UI2", 19: "VT_UI4",
    20: "VT_I8", 21: "VT_UI8", 22: "VT_INT", 23: "VT_UINT", 24: "VT_VOID",
    25: "VT_HRESULT", 26: "VT_PTR", 27: "VT_SAFEARRAY", 28: "VT_CARRAY",
    29: "VT_USERDEFINED", 30: "VT_LPSTR", 31: "VT_LPWSTR", 36: "VT_RECORD",
}

INVOKEKIND_NAMES = {
    1: "FUNCTION", 2: "PROPERTYGET", 4: "PROPERTYPUT", 8: "PROPERTYPUTREF",
}

FUNCKIND_NAMES = {
    0: "VIRTUAL", 1: "PUREVIRTUAL", 2: "NONBROWSABLE",
    3: "STATIC", 4: "DISPATCH",
}


def _vt_name(vt: int) -> str:
    base = vt & 0x0FFF
    flags = vt & 0xF000
    name = VT_NAMES.get(base, f"VT_{base}")
    if flags & 0x2000:
        name = f"VT_ARRAY|{name}"
    if flags & 0x4000:
        name = f"VT_BYREF|{name}"
    return name


def _dump_funcdesc(fd: Any) -> dict[str, Any]:
    """Extract a serializable summary from a FUNCDESC."""
    arg_types = []
    for i, elem_desc in enumerate(fd.args):
        vt = elem_desc[0] if isinstance(elem_desc, tuple) else elem_desc
        arg_types.append(_vt_name(vt))

    ret_vt = fd.rettype[0] if isinstance(fd.rettype, tuple) else fd.rettype

    return {
        "memid": fd.memid,
        "func_kind": FUNCKIND_NAMES.get(fd.funckind, str(fd.funckind)),
        "invoke_kind": INVOKEKIND_NAMES.get(fd.invkind, str(fd.invkind)),
        "arg_count": fd.cParams,
        "arg_types": arg_types,
        "return_type": _vt_name(ret_vt),
        "optional_count": getattr(fd, "cParamsOpt", 0),
        "flags": fd.wFuncFlags,
    }


def probe_interface(mod: Any, iface_name: str) -> dict[str, Any]:
    """Dump all FUNCDESCs for a named interface from the gen_py module."""
    cls = getattr(mod, iface_name, None)
    if cls is None:
        return {"error": f"interface {iface_name!r} not in gen_py module"}

    methods: dict[str, list[dict]] = {}
    for attr_name in dir(cls):
        if attr_name.startswith("_"):
            continue
        try:
            attr = getattr(cls, attr_name)
        except Exception:
            continue
        if not callable(attr):
            continue

        func_descs = []
        raw_funcdescs = getattr(attr, "funcdescs", None)
        if raw_funcdescs:
            for fd in raw_funcdescs:
                try:
                    func_descs.append(_dump_funcdesc(fd))
                except Exception:
                    func_descs.append({"error": "dump failed"})

        if func_descs:
            methods[attr_name] = func_descs

    return {"interface": iface_name, "method_count": len(methods), "methods": methods}


def probe_modeldoc2_design_table_methods(mod: Any) -> dict[str, Any]:
    """Find all design-table/family-table methods on IModelDoc2."""
    cls = getattr(mod, "IModelDoc2", None)
    if cls is None:
        return {"error": "IModelDoc2 not in gen_py module"}

    targets = ("designtable", "familytable", "insertfamily", "design_table")
    matches: dict[str, list[dict]] = {}

    for attr_name in dir(cls):
        if attr_name.startswith("_"):
            continue
        lower = attr_name.lower()
        if not any(t in lower for t in targets):
            continue
        try:
            attr = getattr(cls, attr_name)
        except Exception:
            continue
        if not callable(attr):
            continue

        func_descs = []
        raw_funcdescs = getattr(attr, "funcdescs", None)
        if raw_funcdescs:
            for fd in raw_funcdescs:
                try:
                    func_descs.append(_dump_funcdesc(fd))
                except Exception:
                    func_descs.append({"error": "dump failed"})

        if func_descs:
            matches[attr_name] = func_descs

    return {
        "interface": "IModelDoc2",
        "filter": "design_table | family_table | insertfamily",
        "match_count": len(matches),
        "methods": matches,
    }


def run() -> dict[str, Any]:
    """Execute the typelib probe. Returns the full FUNCDESC report."""
    result: dict[str, Any] = {"ok": False, "stage": "init"}

    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
        from win32com.client import gencache
    except ImportError:
        result["error"] = "pywin32 not available (expected on non-Windows/non-seat)"
        return result

    from ai_sw_bridge.com.sw_type_info import SW_TLB_IID

    result["stage"] = "load_module"
    mod = None
    for major in (35, 34, 33, 32, 31, 30):
        try:
            mod = gencache.GetModuleForTypelib(SW_TLB_IID, 0, major, 0)
            if mod:
                result["sw_major"] = major
                break
        except Exception:
            continue

    if mod is None:
        for major in (35, 34, 33, 32, 31, 30):
            try:
                gencache.EnsureModule(SW_TLB_IID, 0, major, 0)
                mod = gencache.GetModuleForTypelib(SW_TLB_IID, 0, major, 0)
                if mod:
                    result["sw_major"] = major
                    break
            except Exception:
                continue

    if mod is None:
        result["error"] = "could not load SW gen_py module"
        return result

    result["module"] = mod.__name__
    result["stage"] = "probe"

    # Probe design table interfaces
    design_table_ifaces = [
        "IDesignTable",
        "IDesignTableFeatureData",
        "IFamilyTable",
        "IFamilyTableFeatureData",
    ]

    result["interfaces"] = {}
    for iface_name in design_table_ifaces:
        probe = probe_interface(mod, iface_name)
        if "error" not in probe:
            result["interfaces"][iface_name] = probe

    # Probe IModelDoc2 for design-table methods
    result["modeldoc2_dt_methods"] = probe_modeldoc2_design_table_methods(mod)

    # Also dump IConfigurationManager for baseline
    result["config_manager"] = probe_interface(mod, "IConfigurationManager")

    # Dump IConfiguration
    result["configuration"] = probe_interface(mod, "IConfiguration")

    # Search ALL interfaces for anything matching design/family table
    result["all_dt_interfaces"] = []
    for name in dir(mod):
        if name.startswith("_"):
            continue
        lower = name.lower()
        if "designtable" in lower or "familytable" in lower:
            result["all_dt_interfaces"].append(name)

    result["ok"] = True
    result["stage"] = "complete"
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--out", type=Path, default=None,
                   help="Write JSON report to path (default: stdout).")
    args = p.parse_args()

    try:
        import pythoncom
        pythoncom.CoInitialize()
    except ImportError:
        pass

    try:
        result = run()
    finally:
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except ImportError:
            pass

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
