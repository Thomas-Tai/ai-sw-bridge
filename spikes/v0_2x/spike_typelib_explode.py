"""
T6 typelib dump for explode-related methods on IAssemblyDoc and IConfiguration.
Simple runtime IDispatch probe approach.
"""
import pythoncom
from win32com.client import GetActiveObject, Dispatch
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def dump_explode_methods():
    """Dump IAssemblyDoc and IConfiguration members matching explod* via runtime probe."""
    pythoncom.CoInitialize()
    try:
        # Get running SW instance
        sw_app = GetActiveObject("SldWorks.Application")
        print(f"Got SW application: {sw_app}")

        repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        temp_dir = os.path.join(repo_dir, "spikes", "v0_2x", "_temp_W32")
        os.makedirs(temp_dir, exist_ok=True)

        part1_path = os.path.join(temp_dir, "Cube1.SLDPRT")
        part2_path = os.path.join(temp_dir, "Cube2.SLDPRT")
        asm_path = os.path.join(temp_dir, "ExplodeTest.SLDASM")

        # Create parts and assembly using W8 proven pipeline
        # OpenDoc6 pre-open → AddComponent4

        print("\n=== Creating test fixtures ===")

        # Create part1 - use OpenDoc6 with swOpenDocOptions_New
        # swDocPART = 1, swOpenDocOptions_New = 256, swOpenDocOptions_Silent = 1
        print(f"Creating part1...")
        part1 = sw_app.OpenDoc6("", 1, 256, "", 0, 0)  # Create new empty part
        if part1:
            print(f"  Created empty part1")
            # Add a simple box extrude for geometry
            # Use SketchManager to create a sketch and extrude
            try:
                # Insert a sketch
                part1.InsertSketch2(True)
                # Get SketchManager
                sk_mgr = part1.SketchManager
                # Create rectangle
                sk_mgr.CreateCornerRectangle(0, 0, 0, 0.01, 0.01, 0)  # 10mm square
                # Exit sketch
                part1.InsertSketch2(False)
                # Get FeatureManager
                fm = part1.FeatureManager
                # Extrude the sketch
                # FeatureExtrusion2 parameters: swExtrudeFromSketchPlane=0, etc
                extrude = fm.FeatureExtrusion2(True, False, False, 0, 0, 0.01, 0.01, False, False, False, False, 0, 0, False, False, False, False, False, True, True, True, 0, 0, False)
                print(f"  Extruded box: {extrude}")
            except Exception as e:
                print(f"  Extrude error: {e} (continuing with empty part)")

            part1.SaveAs3(part1_path, 0, 0)
            print(f"  Saved: {part1_path}")
            sw_app.CloseDoc(part1.GetTitle())
        else:
            print(f"  Failed to create part1")

        # Create part2 (copy of part1)
        if os.path.exists(part1_path):
            import shutil
            shutil.copy(part1_path, part2_path)
            print(f"  Created part2 (copy of part1)")

        # Create assembly with 2 components
        print(f"\nCreating assembly...")
        asm = sw_app.OpenDoc6("", 2, 256, "", 0, 0)  # Create new empty assembly, swDocASSEMBLY=2
        if asm:
            print(f"  Created empty assembly")

            # W8 pipeline: OpenDoc6 pre-open parts
            sw_app.OpenDoc6(part1_path, 1, 1, "", 0, 0)  # Pre-open part1
            sw_app.OpenDoc6(part2_path, 1, 1, "", 0, 0)  # Pre-open part2

            # AddComponent4 to place components
            comp1 = asm.AddComponent4(part1_path, "", 0, 0, 0)  # Origin
            comp2 = asm.AddComponent4(part2_path, "", 0.02, 0, 0)  # 20mm offset in X
            print(f"  comp1: {comp1}")
            print(f"  comp2: {comp2}")

            # Save assembly
            asm.SaveAs3(asm_path, 0, 0)
            print(f"  Saved: {asm_path}")

            # === NOW PROBE FOR EXPLODE METHODS ===
            print("\n" + "="*80)
            print("IAssemblyDoc GetIDsOfNames probe (explode-related):")
            print("="*80)

            test_names = [
                # Possible creation methods
                "NewExplodedView", "CreateExplodeStep", "CreateExplodedView",
                "InsertExplodeStep", "AddExplodeStep", "CreateExplodeStepWizard",
                # Possible access methods
                "GetExplodedViews", "GetExplodedViewCount", "IGetExplodedViews",
                "GetFirstExplodedView", "GetNextExplodedView", "GetExplodedView2",
                "GetExplodeSteps", "GetExplodeStepCount", "IGetExplodeSteps",
                # Toggle methods
                "ShowExploded", "ShowExploded2", "IsExploded",
                # Delete/edit
                "DeleteExplodedView", "EditExplodedView",
            ]

            asm_found = []
            asm_not_found = []

            for name in test_names:
                try:
                    disp_id = asm._oleobj_.GetIDsOfNames(0, name)
                    if disp_id:
                        asm_found.append((name, disp_id))
                        print(f"  {name}: FOUND, dispid={disp_id}")
                except pythoncom.com_error as e:
                    if e[0] == -2147352567:  # DISP_E_UNKNOWNNAME
                        asm_not_found.append(name)

            print(f"\n  NOT FOUND on IAssemblyDoc: {asm_not_found}")

            # Probe IConfiguration
            config = asm.GetActiveConfiguration()
            if config:
                print("\n" + "="*80)
                print("IConfiguration GetIDsOfNames probe (explode-related):")
                print("="*80)

                config_found = []
                config_not_found = []

                for name in test_names:
                    try:
                        disp_id = config._oleobj_.GetIDsOfNames(0, name)
                        if disp_id:
                            config_found.append((name, disp_id))
                            print(f"  {name}: FOUND, dispid={disp_id}")
                    except pythoncom.com_error as e:
                        if e[0] == -2147352567:
                            config_not_found.append(name)

                # Additional config-specific names to probe
                additional_names = [
                    "HasExplodedView", "GetExplodedViews2", "GetExplodedView",
                    "AddExplodeStep2", "CreateExplodeStep", "ExplodeStepCount",
                ]
                for name in additional_names:
                    try:
                        disp_id = config._oleobj_.GetIDsOfNames(0, name)
                        if disp_id:
                            config_found.append((name, disp_id))
                            print(f"  {name}: FOUND, dispid={disp_id}")
                    except pythoncom.com_error as e:
                        if e[0] == -2147352567:
                            config_not_found.append(name)

                print(f"\n  NOT FOUND on IConfiguration: {config_not_found}")

            # Summary
            print("\n" + "="*80)
            print("SUMMARY - Available explode-related APIs:")
            print("="*80)
            print(f"IAssemblyDoc FOUND: {len(asm_found)}")
            for name, dispid in asm_found:
                print(f"  - {name} (dispid={dispid})")
            print(f"\nIConfiguration FOUND: {len(config_found)}")
            for name, dispid in config_found:
                print(f"  - {name} (dispid={dispid})")

            sw_app.CloseDoc(asm.GetTitle())

        else:
            print("  Failed to create assembly")

        print("\n=== Typelib dump complete ===")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    dump_explode_methods()