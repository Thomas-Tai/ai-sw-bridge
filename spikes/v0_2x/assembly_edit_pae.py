"""Wave-15 Slice 5: Assembly edit production PAE.

Exercises the edit pipeline on a live SW seat:
  1. Build 2 parts, commit assembly with 1 coincident mate.
  2. Edit: add_mate (parallel) → re-commit same path.
  3. Verify: new mate exists + solved, manifest to_spec() == edited spec.
  4. Edit: remove_mate → re-commit → verify mate gone.

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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "assembly_edit_pae.json"

results: dict[str, Any] = {
    "pae": "w15_assembly_edit",
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
    print("Wave-15 Slice 5: Assembly edit production PAE")
    print("=" * 70)

    from ai_sw_bridge.assembly.storage import AssemblyManifest
    from ai_sw_bridge.mutate import (
        sw_commit_assembly,
        sw_dry_run_assembly,
        sw_edit_assembly,
        sw_propose_assembly,
    )
    from ai_sw_bridge.spec.builder import build as part_build

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # --- Build parts ---
    print("\n--- Building parts ---")
    PART_A = str(_tmp / f"w15_edit_{_ts}_a.SLDPRT")
    PART_B = str(_tmp / f"w15_edit_{_ts}_b.SLDPRT")

    for label, path, w in [
        ("a", PART_A, 40.0),
        ("b", PART_B, 30.0),
    ]:
        spec = {
            "schema_version": 1,
            "name": f"Edit{label.upper()}",
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK",
                    "plane": "Front",
                    "width": w,
                    "height": 20.0,
                },
                {
                    "type": "boss_extrude_blind",
                    "name": "EX",
                    "sketch": "SK",
                    "depth": 10.0,
                },
            ],
        }
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
        gate(f"build_{label}", r.ok and os.path.isfile(path), f"ok={r.ok}")

    if not os.path.isfile(PART_A) or not os.path.isfile(PART_B):
        save_results()
        return "WALL"

    # --- Initial assembly: 2 components + 1 coincident mate ---
    print("\n--- Initial assembly ---")
    initial_spec = {
        "kind": "assembly",
        "name": "edit_test",
        "components": [
            {"id": "a", "part": PART_A, "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": PART_B, "transform": {"xyz_mm": [0, 0, 15]}},
        ],
        "mates": [
            {
                "type": "coincident",
                "alignment": "aligned",
                "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
                "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
            },
        ],
    }

    ASM_PATH = str(_tmp / f"w15_edit_{_ts}.SLDASM")

    p = sw_propose_assembly(initial_spec)
    gate("initial_propose", p.get("ok", False), f"pid={p.get('proposal_id')}")

    d = sw_dry_run_assembly(p["proposal_id"])
    gate("initial_dry_run", d.get("ok", False))

    c = sw_commit_assembly(p["proposal_id"], ASM_PATH)
    gate(
        "initial_commit",
        c.get("ok", False),
        f"components={c.get('component_count')}, " f"mates={c.get('mate_count')}",
    )

    manifest_path = c.get("manifest_path")
    gate(
        "initial_manifest", manifest_path is not None and os.path.isfile(manifest_path)
    )

    if not c.get("ok") or not manifest_path:
        save_results()
        return "WALL"

    # --- EDIT 1: add_mate (parallel) ---
    print("\n--- Edit 1: add_mate ---")
    add_mate_op = {
        "op": "add_mate",
        "mate": {
            "type": "parallel",
            "a": {"component": "a", "face_ref": {"normal": [0, 1, 0]}},
            "b": {"component": "b", "face_ref": {"normal": [0, 1, 0]}},
        },
    }

    edit1 = sw_edit_assembly(manifest_path, add_mate_op)
    gate("edit1_propose", edit1.get("ok", False), f"pid={edit1.get('proposal_id')}")

    if not edit1.get("ok"):
        results["edit1_error"] = edit1.get("error")
        save_results()
        return "PARTIAL"

    d1 = sw_dry_run_assembly(edit1["proposal_id"])
    gate("edit1_dry_run", d1.get("ok", False))

    c1 = sw_commit_assembly(edit1["proposal_id"], ASM_PATH)
    gate("edit1_commit", c1.get("ok", False), f"mates={c1.get('mate_count')}")

    # --- Verify edit 1: new mate exists + solved ---
    print("\n--- Verify edit 1 ---")
    m1_path = c1.get("manifest_path")
    gate("edit1_manifest", m1_path is not None and os.path.isfile(m1_path))

    if m1_path:
        reloaded = AssemblyManifest.load(Path(m1_path))
        edited_spec = reloaded.to_spec()
        gate(
            "edit1_lossless",
            edited_spec == edit1.get("spec", {}),
            "reloaded spec matches edited spec",
        )

        # Check the edited spec has 2 mates
        gate(
            "edit1_two_mates",
            len(edited_spec.get("mates", [])) == 2,
            f"mates={len(edited_spec.get('mates', []))}",
        )

    # Verify mates on the live assembly
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.assembly.handlers import verify_mates
    import win32com.client as w32

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # Reopen the assembly
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)
    asm_doc = ret[0] if isinstance(ret, tuple) else ret

    if asm_doc:
        try:
            vm = verify_mates(asm_doc, mod=mod)
            gate(
                "edit1_verify_mates",
                len(vm) == 2 and all(m.get("solved") for m in vm),
                f"mates={len(vm)}, " f"solved={sum(1 for m in vm if m.get('solved'))}",
            )

            mate_types = [m["type"] for m in vm]
            gate(
                "edit1_parallel_mate_exists",
                "MateParallel" in mate_types,
                f"types={mate_types}",
            )
        finally:
            try:
                t = asm_doc.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
    else:
        gate("edit1_reopen", False, "OpenDoc6 returned None")

    # --- EDIT 2: remove_mate (index 1 — the parallel we just added) ---
    print("\n--- Edit 2: remove_mate ---")
    remove_op = {"op": "remove_mate", "index": 1}

    edit2 = sw_edit_assembly(m1_path, remove_op)
    gate("edit2_propose", edit2.get("ok", False), f"pid={edit2.get('proposal_id')}")

    if edit2.get("ok"):
        d2 = sw_dry_run_assembly(edit2["proposal_id"])
        gate("edit2_dry_run", d2.get("ok", False))

        c2 = sw_commit_assembly(edit2["proposal_id"], ASM_PATH)
        gate("edit2_commit", c2.get("ok", False), f"mates={c2.get('mate_count')}")

        m2_path = c2.get("manifest_path")
        if m2_path:
            reloaded2 = AssemblyManifest.load(Path(m2_path))
            edited_spec2 = reloaded2.to_spec()
            gate(
                "edit2_lossless",
                edited_spec2 == edit2.get("spec", {}),
                "reloaded spec matches edited spec",
            )
            gate(
                "edit2_one_mate",
                len(edited_spec2.get("mates", [])) == 1,
                f"mates={len(edited_spec2.get('mates', []))}",
            )

    # --- Overall ---
    all_pass = all(g["ok"] for g in results["gates"].values())
    gate(
        "OVERALL_GREEN",
        all_pass,
        f"{sum(1 for g in results['gates'].values() if g['ok'])}/"
        f"{len(results['gates'])} gates pass",
    )

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
