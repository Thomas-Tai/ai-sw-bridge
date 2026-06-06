"""
Deep investigation of explode-related APIs using makepy direct module access.
"""
import pythoncom
from win32com.client import gencache, GetActiveObject, dynamic
import winreg
import os

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

def investigate():
    pythoncom.CoInitialize()
    try:
        path = _sw_tlb_path()
        tlb = pythoncom.LoadTypeLib(path)
        iid, lcid, _, major, minor = tlb.GetLibAttr()[:5]

        mod = gencache.EnsureModule(str(iid), lcid, major, minor)
        print(f"Module: {mod}")
        print(f"Module file: {mod.__file__}")

        # List all attributes in the module
        print("\n" + "="*80)
        print("All module attributes containing 'Explode' or 'Explod':")
        print("="*80)

        for name in sorted(dir(mod)):
            if "explode" in name.lower() or "explod" in name.lower():
                obj = getattr(mod, name, None)
                print(f"  {name}: {obj}")

        # Also look for lowercase versions
        print("\nSearching for any explode-related classes:")
        for name in sorted(dir(mod)):
            obj = getattr(mod, name, None)
            if obj and hasattr(obj, "__name__"):
                if "explod" in obj.__name__.lower():
                    print(f"  {name}: {obj}")

        # Check the generated module source directly for explode methods
        gen_file = mod.__file__
        if os.path.exists(gen_file):
            print(f"\n" + "="*80)
            print(f"Scanning generated module source for 'Explod':")
            print("="*80)
            with open(gen_file, "r") as f:
                content = f.read()

            # Find lines containing Explod
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "Explod" in line or "explod" in line.lower():
                    # Print context
                    start = max(0, i-2)
                    end = min(len(lines), i+3)
                    for j in range(start, end):
                        marker = ">>>" if j == i else "   "
                        print(f"{marker} {lines[j]}")
                    print()

        # Runtime probe using dynamic dispatch (not early bound)
        print("\n" + "="*80)
        print("Runtime IDispatch probe (dynamic dispatch):")
        print("="*80)

        sw = dynamic.Dispatch("SldWorks.Application")
        print(f"SW (dynamic): {sw}")

        # Create assembly using dynamic dispatch
        template = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"

        # Use ISldWorks.NewDocument
        asm = sw.NewDocument(template, 0, 0, 0)
        print(f"Assembly (dynamic): {asm}")

        if asm:
            # Get config via IModelDoc2
            model = asm  # Same object, different interface view
            config = model.GetActiveConfiguration()
            print(f"Config: {config}")

            # Probe explode methods on assembly
            asm_methods = [
                "CreateExplodedView", "ShowExploded", "ShowExploded2",
                "GetExplodedViewCount", "IGetExplodedViews", "GetFirstExplodedView",
                "CreateExplodeStep", "AddExplodeStep", "InsertExplodeStep",
            ]

            print("\nAssembly IDispatch probe:")
            for name in asm_methods:
                try:
                    disp_id = asm._oleobj_.GetIDsOfNames(0, name)
                    print(f"  {name}: dispid={disp_id}")
                except pythoncom.com_error as e:
                    if e.hresult == -2147352567:
                        print(f"  {name}: NOT FOUND")

            # Probe on config
            if config:
                print("\nConfiguration IDispatch probe:")
                config_methods = [
                    "GetExplodedViews", "GetExplodedView", "GetExplodedViews2",
                    "CreateExplodedView", "AddExplodeStep", "GetExplodeSteps",
                    "GetExplodeStepCount", "IGetExplodeSteps", "GetFirstExplodeStep",
                    "ShowExploded", "ShowExploded2",
                ]
                for name in config_methods:
                    try:
                        disp_id = config._oleobj_.GetIDsOfNames(0, name)
                        print(f"  {name}: dispid={disp_id}")
                    except pythoncom.com_error as e:
                        if e.hresult == -2147352567:
                            print(f"  {name}: NOT FOUND")

            # Try calling CreateExplodedView
            print("\n" + "="*80)
            print("Calling CreateExplodedView on assembly:")
            print("="*80)

            try:
                result = asm.CreateExplodedView()
                print(f"  CreateExplodedView() returned: {result} (type={type(result)})")

                # Now check if there's an exploded view
                ev_count = asm.GetExplodedViewCount()
                print(f"  GetExplodedViewCount(): {ev_count}")

                if ev_count > 0:
                    # Try to get the exploded view
                    # IGetExplodedViews or GetFirstExplodedView?
                    try:
                        views = asm.IGetExplodedViews(ev_count)
                        print(f"  IGetExplodedViews({ev_count}): {views}")
                    except Exception as e:
                        print(f"  IGetExplodedViews error: {e}")

                    try:
                        first_view = asm.GetFirstExplodedView()
                        print(f"  GetFirstExplodedView(): {first_view}")
                        if first_view:
                            # Probe this view object for step methods
                            print("\n  ExplodedView object methods:")
                            for name in ["AddExplodeStep", "GetExplodeStepCount",
                                        "GetFirstExplodeStep", "IGetExplodeSteps"]:
                                try:
                                    disp_id = first_view._oleobj_.GetIDsOfNames(0, name)
                                    print(f"    {name}: dispid={disp_id}")
                                except pythoncom.com_error as e:
                                    if e.hresult == -2147352567:
                                        print(f"    {name}: NOT FOUND")
                    except Exception as e:
                        print(f"  GetFirstExplodedView error: {e}")

            except Exception as e:
                print(f"  CreateExplodedView error: {e}")

            # Cleanup
            sw.CloseDoc(asm.GetTitle())

    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    investigate()