"""Phase-2 Completion PAE: all four mate types (distance, parallel, perpendicular, concentric).

Builds two identical parts (box base + cylindrical boss on top), authors an
assembly exercising all four Phase-2 mate types, runs the full lifecycle,
and verifies via verify_mates() that all four mates are solved:true.

Part geometry:
  - 30x30x10mm box base (planar faces for distance/parallel/perpendicular)
  - 5mm radius x 10mm tall cylindrical boss on top (for concentric)
"""
import json
import os
import sys
import time
import hashlib
import base64

sys.path.insert(0, r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\aisw-W10\src")

WORKTREE = r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\aisw-W10"
RESULTS_PATH = os.path.join(WORKTREE, "_results", "phase2_complete_pae.json")

results = {
    "pae": "phase2_complete",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "per_mate_results": [],
    "errors": [],
}

def gate(name, ok, detail=""):
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok

print("=" * 70)
print("Phase-2 Completion PAE: Four Mate Types")
print("=" * 70)

# Part spec: box + cylindrical boss
PART_SPEC = {
    "schema_version": 1,
    "name": "BoxWithBoss",
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

PART_A_PATH = os.path.join(WORKTREE, "spikes", "phase2_part_a.SLDPRT")
PART_B_PATH = os.path.join(WORKTREE, "spikes", "phase2_part_b.SLDPRT")
OUTPUT_ASM = os.path.join(WORKTREE, "spikes", "phase2_complete_v2.SLDASM")

# Clean up
for p in [PART_A_PATH, PART_B_PATH, OUTPUT_ASM]:
    if os.path.isfile(p):
        try:
            os.remove(p)
        except PermissionError:
            pass  # file locked by SW — will be overwritten

# Step 1: Build parts
print("\n--- Step 1: Build parts ---")
from ai_sw_bridge.spec.builder import build as part_build

for label, path in [("A", PART_A_PATH), ("B", PART_B_PATH)]:
    print(f"  Building Part {label}...")
    try:
        r = part_build(PART_SPEC, save_as=path, save_format="current", no_dim=True)
        gate(f"build_part_{label.lower()}", r.ok and os.path.isfile(path),
             f"ok={r.ok}, features={r.features_built}")
    except Exception as exc:
        on_disk = os.path.isfile(path)
        gate(f"build_part_{label.lower()}", on_disk, f"raised: {exc}, on_disk={on_disk}")

if not os.path.isfile(PART_A_PATH) or not os.path.isfile(PART_B_PATH):
    results["errors"].append("Part build failed")
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    sys.exit(1)

# Step 2: Probe faces
print("\n--- Step 2: Probe faces ---")
from ai_sw_bridge.sw_com import get_sw_app
from ai_sw_bridge.com.earlybind import typed, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module

sw = get_sw_app()
mod = wrapper_module()
tsw = typed(sw, "ISldWorks", module=mod)

def probe_faces(part_path):
    """Probe all faces, returning list of face dicts with is_cylinder flag."""
    ret = tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        doc = sw.ActiveDoc
        if doc is None:
            return []

    try:
        title = doc.GetTitle() if callable(doc.GetTitle) else doc.GetTitle
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

                face_list.append({
                    "face_idx": idx,
                    "is_cylinder": is_cyl,
                    "is_plane": is_plane,
                    "normal": [round(n, 6) for n in normal],
                    "centroid": [round(cx * 1000, 3), round(cy * 1000, 3), round(cz * 1000, 3)],
                    "persist_id": persist_id,
                })
            except Exception:
                pass
        return face_list
    finally:
        title = doc.GetTitle() if callable(doc.GetTitle) else doc.GetTitle
        sw.CloseDoc(title)

faces_a = probe_faces(PART_A_PATH)
faces_b = probe_faces(PART_B_PATH)
print(f"  Part A: {len(faces_a)} faces ({sum(1 for f in faces_a if f['is_cylinder'])} cylindrical)")
print(f"  Part B: {len(faces_b)} faces ({sum(1 for f in faces_b if f['is_cylinder'])} cylindrical)")

def find_planar(faces, normal_target, z_approx=None):
    for f in faces:
        if not f["is_plane"]:
            continue
        n = f["normal"]
        if all(abs(n[i] - normal_target[i]) < 0.01 for i in range(3)):
            if z_approx is not None:
                if abs(f["centroid"][2] - z_approx) < 5.0:
                    return f
            else:
                return f
    return None

def find_cylindrical(faces):
    for f in faces:
        if f["is_cylinder"]:
            return f
    return None

face_a_top = find_planar(faces_a, [0, 0, 1], z_approx=10)
face_a_right = find_planar(faces_a, [1, 0, 0])
face_a_front = find_planar(faces_a, [0, 1, 0])
face_b_bottom = find_planar(faces_b, [0, 0, -1], z_approx=0)
face_b_right = find_planar(faces_b, [1, 0, 0])
face_a_cyl = find_cylindrical(faces_a)
face_b_cyl = find_cylindrical(faces_b)

gate("probe_faces",
     all([face_a_top, face_b_bottom, face_a_right, face_b_right, face_a_cyl, face_b_cyl]),
     f"planar={all([face_a_top, face_b_bottom, face_a_right, face_b_right])}, "
     f"cyl_A={face_a_cyl is not None}, cyl_B={face_b_cyl is not None}")

# Step 3: Assembly spec with all four mate types
print("\n--- Step 3: Assembly spec ---")

def make_face_ref(face_data):
    """Build a face_ref dict from probed face data."""
    ref = {"normal": face_data["normal"], "centroid": face_data["centroid"]}
    if face_data.get("is_cylinder"):
        ref["is_cylinder"] = True
    if face_data.get("persist_id"):
        ref["persist_id"] = face_data["persist_id"]
    return ref

ASSEMBLY_SPEC = {
    "kind": "assembly",
    "name": "Phase2_Complete",
    "components": [
        {
            "id": "part_a",
            "part": PART_A_PATH,
            "transform": {"xyz_mm": [0, 0, 0]},
        },
        {
            "id": "part_b",
            "part": PART_B_PATH,
            "transform": {"xyz_mm": [0, 0, 15]},
        },
    ],
    "mates": [
        {
            "type": "distance",
            "alignment": "aligned",
            "value_mm": 5.0,
            "a": {"component": "part_a", "face_ref": make_face_ref(face_a_top)},
            "b": {"component": "part_b", "face_ref": make_face_ref(face_b_bottom)},
        },
        {
            "type": "parallel",
            "a": {"component": "part_a", "face_ref": make_face_ref(face_a_right)},
            "b": {"component": "part_b", "face_ref": make_face_ref(face_b_right)},
        },
        {
            "type": "perpendicular",
            "a": {"component": "part_a", "face_ref": make_face_ref(face_a_front or face_a_right)},
            "b": {"component": "part_b", "face_ref": make_face_ref(face_b_right)},
        },
        {
            "type": "concentric",
            "a": {"component": "part_a", "face_ref": make_face_ref(face_a_cyl)},
            "b": {"component": "part_b", "face_ref": make_face_ref(face_b_cyl)},
        },
    ],
}

gate("assembly_spec", True, f"2 components, {len(ASSEMBLY_SPEC['mates'])} mates")

# Step 4: Run lifecycle
print("\n--- Step 4: Lifecycle ---")
from ai_sw_bridge.mutate import (
    sw_propose_assembly,
    sw_dry_run_assembly,
    sw_commit_assembly,
)

propose_result = sw_propose_assembly(ASSEMBLY_SPEC)
propose_ok = propose_result.get("ok", False)
gate("propose", propose_ok, f"id={propose_result.get('proposal_id')}")

if not propose_ok:
    results["errors"].append(f"propose: {propose_result.get('error')}")
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    sys.exit(1)

proposal_id = propose_result["proposal_id"]
dry_result = sw_dry_run_assembly(proposal_id)
dry_ok = dry_result.get("ok", False)
gate("dry_run", dry_ok, f"state={dry_result.get('state')}")

if not dry_ok:
    results["errors"].append(f"dry_run: {dry_result.get('error')}")
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    sys.exit(1)

commit_result = sw_commit_assembly(proposal_id, OUTPUT_ASM)
commit_ok = commit_result.get("ok", False)
asm_on_disk = os.path.isfile(OUTPUT_ASM)
commit_error = commit_result.get("error", "")
gate("commit", commit_ok or asm_on_disk,
     f"ok={commit_ok}, on_disk={asm_on_disk}, error={commit_error[:200] if commit_error else 'none'}")

if commit_ok or asm_on_disk:
    gate("component_count", commit_result.get("component_count", 0) == 2,
         f"count={commit_result.get('component_count')}")
    gate("mate_count", commit_result.get("mate_count", 0) >= 4,
         f"count={commit_result.get('mate_count')}")

# Step 5: verify_mates() — the new pass bar
print("\n--- Step 5: verify_mates() ---")
if os.path.isfile(OUTPUT_ASM):
    from ai_sw_bridge.assembly.handlers import verify_mates

    # Find the assembly in open documents first
    asm_doc = None
    try:
        docs = sw.GetDocuments()
        if docs:
            for d in docs:
                t = d.GetTitle() if callable(d.GetTitle) else d.GetTitle
                if "phase2_complete_v2" in t.lower():
                    asm_doc = d
                    break
    except Exception:
        pass

    # If not found, open it
    if asm_doc is None:
        ret = tsw.OpenDoc6(os.path.abspath(OUTPUT_ASM), 2, 1, "", 0, 0)
        asm_doc = ret[0] if isinstance(ret, tuple) else ret

    if asm_doc is not None:
        title = asm_doc.GetTitle() if callable(asm_doc.GetTitle) else asm_doc.GetTitle
        print(f"  Verifying assembly: {title}")

        # Debug: dump feature tree
        try:
            fm = asm_doc.FeatureManager
            feats = fm.GetFeatures(True)
            print(f"  Features: {len(feats) if feats else 0}")
            if feats:
                for f in feats:
                    try:
                        ifeat = typed(f, "IFeature", module=mod)
                        t = ifeat.GetTypeName2()
                        n = f.Name if hasattr(f, "Name") else "?"
                        print(f"    {n:30} type={t}")
                        if t == "MateGroup":
                            sub = f.GetFirstSubFeature()
                            count = 0
                            while sub is not None:
                                count += 1
                                try:
                                    sub_ifeat = typed(sub, "IFeature", module=mod)
                                    st = sub_ifeat.GetTypeName2()
                                    sn = sub.Name if hasattr(sub, "Name") else "?"
                                    print(f"      sub: {sn:25} type={st}")
                                except:
                                    print(f"      sub #{count}: (error reading)")
                                sub = sub.GetNextSubFeature()
                            print(f"      (total sub-features: {count})")
                    except Exception as e:
                        print(f"    (error: {e})")
        except Exception as e:
            print(f"  Feature dump error: {e}")

        per_mate = verify_mates(asm_doc, mod=mod)
        results["per_mate_results"] = per_mate

        gate("verify_mates_nonempty", len(per_mate) >= 4,
             f"found {len(per_mate)} mates")

        all_solved = len(per_mate) >= 4 and all(m.get("solved", False) for m in per_mate)
        gate("all_mates_solved", all_solved,
             f"solved={[m.get('solved') for m in per_mate]}, "
             f"types={[m.get('type') for m in per_mate]}")

        for m in per_mate:
            print(f"    {m['name']:20} {m['type']:20} error={m['error_code']} solved={m['solved']}")
    else:
        gate("verify_mates_nonempty", False, "could not open assembly doc")
        gate("all_mates_solved", False, "no assembly doc")

# Summary
print("\n" + "=" * 70)
all_pass = all(g["ok"] for g in results["gates"].values())
print(f"OVERALL: {'ALL GATES PASS' if all_pass else 'SOME GATES FAILED'}")
print(f"Gates: {sum(1 for g in results['gates'].values() if g['ok'])}/{len(results['gates'])} passed")
print("=" * 70)

results["assembly_path"] = OUTPUT_ASM
os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
with open(RESULTS_PATH, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults: {RESULTS_PATH}")

if not all_pass:
    sys.exit(1)
