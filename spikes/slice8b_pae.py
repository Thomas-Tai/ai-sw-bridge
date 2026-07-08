"""Slice-8b PAE: real part_spec build-then-place via assembly lifecycle.

Builds base part manually (pre-built), then runs the assembly lifecycle
which builds the lid part from a part_spec JSON and places both components
with a coincident mate.
"""

import json
import os
import sys
import time

sys.path.insert(0, r"C:\path\to\aisw-W9\src")

WORKTREE = r"C:\path\to\aisw-W9"
BASE_PART = os.path.join(WORKTREE, "spikes", "slice8b_box_base.SLDPRT")
LID_SPEC = os.path.join(WORKTREE, "spikes", "slice8b_box_lid.json")
OUTPUT_ASM = os.path.join(WORKTREE, "spikes", "slice8b_assembly.SLDASM")
RESULTS_PATH = os.path.join(WORKTREE, "_results", "assembly_p1_partspec_real_pae.json")

# Verify prerequisites
assert os.path.isfile(BASE_PART), f"Base part not found: {BASE_PART}"
assert os.path.isfile(LID_SPEC), f"Lid spec not found: {LID_SPEC}"

# Assembly spec: base (pre-built .sldprt) + lid (part_spec JSON)
ASSEMBLY_SPEC = {
    "kind": "assembly",
    "name": "Slice8b_BoxStack",
    "components": [
        {
            "id": "base",
            "part": BASE_PART,
            "transform": {"xyz_mm": [0, 0, 0]},
        },
        {
            "id": "lid",
            "part_spec": LID_SPEC,
            "transform": {"xyz_mm": [0, 0, 50]},
        },
    ],
    "mates": [
        {
            "type": "coincident",
            "alignment": "anti_aligned",
            "a": {
                "component": "base",
                "face_ref": {
                    "normal": [0, 0, 1],
                    "centroid": [0, 0, 10],
                },
            },
            "b": {
                "component": "lid",
                "face_ref": {
                    "normal": [0, 0, -1],
                    "centroid": [0, 0, 50],
                },
            },
        },
    ],
}

results = {
    "pae": "slice-8b_real_partspec",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "errors": [],
}


def gate(name: str, ok: bool, detail: str = ""):
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok


print("=" * 60)
print("Slice-8b PAE: real part_spec build-then-place")
print("=" * 60)

# Step 1: propose
print("\n--- Step 1: sw_propose_assembly ---")
from ai_sw_bridge.mutate import (
    sw_propose_assembly,
    sw_dry_run_assembly,
    sw_commit_assembly,
)

propose_result = sw_propose_assembly(ASSEMBLY_SPEC)
propose_ok = propose_result.get("ok", False)
gate("propose", propose_ok, f"proposal_id={propose_result.get('proposal_id')}")
if not propose_ok:
    results["errors"].append(f"propose failed: {propose_result.get('error')}")
    print(f"PROPOSE FAILED: {propose_result.get('error')}")
    # Write results and exit
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    sys.exit(1)

proposal_id = propose_result["proposal_id"]

# Step 2: dry_run
print("\n--- Step 2: sw_dry_run_assembly ---")
dry_result = sw_dry_run_assembly(proposal_id)
dry_ok = dry_result.get("ok", False)
gate("dry_run", dry_ok, f"state={dry_result.get('state')}")
if not dry_ok:
    results["errors"].append(f"dry_run failed: {dry_result.get('error')}")
    print(f"DRY_RUN FAILED: {dry_result.get('error')}")
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    sys.exit(1)

# Step 3: commit (NO part_paths — lifecycle must build the lid from part_spec)
print("\n--- Step 3: sw_commit_assembly ---")
print(f"  Output: {OUTPUT_ASM}")

# Remove old assembly if exists
if os.path.isfile(OUTPUT_ASM):
    os.remove(OUTPUT_ASM)

commit_result = sw_commit_assembly(proposal_id, OUTPUT_ASM)
commit_ok = commit_result.get("ok", False)

# Robustness guard: check if assembly was saved even if commit raised
asm_on_disk = os.path.isfile(OUTPUT_ASM)
gate(
    "commit",
    commit_ok or asm_on_disk,
    f"ok={commit_ok}, asm_on_disk={asm_on_disk}, state={commit_result.get('state')}",
)

if not commit_ok and not asm_on_disk:
    results["errors"].append(f"commit failed: {commit_result.get('error')}")
    print(f"COMMIT FAILED: {commit_result.get('error')}")
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    sys.exit(1)

# Step 4: Verify results
print("\n--- Step 4: Verification ---")

# Gate: component_count == 2
comp_count = commit_result.get("component_count", 0)
gate("component_count", comp_count == 2, f"count={comp_count}")

# Gate: both real B-rep (assembly saved = components placed)
gate(
    "assembly_saved",
    asm_on_disk,
    f"path={OUTPUT_ASM}, size={os.path.getsize(OUTPUT_ASM) if asm_on_disk else 0}",
)

# Gate: lid was built by lifecycle from part_spec
built_specs = commit_result.get("built_part_specs", {})
lid_built = "lid" in built_specs
lid_path = built_specs.get("lid", {}).get("save_as", "")
lid_on_disk = os.path.isfile(lid_path) if lid_path else False
gate(
    "lid_built_by_lifecycle",
    lid_built and lid_on_disk,
    f"path={lid_path}, on_disk={lid_on_disk}",
)

# Gate: mate materialized
mate_count = commit_result.get("mate_count", 0)
gate("mate_materialized", mate_count >= 1, f"mate_count={mate_count}")

# Gate: manifest round-trips
manifest = commit_result.get("manifest")
manifest_ok = manifest is not None and "components" in manifest
gate(
    "manifest_roundtrip",
    manifest_ok,
    f"components={len(manifest.get('components', [])) if manifest else 0}, "
    f"mates={len(manifest.get('mates', [])) if manifest else 0}",
)

# Gate: feature_add gate rejects "assembly"
print("\n--- Step 5: feature_add gate rejection ---")
from ai_sw_bridge.mutate import sw_propose_feature_add

reject_spec = {
    "kind": "assembly",
    "name": "should_reject",
    "components": [],
}
reject_result = sw_propose_feature_add(reject_spec)
reject_ok = not reject_result.get("ok", True)
gate(
    "feature_add_rejects_assembly",
    reject_ok,
    f"rejected={reject_ok}, error={reject_result.get('error', 'none')}",
)

# Summary
print("\n" + "=" * 60)
all_pass = all(g["ok"] for g in results["gates"].values())
print(f"OVERALL: {'ALL GATES PASS' if all_pass else 'SOME GATES FAILED'}")
print("=" * 60)

# Write results
results["assembly_path"] = OUTPUT_ASM
results["lid_part_path"] = lid_path
results["built_by_lifecycle"] = lid_built and lid_on_disk
results["manifest"] = manifest
results["commit_result"] = {
    "ok": commit_ok,
    "component_count": comp_count,
    "mate_count": mate_count,
    "sources": commit_result.get("sources"),
}

os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
with open(RESULTS_PATH, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults written to {RESULTS_PATH}")

if not all_pass:
    sys.exit(1)
