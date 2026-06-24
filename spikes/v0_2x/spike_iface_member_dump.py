"""Dump full IDrawingDoc member list to check exact names."""

from __future__ import annotations

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"

TARGET_IFACES = ["IDrawingDoc", "IModelDoc2", "IModelDocExtension", "IView"]

VT_MAP = {
    0: "VT_EMPTY",
    3: "VT_I4",
    5: "VT_R8",
    9: "VT_DISPATCH",
    11: "VT_BOOL",
    12: "VT_VARIANT",
}


def decode_vt(vt_tuple) -> str:
    if not vt_tuple:
        return "None"
    vt_type = vt_tuple[0] if isinstance(vt_tuple, tuple) else vt_tuple
    return VT_MAP.get(vt_type, f"VT_{vt_type}")


def main() -> None:
    import pythoncom

    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    n = tlb.GetTypeInfoCount()

    for i in range(n):
        info = tlb.GetTypeInfo(i)
        name, doc, ctx, _f = tlb.GetDocumentation(i)
        if name in TARGET_IFACES:
            print(f"\n=== {name} ===")
            ta = info.GetTypeAttr()
            print(f"  cFuncs: {ta.cFuncs}")
            for f in range(ta.cFuncs):
                try:
                    fd = info.GetFuncDesc(f)
                    memid = fd.memid
                    names = info.GetNames(memid)
                    if names:
                        mname = names[0]
                        # Print all members with "ord" or "base" or "chain" in name
                        lower = mname.lower()
                        if (
                            "ord" in lower
                            or "base" in lower
                            or "chain" in lower
                            or "dim" in lower
                        ):
                            param_count = fd.cParams
                            ret_vt = decode_vt(fd.elemdescFunc.tdesc)
                            param_names = list(names)[1:] if len(names) > 1 else []
                            print(f"    {memid}: {mname}({param_count}) -> {ret_vt}")
                            if param_names:
                                print(f"      params: {param_names}")
                except Exception as e:
                    print(f"    ERROR at f={f}: {e}")
                    continue


if __name__ == "__main__":
    main()
