"""Spike v0.18 — Wave-8: Assembly mate retry (feature-data path).

Proves that two placed components can be joined by a mate out-of-process using
the MODERN feature-data path: CreateMateData → ICoincidentMateFeatureData →
EntitiesToMate (SAFEARRAY) → CreateMate.

KEY FINDING: The legacy AddMate5 path requires assembly-context face entities
(not available out-of-process). The modern CreateMateData path accepts
component-context faces from IComponent2.GetBodies() via SAFEARRAY — same
marshaling pattern as Wave-7's edge flange.

Recipe:
  1. Build + SaveAs box part (proven).
  2. Pre-open part via typed ISldWorks.OpenDoc6 (mandatory for AddComponent4).
  3. NewDocument(asmdot) → AddComponent4 × 2 (proven placement).
  4. IComponent2.GetBodies(0) → body.GetFaces() → pick faces.
  5. CreateMateData(0) → typed_qi(ICoincidentMateFeatureData) →
     EntitiesToMate = VARIANT(VT_ARRAY|VT_DISPATCH, (face1, face2)) →
     MateAlignment = 0 → CreateMate(mate_data).
  6. Verify: returned object typed as IFeature → GetTypeName2() == "MateCoincident".

Usage:
    python spikes/v0_18/spike_assembly_mate_retry.py
"""

from __future__ import annotations

import json
import os
import sys
import glob
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

from ai_sw_bridge.com.earlybind import typed, typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module

from spike_earlybind_persist import connect_running_sw

RESULTS_DIR = Path(__file__).resolve().parent / "_results"


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


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


