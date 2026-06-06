"""W31 S1 - Dump ALL methods from IDrawingDoc with param signatures.

Full dump without filtering - we need to find ordinate/baseline methods.
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
    9: "DISP",
    10: "ERR",
    11: "BOOL",
    12: "VAR",
    13: "UNK",
    14: "DEC",
}


def decode_vt(tdesc) -> str:
    if tdesc is None:
        return "None"
    vt_type = tdesc[0] if isinstance(tdesc, tuple) else tdesc
    return VT_MAP.get(vt_type, f"T{vt_type}")


def main() -> None:
    import pythoncom

    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    n = tlb.GetTypeInfoCount()

    for i in range(n):
        info = tlb.GetTypeInfo(i)
        name, doc, ctx, _f = tlb.GetDocumentation(i)

        if name != "IDrawingDoc":
            continue

        ta = info.GetTypeAttr()
        print(f"\n=== IDrawingDoc ({ta.cFuncs} methods) ===\n")

        # Dump ALL methods
        for f in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f)
                memid = fd.memid
                names = info.GetNames(memid)
                if names:
                    mname = names[0]
                    param_names = list(names)[1:] if len(names) > 1 else []
                    ret_vt = decode_vt(fd.elemdescFunc.tdesc)
                    params = []
                    for p in fd.args:
                        params.append(decode_vt(p))
                    inv_name = {1: "M", 2: "G", 4: "P"}.get(fd.invkind, str(fd.invkind))

                    # Highlight ordinate/baseline/dim related
                    low = mname.lower()
                    marker = ""
                    if "ord" in low:
                        marker = " **ORD**"
                    elif "base" in low and "flange" not in low:
                        marker = " **BASE**"
                    elif "dim" in low:
                        marker = " **DIM**"

                    pstr = ", ".join(
                        f"{pn}:{pt}" for pn, pt in zip(param_names, params)
                    )
                    print(f"  [{memid}] {inv_name} {mname}({pstr}) -> {ret_vt}{marker}")
            except Exception as e:
                print(f"  ERROR at f={f}: {e}")
                continue


if __name__ == "__main__":
    main()