"""
Find explode step creation method.
"""
import pythoncom
from win32com.client import gencache, GetActiveObject, dynamic
import winreg
import os
import re

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

def find_creation_method():
    pythoncom.CoInitialize()
    try:
        path = _sw_tlb_path()
        tlb = pythoncom.LoadTypeLib(path)
        iid, lcid, _, major, minor = tlb.GetLibAttr()[:5]
        mod = gencache.EnsureModule(str(iid), lcid, major, minor)

        gen_file = mod.__file__
        print(f"Module file: {gen_file}")

        # Search for CreateExplodeStep pattern
        with open(gen_file, "r") as f:
            content = f.read()

        print("\n" + "="*80)
        print("Searching for explode STEP creation methods:")
        print("="*80)

        # Find lines containing CreateExplode or AddExplode
        for match in re.finditer(r".*(CreateExplode|AddExplode|NewExplode|InsertExplode).*", content):
            line = match.group()
            print(f"  {line.strip()}")

        # Also search for GetExplodeStepCount and IGetExplodeStep
        print("\n" + "="*80)
        print("Explode step access methods:")
        print("="*80)
        for match in re.finditer(r".*(GetExplodeStep|IGetExplodeStep).*", content):
            line = match.group()
            print(f"  {line.strip()}")

        # Search for ExplodeDistance setter
        print("\n" + "="*80)
        print("ExplodeDistance property:")
        print("="*80)
        for match in re.finditer(r".*ExplodeDistance.*", content):
            line = match.group()
            print(f"  {line.strip()}")

        # Search for SetComponents on IExplodeStep
        print("\n" + "="*80)
        print("SetComponents method:")
        print("="*80)
        for match in re.finditer(r".*SetComponents.*", content):
            line = match.group()
            if "Explode" in content[max(0, match.start()-100):match.end()+100]:
                print(f"  {line.strip()}")

        # Now runtime probe for creation method on IConfiguration
        print("\n" + "="*80)
        print("Runtime IDispatch probe on Configuration:")
        print("="*80)

        sw = dynamic.Dispatch("SldWorks.Application")
        template = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"
        asm = sw.NewDocument(template, 0, 0, 0)

        if asm:
            model = asm  # dynamic dispatch sees all interfaces
            config = model.GetActiveConfiguration()

            # First create exploded view
            result = asm.CreateExplodedView()
            print(f"  CreateExplodedView() = {result}")

            ev_count = asm.GetExplodedViewCount()
            print(f"  GetExplodedViewCount() = {ev_count}")

            if config:
                # Probe config for explode step creation
                config_methods = [
                    "CreateExplodeStep", "AddExplodeStep", "NewExplodeStep",
                    "InsertExplodeStep", "GetExplodeStepCount", "IGetExplodeStep",
                    "GetFirstExplodeStep", "GetNextExplodeStep",
                    "GetExplodeSteps", "IGetExplodeSteps",
                ]

                print("\n  IConfiguration methods probe:")
                for name in config_methods:
                    try:
                        disp_id = config._oleobj_.GetIDsOfNames(0, name)
                        print(f"    {name}: FOUND, dispid={disp_id}")
                    except pythoncom.com_error as e:
                        if e.hresult == -2147352567:
                            pass

                # Try calling CreateExplodeStep if it exists
                try:
                    disp_id = config._oleobj_.GetIDsOfNames(0, "CreateExplodeStep")
                    print(f"\n  CreateExplodeStep EXISTS! Trying to call...")

                    # Try different argument patterns
                    # Pattern 1: no args
                    try:
                        step = config.CreateExplodeStep()
                        print(f"    CreateExplodeStep() = {step} (type={type(step)})")
                    except Exception as e:
                        print(f"    CreateExplodeStep() error: {e}")

                except pythoncom.com_error:
                    print(f"  CreateExplodeStep NOT FOUND on config")

            # Also check assembly directly for step creation
            asm_step_methods = [
                "CreateExplodeStep", "AddExplodeStep", "NewExplodeStep",
                "InsertExplodeStep", "GetExplodeStepCount", "IGetExplodeStep",
            ]
            print("\n  IAssemblyDoc step methods probe:")
            for name in asm_step_methods:
                try:
                    disp_id = asm._oleobj_.GetIDsOfNames(0, name)
                    print(f"    {name}: FOUND, dispid={disp_id}")
                except pythoncom.com_error:
                    pass

            # Try to create explode step on assembly
            try:
                step = asm.CreateExplodeStep()
                print(f"  asm.CreateExplodeStep() = {step}")
            except Exception as e:
                print(f"  asm.CreateExplodeStep() error: {e}")

            # Try IGetExplodeStep to see if there are existing steps
            try:
                count = asm.GetExplodeStepCount()
                print(f"  asm.GetExplodeStepCount() = {count}")
            except Exception as e:
                print(f"  asm.GetExplodeStepCount() error: {e}")

            sw.CloseDoc(asm.GetTitle())

    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    find_creation_method()