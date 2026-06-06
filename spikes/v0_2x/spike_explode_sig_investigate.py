"""
Investigate exact signatures for explode-related methods from the typelib.
More comprehensive dump.
"""
import pythoncom
from win32com.client import gencache
import winreg

SW_LIBID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"

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

def investigate_signatures():
    pythoncom.CoInitialize()
    try:
        path = _sw_tlb_path()
        print(f"TLB path: {path}")

        tlb = pythoncom.LoadTypeLib(path)
        iid, lcid, _syskind, major, minor = tlb.GetLibAttr()[:5]
        print(f"Version: {major}.{minor}")

        mod = gencache.EnsureModule(str(iid), lcid, major, minor)

        # Check IExplodeStep interface
        print("\n" + "="*80)
        print("IExplodeStep interface:")
        print("="*80)
        explode_step_iface = getattr(mod, "IExplodeStep", None)
        if explode_step_iface and hasattr(explode_step_iface, "_methods_"):
            print(f"  Total methods: {len(explode_step_iface._methods_)}")
            for m in explode_step_iface._methods_:
                print(f"    {m[0]}: {m}")

        # Find IAssemblyDoc interface
        print("\n" + "="*80)
        print("IAssemblyDoc methods 150-160 (around explode):")
        print("="*80)
        asm_iface = getattr(mod, "IAssemblyDoc", None)
        if asm_iface and hasattr(asm_iface, "_methods_"):
            # Look at methods around dispid 155 (CreateExplodedView)
            for i, m in enumerate(asm_iface._methods_):
                # Check around index 150-160 or by dispid
                # m[1] is typically dispid
                if len(m) >= 2:
                    dispid = m[1] if isinstance(m[1], int) else None
                    name = m[0]
                    if name and ("explod" in name.lower() or
                                (dispid and 150 <= dispid <= 160)):
                        print(f"  [{i}] {name}: dispid={dispid}, full={m}")

        # Also search by IDispatch GetIDsOfNames on actual assembly
        print("\n" + "="*80)
        print("Runtime IDispatch probe for explode step creation:")
        print("="*80)

        # Need a running SW instance
        from win32com.client import GetActiveObject
        try:
            sw = GetActiveObject("SldWorks.Application")
            print(f"Got SW: {sw}")

            # Create or open an assembly
            template = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"
            asm = sw.NewDocument(template, 0, 0, 0)
            if asm:
                print(f"Created assembly")

                # Probe for explode step creation methods
                step_methods = [
                    "CreateExplodeStep", "AddExplodeStep", "InsertExplodeStep",
                    "NewExplodeStep", "GetExplodeSteps", "IGetExplodeSteps",
                    "GetExplodeStepCount", "GetFirstExplodeStep", "GetNextExplodeStep",
                ]

                for name in step_methods:
                    try:
                        disp_id = asm._oleobj_.GetIDsOfNames(0, name)
                        if disp_id:
                            print(f"  IAssemblyDoc.{name}: FOUND, dispid={disp_id}")
                    except pythoncom.com_error as e:
                        if e.hresult == -2147352567:
                            print(f"  IAssemblyDoc.{name}: NOT FOUND")

                # Also probe on the configuration
                config = asm.GetActiveConfiguration()
                if config:
                    print("\nIConfiguration probe:")
                    for name in step_methods:
                        try:
                            disp_id = config._oleobj_.GetIDsOfNames(0, name)
                            if disp_id:
                                print(f"  IConfiguration.{name}: FOUND, dispid={disp_id}")
                        except pythoncom.com_error as e:
                            if e.hresult == -2147352567:
                                pass

                # Probe on component for explode-related methods
                # First add a component
                part_template = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT"
                part = sw.NewDocument(part_template, 0, 0, 0)
                if part:
                    # Build minimal part
                    part.InsertSketch2(True)
                    sk = part.SketchManager
                    sk.CreateCornerRectangle(0, 0, 0, 0.01, 0.01, 0)
                    part.InsertSketch2(False)
                    fm = part.FeatureManager
                    fm.FeatureExtrusion2(True, False, False, 0, 0, 0.01, 0.01,
                                        False, False, False, False, 0, 0,
                                        False, False, False, False, False,
                                        True, True, True, 0, 0, False)
                    part_path = r"C:\Users\sky\AppData\Local\Temp\W32ProbePart.SLDPRT"
                    part.SaveAs3(part_path, 0, 0)
                    sw.CloseDoc(part.GetTitle())

                    # Add to assembly
                    sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
                    comp = asm.AddComponent4(part_path, "", 0, 0, 0)

                    if comp:
                        print("\nIComponent2 probe:")
                        comp_methods = ["GetExplodeStep", "SetExplodeStep",
                                       "GetExplodeSteps", "Explode"]
                        for name in comp_methods:
                            try:
                                disp_id = comp._oleobj_.GetIDsOfNames(0, name)
                                if disp_id:
                                    print(f"  IComponent2.{name}: FOUND, dispid={disp_id}")
                            except pythoncom.com_error as e:
                                if e.hresult == -2147352567:
                                    print(f"  IComponent2.{name}: NOT FOUND")

                sw.CloseDoc(asm.GetTitle())
        except Exception as e:
            print(f"Runtime probe error: {e}")

    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    investigate_signatures()