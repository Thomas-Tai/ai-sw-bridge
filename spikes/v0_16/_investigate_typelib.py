"""Read-only investigation: walk sldworks.tlb DIRECTLY (authoritative source)
to find whether the 'missing' members exist in the typelib at all, and on which
interface. This decides whether a makepy regen could ever help.

NO mutation. NO makepy regen. Just reports. Run with the bridge's venv.
"""

from __future__ import annotations

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"

# Members O1 reported MISSING at runtime, and which interface we expected them on.
HUNT = [
    "SetVariableRadiusParameters",
    "VariableRadiusParameters",
    "GetVariableRadiusInstances",
    "SetVariableRadiusInstances",
    "AddVariableRadiusPoint",
    "RadiiCount",
    "FilletType",
    "HoleType",
    "Initialize",
    "Initialize2",
    "GetHoleElementCount",
    "SetHoleElementValue",
]

FOCUS_IFACES = {
    "ISimpleFilletFeatureData2",
    "IVariableFilletFeatureData2",
    "IWizardHoleFeatureData2",
    "IWizardHoleFeatureData",
}


def main() -> None:
    import pythoncom

    tlb = pythoncom.LoadTypeLib(TLB_PATH)
    n = tlb.GetTypeInfoCount()
    libname, libdoc, libctx, libfile = tlb.GetDocumentation(-1)
    la = tlb.GetLibAttr()
    print(f"typelib: {libname} (major={la[3]}, minor={la[4]}, lcid={la[1]})")
    print(f"  {n} type infos")

    # Map member name -> set of interfaces that declare it
    found: dict[str, set[str]] = {h: set() for h in HUNT}
    focus_members: dict[str, list[str]] = {}

    for i in range(n):
        info = tlb.GetTypeInfo(i)
        name, doc, ctx, _f = tlb.GetDocumentation(i)
        ta = info.GetTypeAttr()
        n_funcs = ta.cFuncs
        member_names: list[str] = []
        for f in range(n_funcs):
            try:
                fd = info.GetFuncDesc(f)
                memid = fd.memid
                names = info.GetNames(memid)
                if names:
                    mname = names[0]
                    member_names.append(mname)
                    if mname in found:
                        found[mname].add(name)
            except Exception:
                continue
        if name in FOCUS_IFACES:
            focus_members[name] = sorted(set(member_names))

    print("\n=== HUNT: which typelib interface declares each 'missing' member ===")
    for h in HUNT:
        ifaces = sorted(found[h])
        if ifaces:
            print(f"  {h}: FOUND on {ifaces}")
        else:
            print(f"  {h}: NOT IN TYPELIB ANYWHERE")

    print("\n=== focus interface member dumps ===")
    for iface in sorted(FOCUS_IFACES):
        members = focus_members.get(iface)
        if members is None:
            print(f"  {iface}: NOT FOUND in typelib")
            continue
        print(f"  {iface} ({len(members)} funcs):")
        # print in columns-ish
        line = "      "
        for m in members:
            if len(line) + len(m) + 2 > 100:
                print(line)
                line = "      "
            line += m + ", "
        if line.strip():
            print(line)


if __name__ == "__main__":
    main()
