"""
Search for IExplodeStepWizard or alternative explode step creation.
"""
import pythoncom
from win32com.client import gencache, dynamic
import winreg
import re
from pathlib import Path

SW_LIBID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"

def _sw_tlb_path():
    try:
        libk = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"TypeLib")
        libk = winreg.OpenKey(libk, SW_LIBID)
    except:
        return None
    vers, i = [], 0
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

def search_explode_wizard():
    pythoncom.CoInitialize()
    try:
        path = _sw_tlb_path()
        tlb = pythoncom.LoadTypeLib(path)
        iid, lcid, _, major, minor = tlb.GetLibAttr()[:5]
        mod = gencache.EnsureModule(str(iid), lcid, major, minor)

        gen_file = mod.__file__
        print(f"Module: {gen_file}")

        with open(gen_file, "r") as f:
            content = f.read()

        print("\n" + "="*80)
        print("Searching for explode wizard interfaces:")
        print("="*80)

        # Search for Wizard-related classes
        for pattern in ["Wizard", "Explode", "IExplode"]:
            for match in re.finditer(rf"class \w*{pattern}\w*", content):
                print(f"  Found: {match.group()}")

        # Search for CreateExplodeStepWizard or similar methods
        print("\n" + "="*80)
        print("Searching for explode creation methods:")
        print("="*80)

        for pattern in ["CreateExplode", "AddExplode", "InsertExplode", "NewExplode"]:
            for match in re.finditer(rf"def \w*{pattern}\w*", content):
                line = match.group()
                print(f"  Found: {line}")

        # Search for any method that takes explode step args
        print("\n" + "="*80)
        print("Searching for ExplodeStep in vtables:")
        print("="*80)

        for match in re.finditer(r".*ExplodeStep.*", content):
            line = match.group()
            if "vtable" in line.lower() or "InvokeTypes" in line:
                print(f"  {line.strip()}")

        # Check IExplodeStepWizard interface if it exists
        print("\n" + "="*80)
        print("Checking IExplodeStepWizard:")
        print("="*80)

        wizard = getattr(mod, "IExplodeStepWizard", None)
        if wizard:
            print(f"  IExplodeStepWizard EXISTS!")
            if hasattr(wizard, "_methods_"):
                for m in wizard._methods_[:30]:
                    print(f"    {m[0]}")
        else:
            print("  IExplodeStepWizard NOT FOUND")

        # Check ExplodeStep class
        print("\n" + "="*80)
        print("Checking ExplodeStep class:")
        print("="*80)

        es = getattr(mod, "ExplodeStep", None)
        if es:
            print(f"  ExplodeStep class exists")
            if hasattr(es, "_methods_"):
                print(f"  Methods: {len(es._methods_)}")
                for m in es._methods_[:30]:
                    print(f"    {m[0]}")
        else:
            print("  ExplodeStep NOT FOUND")

        # Check if CreateExplodedView returns an object (not just bool)
        # by looking at its vtable signature
        print("\n" + "="*80)
        print("CreateExplodedView signature:")
        print("="*80)

        # Find the signature in IAssemblyDoc
        asm_iface = getattr(mod, "IAssemblyDoc", None)
        if asm_iface and hasattr(asm_iface, "_methods_"):
            for m in asm_iface._methods_:
                if "CreateExplodedView" in m[0]:
                    print(f"  Full sig: {m}")

        # Also check IConfiguration
        config_iface = getattr(mod, "IConfiguration", None)
        if config_iface and hasattr(config_iface, "_methods_"):
            for m in config_iface._methods_:
                if "CreateExplodedView" in m[0] or "AddExplode" in m[0]:
                    print(f"  IConfiguration.{m[0]}: {m}")

        # Check IModelDoc2 for explode-related methods
        model_iface = getattr(mod, "IModelDoc2", None)
        if model_iface and hasattr(model_iface, "_methods_"):
            for m in model_iface._methods_:
                if "Explode" in m[0]:
                    print(f"  IModelDoc2.{m[0]}: {m}")

        # Search for GetExplodedViews pattern
        print("\n" + "="*80)
        print("GetExplodedViews patterns:")
        print("="*80)

        for match in re.finditer(r".*GetExploded.*", content):
            line = match.group()
            print(f"  {line.strip()}")

        # Runtime probe on configuration
        print("\n" + "="*80)
        print("Runtime config probe for step creation:")
        print("="*80)

        sw = dynamic.Dispatch("SldWorks.Application")
        asm_template = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"
        asm = sw.NewDocument(asm_template, 0, 0, 0)

        if asm:
            model = asm  # dynamic sees all interfaces

            # Probe IAssemblyDoc for CreateExplodeStepWizard
            print("\n  IAssemblyDoc methods probe:")
            for method in ["CreateExplodeStepWizard", "CreateExplodeStep", "InsertExplodeStepWizard"]:
                try:
                    dispid = asm._oleobj_.GetIDsOfNames(0, method)
                    print(f"    {method}: FOUND")
                except:
                    print(f"    {method}: NOT FOUND")

            # Probe IModelDoc2
            print("\n  IModelDoc2 methods probe:")
            for method in ["InsertExplodeLineSketch", "FeatureManager"]:
                try:
                    dispid = asm._oleobj_.GetIDsOfNames(0, method)
                    print(f"    {method}: FOUND (dispid={dispid})")
                except:
                    pass

            # Check FeatureManager for explode step creation
            try:
                fm = asm.FeatureManager
                if fm:
                    print(f"\n  FeatureManager: {fm}")
                    for method in ["CreateExplodeStep", "InsertExplodeStep"]:
                        try:
                            dispid = fm._oleobj_.GetIDsOfNames(0, method)
                            print(f"    FeatureManager.{method}: FOUND")
                        except:
                            pass
            except:
                pass

            sw.CloseDoc(asm.GetTitle())

    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    search_explode_wizard()