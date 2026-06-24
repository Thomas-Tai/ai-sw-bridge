"""Phase-3 Slice 2A spike: typelib audit + tangent(=4) + angle(=6) mates.

W11 Slice 2A — extends the shipped mate engine with tangent and angle.

Steps:
  1. Dump swMateType_e from the typelib — verify TANGENT=4, ANGLE=6,
     and discover WIDTH and any other enum values.
  2. Dump ITangentMateFeatureData and IAngleMateFeatureData members.
  3. Build two test parts (box + cylindrical boss, same as Phase-2).
  4. Create tangent + angle mates directly through create_mate().
  5. verify_mates() — both must be solved:true.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_20" / "_results" / "phase3_2A_pae.json"

results: dict[str, Any] = {
    "pae": "phase3_slice2A",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "typelib": {},
    "per_mate_results": [],
    "errors": [],
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"  wrote {RESULTS_PATH}", file=sys.stderr)


# ============================================================================
# Step 1: Typelib audit
# ============================================================================
def typelib_audit() -> bool:
    print("\n--- Step 1: Typelib audit ---")
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.com.earlybind import typed, typed_qi

    mod = wrapper_module()
    if mod is None:
        gate("typelib_module", False, "wrapper_module() returned None")
        return False

    from win32com.client import dynamic

    try:
        sw = dynamic.Dispatch(pythoncom.GetActiveObject("SldWorks.Application"))
    except Exception:
        sw = dynamic.Dispatch("SldWorks.Application")

    # Find assembly template
    import glob

    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    if not asm_templates:
        gate("asm_template", False, "No assembly template found")
        return False

    asm_doc = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
    if asm_doc is None:
        gate("asm_doc", False, "NewDocument returned None")
        return False

    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    # Test all candidate enum values
    candidates = {
        "swMateCOINCIDENT": 0,
        "swMateCONCENTRIC": 1,
        "swMatePERPENDICULAR": 2,
        "swMatePARALLEL": 3,
        "swMateTANGENT": 4,
        "swMateDISTANCE": 5,
        "swMateANGLE": 6,
        "swMateSYMMETRIC": 8,
        "swMateCAMFOLLOWER": 9,
        "swMateGEAR": 10,
        "swMateWIDTH": 11,
        "swMateSCREW": 13,
    }

    verified: dict[str, Any] = {}
    for name, val in candidates.items():
        try:
            md = typed_asm.CreateMateData(val)
            if md is not None:
                mfd = typed_qi(md, "IMateFeatureData", module=mod)
                _ = mfd.ErrorStatus
                verified[name] = {"value": val, "works": True}
            else:
                verified[name] = {"value": val, "works": False, "reason": "None"}
        except Exception as e:
            verified[name] = {"value": val, "works": False, "reason": str(e)[:200]}

    results["typelib"]["swMateType_e"] = verified

    # Dump typed interfaces for tangent and angle
    iface_audit: dict[str, Any] = {}
    for mate_name, iface_name in [
        ("TANGENT", "ITangentMateFeatureData"),
        ("ANGLE", "IAngleMateFeatureData"),
        ("WIDTH", "IWidthMateFeatureData"),
    ]:
        enum_val = candidates.get(f"swMate{mate_name}")
        if enum_val is None:
            continue
        try:
            md = typed_asm.CreateMateData(enum_val)
            if md is None:
                iface_audit[mate_name] = {
                    "interface": iface_name,
                    "error": "CreateMateData None",
                }
                continue
            typed_mate = typed_qi(md, iface_name, module=mod)
            props = [
                p
                for p in dir(typed_mate)
                if not p.startswith("_")
                and p not in ("MateAlignment", "EntitiesToMate", "ErrorStatus")
            ]
            key_props = [
                p
                for p in props
                if any(
                    kw in p.lower()
                    for kw in [
                        "angle",
                        "distance",
                        "align",
                        "lock",
                        "flip",
                        "abs",
                        "limit",
                        "min",
                        "max",
                        "variation",
                        "width",
                        "tab",
                        "selection",
                        "constraint",
                        "tangent",
                    ]
                )
            ]
            iface_audit[mate_name] = {
                "interface": iface_name,
                "qi_ok": True,
                "all_properties": sorted(props),
                "key_properties": sorted(key_props),
            }
        except Exception as e:
            iface_audit[mate_name] = {
                "interface": iface_name,
                "qi_ok": False,
                "error": str(e)[:200],
            }

    results["typelib"]["interfaces"] = iface_audit

    # Cleanup
    try:
        title = asm_doc.GetTitle() if callable(asm_doc.GetTitle) else asm_doc.GetTitle
        sw.CloseDoc(title)
    except Exception:
        pass

    anchor_ok = verified.get("swMateCOINCIDENT", {}).get("works", False)
    tangent_ok = verified.get("swMateTANGENT", {}).get("works", False)
    angle_ok = verified.get("swMateANGLE", {}).get("works", False)
    width_ok = verified.get("swMateWIDTH", {}).get("works", False)

    gate("typelib_anchor", anchor_ok, f"COINCIDENT=0 works={anchor_ok}")
    gate("typelib_tangent", tangent_ok, f"TANGENT=4 works={tangent_ok}")
    gate("typelib_angle", angle_ok, f"ANGLE=6 works={angle_ok}")
    gate("typelib_width", width_ok, f"WIDTH=11 works={width_ok}")

    return anchor_ok and tangent_ok and angle_ok


# ============================================================================
# Step 2-5: Build parts, create mates, verify
# ============================================================================
def run_mate_pae() -> bool:
    print("\n--- Step 2: Build parts ---")
    from ai_sw_bridge.spec.builder import build as part_build
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.com.earlybind import typed, typed_extension, typed_qi
    from ai_sw_bridge.sw_com import get_sw_app
    from ai_sw_bridge.assembly.handlers import (
        create_mate,
        verify_mates,
        place_components,
    )

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)

    # Close all open documents to avoid stale-doc interference with SaveAs3
    try:
        docs = sw.GetDocuments()
        if docs:
            for d in docs:
                try:
                    t = d.GetTitle() if callable(d.GetTitle) else d.GetTitle
                    d.CloseDoc
                except Exception:
                    pass
    except Exception:
        pass

    PART_SPEC = {
        "schema_version": 1,
        "name": "Phase3_TestPart",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Base",
                "plane": "Front",
                "width": 30.0,
                "height": 30.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Base",
                "sketch": "SK_Base",
                "depth": 10.0,
            },
            {
                "type": "sketch_circle_on_face",
                "name": "SK_Boss",
                "of_feature": "EX_Base",
                "face": "+z",
                "center": {"u": 0.5, "v": 0.5},
                "diameter": 10.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Boss",
                "sketch": "SK_Boss",
                "depth": 10.0,
            },
        ],
    }

    import tempfile

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    PART_A_PATH = str(_tmp / f"phase3_{_ts}_a.SLDPRT")
    PART_B_PATH = str(_tmp / f"phase3_{_ts}_b.SLDPRT")

    for label, path in [("A", PART_A_PATH), ("B", PART_B_PATH)]:
        for ext_path in [path, path.replace(".SLDPRT", ".sldprt")]:
            if os.path.isfile(ext_path):
                try:
                    os.remove(ext_path)
                except PermissionError:
                    pass

    for label, path in [("A", PART_A_PATH), ("B", PART_B_PATH)]:
        print(f"  Building Part {label}...")
        r = part_build(PART_SPEC, save_as=path, save_format="current", no_dim=True)
        gate(
            f"build_part_{label.lower()}",
            r.ok and os.path.isfile(path),
            f"ok={r.ok}, features={r.features_built}",
        )

    if not os.path.isfile(PART_A_PATH) or not os.path.isfile(PART_B_PATH):
        gate("parts_built", False, "Part build failed")
        return False

    # --- Probe faces ---
    print("\n--- Step 3: Probe faces ---")

    def probe_faces(part_path: str) -> list[dict]:
        ret = tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
        print(f"  OpenDoc6({part_path}): ret type={type(ret).__name__}")
        if isinstance(ret, tuple):
            doc = ret[0]
            print(
                f"    tuple[0]={type(doc).__name__ if doc else None}, tuple[1:]={ret[1:]}"
            )
        else:
            doc = ret
            print(f"    doc={type(doc).__name__ if doc else None}")
        if doc is None:
            print(f"    doc is None — OpenDoc6 failed")
            return []
        try:
            tpart = typed(doc, "IPartDoc", module=mod)
            bodies = tpart.GetBodies2(0, True)
            print(f"    GetBodies2: {len(bodies) if bodies else 0} bodies")
            if not bodies:
                return []
            body = bodies[0]
            faces = body.GetFaces()
            print(f"    GetFaces: {len(faces) if faces else 0} faces")
            if not faces:
                return []
            ext = typed_extension(doc, module=mod)
            face_list = []
            for idx, face in enumerate(faces):
                try:
                    iface = typed(face, "IFace2", module=mod)
                    surf = iface.GetSurface()
                    isurf = typed(surf, "ISurface", module=mod)
                    is_cyl = bool(isurf.IsCylinder())
                    is_plane = bool(isurf.IsPlane())
                    normal = list(iface.Normal) if is_plane else [0, 0, 0]
                    bbox = iface.GetBox()
                    cx = (bbox[0] + bbox[3]) / 2.0
                    cy = (bbox[1] + bbox[4]) / 2.0
                    cz = (bbox[2] + bbox[5]) / 2.0
                    persist_id = None
                    try:
                        pid_bytes = ext.GetPersistReference3(face)
                        if pid_bytes:
                            persist_id = base64.b64encode(bytes(pid_bytes)).decode(
                                "ascii"
                            )
                    except Exception:
                        pass
                    face_list.append(
                        {
                            "face_idx": idx,
                            "is_cylinder": is_cyl,
                            "is_plane": is_plane,
                            "normal": [round(n, 6) for n in normal],
                            "centroid": [
                                round(cx * 1000, 3),
                                round(cy * 1000, 3),
                                round(cz * 1000, 3),
                            ],
                            "persist_id": persist_id,
                        }
                    )
                except Exception:
                    pass
            return face_list
        finally:
            title = doc.GetTitle() if callable(doc.GetTitle) else doc.GetTitle
            sw.CloseDoc(title)

    faces_a = probe_faces(PART_A_PATH)
    faces_b = probe_faces(PART_B_PATH)
    print(
        f"  Part A: {len(faces_a)} faces ({sum(1 for f in faces_a if f['is_cylinder'])} cylindrical)"
    )
    print(
        f"  Part B: {len(faces_b)} faces ({sum(1 for f in faces_b if f['is_cylinder'])} cylindrical)"
    )

    def find_planar(faces, normal_target, z_approx=None):
        for f in faces:
            if not f["is_plane"]:
                continue
            n = f["normal"]
            if all(abs(n[i] - normal_target[i]) < 0.01 for i in range(3)):
                if z_approx is not None and abs(f["centroid"][2] - z_approx) >= 5.0:
                    continue
                return f
        return None

    def find_cylindrical(faces):
        for f in faces:
            if f["is_cylinder"]:
                return f
        return None

    # For tangent: need a cylindrical face + a planar face
    # For angle: need two non-parallel planar faces
    face_a_cyl = find_cylindrical(faces_a)
    face_b_right = find_planar(faces_b, [1, 0, 0])
    face_a_right = find_planar(faces_a, [1, 0, 0])
    face_a_front = find_planar(faces_a, [0, 1, 0])

    gate(
        "probe_faces",
        all([face_a_cyl, face_b_right, face_a_right, face_a_front]),
        f"cyl_A={face_a_cyl is not None}, "
        f"right_A={face_a_right is not None}, "
        f"right_B={face_b_right is not None}, "
        f"front_A={face_a_front is not None}",
    )

    if not all([face_a_cyl, face_b_right, face_a_right, face_a_front]):
        gate("face_selection", False, "Could not find required faces")
        return False

    # --- Create assembly and mates ---
    print("\n--- Step 4: Create assembly + tangent/angle mates ---")

    # Open assembly
    import glob

    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    asm_doc = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
    if asm_doc is None:
        gate("asm_create", False, "NewDocument assembly returned None")
        return False
    gate("asm_create", True, "Assembly created")

    # Place components
    components = [
        {"id": "part_a", "part": PART_A_PATH, "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "part_b", "part": PART_B_PATH, "transform": {"xyz_mm": [0, 0, 25]}},
    ]

    placed, place_err = place_components(sw, asm_doc, components, mod=mod)
    gate(
        "place_components",
        place_err is None,
        f"placed={len(placed)}, error={place_err}",
    )
    if place_err is not None:
        return False

    # Helper to build face_ref from probed data
    def make_face_ref(face_data):
        ref = {"normal": face_data["normal"], "centroid": face_data["centroid"]}
        if face_data.get("is_cylinder"):
            ref["is_cylinder"] = True
        if face_data.get("persist_id"):
            ref["persist_id"] = face_data["persist_id"]
        return ref

    # Tangent mate: cylindrical face on part_a + planar face on part_b
    tangent_spec = {
        "type": "tangent",
        "alignment": "aligned",
        "a": {"component": "part_a", "face_ref": make_face_ref(face_a_cyl)},
        "b": {"component": "part_b", "face_ref": make_face_ref(face_b_right)},
    }

    mate_feat, mate_err = create_mate(asm_doc, placed, tangent_spec, mod=mod)
    tangent_ok = mate_feat is not None and mate_err is None
    gate(
        "create_tangent_mate",
        tangent_ok,
        f"feat={mate_feat is not None}, error={mate_err}",
    )
    results["per_mate_results"].append(
        {
            "type": "tangent",
            "created": tangent_ok,
            "error": mate_err,
        }
    )

    # Angle mate: two non-parallel planar faces (right + front), 45 degrees
    angle_spec = {
        "type": "angle",
        "alignment": "aligned",
        "value_deg": 45.0,
        "a": {"component": "part_a", "face_ref": make_face_ref(face_a_right)},
        "b": {"component": "part_b", "face_ref": make_face_ref(face_a_front)},
    }

    mate_feat2, mate_err2 = create_mate(asm_doc, placed, angle_spec, mod=mod)
    angle_ok = mate_feat2 is not None and mate_err2 is None
    gate(
        "create_angle_mate_45deg",
        angle_ok,
        f"feat={mate_feat2 is not None}, error={mate_err2}",
    )
    results["per_mate_results"].append(
        {
            "type": "angle",
            "value_deg": 45.0,
            "created": angle_ok,
            "error": mate_err2,
        }
    )

    # --- verify_mates ---
    print("\n--- Step 5: verify_mates ---")
    try:
        asm_doc.ForceRebuild3(True)
    except Exception:
        pass

    vm = verify_mates(asm_doc, mod=mod)
    results["verify_mates_raw"] = vm
    print(f"  verify_mates returned {len(vm)} mates:")
    for m in vm:
        print(
            f"    {m['name']}: type={m['type']}, solved={m['solved']}, "
            f"error_code={m['error_code']}, suppressed={m['suppressed']}"
        )

    all_solved = len(vm) > 0 and all(m.get("solved") for m in vm)
    gate(
        "verify_mates_all_solved",
        all_solved,
        f"total={len(vm)}, solved={sum(1 for m in vm if m.get('solved'))}",
    )

    # Cleanup
    try:
        title = asm_doc.GetTitle() if callable(asm_doc.GetTitle) else asm_doc.GetTitle
        sw.CloseDoc(title)
    except Exception:
        pass

    return all_solved


def main() -> int:
    print("=" * 70)
    print("Phase-3 Slice 2A: Typelib audit + Tangent + Angle mates")
    print("=" * 70)

    pythoncom.CoInitialize()
    try:
        typelib_ok = typelib_audit()
        if not typelib_ok:
            results["overall"] = "WALL"
            results["verdict"] = (
                "Typelib audit failed — enum values or interfaces not confirmed"
            )
            save_results()
            return 1

        mate_ok = run_mate_pae()
        if mate_ok:
            results["overall"] = "GREEN"
            results["verdict"] = "Tangent + angle mates created and verified solved"
        else:
            results["overall"] = "PARTIAL"
            results["verdict"] = "Some mates created but not all verified solved"
    finally:
        pythoncom.CoUninitialize()

    save_results()
    return 0 if results.get("overall") == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
