"""
Find where AddExplodeStep lives - probe IConfiguration.
"""
import pythoncom
from win32com.client import dynamic, gencache, VARIANT
import winreg

SW_LIBID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"

def _sw_tlb_path():
    try:
        libk = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"TypeLib")
        libk = winreg.OpenKey(libk, SW_LIBID)
    except:
        return None
    vers = []
    i = 0
    while True:
        try:
            vers.append(winreg.EnumKey(libk, i))
            i += 1
        except:
            break
    for ver in reversed(vers):
        for arch in ("win64", "win32"):
            try:
                kk = winreg.OpenKey(libk, f"{ver}\\0\\{arch}")
                path, _ = winreg.QueryValueEx(kk, "")
                return path
            except:
                continue
    return None

def find_add_explode_step():
    pythoncom.CoInitialize()
    try:
        path = _sw_tlb_path()
        tlb = pythoncom.LoadTypeLib(path)
        iid, lcid, _, major, minor = tlb.GetLibAttr()[:5]
        mod = gencache.EnsureModule(str(iid), lcid, major, minor)

        gen_file = mod.__file__

        # Search for AddExplodeStep definition and see which class it's in
        with open(gen_file, "r") as f:
            content = f.read()

        # Find AddExplodeStep method and the class it belongs to
        import re
        lines = content.split("\n")

        print("Finding AddExplodeStep method's class:")
        for i, line in enumerate(lines):
            if "def AddExplodeStep" in line:
                # Look backward to find the class
                for j in range(i-1, max(0, i-100), -1):
                    if "class " in lines[j] and "(DispatchBaseClass)" in lines[j]:
                        class_name = lines[j].split("class ")[1].split("(")[0]
                        print(f"  Found in class: {class_name}")
                        print(f"    Line {j}: {lines[j]}")
                        print(f"    Line {i}: {line}")
                        break

        # Also find IExplodeStep_vtables source class
        print("\nFinding IExplodeStep_vtables_ source:")
        for i, line in enumerate(lines):
            if "IExplodeStep_vtables_" in line:
                for j in range(i-1, max(0, i-20), -1):
                    if "class " in lines[j]:
                        class_name = lines[j].split("class ")[1].split("(")[0]
                        print(f"  From class: {class_name}")
                        break
                print(f"    Line {i}: {line[:100]}")
                break

        # Runtime probe on IConfiguration
        print("\nRuntime probe on actual Configuration:")
        sw = dynamic.Dispatch("SldWorks.Application")
        template = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"
        asm = sw.NewDocument(template, 0, 0, 0)

        if asm:
            # Get config via IModelDoc2 (dynamic dispatch sees all interfaces)
            config = asm.GetActiveConfiguration()
            print(f"  Config: {config}")

            if config:
                # Probe for AddExplodeStep
                methods = ["AddExplodeStep", "IAddExplodeStep", "AddExplodeStep2",
                          "CreateExplodeStep", "GetExplodeStepCount", "IGetExplodeStep"]
                print("\n  IConfiguration methods:")
                for name in methods:
                    try:
                        disp_id = config._oleobj_.GetIDsOfNames(0, name)
                        print(f"    {name}: FOUND, dispid={disp_id}")
                    except pythoncom.com_error as e:
                        if e.hresult == -2147352567:
                            print(f"    {name}: NOT FOUND")

                # Try calling AddExplodeStep on config
                try:
                    print("\n  Trying config.AddExplodeStep(0.05, False, False, False)...")
                    step = config.AddExplodeStep(0.05, False, False, False)
                    print(f"    Result: {step} (type={type(step)})")
                except Exception as e:
                    print(f"    Error: {e}")

                # Try IAddExplodeStep
                try:
                    print("\n  Trying config.IAddExplodeStep(0.05, False, False, False)...")
                    step = config.IAddExplodeStep(0.05, False, False, False)
                    print(f"    Result: {step} (type={type(step)})")
                except Exception as e:
                    print(f"    Error: {e}")

            sw.CloseDoc(asm.GetTitle())

    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    find_add_explode_step()