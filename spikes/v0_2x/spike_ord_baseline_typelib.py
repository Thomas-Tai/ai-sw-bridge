"""W31 S1 - Investigate typelib for ordinate/baseline dimension methods.

NO mutation. Just reports what the typelib declares for these APIs.
Run with the bridge's venv.
"""
from __future__ import annotations

TLB_PATH = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"

# Hunt targets - ordinate/baseline dimension method candidates
HUNT_ORDINATE = [
    "AddOrdinateDimension",
    "AddOrdinateDimension2",
    "InsertOrdinateDimension",
    "InsertOrdinateDimension2",
    "SetOrdinateDimensionOrigin",
]

HUNT_BASELINE = [
    "InsertBaselineDimension",
    "InsertBaselineDimension2",
    "AddBaselineDimension",
    "SetBaselineDimension",
]

FOCUS_IFACES = {
    "IDrawingDoc",
    "IModelDoc2",
    "IModelDocExtension",
    "IView",
    "IDisplayDimension",
    "IDimension",
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
    found_ordinate: dict[str, set[str]] = {h: set() for h in HUNT_ORDINATE}
    found_baseline: dict[str, set[str]] = {h: set() for h in HUNT_BASELINE}
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
                    if mname in found_ordinate:
                        found_ordinate[mname].add(name)
                    if mname in found_baseline:
                        found_baseline[mname].add(name)
            except Exception:
                continue
        if name in FOCUS_IFACES:
            focus_members[name] = sorted(set(member_names))

    print("\n=== ORDINATE candidates ===")
    for h in HUNT_ORDINATE:
        ifaces = sorted(found_ordinate[h])
        if ifaces:
            print(f"  {h}: FOUND on {ifaces}")
        else:
            print(f"  {h}: NOT IN TYPELIB ANYWHERE")

    print("\n=== BASELINE candidates ===")
    for h in HUNT_BASELINE:
        ifaces = sorted(found_baseline[h])
        if ifaces:
            print(f"  {h}: FOUND on {ifaces}")
        else:
            print(f"  {h}: NOT IN TYPELIB ANYWHERE")

    # Now dump the actual method signatures for any found methods
    print("\n=== Method signatures ===")
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
                    if mname in found_ordinate or mname in found_baseline:
                        if found_ordinate.get(mname) or found_baseline.get(mname):
                            # Dump the full signature
                            vt_in = fd.args[0] if fd.args else []
                            vt_out = fd.args[1] if len(fd.args) > 1 else []
                            inv_kind = fd.invkind  # 1=func, 2=propget, 4=propput
                            print(f"\n  {name}.{mname}:")
                            print(f"    memid: {memid}")
                            print(f"    invoke: {inv_kind} (1=func,2=get,4=put)")
                            print(f"    args VT: {list(fd.args)}")
                            print(f"    return VT: {fd.elemdescFunc.tdesc}")
                            print(f"    names: {names}")
            except Exception as e:
                continue

    print("\n=== IDrawingDoc full member dump (filtering dim-related) ===")
    if "IDrawingDoc" in focus_members:
        members = focus_members["IDrawingDoc"]
        dim_related = [m for m in members if "dim" in m.lower() or "dim" in m.lower() or "ord" in m.lower() or "base" in m.lower()]
        print(f"  ({len(dim_related)} dim-related): {dim_related}")

    print("\n=== IModelDoc2 full member dump (filtering dim-related) ===")
    if "IModelDoc2" in focus_members:
        members = focus_members["IModelDoc2"]
        dim_related = [m for m in members if "dim" in m.lower() or "ord" in m.lower() or "base" in m.lower()]
        print(f"  ({len(dim_related)} dim-related): {dim_related}")


if __name__ == "__main__":
    main()