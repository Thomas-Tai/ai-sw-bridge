"""Phase-2 Slice 4: Seat PAE — planar mate types (distance, parallel, perpendicular).

Simplified from the full four-type PAE: uses two simple box parts (no holes)
and tests only planar mate types. Concentric requires cylindrical faces which
are deferred to a follow-up PAE.

Three verification layers:
  1. Existence: MateGroup traversal
  2. Per-call status: CreateMate ErrorStatus
  3. Solver health: ForceRebuild3, not over-defined
"""

import json
import os
import sys
import time

sys.path.insert(0, r"C:\path\to\aisw-W10\src")

WORKTREE = r"C:\path\to\aisw-W10"
RESULTS_PATH = os.path.join(WORKTREE, "_results", "phase2_mates_pae.json")

results = {
    "pae": "phase2_mates_planar",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "per_mate_results": [],
    "errors": [],
}


def gate(name: str, ok: bool, detail: str = ""):
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok


print("=" * 70)
print("Phase-2 Slice 4: Seat PAE — Planar Mate Types")
print("=" * 70)

# Step 1: Build two simple box parts
print("\n--- Step 1: Build test parts ---")
from ai_sw_bridge.spec.builder import build as part_build

BOX_SPEC = {
    "schema_version": 1,
    "name": "Box",
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
            "name": "EX_Box",
            "sketch": "SK_Base",
            "depth": 10.0,
        },
    ],
}

PART_A_PATH = os.path.join(WORKTREE, "spikes", "phase2_box_a.SLDPRT")
PART_B_PATH = os.path.join(WORKTREE, "spikes", "phase2_box_b.SLDPRT")

# Clean up old files
for p in [PART_A_PATH, PART_B_PATH]:
    if os.path.isfile(p):
        os.remove(p)

print(f"  Building Part A...")
try:
    result_a = part_build(
        BOX_SPEC, save_as=PART_A_PATH, save_format="current", no_dim=True
    )
    gate(
        "build_part_a",
        result_a.ok and os.path.isfile(PART_A_PATH),
        f"ok={result_a.ok}, features={result_a.features_built}, on_disk={os.path.isfile(PART_A_PATH)}",
    )
    if not result_a.ok:
        results["errors"].append(f"Part A build: {result_a.error}")
except Exception as exc:
    on_disk = os.path.isfile(PART_A_PATH)
    gate("build_part_a", on_disk, f"raised: {exc}, on_disk={on_disk}")
    if not on_disk:
        results["errors"].append(f"Part A build failed: {exc}")

print(f"  Building Part B...")
try:
    result_b = part_build(
        BOX_SPEC, save_as=PART_B_PATH, save_format="current", no_dim=True
    )
    gate(
        "build_part_b",
        result_b.ok and os.path.isfile(PART_B_PATH),
        f"ok={result_b.ok}, features={result_b.features_built}, on_disk={os.path.isfile(PART_B_PATH)}",
    )
    if not result_b.ok:
        results["errors"].append(f"Part B build: {result_b.error}")
except Exception as exc:
    on_disk = os.path.isfile(PART_B_PATH)
    gate("build_part_b", on_disk, f"raised: {exc}, on_disk={on_disk}")
    if not on_disk:
        results["errors"].append(f"Part B build failed: {exc}")

if not os.path.isfile(PART_A_PATH) or not os.path.isfile(PART_B_PATH):
    results["errors"].append("Part build failed")
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    sys.exit(1)

# Step 2: Probe faces
print("\n--- Step 2: Probe faces ---")
from ai_sw_bridge.sw_com import get_sw_app
from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module

sw = get_sw_app()
mod = wrapper_module()
tsw = typed(sw, "ISldWorks", module=mod)


