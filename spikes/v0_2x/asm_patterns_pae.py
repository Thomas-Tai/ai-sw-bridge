"""Wave-22 S3: Assembly mirror-components production PAE.

Exercises the production mirror handler end-to-end on a live SW seat:
  1. Build a box part.
  2. Author an assembly spec with one seed component + one mirror pattern.
  3. ``propose → dry_run → commit`` via the production lifecycle.
  4. Re-open the ``.SLDASM`` and verify ``GetComponentCount`` == 2
     (1 seed + 1 mirror) and the mirrored component is present.

Proves the W22 S1 spike recipe works through the full production pipeline.

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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "asm_patterns_pae.json"

results: dict[str, Any] = {
    "pae": "wave22_asm_mirror_components",
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
    print("Wave-22: Assembly mirror-components production PAE")
    print("=" * 70)

    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.assembly.lifecycle import (
        commit_assembly,
        dry_run_assembly,
    )
    from ai_sw_bridge.assembly.validator import validate_assembly

    mod = wrapper_module()

    import win32com.client as w32_compat
    from win32com.client import dynamic
    import pythoncom

    try:
        sw = dynamic.Dispatch(pythoncom.GetActiveObject("SldWorks.Application"))
    except Exception:
        sw = dynamic.Dispatch("SldWorks.Application")

    # Build part
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    BOX_PATH = str(_tmp / f"w22_mirror_{_ts}_box.SLDPRT")
    ASM_PATH = str(_tmp / f"w22_mirror_{_ts}_asm.SLDASM")

    from ai_sw_bridge.spec.builder import build as part_build

    box_spec = {
        "schema_version": 1,
        "name": "W22MirrorBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 20.0,
                "height": 10.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX",
                "sketch": "SK",
                "depth": 10.0,
            },
        ],
    }

    print("\n--- Building box part ---")
    r = part_build(box_spec, save_as=BOX_PATH, save_format="current", no_dim=True)
    if not gate("build_box", r.ok and os.path.isfile(BOX_PATH), f"ok={r.ok}"):
        save_results()
        return "WALL"

    # Assembly spec with 1 seed + 1 mirror pattern
    asm_spec: dict[str, Any] = {
        "kind": "assembly",
        "name": "W22MirrorTest",
        "components": [
            {
                "id": "seed",
                "part": BOX_PATH,
                "transform": {"xyz_mm": [0, 0, 0]},
            },
        ],
        "component_patterns": [
            {"type": "mirror", "seed": "seed", "plane": "right"},
        ],
    }

    print("\n--- Validating spec ---")
    try:
        validate_assembly(asm_spec)
        gate("validate", True, "spec valid")
    except Exception as exc:
        gate("validate", False, str(exc)[:200])
        save_results()
        return "WALL"

    # Dry run
    print("\n--- Dry run ---")
    dry_result = dry_run_assembly(asm_spec)
    gate("dry_run", dry_result.get("ok", False),
         f"resolved={len(dry_result.get('resolved_parts', {}))}")
    if not dry_result.get("ok"):
        gate("dry_run_detail", False, dry_result.get("error", "?"))
        save_results()
        return "WALL"

    # Commit
    print("\n--- Commit ---")
    commit_result = commit_assembly(
        sw, asm_spec, ASM_PATH, mod=mod
    )
    gate("commit", commit_result.get("ok", False),
         f"components={commit_result.get('component_count', '?')}, "
         f"mirror={commit_result.get('mirror_count', '?')}")

    if not commit_result.get("ok"):
        gate("commit_detail", False, commit_result.get("error", "?"))
        save_results()
        return "WALL"

    gate("component_count", commit_result.get("component_count") == 1,
         f"placed={commit_result.get('component_count')}")
    gate("mirror_count", commit_result.get("mirror_count") == 1,
         f"mirrored={commit_result.get('mirror_count')}")
    gate("asm_saved", os.path.isfile(ASM_PATH),
         f"size={os.path.getsize(ASM_PATH) if os.path.isfile(ASM_PATH) else '?'}")

    # Re-open and verify
    print("\n--- Re-open and verify ---")
    typed_sw = typed(sw, "ISldWorks", module=mod)

    try:
        open_ret = typed_sw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)
        if isinstance(open_ret, tuple):
            asm_doc = open_ret[0]
        else:
            asm_doc = open_ret
    except Exception as exc:
        gate("reopen", False, f"OpenDoc6: {exc!r}")
        save_results()
        return "PARTIAL"

    if asm_doc is None:
        gate("reopen", False, "OpenDoc6 returned None")
        save_results()
        return "PARTIAL"

    gate("reopen", True, "assembly re-opened")

    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
    try:
        comp_count = int(typed_asm.GetComponentCount(True))
    except Exception as exc:
        gate("comp_count_reopen", False, f"GetComponentCount: {exc!r}")
        comp_count = -1

    gate("comp_count_reopen", comp_count == 2,
         f"expected 2, got {comp_count}")

    # Check for mirror component in feature tree
    try:
        fm = asm_doc.FeatureManager
        feats = fm.GetFeatures(True)
        mirror_found = False
        if feats:
            for f in feats:
                fn = f.Name
                if callable(fn):
                    fn = fn()
                if fn and "Mirror" in str(fn):
                    mirror_found = True
                    break
        gate("mirror_in_tree", mirror_found, "Mirror component in feature tree")
    except Exception as exc:
        gate("mirror_in_tree", False, f"tree scan: {exc!r}")

    # Close docs
    try:
        t = asm_doc.GetTitle
        if isinstance(t, tuple):
            t = t[0]
        sw.CloseDoc(t() if callable(t) else t)
    except Exception:
        pass
    try:
        sw.CloseDoc(Path(BOX_PATH).name)
    except Exception:
        pass

    save_results()

    all_ok = all(g["ok"] for g in results["gates"].values())
    return "PASS" if all_ok else "PARTIAL"


if __name__ == "__main__":
    import pythoncom

    pythoncom.CoInitialize()
    try:
        verdict = run()
    finally:
        pythoncom.CoUninitialize()

    print(f"\n  VERDICT: {verdict}")
    all_ok = all(g["ok"] for g in results["gates"].values())
    raise SystemExit(0 if all_ok else 1)
