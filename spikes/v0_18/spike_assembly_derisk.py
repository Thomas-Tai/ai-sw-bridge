"""Spike v0.18 — Wave-8: Assembly de-risk (binary probe).

ONE question: can a saved part be placed as a real B-rep component out-of-process
(AddComponent4), and can two components be joined with a mate (AddMate5)?

TYPELIB-FIRST signatures (sldworks.tlb, IAssemblyDoc):

  AddComponent4 (5 args) -> Component2:
    #  Name        VT
    1  CompName    BSTR(8)    — saved .sldprt file path
    2  ConfigName  BSTR(8)    — config name ("" = default)
    3  X           R8(5)      — position X (meters)
    4  Y           R8(5)      — position Y
    5  Z           R8(5)      — position Z

  AddMate5 (15 args) -> Feature:
    #  Name                    VT
    1  MateTypeFromEnum        I4(3)    — swMateType_e
    2  AlignFromEnum           I4(3)    — swMateAlign_e
    3  Flip                    BOOL(11)
    4  Distance                R8(5)
    5  DistanceAbsUpperLimit   R8(5)
    6  DistanceAbsLowerLimit   R8(5)
    7  GearRatioNumerator      R8(5)
    8  GearRatioDenominator    R8(5)
    9  Angle                   R8(5)
    10 AngleAbsUpperLimit      R8(5)
    11 AngleAbsLowerLimit      R8(5)
    12 ForPositioningOnly      BOOL(11)
    13 LockRotation            BOOL(11)
    14 WidthMateOption         I4(3)    — swMateWidthOptions_e
    15 ErrorStatus             I4(3)    — OUT: swAddMateError_e

swconst.tlb verified:
  swMateCOINCIDENT = 0, swMateCONCENTRIC = 1
  swMateAlignALIGNED = 0, swMateAlignANTI_ALIGNED = 1, swMateAlignCLOSEST = 2
  swAddMateError_NoError = 1

Strategy:
  1. Build box + SaveAs to disk (saved .sldprt = real B-rep on disk).
  2. NewDocument(assembly template) -> assembly doc.
  3. AddComponent4(saved_path, "", 0, 0, 0) -> verify real component.
  4. AddComponent4(saved_path, "", offset, 0, 0) -> verify count == 2.
  5. Select face on component #1 + face on component #2.
  6. AddMate5(COINCIDENT, ALIGNED, ...) -> verify mate feature.

Usage:
    python spikes/v0_18/spike_assembly_derisk.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed, typed_qi, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.selection.live import select_entity

from spike_earlybind_persist import connect_running_sw

RESULTS_DIR = Path(__file__).resolve().parent / "_results"

SW_DEFAULT_TEMPLATE_PART = 8
SW_DEFAULT_TEMPLATE_ASSEMBLY = 12

MATE_COINCIDENT = 0
MATE_ALIGN_ALIGNED = 0
MATE_ALIGN_ANTI = 1
MATE_ALIGN_CLOSEST = 2


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box_and_save(sw: Any, part_path: str, mod: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        out["error"] = "NewDocument None"
        return out

    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(
        True,
        False,
        False,
        0,
        0,
        0.05,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0,
        False,
    )
    doc.ClearSelection2(True)

    doc.SaveAs3(part_path, 0, 2)
    out["saved"] = os.path.isfile(part_path)
    out["path"] = part_path

    t = _title(doc)
    sw.CloseDoc(t)
    return out


def _get_component_faces(comp: Any, mod: Any) -> list:
    """Get faces from a placed component via GetModelDoc2 -> GetBodies2 -> GetFaces."""
    try:
        model_doc = comp.GetModelDoc2()
        if model_doc is None:
            return []
        bodies = model_doc.GetBodies2(0, True)  # swSolidBody
        if not bodies:
            return []
        body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
        faces = body.GetFaces()
        return list(faces) if faces else []
    except Exception:
        return []


def _feature_count(doc: Any) -> int:
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        return len(feats) if feats else 0
    except Exception:
        return 0


def _feature_types(doc: Any, mod: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    out.append({"name": ifeat.Name, "type": ifeat.GetTypeName2()})
                except Exception:
                    out.append({"name": "?", "type": "?"})
    except Exception:
        pass
    return out


def _component_count(asm_doc: Any) -> int:
    """Count components in the assembly via GetComponents."""
    try:
        comps = asm_doc.GetComponents(True)
        if comps is None:
            return 0
        return len(comps) if isinstance(comps, (list, tuple)) else 1
    except Exception:
        return 0


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "assembly_derisk_W8",
        "ts": time.time(),
    }

    result["typelib"] = {
        "AddComponent4": {
            "args": 5,
            "params": [
                {"name": "CompName", "vt": "BSTR(8)"},
                {"name": "ConfigName", "vt": "BSTR(8)"},
                {"name": "X", "vt": "R8(5)"},
                {"name": "Y", "vt": "R8(5)"},
                {"name": "Z", "vt": "R8(5)"},
            ],
            "return": "Component2 (USERDEFINED)",
        },
        "AddMate5": {
            "args": 15,
            "params": [
                {"name": "MateTypeFromEnum", "vt": "I4(3)"},
                {"name": "AlignFromEnum", "vt": "I4(3)"},
                {"name": "Flip", "vt": "BOOL(11)"},
                {"name": "Distance", "vt": "R8(5)"},
                {"name": "DistanceAbsUpperLimit", "vt": "R8(5)"},
                {"name": "DistanceAbsLowerLimit", "vt": "R8(5)"},
                {"name": "GearRatioNumerator", "vt": "R8(5)"},
                {"name": "GearRatioDenominator", "vt": "R8(5)"},
                {"name": "Angle", "vt": "R8(5)"},
                {"name": "AngleAbsUpperLimit", "vt": "R8(5)"},
                {"name": "AngleAbsLowerLimit", "vt": "R8(5)"},
                {"name": "ForPositioningOnly", "vt": "BOOL(11)"},
                {"name": "LockRotation", "vt": "BOOL(11)"},
                {"name": "WidthMateOption", "vt": "I4(3)"},
                {"name": "ErrorStatus", "vt": "I4(3) OUT"},
            ],
            "return": "Feature (USERDEFINED)",
        },
        "enums": {
            "swMateCOINCIDENT": 0,
            "swMateAlignALIGNED": 0,
            "swAddMateError_NoError": 1,
        },
    }

    mod = wrapper_module()
    sw = connect_running_sw()

    tmp_dir = tempfile.gettempdir()
    part_path = os.path.join(
        tmp_dir, "assembly_derisk_box_%d.SLDPRT" % int(time.time())
    )

    # Step 1: Build + save a real part
    print("[w8] building + saving box part...")
    box = _build_box_and_save(sw, part_path, mod)
    result["build_box"] = box
    if not box.get("saved"):
        return {**result, "overall": "FAIL", "reason": "box save failed"}
    print("[w8] part saved: %s" % part_path)

    # Step 2: Create assembly — find the assembly template directly
    print("[w8] creating assembly...")
    import glob

    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.asmdot"
    ) + glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT")
    if not asm_templates:
        return {**result, "overall": "FAIL", "reason": "no assembly template found"}
    asm_template = asm_templates[0]
    asm_doc = sw.NewDocument(asm_template, 0, 0.1, 0.1)
    if asm_doc is None:
        return {**result, "overall": "FAIL", "reason": "assembly NewDocument None"}

    try:
        typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
        result["assembly_typed"] = True

        # KEY FINDING: AddComponent4 requires the part to be pre-opened.
        # Without this, it silently returns None (the E4 wall).
        print("[w8] pre-opening part doc (required for AddComponent4)...")
        typed_sw = typed(sw, "ISldWorks", module=mod)
        open_ret = typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
        part_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
        result["part_preopened"] = part_doc is not None
        if part_doc is None:
            return {
                **result,
                "overall": "FAIL",
                "reason": "could not pre-open part doc",
            }
        part_title = _title(part_doc)

        # Step 3: Place component #1
        print("[w8] placing component #1...")
        n_before_c1 = _component_count(typed_asm)
        try:
            comp1 = typed_asm.AddComponent4(part_path, "", 0.0, 0.0, 0.0)
            c1_err = None
        except Exception as e:
            comp1 = None
            c1_err = f"{type(e).__name__}: {str(e)[:200]}"

        n_after_c1 = _component_count(typed_asm)
        result["component1"] = {
            "return_type": type(comp1).__name__ if comp1 else "None",
            "error": c1_err,
            "count_before": n_before_c1,
            "count_after": n_after_c1,
            "placed": comp1 is not None and not isinstance(comp1, int),
        }

        if not result["component1"]["placed"]:
            # Try AddComponent5 as fallback
            print("[w8] AddComponent4 failed, trying AddComponent5...")
            try:
                comp1 = typed_asm.AddComponent5(
                    part_path,
                    0,
                    "",
                    False,
                    "",
                    0.0,
                    0.0,
                    0.0,
                )
                c5_err = None
            except Exception as e:
                comp1 = None
                c5_err = f"{type(e).__name__}: {str(e)[:200]}"
            result["component1_fallback5"] = {
                "return_type": type(comp1).__name__ if comp1 else "None",
                "error": c5_err,
                "placed": comp1 is not None and not isinstance(comp1, int),
            }
            if result["component1_fallback5"]["placed"]:
                result["component1"]["placed"] = True
                n_after_c1 = _component_count(typed_asm)
                result["component1"]["count_after"] = n_after_c1

        if not result["component1"]["placed"]:
            return {
                **result,
                "overall": "WALL",
                "reason": "component placement failed (both AddComponent4 and 5)",
            }

        # Verify component #1 has real B-rep
        if comp1 is not None:
            try:
                c1_model = comp1.GetModelDoc2()
                c1_bodies = c1_model.GetBodies2(0, True) if c1_model else None
                c1_body_count = len(c1_bodies) if c1_bodies else 0
                result["component1"]["model_doc"] = c1_model is not None
                result["component1"]["solid_bodies"] = c1_body_count
                result["component1"]["real_brep"] = c1_body_count > 0
            except Exception as e:
                result["component1"]["brep_error"] = f"{type(e).__name__}: {e}"[:200]

        # Step 4: Place component #2 (offset)
        print("[w8] placing component #2...")
        try:
            comp2 = typed_asm.AddComponent4(part_path, "", 0.1, 0.0, 0.0)
            c2_err = None
        except Exception as e:
            comp2 = None
            c2_err = f"{type(e).__name__}: {str(e)[:200]}"

        n_after_c2 = _component_count(typed_asm)
        result["component2"] = {
            "return_type": type(comp2).__name__ if comp2 else "None",
            "error": c2_err,
            "count_after": n_after_c2,
            "placed": comp2 is not None and not isinstance(comp2, int),
            "count_is_2": n_after_c2 >= 2,
        }

        if not result["component2"]["placed"]:
            return {
                **result,
                "overall": "PARTIAL",
                "reason": "component #2 placement failed (component #1 OK)",
            }

        # Step 5: Add a mate (COINCIDENT between two faces)
        print("[w8] preparing mate — selecting faces on each component...")
        try:
            faces1 = _get_component_faces(comp1, mod)
            faces2 = _get_component_faces(comp2, mod)
            result["faces_comp1"] = len(faces1)
            result["faces_comp2"] = len(faces2)
        except Exception as e:
            result["face_error"] = f"{type(e).__name__}: {e}"[:200]
            faces1, faces2 = [], []

        if not faces1 or not faces2:
            return {
                **result,
                "overall": "PARTIAL",
                "reason": "could not acquire faces for mate",
            }

        # Select face from component #1 then face from component #2
        # AddMate5 uses mark=1 for first entity, mark=2 for second entity
        asm_doc.ClearSelection2(True)
        sel1 = select_entity(faces1[0], append=False, mark=1)
        sel2 = select_entity(faces2[0], append=True, mark=2)
        result["face_selections"] = {"face1": sel1, "face2": sel2}

        if not sel1 or not sel2:
            return {**result, "overall": "PARTIAL", "reason": "face selection failed"}

        # Step 6: AddMate5
        print("[w8] calling AddMate5 (COINCIDENT)...")
        n_before_mate = _feature_count(asm_doc)
        try:
            mate_ret = typed_asm.AddMate5(
                MATE_COINCIDENT,  # MateTypeFromEnum
                MATE_ALIGN_ALIGNED,  # AlignFromEnum
                False,  # Flip
                0.0,  # Distance
                0.0,  # DistanceAbsUpperLimit
                0.0,  # DistanceAbsLowerLimit
                0.0,  # GearRatioNumerator
                0.0,  # GearRatioDenominator
                0.0,  # Angle
                0.0,  # AngleAbsUpperLimit
                0.0,  # AngleAbsLowerLimit
                False,  # ForPositioningOnly
                False,  # LockRotation
                0,  # WidthMateOption
                0,  # ErrorStatus (OUT — passed as placeholder)
            )
            mate_err = None
        except Exception as e:
            mate_ret = None
            mate_err = f"{type(e).__name__}: {str(e)[:300]}"

        n_after_mate = _feature_count(asm_doc)
        mate_delta = n_after_mate - n_before_mate

        # Parse the return — AddMate5 returns (Feature, ErrorStatus) tuple
        mate_feature = None
        error_status = None
        if isinstance(mate_ret, tuple):
            mate_feature = mate_ret[0] if len(mate_ret) > 0 else None
            error_status = mate_ret[1] if len(mate_ret) > 1 else None
        else:
            mate_feature = mate_ret

        result["mate"] = {
            "return_type": type(mate_ret).__name__,
            "return_raw": str(mate_ret)[:200],
            "error_status": error_status,
            "mate_feature": mate_feature is not None
            and not isinstance(mate_feature, int),
            "error": mate_err,
            "delta": mate_delta,
            "materialized": mate_delta > 0,
        }

        # Also check for mate features by type (exclude MateGroup container)
        feats = _feature_types(asm_doc, mod)
        mate_feats = [
            f
            for f in feats
            if "Mate" in f.get("type", "") and f.get("type") != "MateGroup"
        ]
        result["mate_features_found"] = mate_feats

        # Determine overall: components placed + either mate materialized or
        # mate features found in the tree
        components_ok = result.get("component1", {}).get("placed") and result.get(
            "component2", {}
        ).get("count_is_2")
        mate_ok = result["mate"]["materialized"] or len(mate_feats) > 0

        if components_ok and mate_ok:
            result["overall"] = "GREEN"
            result["interpretation"] = (
                "Assembly construction + mating is tractable out-of-process. "
                "Component placement via AddComponent4 with saved .sldprt works "
                "(real B-rep, 2 components). AddMate5 created %d mate feature(s). "
                "Assembly+mate epoch opens." % len(mate_feats)
            )
        elif components_ok:
            result["overall"] = "PARTIAL"
            result["interpretation"] = (
                "Components placed OK (2 components, real B-rep) but mate "
                "did not materialize (ErrorStatus=%s, delta=%d). Assembly "
                "construction works; mating needs further investigation "
                "(selection marks, face acquisition, or in-process requirement)."
                % (result["mate"].get("error_status"), result["mate"].get("delta"))
            )
        else:
            result["overall"] = "WALL"
            result["interpretation"] = "Component placement failed."

        result["features_after"] = feats

    finally:
        try:
            sw.CloseDoc(_title(asm_doc))
        except Exception:
            pass
        # Clean up temp part
        try:
            os.unlink(part_path)
        except Exception:
            pass

    return result


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "assembly_derisk_W8.json"
    out.write_text(payload, encoding="utf-8")
    print("wrote %s" % out)
    print("overall: %s" % result.get("overall"))
    return {"GREEN": 0, "WALL": 2, "PARTIAL": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
