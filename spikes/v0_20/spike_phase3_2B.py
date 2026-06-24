"""Phase-3 Slice 2B spike: limit mates (distance + angle with Min/Max).

A limit mate is NOT a new swMateType_e — it's a distance or angle mate
with MaximumVariation + MinimumVariation set on the typed interface.

From the Slice 2A typelib dump:
  IDistanceMateFeatureData: Distance, MaximumDistance, MinimumDistance, FlipDimension, IsAdvancedMate
  IAngleMateFeatureData: Angle, MaximumAngle, MinimumAngle, FlipDimension, IsAdvancedMate, ReferenceEntity

This spike:
  1. Create a distance mate with limits (min_mm=3, max_mm=7, value_mm=5)
  2. Create an angle mate with limits (min_deg=30, max_deg=60, value_deg=45)
  3. verify_mates — both must be solved:true
  4. Read back the limit properties to confirm they persist

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_20" / "_results" / "phase3_2B_pae.json"

results: dict[str, Any] = {
    "pae": "phase3_slice2B",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
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


PART_SPEC = {
    "schema_version": 1,
    "name": "Phase3_LimitPart",
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
    ],
}


def probe_faces(part_path: str, sw: Any, tsw: Any, mod: Any) -> list[dict]:
    from ai_sw_bridge.com.earlybind import typed, typed_extension

    ret = tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        return []
    try:
        tpart = typed(doc, "IPartDoc", module=mod)
        bodies = tpart.GetBodies2(0, True)
        if not bodies:
            return []
        body = bodies[0]
        faces = body.GetFaces()
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
                        persist_id = base64.b64encode(bytes(pid_bytes)).decode("ascii")
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


def make_face_ref(face_data):
    ref = {"normal": face_data["normal"], "centroid": face_data["centroid"]}
    if face_data.get("is_cylinder"):
        ref["is_cylinder"] = True
    if face_data.get("persist_id"):
        ref["persist_id"] = face_data["persist_id"]
    return ref


def run() -> bool:
    print("=" * 70)
    print("Phase-3 Slice 2B: Limit mates (distance + angle with Min/Max)")
    print("=" * 70)

    from ai_sw_bridge.spec.builder import build as part_build
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.sw_com import get_sw_app
    from ai_sw_bridge.assembly.handlers import (
        create_mate,
        verify_mates,
        place_components,
    )

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)

    # Close all open docs
    try:
        docs = sw.GetDocuments()
        if docs:
            for d in docs:
                try:
                    d.CloseDoc
                except Exception:
                    pass
    except Exception:
        pass

    # Build parts
    print("\n--- Step 1: Build parts ---")
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    PART_A_PATH = str(_tmp / f"phase3_lim_{_ts}_a.SLDPRT")
    PART_B_PATH = str(_tmp / f"phase3_lim_{_ts}_b.SLDPRT")

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

    # Probe faces
    print("\n--- Step 2: Probe faces ---")
    faces_a = probe_faces(PART_A_PATH, sw, tsw, mod)
    faces_b = probe_faces(PART_B_PATH, sw, tsw, mod)
    print(f"  Part A: {len(faces_a)} faces")
    print(f"  Part B: {len(faces_b)} faces")

    face_a_top = find_planar(faces_a, [0, 0, 1], z_approx=10)
    face_b_bottom = find_planar(faces_b, [0, 0, -1], z_approx=0)
    face_a_right = find_planar(faces_a, [1, 0, 0])
    face_b_right = find_planar(faces_b, [1, 0, 0])

    gate(
        "probe_faces",
        all([face_a_top, face_b_bottom, face_a_right, face_b_right]),
        f"top_A={face_a_top is not None}, bottom_B={face_b_bottom is not None}",
    )

    # Create assembly
    print("\n--- Step 3: Assembly + limit mates ---")
    import glob

    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    asm_doc = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
    if asm_doc is None:
        gate("asm_create", False, "NewDocument returned None")
        return False

    components = [
        {"id": "part_a", "part": PART_A_PATH, "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "part_b", "part": PART_B_PATH, "transform": {"xyz_mm": [0, 0, 20]}},
    ]
    placed, place_err = place_components(sw, asm_doc, components, mod=mod)
    gate("place_components", place_err is None, f"placed={len(placed)}")
    if place_err:
        return False

    # --- Distance mate with limits ---
    print("\n  Creating distance mate with limits (5mm ± 2mm)...")
    dist_limit_spec = {
        "type": "distance",
        "alignment": "aligned",
        "value_mm": 5.0,
        "limit": {"min_mm": 3.0, "max_mm": 7.0},
        "a": {"component": "part_a", "face_ref": make_face_ref(face_a_top)},
        "b": {"component": "part_b", "face_ref": make_face_ref(face_b_bottom)},
    }

    mate_feat, mate_err = create_mate(asm_doc, placed, dist_limit_spec, mod=mod)
    dist_ok = mate_feat is not None and mate_err is None
    gate(
        "create_distance_limit_mate",
        dist_ok,
        f"feat={mate_feat is not None}, error={mate_err}",
    )

    # --- Angle mate with limits ---
    print("\n  Creating angle mate with limits (45° ± 15°)...")
    angle_limit_spec = {
        "type": "angle",
        "alignment": "aligned",
        "value_deg": 45.0,
        "limit": {"min_deg": 30.0, "max_deg": 60.0},
        "a": {"component": "part_a", "face_ref": make_face_ref(face_a_right)},
        "b": {"component": "part_b", "face_ref": make_face_ref(face_b_right)},
    }

    mate_feat2, mate_err2 = create_mate(asm_doc, placed, angle_limit_spec, mod=mod)
    angle_ok = mate_feat2 is not None and mate_err2 is None
    gate(
        "create_angle_limit_mate",
        angle_ok,
        f"feat={mate_feat2 is not None}, error={mate_err2}",
    )

    # --- verify_mates ---
    print("\n--- Step 4: verify_mates ---")
    try:
        asm_doc.ForceRebuild3(True)
    except Exception:
        pass

    vm = verify_mates(asm_doc, mod=mod)
    print(f"  verify_mates returned {len(vm)} mates:")
    for m in vm:
        print(
            f"    {m['name']}: type={m['type']}, solved={m['solved']}, "
            f"error_code={m['error_code']}"
        )

    all_solved = len(vm) >= 2 and all(m.get("solved") for m in vm)
    gate(
        "verify_mates_all_solved",
        all_solved,
        f"total={len(vm)}, solved={sum(1 for m in vm if m.get('solved'))}",
    )

    # --- Read back limit properties ---
    print("\n--- Step 5: Read back limit properties ---")
    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
    try:
        fm = asm_doc.FeatureManager
        feats = fm.GetFeatures(False)
        for feat in feats or []:
            ifeat = typed(feat, "IFeature", module=mod)
            type_name = ifeat.GetTypeName2()
            if "Mate" not in type_name or type_name == "MateGroup":
                continue

            md = ifeat.GetDefinition()
            if md is None:
                continue

            if "Distance" in type_name:
                try:
                    d_iface = typed_qi(md, "IDistanceMateFeatureData", module=mod)
                    dist_val = d_iface.Distance
                    max_dist = d_iface.MaximumDistance
                    min_dist = d_iface.MinimumDistance
                    print(
                        f"  {ifeat.Name}: Distance={dist_val}, "
                        f"Min={min_dist}, Max={max_dist}"
                    )
                    results["per_mate_results"].append(
                        {
                            "name": ifeat.Name,
                            "type": type_name,
                            "distance_m": dist_val,
                            "min_distance_m": min_dist,
                            "max_distance_m": max_dist,
                            "limits_set": min_dist != 0 or max_dist != 0,
                        }
                    )
                except Exception as e:
                    print(f"  {ifeat.Name}: read error: {e}")
            elif "Angle" in type_name:
                try:
                    a_iface = typed_qi(md, "IAngleMateFeatureData", module=mod)
                    angle_val = a_iface.Angle
                    max_angle = a_iface.MaximumAngle
                    min_angle = a_iface.MinimumAngle
                    print(
                        f"  {ifeat.Name}: Angle={angle_val}, "
                        f"Min={min_angle}, Max={max_angle}"
                    )
                    results["per_mate_results"].append(
                        {
                            "name": ifeat.Name,
                            "type": type_name,
                            "angle_rad": angle_val,
                            "min_angle_rad": min_angle,
                            "max_angle_rad": max_angle,
                            "limits_set": min_angle != 0 or max_angle != 0,
                        }
                    )
                except Exception as e:
                    print(f"  {ifeat.Name}: read error: {e}")
    except Exception as e:
        print(f"  Read-back error: {e}")

    # Cleanup
    try:
        title = asm_doc.GetTitle() if callable(asm_doc.GetTitle) else asm_doc.GetTitle
        sw.CloseDoc(title)
    except Exception:
        pass

    return all_solved


def main() -> int:
    pythoncom.CoInitialize()
    try:
        ok = run()
        if ok:
            results["overall"] = "GREEN"
            results["verdict"] = "Limit mates created and verified solved"
        else:
            results["overall"] = "PARTIAL"
            results["verdict"] = "Some limit mates not verified"
    finally:
        pythoncom.CoUninitialize()

    save_results()
    return 0 if results.get("overall") == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
