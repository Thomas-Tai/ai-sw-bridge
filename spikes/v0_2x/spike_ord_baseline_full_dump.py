"""W31 S1 - Dump ALL dim-related methods from IDrawingDoc and IModelDoc2.

Comprehensive search, not filtered by exact name match.
"""

from __future__ import annotations

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"

VT_MAP = {
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
    14: "DECIMAL",
}

TARGET_IFACES = ["IDrawingDoc", "IModelDoc2", "IModelDocExtension", "IView"]


def decode_vt(vt_tuple) -> str:
    if not vt_tuple:
        return "None"
    vt_type = vt_tuple[0] if isinstance(vt_tuple, tuple) else vt_tuple
    return VT_MAP.get(vt_type, f"VT{vt_type}")


def main() -> None:
    import pythoncom

    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    n = tlb.GetTypeInfoCount()

    for i in range(n):
        info = tlb.GetTypeInfo(i)
        name, doc, ctx, _f = tlb.GetDocumentation(i)

        if name not in TARGET_IFACES:
            continue

        ta = info.GetTypeAttr()
        print(f"\n=== {name} (memid range) ===")

        # Collect dim-related methods
        dim_methods = []
        for f in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f)
                memid = fd.memid
                names = info.GetNames(memid)
                if names:
                    mname = names[0]
                    # Filter for dim-related (ord, base, dim)
                    low = mname.lower()
                    if "dim" in low or "ord" in low or "base" in low:
                        param_names = list(names)[1:] if len(names) > 1 else []
                        ret_vt = decode_vt(fd.elemdescFunc.tdesc)
                        params = []
                        for p in fd.args:
                            params.append(decode_vt(p))
                        dim_methods.append(
                            {
                                "name": mname,
                                "memid": memid,
                                "inv": fd.invkind,
                                "params": params,
                                "pnames": param_names,
                                "ret": ret_vt,
                            }
                        )
            except Exception:
                continue

        # Print dim-related methods
        for m in dim_methods:
            inv_name = {1: "M", 2: "G", 4: "P"}.get(m["inv"], str(m["inv"]))
            pstr = ", ".join(f"{pn}:{pt}" for pn, pt in zip(m["pnames"], m["params"]))
            if len(m["params"]) > len(m["pnames"]):
                for idx in range(len(m["pnames"]), len(m["params"])):
                    pstr += f", arg{idx}:{m['params'][idx]}"
            print(f"  [{m['memid']}] {inv_name} {m['name']}({pstr}) -> {m['ret']}")


if __name__ == "__main__":
    main()
