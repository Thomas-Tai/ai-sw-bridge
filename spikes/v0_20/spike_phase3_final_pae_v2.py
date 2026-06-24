"""Phase-3 Final PAE v2: all four mate types on 3 components.

The v1 attempt over-constrained 2 parts with 4 mates. This version uses
3 components to distribute the constraints:

  - Part A: 30x30x10 box + cylindrical boss
  - Part B: 20x20x10 narrow box
  - Part C: 30x30x10 box (same as A without boss)

Mates (each on independent face pairs):
  1. Tangent: A.cyl + B.right
  2. Angle (45°): A.right + C.front
  3. Limit distance (5mm, 3-7): A.top + B.bottom
  4. Width: A.left+right (groove) + C.left+right (tab)
"""

from __future__ import annotations

import base64
import json
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
    "pae": "phase3_final_v2",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "per_mate_results": [],
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


def probe_faces(part_path, tsw, sw, mod):
    from ai_sw_bridge.com.earlybind import typed, typed_extension

    ret = tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        return []
    try:
        from ai_sw_bridge.com.earlybind import typed as _typed

        tpart = _typed(doc, "IPartDoc", module=mod)
        bodies = tpart.GetBodies2(0, True)
        if not bodies:
            return []
        faces = bodies[0].GetFaces()
        ext = typed_extension(doc, module=mod)
        face_list = []
        for idx, face in enumerate(faces):
            try:
                iface = _typed(face, "IFace2", module=mod)
                surf = iface.GetSurface()
                isurf = _typed(surf, "ISurface", module=mod)
                is_cyl = bool(isurf.IsCylinder())
                is_plane = bool(isurf.IsPlane())
                normal = list(iface.Normal) if is_plane else [0, 0, 0]
                bbox = iface.GetBox()
                cx, cy, cz = (
                    (bbox[0] + bbox[3]) / 2,
                    (bbox[1] + bbox[4]) / 2,
                    (bbox[2] + bbox[5]) / 2,
                )
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


def make_face_ref(fd):
    ref = {"normal": fd["normal"], "centroid": fd["centroid"]}
    if fd.get("is_cylinder"):
        ref["is_cylinder"] = True
    if fd.get("persist_id"):
        ref["persist_id"] = fd["persist_id"]
    return ref


