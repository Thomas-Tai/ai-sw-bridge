"""Read-only: dump the enum members the corrected spikes need. NO mutation."""
from __future__ import annotations

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb"

WANT_ENUMS = {
    "swWzdGeneralHoleTypes_e",
    "swWzdHoleStandards_e",
    "swFilletType_e",
    "swEndConditions_e",
    "swWzdHoleEndTypes_e",
    "swFilletProfileType_e",
}


def main() -> None:
    import pythoncom

    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    n = tlb.GetTypeInfoCount()
    # also fuzzy: any enum whose name contains these tokens
    tokens = ("Wzd", "Fillet", "EndCond")
    dumped = 0
    for i in range(n):
        name, *_ = tlb.GetDocumentation(i)
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        # typekind 4 == TKIND_ENUM
        if ta.typekind != pythoncom.TKIND_ENUM:
            continue
        want = name in WANT_ENUMS or any(t in name for t in tokens)
        if not want:
            continue
        members = []
        for v in range(ta.cVars):
            vd = info.GetVarDesc(v)
            vname = info.GetNames(vd.memid)[0]
            members.append((vname, vd.value))
        print(f"\n{name} ({len(members)}):")
        for vname, val in members:
            print(f"    {vname} = {val}")
        dumped += 1
    if dumped == 0:
        print("no matching enums found")


if __name__ == "__main__":
    main()
