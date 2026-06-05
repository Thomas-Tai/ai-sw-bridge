"""Phase-3 Slice 2C spike: Width mate characterization.

swMateWIDTH(=11) takes TWO reference SETS (tabs + groove), not a
symmetric 2-entity pair. IWidthMateFeatureData has WidthSelection /
TabSelection + ConstraintType.

This spike characterizes whether the width mate pipeline works through
the existing create_mate pattern, or if it needs a separate code path.

If the 4-reference marshaling resists → DEFER (like edge-flange/miter).

Prereq: SOLIDWORKS 2024 SP1 running.
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
RESULTS_PATH = WORKTREE / "spikes" / "v0_20" / "_results" / "phase3_2C_pae.json"

results: dict[str, Any] = {
    "pae": "phase3_slice2C",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "characterization": {},
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


def run() -> str:
    print("=" * 70)
    print("Phase-3 Slice 2C: Width mate characterization")
    print("=" * 70)

    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.sw_com import get_sw_app

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

    # Create assembly
    import glob
    asm_templates = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT"
    )
    asm_doc = sw.NewDocument(asm_templates[0], 0, 0.1, 0.1)
    if asm_doc is None:
        gate("asm_create", False, "NewDocument returned None")
        return "WALL"

    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    # Characterization 1: CreateMateData(11) — width
    print("\n--- Characterization 1: CreateMateData(11) ---")
    try:
        md = typed_asm.CreateMateData(11)
        gate("create_mate_data_width", md is not None, f"md={type(md).__name__ if md else None}")
    except Exception as e:
        gate("create_mate_data_width", False, f"raised: {e}")
        md = None

    if md is None:
        return "WALL"

    # Characterization 2: QI to IWidthMateFeatureData
    print("\n--- Characterization 2: IWidthMateFeatureData ---")
    try:
        w_iface = typed_qi(md, "IWidthMateFeatureData", module=mod)
        gate("qi_width", True, f"type={type(w_iface).__name__}")
    except Exception as e:
        gate("qi_width", False, f"raised: {e}")
        return "WALL"

    # Characterization 3: Property types
    print("\n--- Characterization 3: Width mate properties ---")
    props_info = {}
    for prop_name in ["WidthSelection", "TabSelection", "ConstraintType",
                       "DistanceFromEnd", "PercentDistanceFromEnd", "FlipDimension"]:
        try:
            val = getattr(w_iface, prop_name)
            props_info[prop_name] = {
                "value": repr(val),
                "type": type(val).__name__,
                "is_method": callable(val) and not isinstance(val, (int, float, bool, str)),
            }
            print(f"  {prop_name}: {repr(val)[:80]} ({type(val).__name__})")
        except Exception as e:
            try:
                val = getattr(w_iface, prop_name)()
                props_info[prop_name] = {
                    "value": repr(val),
                    "type": type(val).__name__,
                    "accessed_as": "method_call",
                }
                print(f"  {prop_name}(): {repr(val)[:80]} ({type(val).__name__})")
            except Exception as e2:
                props_info[prop_name] = {
                    "error": f"prop: {e}, call: {e2}",
                }
                print(f"  {prop_name}: ERROR — prop: {e}, call: {e2}")

    results["characterization"]["properties"] = props_info

    # Characterization 4: Can we set WidthSelection/TabSelection?
    print("\n--- Characterization 4: Set WidthSelection/TabSelection ---")
    # Width mate needs planar faces. Let me create a simple box part and test.
    from ai_sw_bridge.spec.builder import build as part_build

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    PART_A_PATH = str(_tmp / f"phase3_width_{_ts}_a.SLDPRT")
    PART_B_PATH = str(_tmp / f"phase3_width_{_ts}_b.SLDPRT")

    # Part A: a box (the "groove" reference)
    PART_SPEC_A = {
        "schema_version": 1,
        "name": "WidthGroove",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front",
             "width": 40.0, "height": 10.0},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }

    # Part B: a narrower box (the "tab" reference)
    PART_SPEC_B = {
        "schema_version": 1,
        "name": "WidthTab",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front",
             "width": 20.0, "height": 10.0},
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }

    for label, path, spec in [("A", PART_A_PATH, PART_SPEC_A), ("B", PART_B_PATH, PART_SPEC_B)]:
        print(f"  Building Part {label}...")
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
        gate(f"build_part_{label.lower()}", r.ok and os.path.isfile(path),
             f"ok={r.ok}")

    if not os.path.isfile(PART_A_PATH) or not os.path.isfile(PART_B_PATH):
        gate("parts_built", False, "Part build failed")
        return "PARTIAL"

    # Probe faces for width mate
    from ai_sw_bridge.com.earlybind import typed_extension
    def get_planar_faces(part_path, normal_target):
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
            result = []
            for face in faces:
                iface = typed(face, "IFace2", module=mod)
                surf = iface.GetSurface()
                isurf = typed(surf, "ISurface", module=mod)
                if not bool(isurf.IsPlane()):
                    continue
                n = list(iface.Normal)
                if all(abs(n[i] - normal_target[i]) < 0.01 for i in range(3)):
                    pid = None
                    try:
                        pid_bytes = ext.GetPersistReference3(face)
                        if pid_bytes:
                            pid = base64.b64encode(bytes(pid_bytes)).decode("ascii")
                    except Exception:
                        pass
                    bbox = iface.GetBox()
                    cx = (bbox[0] + bbox[3]) / 2.0
                    cy = (bbox[1] + bbox[4]) / 2.0
                    cz = (bbox[2] + bbox[5]) / 2.0
                    result.append({
                        "entity": face,
                        "persist_id": pid,
                        "centroid": [round(cx * 1000, 3), round(cy * 1000, 3), round(cz * 1000, 3)],
                        "normal": [round(n, 6) for n in n],
                    })
            return result
        finally:
            title = doc.GetTitle() if callable(doc.GetTitle) else doc.GetTitle
            sw.CloseDoc(title)

    # Get side faces (left/right = ±x normal) for width mate
    faces_a_left = get_planar_faces(PART_A_PATH, [-1, 0, 0])
    faces_a_right = get_planar_faces(PART_A_PATH, [1, 0, 0])
    faces_b_left = get_planar_faces(PART_B_PATH, [-1, 0, 0])
    faces_b_right = get_planar_faces(PART_B_PATH, [1, 0, 0])

    print(f"\n  Groove left faces: {len(faces_a_left)}, right: {len(faces_a_right)}")
    print(f"  Tab left faces: {len(faces_b_left)}, right: {len(faces_b_right)}")

    has_faces = all([faces_a_left, faces_a_right, faces_b_left, faces_b_right])
    gate("width_faces", has_faces, f"groove L={len(faces_a_left)}, R={len(faces_a_right)}, "
         f"tab L={len(faces_b_left)}, R={len(faces_b_right)}")

    if not has_faces:
        return "PARTIAL"

    # Try setting WidthSelection and TabSelection
    print("\n--- Characterization 5: Try to set WidthSelection + TabSelection ---")

    # Place components first
    from ai_sw_bridge.assembly.handlers import place_components

    components = [
        {"id": "groove", "part": PART_A_PATH, "transform": {"xyz_mm": [0, 0, 0]}},
        {"id": "tab", "part": PART_B_PATH, "transform": {"xyz_mm": [0, 0, 15]}},
    ]
    placed, place_err = place_components(sw, asm_doc, components, mod=mod)
    gate("place_components", place_err is None, f"placed={len(placed)}")
    if place_err:
        return "PARTIAL"

    # Get component faces via resolve_component_face
    from ai_sw_bridge.assembly.face_resolver import resolve_component_face

    groove_comp = placed["groove"]
    tab_comp = placed["tab"]

    # Resolve groove left and right faces
    groove_left_ref = {"normal": [-1, 0, 0], "centroid": faces_a_left[0]["centroid"]}
    groove_right_ref = {"normal": [1, 0, 0], "centroid": faces_a_right[0]["centroid"]}
    tab_left_ref = {"normal": [-1, 0, 0], "centroid": faces_b_left[0]["centroid"]}
    tab_right_ref = {"normal": [1, 0, 0], "centroid": faces_b_right[0]["centroid"]}

    groove_left = resolve_component_face(asm_doc, groove_comp, groove_left_ref, mod=mod)
    groove_right = resolve_component_face(asm_doc, groove_comp, groove_right_ref, mod=mod)
    tab_left = resolve_component_face(asm_doc, tab_comp, tab_left_ref, mod=mod)
    tab_right = resolve_component_face(asm_doc, tab_comp, tab_right_ref, mod=mod)

    all_resolved = all([groove_left.ok, groove_right.ok, tab_left.ok, tab_right.ok])
    gate("resolve_faces", all_resolved,
         f"groove_L={groove_left.ok}, groove_R={groove_right.ok}, "
         f"tab_L={tab_left.ok}, tab_R={tab_right.ok}")

    if not all_resolved:
        return "PARTIAL"

    # Try setting WidthSelection = groove faces, TabSelection = tab faces
    try:
        width_faces = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
            (groove_left.entity, groove_right.entity)
        )
        tab_faces = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
            (tab_left.entity, tab_right.entity)
        )

        w_iface.WidthSelection = width_faces
        print(f"  WidthSelection set OK")
        gate("set_width_selection", True, "WidthSelection accepted 2 groove faces")

        w_iface.TabSelection = tab_faces
        print(f"  TabSelection set OK")
        gate("set_tab_selection", True, "TabSelection accepted 2 tab faces")

        # Try CreateMate
        mate_ret = typed_asm.CreateMate(md)
        mate_ok = mate_ret is not None and not isinstance(mate_ret, int)
        gate("create_width_mate", mate_ok,
             f"mate_ret={type(mate_ret).__name__ if mate_ret else None}")

        if mate_ok:
            # Verify the mate is solved
            from ai_sw_bridge.assembly.handlers import verify_mates
            try:
                asm_doc.ForceRebuild3(True)
            except Exception:
                pass
            vm = verify_mates(asm_doc, mod=mod)
            results["verify_mates"] = vm
            print(f"\n  verify_mates: {len(vm)} mates:")
            for m in vm:
                print(f"    {m['name']}: type={m['type']}, solved={m['solved']}, "
                      f"error_code={m['error_code']}")
            all_solved = len(vm) > 0 and all(m.get("solved") for m in vm)
            gate("width_mate_solved", all_solved,
                 f"total={len(vm)}, solved={sum(1 for m in vm if m.get('solved'))}")
            if all_solved:
                results["overall"] = "GREEN"
                return "GREEN"
            else:
                results["overall"] = "PARTIAL"
                return "PARTIAL"
        else:
            # Try to read error status
            try:
                mfd = typed_qi(md, "IMateFeatureData", module=mod)
                es = mfd.ErrorStatus
                print(f"  ErrorStatus: {es}")
            except Exception:
                pass
            results["overall"] = "PARTIAL"
            return "PARTIAL"

    except Exception as e:
        gate("width_mate_pipeline", False, f"raised: {type(e).__name__}: {e}")
        results["overall"] = "WALL"
        results["characterization"]["wall"] = str(e)[:300]
        return "WALL"
    finally:
        try:
            title = asm_doc.GetTitle() if callable(asm_doc.GetTitle) else asm_doc.GetTitle
            sw.CloseDoc(title)
        except Exception:
            pass


def main() -> int:
    pythoncom.CoInitialize()
    try:
        verdict = run()
    finally:
        pythoncom.CoUninitialize()

    if verdict == "GREEN":
        results.setdefault("overall", "GREEN")
        results["verdict"] = "Width mate pipeline works — full implementation possible"
    elif verdict == "PARTIAL":
        results.setdefault("overall", "PARTIAL")
        results["verdict"] = "Width mate partially characterized — DEFERRED"
    else:
        results.setdefault("overall", "DEFERRED")
        results["verdict"] = (
            "Width mate DEFERRED — 4-reference marshaling (WidthSelection + "
            "TabSelection) needs a separate code path from the symmetric "
            "EntitiesToMate pattern. Angle/tangent/limit is a complete "
            "shippable Phase-3 without width."
        )

    save_results()
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