def run() -> bool:
    print("=" * 70)
    print("Phase-3 Final PAE v2: Tangent + Angle + Limit + Width (3 components)")
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

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    PART_A_SPEC = {
        "schema_version": 1,
        "name": "BoxWithCyl",
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
        "name": "NarrowBox",
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
    PART_C_SPEC = {
        "schema_version": 1,
        "name": "WideBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 30.0,
                "height": 30.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }

    PART_A_PATH = str(_tmp / f"p3f2_{_ts}_a.SLDPRT")
    PART_B_PATH = str(_tmp / f"p3f2_{_ts}_b.SLDPRT")
    PART_C_PATH = str(_tmp / f"p3f2_{_ts}_c.SLDPRT")

    print("\n--- Step 1: Build parts ---")
    for label, path, spec in [
        ("A", PART_A_PATH, PART_A_SPEC),
        ("B", PART_B_PATH, PART_B_SPEC),
        ("C", PART_C_PATH, PART_C_SPEC),
    ]:
        print(f"  Building Part {label}...")
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
        gate(f"build_part_{label.lower()}", r.ok and os.path.isfile(path), f"ok={r.ok}")

    if not all(os.path.isfile(p) for p in [PART_A_PATH, PART_B_PATH, PART_C_PATH]):
        gate("parts_built", False, "Build failed")
        return False

    print("\n--- Step 2: Probe faces ---")
    faces_a = probe_faces(PART_A_PATH, tsw, sw, mod)
    faces_b = probe_faces(PART_B_PATH, tsw, sw, mod)
    faces_c = probe_faces(PART_C_PATH, tsw, sw, mod)

    fa_cyl = find_cylindrical(faces_a)
    fa_top = find_planar(faces_a, [0, 0, 1], z_approx=10)
    fa_right = find_planar(faces_a, [1, 0, 0])
    fa_left = find_planar(faces_a, [-1, 0, 0])
    fb_bottom = find_planar(faces_b, [0, 0, -1], z_approx=0)
    fb_right = find_planar(faces_b, [1, 0, 0])
    fc_front = find_planar(faces_c, [0, 1, 0])
    fc_left = find_planar(faces_c, [-1, 0, 0])
    fc_right = find_planar(faces_c, [1, 0, 0])

    all_faces = all(
        [
            fa_cyl,
            fa_top,
            fa_right,
            fa_left,
            fb_bottom,
            fb_right,
            fc_front,
            fc_left,
            fc_right,
        ]
    )
    gate(
        "probe_faces", all_faces, f"A:{len(faces_a)} B:{len(faces_b)} C:{len(faces_c)}"
    )
    if not all_faces:
        return False

    print("\n--- Step 3: Assembly ---")
    import glob

    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    asm_doc = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    components = [
        {"id": "part_a", "part": PART_A_PATH, "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "part_b", "part": PART_B_PATH, "transform": {"xyz_mm": [0, 0, 25]}},
        {"id": "part_c", "part": PART_C_PATH, "transform": {"xyz_mm": [50, 0, 0]}},
    ]
    placed, place_err = place_components(sw, asm_doc, components, mod=mod)
    gate("place", place_err is None, f"placed={len(placed)}")
    if place_err:
        return False

    # Mate 1: Tangent (A.cyl + B.right) — constrains B against A
    print("\n--- Mate 1: Tangent ---")
    f, e = create_mate(
        asm_doc,
        placed,
        {
            "type": "tangent",
            "alignment": "aligned",
            "a": {"component": "part_a", "face_ref": make_face_ref(fa_cyl)},
            "b": {"component": "part_b", "face_ref": make_face_ref(fb_right)},
        },
        mod=mod,
    )
    gate("tangent", f is not None, f"err={e}")

    # Mate 2: Angle 45° (A.right + C.front) — constrains C against A
    print("\n--- Mate 2: Angle 45° ---")
    f2, e2 = create_mate(
        asm_doc,
        placed,
        {
            "type": "angle",
            "alignment": "aligned",
            "value_deg": 45.0,
            "a": {"component": "part_a", "face_ref": make_face_ref(fa_right)},
            "b": {"component": "part_c", "face_ref": make_face_ref(fc_front)},
        },
        mod=mod,
    )
    gate("angle_45", f2 is not None, f"err={e2}")

    # Mate 3: Limit distance (A.top + B.bottom, 5mm, 3-7)
    print("\n--- Mate 3: Limit distance ---")
    f3, e3 = create_mate(
        asm_doc,
        placed,
        {
            "type": "distance",
            "alignment": "aligned",
            "value_mm": 5.0,
            "limit": {"min_mm": 3.0, "max_mm": 7.0},
            "a": {"component": "part_a", "face_ref": make_face_ref(fa_top)},
            "b": {"component": "part_b", "face_ref": make_face_ref(fb_bottom)},
        },
        mod=mod,
    )
    gate("limit_dist", f3 is not None, f"err={e3}")

    # Mate 4: Width (A groove + C tab)
    print("\n--- Mate 4: Width ---")
    g_l = resolve_component_face(
        asm_doc,
        placed["part_a"],
        {"normal": [-1, 0, 0], "centroid": fa_left["centroid"]},
        mod=mod,
    )
    g_r = resolve_component_face(
        asm_doc,
        placed["part_a"],
        {"normal": [1, 0, 0], "centroid": fa_right["centroid"]},
        mod=mod,
    )
    t_l = resolve_component_face(
        asm_doc,
        placed["part_c"],
        {"normal": [-1, 0, 0], "centroid": fc_left["centroid"]},
        mod=mod,
    )
    t_r = resolve_component_face(
        asm_doc,
        placed["part_c"],
        {"normal": [1, 0, 0], "centroid": fc_right["centroid"]},
        mod=mod,
    )

    width_ok = False
    if all([g_l.ok, g_r.ok, t_l.ok, t_r.ok]):
        try:
            md = typed_asm.CreateMateData(11)
            w = typed_qi(md, "IWidthMateFeatureData", module=mod)
            w.WidthSelection = w32.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (g_l.entity, g_r.entity)
            )
            w.TabSelection = w32.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (t_l.entity, t_r.entity)
            )
            mr = typed_asm.CreateMate(md)
            width_ok = mr is not None and not isinstance(mr, int)
            gate("width", width_ok, f"ret={type(mr).__name__}")
        except Exception as exc:
            gate("width", False, f"raised: {exc}")
    else:
        gate("width_faces", False, "resolution failed")

    # verify_mates
    print("\n--- Step 4: verify_mates ---")
    try:
        asm_doc.ForceRebuild3(True)
    except Exception:
        pass

    vm = verify_mates(asm_doc, mod=mod)
    print(f"  {len(vm)} mates:")
    for m in vm:
        print(
            f"    {m['name']}: type={m['type']}, solved={m['solved']}, err={m['error_code']}"
        )

    results["per_mate_results"] = vm
    all_solved = len(vm) >= 4 and all(m.get("solved") for m in vm)
    gate(
        "all_solved",
        all_solved,
        f"total={len(vm)}, solved={sum(1 for m in vm if m.get('solved'))}",
    )

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
        results["overall"] = "GREEN" if ok else "PARTIAL"
        results["verdict"] = (
            "All 4 Phase-3 mate types solved on 3-component assembly"
            if ok
            else "Some mates over-defined or unsolved"
        )
    finally:
        pythoncom.CoUninitialize()
    save_results()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
