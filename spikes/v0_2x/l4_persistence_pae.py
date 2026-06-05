"""Wave-14 Slice 5: L4 assembly persistence production PAE.

Exercises the full propose → dry_run → commit pipeline on a live SW seat,
then verifies the manifest v2 sidecar is lossless:

  1. Build a prebuilt part (component A, via ``part``).
  2. Write a part_spec .aisw.json (component B, via ``part_spec``).
  3. Author an assembly spec with both components + a coincident mate.
  4. Run ``sw_propose_assembly → sw_dry_run_assembly → sw_commit_assembly``.
  5. Reload the manifest sidecar via ``AssemblyManifest.load()``.
  6. Verify: ``reloaded.to_spec() == authored_spec`` (lossless),
     live sw_names populated, provenance sha256 matches.

Prereq: SOLIDWORKS 2024 SP1 running.
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
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "l4_persistence_pae.json"
)

results: dict[str, Any] = {
    "pae": "w14_l4_persistence",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
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
    print("Wave-14 Slice 5: L4 persistence production PAE")
    print("=" * 70)

    from ai_sw_bridge.assembly.storage import AssemblyManifest, sha256_of_file
    from ai_sw_bridge.mutate import (
        sw_propose_assembly,
        sw_dry_run_assembly,
        sw_commit_assembly,
    )
    from ai_sw_bridge.spec.builder import build as part_build

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # --- Build prebuilt part (component A) ---
    print("\n--- Building prebuilt part (component A) ---")
    PART_A_PATH = str(_tmp / f"w14_l4_{_ts}_plateA.SLDPRT")
    SPEC_A = {
        "schema_version": 1,
        "name": "PlateA",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK",
             "plane": "Front", "width": 40.0, "height": 30.0},
            {"type": "boss_extrude_blind", "name": "EX",
             "sketch": "SK", "depth": 5.0},
        ],
    }
    r = part_build(SPEC_A, save_as=PART_A_PATH, save_format="current",
                   no_dim=True)
    gate("build_part_a", r.ok and os.path.isfile(PART_A_PATH), f"ok={r.ok}")

    if not os.path.isfile(PART_A_PATH):
        save_results()
        return "WALL"

    # --- Write part_spec for component B ---
    print("\n--- Writing part_spec (component B) ---")
    PART_B_SPEC_PATH = str(_tmp / f"w14_l4_{_ts}_plateB.aisw.json")
    SPEC_B = {
        "schema_version": 1,
        "name": "PlateB",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK",
             "plane": "Front", "width": 20.0, "height": 15.0},
            {"type": "boss_extrude_blind", "name": "EX",
             "sketch": "SK", "depth": 5.0},
        ],
    }
    Path(PART_B_SPEC_PATH).write_text(
        json.dumps(SPEC_B, indent=2), encoding="utf-8"
    )
    gate("write_part_spec_b", os.path.isfile(PART_B_SPEC_PATH))

    expected_sha = sha256_of_file(PART_B_SPEC_PATH)
    print(f"  part_spec sha256: {expected_sha}")

    # --- Author assembly spec ---
    print("\n--- Authoring assembly spec ---")
    assembly_spec = {
        "kind": "assembly",
        "name": "l4_test_assy",
        "components": [
            {
                "id": "plate_a",
                "part": PART_A_PATH,
                "transform": {"xyz_mm": [0, 0, 0]},
            },
            {
                "id": "plate_b",
                "part_spec": PART_B_SPEC_PATH,
                "transform": {"xyz_mm": [0, 0, 10]},
            },
        ],
        "mates": [
            {
                "type": "coincident",
                "alignment": "aligned",
                "a": {
                    "component": "plate_a",
                    "face_ref": {"normal": [0, 0, 1]},
                },
                "b": {
                    "component": "plate_b",
                    "face_ref": {"normal": [0, 0, -1]},
                },
            },
        ],
    }
    gate("authored_spec", True,
         f"components={len(assembly_spec['components'])}, "
         f"mates={len(assembly_spec['mates'])}")

    # --- Propose ---
    print("\n--- Propose ---")
    propose = sw_propose_assembly(assembly_spec)
    gate("propose_ok", propose.get("ok", False),
         f"proposal_id={propose.get('proposal_id')}")

    if not propose.get("ok"):
        results["propose_error"] = propose.get("error")
        save_results()
        return "WALL"

    pid = propose["proposal_id"]

    # --- Dry run ---
    print("\n--- Dry run ---")
    dry = sw_dry_run_assembly(pid)
    gate("dry_run_ok", dry.get("ok", False),
         f"state={dry.get('state')}, "
         f"resolved={len(dry.get('resolved_parts', {}))}")

    if not dry.get("ok"):
        results["dry_run_error"] = dry.get("error")
        save_results()
        return "WALL"

    # --- Commit ---
    print("\n--- Commit ---")
    ASM_PATH = str(_tmp / f"w14_l4_{_ts}.SLDASM")
    commit = sw_commit_assembly(pid, ASM_PATH)
    gate("commit_ok", commit.get("ok", False),
         f"state={commit.get('state')}, "
         f"components={commit.get('component_count')}, "
         f"mates={commit.get('mate_count')}")

    if not commit.get("ok"):
        results["commit_error"] = commit.get("error")
        save_results()
        return "WALL"

    # --- Verify manifest sidecar ---
    print("\n--- Verify manifest ---")
    manifest_path = commit.get("manifest_path")
    gate("manifest_path_set",
         manifest_path is not None,
         f"path={manifest_path}")

    if manifest_path is None:
        save_results()
        return "PARTIAL"

    gate("manifest_file_exists", os.path.isfile(manifest_path),
         f"size={os.path.getsize(manifest_path) if os.path.isfile(manifest_path) else 0}")

    if not os.path.isfile(manifest_path):
        save_results()
        return "PARTIAL"

    # --- Reload and verify lossless ---
    print("\n--- Lossless round-trip ---")
    reloaded = AssemblyManifest.load(Path(manifest_path))
    reloaded_spec = reloaded.to_spec()

    lossless = reloaded_spec == assembly_spec
    gate("lossless_to_spec", lossless,
         f"reloaded keys={sorted(reloaded_spec.keys())}, "
         f"authored keys={sorted(assembly_spec.keys())}")

    if not lossless:
        # Diff the specs for diagnosis
        for key in set(list(reloaded_spec.keys()) + list(assembly_spec.keys())):
            rv = reloaded_spec.get(key)
            av = assembly_spec.get(key)
            if rv != av:
                print(f"  DIFF at {key!r}:")
                print(f"    authored:  {av}")
                print(f"    reloaded:  {rv}")

    # --- Verify runtime overlay ---
    print("\n--- Runtime overlay ---")
    rt_comps = {c.id: c for c in reloaded.components}
    gate("runtime_has_both_components",
         len(rt_comps) == 2,
         f"ids={sorted(rt_comps.keys())}")

    for cid in ("plate_a", "plate_b"):
        comp = rt_comps.get(cid)
        if comp is None:
            gate(f"sw_name_{cid}", False, "component not in runtime")
            continue
        has_name = bool(comp.sw_name) and comp.sw_name != cid
        gate(f"sw_name_{cid}", has_name,
             f"sw_name={comp.sw_name!r}")

    # --- Verify provenance ---
    print("\n--- Provenance ---")
    comp_b = rt_comps.get("plate_b")
    if comp_b is not None:
        has_spec_path = comp_b.part_spec_path is not None
        gate("plate_b_has_part_spec_path", has_spec_path,
             f"path={comp_b.part_spec_path}")

        sha_match = (
            comp_b.part_spec_sha256 is not None
            and comp_b.part_spec_sha256 == expected_sha
        )
        gate("plate_b_sha256_match", sha_match,
             f"expected={expected_sha}, "
             f"got={comp_b.part_spec_sha256}")
    else:
        gate("plate_b_provenance", False, "plate_b not in runtime")

    # --- Verify on-disk paths are relative ---
    print("\n--- On-disk path portability ---")
    raw_json = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rt_section = raw_json.get("runtime", {})

    asm_path_on_disk = rt_section.get("assembly_path", "")
    gate("assembly_path_relative",
         not os.path.isabs(asm_path_on_disk),
         f"on_disk={asm_path_on_disk!r}")

    for rc in rt_section.get("components", []):
        pp = rc.get("part_path", "")
        gate(f"part_path_relative_{rc['id']}",
             not os.path.isabs(pp),
             f"on_disk={pp!r}")

    # Spec block untouched on disk
    spec_on_disk = raw_json.get("spec", {})
    gate("spec_block_verbatim_on_disk",
         spec_on_disk == assembly_spec,
         "spec block matches authored spec byte-for-byte")

    # --- Overall ---
    all_pass = all(g["ok"] for g in results["gates"].values())
    gate("OVERALL_GREEN", all_pass,
         f"{sum(1 for g in results['gates'].values() if g['ok'])}/"
         f"{len(results['gates'])} gates pass")

    return "GREEN" if all_pass else "PARTIAL"


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception as exc:
        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        verdict = "WALL"
    finally:
        results["verdict"] = verdict
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict == "GREEN" else 1)
