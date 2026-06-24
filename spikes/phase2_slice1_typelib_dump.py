"""Phase-2 Slice 1: Empirical typelib verification for mate types.

Tests CreateMateData(type) with candidate enum values to verify swMateType_e.
Anchors on COINCIDENT=0 (Phase-1 proven).
"""

import sys
import os

sys.path.insert(0, r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\aisw-W10\src")

import json
import win32com.client
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.com.earlybind import typed, typed_qi

mod = wrapper_module()

print("=" * 70)
print("Phase-2 Slice 1: Empirical Typelib Verification")
print("=" * 70)

# Candidate enum values from SolidWorks API documentation
candidate_enums = {
    "swMateCOINCIDENT": 0,
    "swMateCONCENTRIC": 1,
    "swMatePERPENDICULAR": 2,
    "swMatePARALLEL": 3,
    "swMateTANGENT": 4,
    "swMateDISTANCE": 5,
    "swMateANGLE": 6,
}

print("\n[1] Testing CreateMateData with candidate enum values...")

sw = win32com.client.Dispatch("SldWorks.Application")

# Create test assembly
asm_template = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"
if not os.path.exists(asm_template):
    import glob

    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    if not asm_templates:
        print("ERROR: No assembly template found")
        sys.exit(1)
    asm_template = asm_templates[0]
asm_doc = sw.NewDocument(asm_template, 0, 0.1, 0.1)

if asm_doc is None:
    print("ERROR: Failed to create assembly document")
    sys.exit(1)

try:
    # Cast to IAssemblyDoc (not IModelDoc2) — CreateMateData is on IAssemblyDoc
    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    verified_enums = {}
    typed_interfaces = {}

    for name, val in candidate_enums.items():
        print(f"\n  Testing {name} = {val}...")
        try:
            mate_data = typed_asm.CreateMateData(val)
            if mate_data is None:
                print(f"    CreateMateData({val}) returned None")
                verified_enums[name] = {"value": val, "works": False}
                continue

            # Check if it's a valid COM object by trying to access a base property
            try:
                mfd = typed_qi(mate_data, "IMateFeatureData", module=mod)
                _ = mfd.MateAlignment  # base property on all mate data
                print(f"    CreateMateData({val}) succeeded")
                verified_enums[name] = {"value": val, "works": True}

                # Try to find typed interface
                mate_type = name.replace("swMate", "")
                interface_name = f"I{mate_type.capitalize()}MateFeatureData"

                try:
                    typed_mate = typed_qi(mate_data, interface_name, module=mod)

                    # List key properties
                    props = [
                        p
                        for p in dir(typed_mate)
                        if not p.startswith("_")
                        and not p.startswith("I")
                        and p not in ("MateAlignment", "EntitiesToMate", "ErrorStatus")
                    ]
                    key_props = [
                        p
                        for p in props
                        if any(
                            kw in p.lower()
                            for kw in [
                                "distance",
                                "angle",
                                "align",
                                "lock",
                                "flip",
                                "abs",
                                "limit",
                            ]
                        )
                    ]

                    print(f"    Typed interface: {interface_name}")
                    print(
                        f"    Key properties: {', '.join(key_props[:8]) if key_props else '(none)'}"
                    )

                    typed_interfaces[name] = {
                        "interface": interface_name,
                        "properties": key_props[:10],
                        "path": "typed",
                    }
                except Exception:
                    print(f"    No typed interface (use base IMateFeatureData)")
                    typed_interfaces[name] = {"interface": None, "path": "base"}

            except Exception as e:
                print(f"    CreateMateData({val}) returned non-mate object: {e}")
                verified_enums[name] = {"value": val, "works": False, "error": str(e)}

        except Exception as e:
            print(f"    CreateMateData({val}) raised: {e}")
            verified_enums[name] = {"value": val, "works": False, "error": str(e)}

    # Verify anchor
    print("\n" + "=" * 70)
    print("Anchor Verification:")
    print("=" * 70)
    if verified_enums.get("swMateCOINCIDENT", {}).get("value") == 0:
        if verified_enums["swMateCOINCIDENT"].get("works"):
            print("ANCHOR VERIFIED: swMateCOINCIDENT = 0, CreateMateData(0) works")
        else:
            print("ANCHOR FAILED: swMateCOINCIDENT = 0 but CreateMateData(0) failed")
            sys.exit(1)
    else:
        print("ANCHOR FAILED: swMateCOINCIDENT != 0")
        sys.exit(1)

    # Summary
    print("\n" + "=" * 70)
    print("Summary — Verified Enum Values:")
    print("=" * 70)
    for name, info in verified_enums.items():
        status = "OK" if info.get("works") else "FAILED"
        print(f"  {name:25} = {info['value']}  [{status}]")

    print("\n" + "=" * 70)
    print("Summary — Interface Paths:")
    print("=" * 70)
    for name, info in typed_interfaces.items():
        path = info.get("path", "unknown")
        iface = info.get("interface", "base IMateFeatureData")
        print(f"  {name:25} -> {path:6} path via {iface}")

    # Save findings
    findings = {
        "swMateType_e": {
            name: info["value"]
            for name, info in verified_enums.items()
            if info.get("works")
        },
        "anchor_verified": verified_enums.get("swMateCOINCIDENT", {}).get(
            "works", False
        ),
        "interfaces": typed_interfaces,
        "all_candidates": candidate_enums,
    }

    findings_path = r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\aisw-W10\spikes\phase2_typelib_mate_types.json"
    with open(findings_path, "w") as f:
        json.dump(findings, f, indent=2)

    print(f"\nFindings saved to {findings_path}")

finally:
    title = asm_doc.GetTitle()
    sw.CloseDoc(title)

print("\nSlice 1 complete.")
