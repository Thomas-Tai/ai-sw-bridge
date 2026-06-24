"""Phase-3 Final PAE: all four mate types (tangent, angle, limit-distance, width).

One assembly spec exercising every GREEN Phase-3 mate type. All must be
solved:true. Empty list or any unsolved mate = FAIL.

Part geometry:
  - Part A: 30x30x10mm box + 10mm radius cylindrical boss (for tangent)
  - Part B: 20x20x10mm box (narrower, for width mate tab)

Mates:
  1. Tangent: cylindrical face on A + planar face on B
  2. Angle (45°): right face on A + front face on B
  3. Limit distance (3-7mm, center 5mm): top face on A + bottom face on B
  4. Width: left+right faces of A (groove) + left+right faces of B (tab)

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
import win32com.client as w32  # noqa: E402

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_20" / "_results" / "phase3_mates_pae.json"

results: dict[str, Any] = {
    "pae": "phase3_final",
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
    print(f"\n  wrote {RESULTS_PATH}", file=sys.stderr)


def run() -> bool:
    print("=" * 70)
    print("Phase-3 Final PAE: Tangent + Angle + Limit + Width")
    print("=" * 70)

    from ai_sw_bridge.spec.builder import build as part_build
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.com.earlybind import typed, typed_extension, typed_qi
    from ai_sw_bridge.sw_com import get_sw_app
    from ai_sw_bridge.assembly.handlers import (
        create_mate,
        verify_mates,
        place_components,
    )
    from ai_sw_bridge.assembly.face_resolver import resolve_component_face

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)

    # Close all docs
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

    # Part specs
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    PART_A_SPEC = {
        "schema_version": 1,
        "name": "Phase3_BoxWithCyl",
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
                "name": "SK_Cyl",
                "of_feature": "EX_Base",
                "face": "+z",
                "center": {"u": 0.5, "v": 0.5},
                "diameter": 10.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Cyl",
                "sketch": "SK_Cyl",
                "depth": 10.0,
            },
        ],
    }

    PART_B_SPEC = {
        "schema_version": 1,
        "name": "Phase3_NarrowBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 20.0,
                "height": 20.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }

    PART_A_PATH = str(_tmp / f"phase3_final_{_ts}_a.SLDPRT")
    PART_B_PATH = str(_tmp / f"phase3_final_{_ts}_b.SLDPRT")

    # Build parts
    print("\n--- Step 1: Build parts ---")
    for label, path, spec in [
        ("A", PART_A_PATH, PART_A_SPEC),
        ("B", PART_B_PATH, PART_B_SPEC),
    ]:
        print(f"  Building Part {label}...")
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
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

    def probe_faces(part_path: str) -> list[dict]:
        ret = tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
        doc = ret[0] if isinstance(ret, tuple) else ret
        if doc is None:
            return []
        try:
            tpart = typed(doc, "IPartDoc", module=mod)
            bodies = tpart.GetBodies2(0, True)
            if not bodies:
                return []
            faces = bodies[0].GetFaces()
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
                    pid = None
                    try:
                        pid_bytes = ext.GetPersistReference3(face)
                        if pid_bytes:
                            pid = base64.b64encode(bytes(pid_bytes)).decode("ascii")
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
                            "persist_id": pid,
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

    def find_cylindrical(faces):
        for f in faces:
            if f["is_cylinder"]:
                return f
        return None

    faces_a = probe_faces(PART_A_PATH)
    faces_b = probe_faces(PART_B_PATH)
    print(
        f"  Part A: {len(faces_a)} faces ({sum(1 for f in faces_a if f['is_cylinder'])} cyl)"
    )
    print(
        f"  Part B: {len(faces_b)} faces ({sum(1 for f in faces_b if f['is_cylinder'])} cyl)"
    )

    fa_cyl = find_cylindrical(faces_a)
    fa_top = find_planar(faces_a, [0, 0, 1], z_approx=10)
    fa_right = find_planar(faces_a, [1, 0, 0])
    fa_front = find_planar(faces_a, [0, 1, 0])
    fa_left = find_planar(faces_a, [-1, 0, 0])
    fb_bottom = find_planar(faces_b, [0, 0, -1], z_approx=0)
    fb_right = find_planar(faces_b, [1, 0, 0])
    fb_left = find_planar(faces_b, [-1, 0, 0])

    all_faces = all(
        [fa_cyl, fa_top, fa_right, fa_front, fa_left, fb_bottom, fb_right, fb_left]
    )
    gate("probe_faces", all_faces, f"cyl={fa_cyl is not None}")
    if not all_faces:
        return False

    def make_face_ref(face_data):
        ref = {"normal": face_data["normal"], "centroid": face_data["centroid"]}
        if face_data.get("is_cylinder"):
            ref["is_cylinder"] = True
        if face_data.get("persist_id"):
            ref["persist_id"] = face_data["persist_id"]
        return ref

    # Create assembly
    print("\n--- Step 3: Assembly ---")
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
        {"id": "part_b", "part": PART_B_PATH, "transform": {"xyz_mm": [0, 0, 25]}},
    ]
    placed, place_err = place_components(sw, asm_doc, components, mod=mod)
    gate("place_components", place_err is None, f"placed={len(placed)}")
    if place_err:
        return False

    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    # === Mate 1: Tangent ===
    print("\n--- Mate 1: Tangent ---")
    tangent_spec = {
        "type": "tangent",
        "alignment": "aligned",
        "a": {"component": "part_a", "face_ref": make_face_ref(fa_cyl)},
        "b": {"component": "part_b", "face_ref": make_face_ref(fb_right)},
    }
    feat, err = create_mate(asm_doc, placed, tangent_spec, mod=mod)
    gate("tangent", feat is not None, f"error={err}")
    results["per_mate_results"].append(
        {"type": "tangent", "created": feat is not None, "error": err}
    )

    # === Mate 2: Angle (45°) ===
    print("\n--- Mate 2: Angle (45°) ---")
    angle_spec = {
        "type": "angle",
        "alignment": "aligned",
        "value_deg": 45.0,
        "a": {"component": "part_a", "face_ref": make_face_ref(fa_right)},
        "b": {"component": "part_b", "face_ref": make_face_ref(fb_right)},
    }
    feat2, err2 = create_mate(asm_doc, placed, angle_spec, mod=mod)
    gate("angle_45", feat2 is not None, f"error={err2}")
    results["per_mate_results"].append(
        {
            "type": "angle",
            "value_deg": 45.0,
            "created": feat2 is not None,
            "error": err2,
        }
    )

    # === Mate 3: Limit distance (5mm, limits 3-7mm) ===
    print("\n--- Mate 3: Limit distance (3-7mm) ---")
    limit_spec = {
        "type": "distance",
        "alignment": "aligned",
        "value_mm": 5.0,
        "limit": {"min_mm": 3.0, "max_mm": 7.0},
        "a": {"component": "part_a", "face_ref": make_face_ref(fa_top)},
        "b": {"component": "part_b", "face_ref": make_face_ref(fb_bottom)},
    }
    feat3, err3 = create_mate(asm_doc, placed, limit_spec, mod=mod)
    gate("limit_distance", feat3 is not None, f"error={err3}")
    results["per_mate_results"].append(
        {"type": "distance_limit", "created": feat3 is not None, "error": err3}
    )

    # === Mate 4: Width (groove=part_a sides, tab=part_b sides) ===
    print("\n--- Mate 4: Width ---")
    # Width uses WidthSelection + TabSelection, not EntitiesToMate
    groove_left = resolve_component_face(
        asm_doc,
        placed["part_a"],
        {"normal": [-1, 0, 0], "centroid": fa_left["centroid"]},
        mod=mod,
    )
    groove_right = resolve_component_face(
        asm_doc,
        placed["part_a"],
        {"normal": [1, 0, 0], "centroid": fa_right["centroid"]},
        mod=mod,
    )
    tab_left = resolve_component_face(
        asm_doc,
        placed["part_b"],
        {"normal": [-1, 0, 0], "centroid": fb_left["centroid"]},
        mod=mod,
    )
    tab_right = resolve_component_face(
        asm_doc,
        placed["part_b"],
        {"normal": [1, 0, 0], "centroid": fb_right["centroid"]},
        mod=mod,
    )

    width_resolved = all([groove_left.ok, groove_right.ok, tab_left.ok, tab_right.ok])
    gate("width_faces_resolved", width_resolved, "")

    width_created = False
    if width_resolved:
        try:
            md = typed_asm.CreateMateData(11)  # swMateWIDTH
            w_iface = typed_qi(md, "IWidthMateFeatureData", module=mod)
            w_iface.WidthSelection = w32.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
                (groove_left.entity, groove_right.entity),
            )
            w_iface.TabSelection = w32.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
                (tab_left.entity, tab_right.entity),
            )
            mate_ret = typed_asm.CreateMate(md)
            width_created = mate_ret is not None and not isinstance(mate_ret, int)
            gate(
                "width_mate",
                width_created,
                f"ret={type(mate_ret).__name__ if mate_ret else None}",
            )
        except Exception as e:
            gate("width_mate", False, f"raised: {type(e).__name__}: {e}")

    results["per_mate_results"].append({"type": "width", "created": width_created})

    # === verify_mates ===
    print("\n--- Step 4: verify_mates ---")
    try:
        asm_doc.ForceRebuild3(True)
    except Exception:
        pass

    vm = verify_mates(asm_doc, mod=mod)
    print(f"  {len(vm)} mates found:")
    for m in vm:
        print(
            f"    {m['name']}: type={m['type']}, solved={m['solved']}, "
            f"error_code={m['error_code']}"
        )

    all_solved = len(vm) >= 4 and all(m.get("solved") for m in vm)
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
    pythoncom.CoInitialize()
    try:
        ok = run()
        results["overall"] = "GREEN" if ok else "FAIL"
        results["verdict"] = (
            "All four Phase-3 mate types created and verified solved"
            if ok
            else "Some mates failed or unsolved"
        )
    finally:
        pythoncom.CoUninitialize()

    save_results()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
