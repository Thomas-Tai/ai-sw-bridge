"""Wave-26 S3: Assembly component-arrays production PAE.

Exercises the production linear + circular array pipeline end-to-end:
  1. Build a box part.
  2. Author assembly spec with seed + linear array (3, 40mm +X) +
     circular array (4, r=50mm, +Z, 360°).
  3. ``propose → dry_run → commit`` via production lifecycle.
  4. Re-open ``.SLDASM`` and verify:
     a. ``GetComponentCount`` == 8 (1 seed + 3 + 4).
     b. Linear instances at correct spacing.
     c. Circular instances at correct radius (NOT stacked).
  5. Manifest round-trips ``component_arrays`` VERBATIM.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

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

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "asm_arrays_pae.json"

results: dict[str, Any] = {
    "pae": "wave26_asm_component_arrays",
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
    print("Wave-26: Assembly component-arrays production PAE")
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
    BOX_PATH = str(_tmp / f"w26_arr_{_ts}_box.SLDPRT")
    ASM_PATH = str(_tmp / f"w26_arr_{_ts}_asm.SLDASM")

    from ai_sw_bridge.spec.builder import build as part_build

    box_spec = {
        "schema_version": 1,
        "name": "W26ArrayBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX",
                "sketch": "SK",
                "depth": 5.0,
            },
        ],
    }

    print("\n--- Building box part ---")
    r = part_build(box_spec, save_as=BOX_PATH, save_format="current", no_dim=True)
    if not gate("build_box", r.ok and os.path.isfile(BOX_PATH), f"ok={r.ok}"):
        save_results()
        return "WALL"

    # Assembly spec
    asm_spec: dict[str, Any] = {
        "kind": "assembly",
        "name": "W26ArrayPAE",
        "components": [
            {"id": "seed", "part": BOX_PATH, "transform": {"xyz_mm": [0, 0, 0]}},
        ],
        "component_arrays": [
            {
                "id": "rail",
                "type": "linear",
                "part": BOX_PATH,
                "count": 3,
                "spacing_mm": 40.0,
                "direction": [1, 0, 0],
                "base_xyz_mm": [100, 0, 0],
            },
            {
                "id": "bolt",
                "type": "circular",
                "part": BOX_PATH,
                "count": 4,
                "radius_mm": 50.0,
                "axis": [0, 0, 1],
                "center_xyz_mm": [0, 100, 0],
                "angle_deg": 360.0,
            },
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
    commit_result = commit_assembly(sw, asm_spec, ASM_PATH, mod=mod)
    gate("commit", commit_result.get("ok", False),
         f"components={commit_result.get('component_count', '?')}, "
         f"expanded={commit_result.get('array_expanded_count', '?')}")

    if not commit_result.get("ok"):
        gate("commit_detail", False, commit_result.get("error", "?"))
        save_results()
        return "WALL"

    gate("expanded_count", commit_result.get("array_expanded_count") == 7,
         f"7 expanded (3 rail + 4 bolt)")
    gate("total_count", commit_result.get("component_count") == 8,
         f"8 total (1 seed + 7 expanded)")
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
        comp_count = int(typed_asm.GetComponentCount(False))
    except Exception:
        comp_count = -1

    gate("comp_count", comp_count == 8, f"expected 8, got {comp_count}")

    # Sample instance transforms
    instances: list[dict[str, Any]] = []
    try:
        comps = typed_asm.GetComponents(False)
        if comps:
            for c in comps:
                cn = c.Name
                if callable(cn):
                    cn = cn()
                try:
                    xform = c.Transform2
                    if xform is not None:
                        arr = xform.ArrayData
                        if arr is not None:
                            data = list(arr)
                            instances.append({
                                "name": cn,
                                "tx_mm": round(data[9] * 1000, 2),
                                "ty_mm": round(data[10] * 1000, 2),
                                "tz_mm": round(data[11] * 1000, 2),
                            })
                            continue
                except Exception:
                    pass
                instances.append({"name": cn, "transform_error": True})
    except Exception as exc:
        gate("sample_transforms", False, f"error: {exc!r}")

    gate("sampled_instances", len(instances) == 8,
         f"sampled {len(instances)} of 8 expected")

    # Verify linear spacing
    linear_candidates = [
        i for i in instances
        if abs(i.get("ty_mm", 999)) < 5.0
        and 95.0 < i.get("tx_mm", -999) < 185.0
    ]
    linear_ok = False
    if len(linear_candidates) >= 3:
        xs = sorted([i["tx_mm"] for i in linear_candidates])
        d01 = abs(xs[1] - xs[0])
        d12 = abs(xs[2] - xs[1])
        if abs(d01 - 40.0) < 5.0 and abs(d12 - 40.0) < 5.0:
            linear_ok = True
    gate("linear_spacing", linear_ok,
         f"found {len(linear_candidates)} candidates, "
         f"xs={[i['tx_mm'] for i in sorted(linear_candidates, key=lambda x: x.get('tx_mm', 0))]}")

    # Verify circular radius + not stacked
    circular_candidates = [
        i for i in instances
        if abs(i.get("ty_mm", 0) - 100) < 60.0
        and abs(i.get("tx_mm", 0)) < 60.0
        and i not in linear_candidates
        and not (abs(i.get("tx_mm", 0)) < 5.0 and abs(i.get("ty_mm", 0)) < 5.0)
    ]
    circular_ok = False
    if len(circular_candidates) >= 4:
        radii = []
        for inst in circular_candidates:
            tx = inst.get("tx_mm", 0)
            ty = inst.get("ty_mm", 0) - 100
            radii.append(math.sqrt(tx ** 2 + ty ** 2))
        all_at_radius = all(abs(r - 50.0) < 5.0 for r in radii)
        distinct = len(set(
            (round(inst.get("tx_mm", 0), 1), round(inst.get("ty_mm", 0), 1))
            for inst in circular_candidates
        ))
        if all_at_radius and distinct >= 3:
            circular_ok = True
    gate("circular_radius", circular_ok,
         f"found {len(circular_candidates)}, "
         f"radii={[round(math.sqrt((i.get('tx_mm',0))**2 + (i.get('ty_mm',0)-100)**2), 2) for i in circular_candidates]}")

    # Manifest round-trip
    print("\n--- Manifest round-trip ---")
    manifest_path = ASM_PATH + ".manifest.json"
    if os.path.isfile(manifest_path):
        gate("manifest_exists", True, manifest_path)
        manifest_data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        stored_spec = manifest_data.get("spec", {})
        stored_arrays = stored_spec.get("component_arrays")
        orig_arrays = asm_spec.get("component_arrays")
        roundtrip_ok = stored_arrays == orig_arrays
        gate("manifest_roundtrip", roundtrip_ok,
             f"stored {len(stored_arrays or [])} arrays, "
             f"original {len(orig_arrays or [])}")
        # Verify runtime overlay has all 8 instances
        runtime_comps = manifest_data.get("runtime", {}).get("components", [])
        gate("runtime_instances", len(runtime_comps) == 8,
             f"{len(runtime_comps)} runtime instances")
    else:
        gate("manifest_exists", False, "not found")
        roundtrip_ok = False

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
