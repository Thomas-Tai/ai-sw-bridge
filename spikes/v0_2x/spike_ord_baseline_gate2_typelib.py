"""W31v2 T6 - Comprehensive signature dump for ALL IDrawingDoc dim-related methods.

NO mutation. Just reports what the typelib declares for these APIs.
"""
from __future__ import annotations

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"

# All dim-related methods found in IDrawingDoc dump
ALL_TARGETS = [
    # Ordinate
    "AddOrdinateDimension",
    "AddOrdinateDimension2",
    "InsertOrdinate",
    "InsertHorizontalOrdinate",
    "InsertVerticalOrdinate",
    "CreateOrdinateDim",
    "CreateOrdinateDim2",
    "CreateOrdinateDim3",
    "CreateOrdinateDim4",
    "ICreateOrdinateDim",
    "ICreateOrdinateDim2",
    "ICreateOrdinateDim3",
    "ICreateOrdinateDim4",
    # Baseline/Chain
    "InsertBaseDim",
    "InsertChainDim",
    "InsertAngularRunningDim",
    # Other CreateDim family (for comparison)
    "CreateAngDim",
    "CreateAngDim2",
    "CreateAngDim3",
    "CreateAngDim4",
    "CreateLinearDim",
    "CreateLinearDim2",
    "CreateLinearDim3",
    "CreateLinearDim4",
    "CreateDiamDim",
    "CreateDiamDim2",
    "CreateDiamDim3",
    "CreateDiamDim4",
]

VT_MAP = {
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
    22: "VT_I4|VT_ARRAY",
    23: "VT_I2|VT_ARRAY",
    8192: "VT_ARRAY",
    8200: "VT_ARRAY|VT_BSTR",
}


def decode_vt(vt_tuple) -> str:
    """Decode a VT tuple to a human-readable string."""
    if not vt_tuple:
        return "None"
    vt_type = vt_tuple[0]
    vt_flags = vt_tuple[1] if len(vt_tuple) > 1 else 0
    name = VT_MAP.get(vt_type, f"VT_{vt_type}")
    if vt_flags:
        flags_name = VT_MAP.get(vt_flags, f"flags_{vt_flags}")
        name += f"({flags_name})"
    return name


def main() -> None:
    import pythoncom

    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    n = tlb.GetTypeInfoCount()

    # Map member name -> list of (interface, signature)
    found_methods: dict[str, list[tuple[str, dict]]] = {}

    for i in range(n):
        info = tlb.GetTypeInfo(i)
        name, doc, ctx, _f = tlb.GetDocumentation(i)
        ta = info.GetTypeAttr()
        for f in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f)
                memid = fd.memid
                names = info.GetNames(memid)
                if names:
                    mname = names[0]
                    if mname in ALL_TARGETS:
                        # Build signature dict
                        sig = {
                            "interface": name,
                            "memid": memid,
                            "invoke_kind": fd.invkind,  # 1=func, 2=propget, 4=propput
                            "param_count": fd.cParams,
                            "params": [],
                            "param_names": list(names)[1:] if len(names) > 1 else [],
                            "return_vt": decode_vt(fd.elemdescFunc.tdesc),
                        }
                        # Decode each param
                        for p_idx, param_desc in enumerate(fd.args):
                            vt = decode_vt(param_desc[0] if param_desc else None)
                            sig["params"].append(vt)
                        if mname not in found_methods:
                            found_methods[mname] = []
                        found_methods[mname].append((name, sig))
            except Exception as e:
                continue

    print("=== FOUND METHOD SIGNATURES ===\n")
    for mname in sorted(found_methods.keys()):
        results = found_methods[mname]
        for iface, sig in results:
            inv_kind = sig["invoke_kind"]
            inv_name = {1: "METHOD", 2: "PROPGET", 4: "PROPPUT"}.get(inv_kind, f"inv_{inv_kind}")
            print(f"{iface}.{mname}:")
            print(f"  memid: {sig['memid']}")
            print(f"  kind: {inv_name}")
            print(f"  params: {sig['param_count']}")
            print(f"  param_types: {sig['params']}")
            print(f"  param_names: {sig['param_names']}")
            print(f"  return: {sig['return_vt']}")
            print()


if __name__ == "__main__":
    main()