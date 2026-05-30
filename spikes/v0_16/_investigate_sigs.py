"""Read-only: dump arg signatures for the REAL creation/setup methods, so the
corrected WizHole + VarFil spikes use exact names/arities. NO mutation."""
from __future__ import annotations

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"

WANT = {
    "ISimpleFilletFeatureData2": [
        "Initialize", "IsMultipleRadius", "SetRadius", "GetRadius", "Type",
        "SetFaces", "DefaultRadius",
    ],
    "IVariableFilletFeatureData2": [
        "SetControlPointRadiusAtIndex", "GetControlPointsCount",
        "FilletEdgeCount", "GetFilletEdgeAtIndex", "TransitionType",
        "SetRadius", "GetRadius",
    ],
    "IWizardHoleFeatureData2": [
        "InitializeHole", "ChangeStandard", "Standard2", "FastenerType2",
        "Diameter", "Depth", "EndCondition",
    ],
}

# VT enum -> short name (partial)
VT = {
    0: "void", 2: "i2", 3: "i4", 4: "r4", 5: "r8", 7: "date", 8: "bstr",
    11: "bool", 12: "variant", 13: "unknown", 9: "dispatch", 16: "i1",
    17: "ui1", 18: "ui2", 19: "ui4", 22: "int", 23: "uint", 24: "void",
    26: "ptr", 28: "..", 36: "userdef",
}


def vts(t) -> str:
    # t may be int or tuple (for pointers)
    if isinstance(t, tuple):
        base = t[0]
        return VT.get(base, f"vt{base}") + "*"
    return VT.get(t, f"vt{t}")


def main() -> None:
    import pythoncom

    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    n = tlb.GetTypeInfoCount()
    want_ifaces = set(WANT)

    for i in range(n):
        name, *_ = tlb.GetDocumentation(i)
        if name not in want_ifaces:
            continue
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        wanted = set(WANT[name])
        print(f"\n=== {name} ===")
        for f in range(ta.cFuncs):
            try:
                fd = info.GetFuncDesc(f)
                names = info.GetNames(fd.memid)
            except Exception:
                continue
            if not names or names[0] not in wanted:
                continue
            mname = names[0]
            argnames = names[1:]
            # invkind: 1=func 2=propget 4=propput
            kind = {1: "method", 2: "get", 4: "put", 8: "putref"}.get(fd.invkind, str(fd.invkind))
            args = fd.args  # list of (vt, flags, default, ...)
            sig_parts = []
            for j, a in enumerate(args):
                avt = a[0]
                an = argnames[j] if j < len(argnames) else f"arg{j}"
                sig_parts.append(f"{an}:{vts(avt)}")
            ret = vts(fd.rettype[0]) if fd.rettype else "?"
            print(f"  [{kind}] {mname}({', '.join(sig_parts)}) -> {ret}")


if __name__ == "__main__":
    main()