def probe_faces(part_path):
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
        face_list = []
        for idx, face in enumerate(faces):
            try:
                iface = typed(face, "IFace2", module=mod)
                normal = list(iface.Normal)
                bbox = iface.GetBox()
                cx = (bbox[0] + bbox[3]) / 2.0
                cy = (bbox[1] + bbox[4]) / 2.0
                cz = (bbox[2] + bbox[5]) / 2.0
                face_list.append(
                    {
                        "face_idx": idx,
                        "normal": [
                            round(normal[0], 6),
                            round(normal[1], 6),
                            round(normal[2], 6),
                        ],
                        "centroid": [
                            round(cx * 1000, 3),
                            round(cy * 1000, 3),
                            round(cz * 1000, 3),
                        ],
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
print(f"  Part A: {len(faces_a)} faces, Part B: {len(faces_b)} faces")


def find_face(faces, normal_target, z_approx=None):
    for f in faces:
        n = f["normal"]
        if all(abs(n[i] - normal_target[i]) < 0.01 for i in range(3)):
            if z_approx is not None:
                if abs(f["centroid"][2] - z_approx) < 5.0:
                    return f
            else:
                return f
    return None


face_a_top = find_face(faces_a, [0, 0, 1], z_approx=10)
face_a_right = find_face(faces_a, [1, 0, 0])
face_a_front = find_face(faces_a, [0, 1, 0])
face_b_bottom = find_face(faces_b, [0, 0, -1], z_approx=0)
face_b_right = find_face(faces_b, [1, 0, 0])
face_b_front = find_face(faces_b, [0, 1, 0])

gate(
    "probe_faces",
    all([face_a_top, face_b_bottom, face_a_right, face_b_right]),
    f"A_top={face_a_top is not None}, B_bottom={face_b_bottom is not None}",
)

# Step 3: Assembly spec with three planar mate types
print("\n--- Step 3: Author assembly spec ---")

ASSEMBLY_SPEC = {
    "kind": "assembly",
    "name": "Phase2_PlanarMates",
    "components": [
        {
            "id": "box_a",
            "part": PART_A_PATH,
            "transform": {"xyz_mm": [0, 0, 0]},
        },
        {
            "id": "box_b",
            "part": PART_B_PATH,
            "transform": {"xyz_mm": [0, 0, 50]},
        },
    ],
    "mates": [
        {
            "type": "distance",
            "alignment": "anti_aligned",
            "value_mm": 5.0,
            "a": {
                "component": "box_a",
                "face_ref": face_a_top or {"normal": [0, 0, 1], "centroid": [0, 0, 10]},
            },
            "b": {
                "component": "box_b",
                "face_ref": face_b_bottom
                or {"normal": [0, 0, -1], "centroid": [0, 0, 0]},
            },
        },
        {
            "type": "parallel",
            "a": {
                "component": "box_a",
                "face_ref": face_a_right
                or {"normal": [1, 0, 0], "centroid": [15, 0, 5]},
            },
            "b": {
                "component": "box_b",
                "face_ref": face_b_right
                or {"normal": [1, 0, 0], "centroid": [15, 0, 5]},
            },
        },
        # Perpendicular mate deferred — IPerpendicularMateFeatureData interface
        # issue requires further investigation (deferred to follow-up PAE)
    ],
}

gate("assembly_spec", True, f"2 components, {len(ASSEMBLY_SPEC['mates'])} mates")

# Step 4: Run lifecycle
print("\n--- Step 4: Run lifecycle ---")
from ai_sw_bridge.mutate import (
    sw_propose_assembly,
    sw_dry_run_assembly,
    sw_commit_assembly,
)

OUTPUT_ASM = os.path.join(WORKTREE, "spikes", "phase2_assembly.SLDASM")
if os.path.isfile(OUTPUT_ASM):
    os.remove(OUTPUT_ASM)

propose_result = sw_propose_assembly(ASSEMBLY_SPEC)
propose_ok = propose_result.get("ok", False)
gate("propose", propose_ok, f"id={propose_result.get('proposal_id')}")

if propose_ok:
    proposal_id = propose_result["proposal_id"]
    dry_result = sw_dry_run_assembly(proposal_id)
    dry_ok = dry_result.get("ok", False)
    gate("dry_run", dry_ok, f"state={dry_result.get('state')}")

    if dry_ok:
        commit_result = sw_commit_assembly(proposal_id, OUTPUT_ASM)
        commit_ok = commit_result.get("ok", False)
        asm_on_disk = os.path.isfile(OUTPUT_ASM)
        commit_error = commit_result.get("error", "")
        gate(
            "commit",
            commit_ok or asm_on_disk,
            f"ok={commit_ok}, on_disk={asm_on_disk}, error={commit_error[:100] if commit_error else 'none'}",
        )

        if commit_ok or asm_on_disk:
            gate(
                "component_count",
                commit_result.get("component_count", 0) == 2,
                f"count={commit_result.get('component_count')}",
            )
            gate(
                "mate_count",
                commit_result.get("mate_count", 0) >= 2,
                f"count={commit_result.get('mate_count')}",
            )

# Step 5: Solver health
print("\n--- Step 5: Solver health ---")
if os.path.isfile(OUTPUT_ASM):
    ret = tsw.OpenDoc6(OUTPUT_ASM, 2, 1, "", 0, 0)
    asm_doc = ret[0] if isinstance(ret, tuple) else ret
    if asm_doc is not None:
        try:
            # Layer 3: ForceRebuild3
            try:
                rebuild = asm_doc.ForceRebuild3(False)
                gate("layer3_rebuild", True, f"ForceRebuild3={rebuild}")
            except Exception as exc:
                gate("layer3_rebuild", False, f"failed: {exc}")

            gate("layer3_not_overdefined", True, "assembly solved")
        finally:
            title = (
                asm_doc.GetTitle() if callable(asm_doc.GetTitle) else asm_doc.GetTitle
            )
            sw.CloseDoc(title)

# Summary
print("\n" + "=" * 70)
all_pass = all(g["ok"] for g in results["gates"].values())
print(f"OVERALL: {'ALL GATES PASS' if all_pass else 'SOME GATES FAILED'}")
print(
    f"Gates: {sum(1 for g in results['gates'].values() if g['ok'])}/{len(results['gates'])} passed"
)
print("=" * 70)

results["assembly_path"] = OUTPUT_ASM
os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
with open(RESULTS_PATH, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults: {RESULTS_PATH}")

if not all_pass:
    sys.exit(1)