def _get_component_faces(comp: Any) -> list:
    """Get faces from a placed component via IComponent2.GetBodies(0)."""
    try:
        bodies = comp.GetBodies(0)
        if not bodies:
            return []
        body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
        faces = body.GetFaces()
        return list(faces) if faces else []
    except Exception:
        return []


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "assembly_mate_retry_W8",
        "ts": time.time(),
    }

    mod = wrapper_module()
    sw = connect_running_sw()

    tmp_dir = tempfile.gettempdir()
    part_path = os.path.join(tmp_dir, "mate_retry_box_%d.SLDPRT" % int(time.time()))

    # Step 1: Build + save box
    print("[w8m] building + saving box part...")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "part NewDocument None"}
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    doc.SketchManager.CreateCornerRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    doc.FeatureManager.FeatureExtrusion3(
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
    result["part_saved"] = os.path.isfile(part_path)
    dt = _title(doc)
    sw.CloseDoc(dt)

    if not result["part_saved"]:
        return {**result, "overall": "FAIL", "reason": "part save failed"}

    # Step 2: Assembly + components
    print("[w8m] creating assembly + placing 2 components...")
    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    if not asm_templates:
        return {**result, "overall": "FAIL", "reason": "no assembly template"}
    asm = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
    if asm is None:
        return {**result, "overall": "FAIL", "reason": "assembly NewDocument None"}

    try:
        at = _title(asm)
        typed_sw = typed(sw, "ISldWorks", module=mod)
        open_ret = typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
        part_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
        result["part_preopened"] = part_doc is not None

        typed_asm = typed(asm, "IAssemblyDoc", module=mod)
        c1 = typed_asm.AddComponent4(part_path, "", 0.0, 0.0, 0.0)
        c2 = typed_asm.AddComponent4(part_path, "", 0.1, 0.0, 0.0)
        result["components"] = {
            "c1_type": type(c1).__name__ if c1 else "None",
            "c2_type": type(c2).__name__ if c2 else "None",
            "both_placed": bool(c1) and bool(c2),
        }

        if not result["components"]["both_placed"]:
            return {**result, "overall": "FAIL", "reason": "component placement failed"}

        # Step 3: Get faces from component bodies
        faces1 = _get_component_faces(c1)
        faces2 = _get_component_faces(c2)
        result["faces_c1"] = len(faces1)
        result["faces_c2"] = len(faces2)

        if not faces1 or not faces2:
            return {**result, "overall": "FAIL", "reason": "no faces on components"}

        # Step 4: CreateMateData + EntitiesToMate SAFEARRAY + CreateMate
        print("[w8m] creating mate via feature-data path...")
        n_before = len(asm.FeatureManager.GetFeatures(True))

        mate_data = typed_asm.CreateMateData(0)  # 0 = swMateCOINCIDENT
        result["mate_data_type"] = type(mate_data).__name__ if mate_data else "None"

        if mate_data is None:
            return {**result, "overall": "FAIL", "reason": "CreateMateData None"}

        coin_data = typed_qi(mate_data, "ICoincidentMateFeatureData", module=mod)
        result["coin_data_typed"] = True

        face_arr = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (faces1[0], faces2[0])
        )
        coin_data.EntitiesToMate = face_arr
        coin_data.MateAlignment = 0  # swMateAlignALIGNED

        mate_ret = typed_asm.CreateMate(mate_data)

        n_after = len(asm.FeatureManager.GetFeatures(True))
        delta = n_after - n_before

        result["mate_return_type"] = type(mate_ret).__name__ if mate_ret else "None"
        result["top_level_delta"] = delta

        # Step 5: Verify — check if returned object is a real mate feature
        mate_verified = False
        mate_name = None
        mate_type = None
        error_status = None

        if mate_ret is not None and not isinstance(mate_ret, int):
            try:
                ifeat = typed(mate_ret, "IFeature", module=mod)
                mate_name = ifeat.Name
                mate_type = ifeat.GetTypeName2()
                if "Mate" in mate_type or "mate" in mate_type.lower():
                    mate_verified = True
            except Exception as e:
                result["ifeature_err"] = f"{type(e).__name__}: {e}"[:200]

            try:
                mfd = typed_qi(mate_data, "IMateFeatureData", module=mod)
                error_status = mfd.ErrorStatus
            except Exception:
                pass

        result["mate_verified"] = mate_verified
        result["mate_feature_name"] = mate_name
        result["mate_feature_type"] = mate_type
        result["error_status"] = error_status

        # List all features (including MateGroup children)
        feats = _feature_types(asm, mod)
        result["features_after"] = feats

        # Also check MateGroup for children
        mate_group_children = []
        for f in feats:
            if f["type"] == "MateGroup":
                # Try to enumerate children — MateGroup may have sub-features
                result["mate_group_found"] = True
                break

        # Determine overall
        if mate_verified:
            result["overall"] = "GREEN"
            result["interpretation"] = (
                "Mate materialized via CreateMateData → ICoincidentMateFeatureData "
                "→ EntitiesToMate SAFEARRAY → CreateMate. Feature '%s' (type=%s) "
                "confirmed. ErrorStatus=%s. Assembly+mate epoch opens. "
                "The legacy AddMate5 path WALLs (ErrorStatus=4) because it needs "
                "assembly-context faces; the modern feature-data path accepts "
                "component-context faces via the same SAFEARRAY marshaling that "
                "cracked edge flange in Wave-7." % (mate_name, mate_type, error_status)
            )
        else:
            result["overall"] = "WALL"
            result["interpretation"] = (
                "WALL: CreateMate returned %s but no mate feature verified. "
                "ErrorStatus=%s. Assembly mates may require in-process resolution."
                % (result.get("mate_return_type"), error_status)
            )

    finally:
        try:
            sw.CloseDoc(_title(asm))
        except Exception:
            pass
        try:
            if part_doc:
                pt = _title(part_doc)
                sw.CloseDoc(pt)
        except Exception:
            pass
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
    out = RESULTS_DIR / "assembly_mate_retry_W8.json"
    out.write_text(payload, encoding="utf-8")
    print("wrote %s" % out)
    print("overall: %s" % result.get("overall"))
    return {"GREEN": 0, "WALL": 2, "PARTIAL": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
