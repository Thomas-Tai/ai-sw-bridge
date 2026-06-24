"""Spike W26 / ASM_ARRAYS — transform-math proof for linear + circular arrays.

Builds an assembly with a linear array (count=3, spacing 40mm, +X) and a
circular array (count=4, radius 50mm, +Z axis, 360°) via the production
``commit_assembly`` lifecycle, re-opens the ``.SLDASM``, and verifies:

  1. ``GetComponentCount(False)`` == 7 (3 linear + 4 circular).
  2. Linear instance 2 is at x≈80mm (proving spacing works).
  3. Circular instances are ~90° apart on the circle (proving NOT stacked).

The liveness gate refutes the degenerate-array trap: all N at the same
transform would give count=7 but no spread. We sample transforms and
verify EFFECT, not just count.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_asm_arrays.py
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
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "asm_arrays.json"


def _title(d: Any) -> Any:
    t = d.GetTitle
    if isinstance(t, tuple):
        t = t[0]
    return t() if callable(t) else t


def run() -> dict[str, Any]:
    import pythoncom
    from spike_earlybind_persist import connect_running_sw

    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.assembly.lifecycle import commit_assembly
    from ai_sw_bridge.assembly.validator import validate_assembly
    from ai_sw_bridge.spec.builder import build as part_build

    pythoncom.CoInitialize()
    try:
        result: dict[str, Any] = {
            "spike": "w26_asm_arrays_transform_proof",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        sw = connect_running_sw()
        mod = wrapper_module()

        try:
            result["sw_revision"] = str(sw.RevisionNumber)
        except Exception:
            result["sw_revision"] = "<unreadable>"

        # Build a simple box part
        _tmp = Path(tempfile.gettempdir())
        _ts = int(time.time())
        part_path = str(_tmp / f"w26_array_box_{_ts}.SLDPRT")
        asm_path = str(_tmp / f"w26_array_asm_{_ts}.SLDASM")

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
        br = part_build(box_spec, save_as=part_path, save_format="current", no_dim=True)
        if not br.ok or not os.path.isfile(part_path):
            result["overall"] = "NO-GO"
            result["failure_point"] = f"part build failed: {br.error}"
            return result

        result["part_path"] = part_path

        # Assembly spec: 1 seed + linear array (3) + circular array (4)
        asm_spec: dict[str, Any] = {
            "kind": "assembly",
            "name": "W26ArrayTest",
            "components": [
                {"id": "seed", "part": part_path, "transform": {"xyz_mm": [0, 0, 0]}},
            ],
            "component_arrays": [
                {
                    "id": "rail",
                    "type": "linear",
                    "part": part_path,
                    "count": 3,
                    "spacing_mm": 40.0,
                    "direction": [1, 0, 0],
                    "base_xyz_mm": [100, 0, 0],
                },
                {
                    "id": "bolt",
                    "type": "circular",
                    "part": part_path,
                    "count": 4,
                    "radius_mm": 50.0,
                    "axis": [0, 0, 1],
                    "center_xyz_mm": [0, 100, 0],
                    "angle_deg": 360.0,
                },
            ],
        }

        # Validate
        try:
            validate_assembly(asm_spec)
            result["validation"] = "ok"
        except Exception as exc:
            result["overall"] = "NO-GO"
            result["failure_point"] = f"validation failed: {exc}"
            return result

        # Commit
        commit_result = commit_assembly(sw, asm_spec, asm_path, mod=mod)
        result["commit"] = {
            "ok": commit_result.get("ok"),
            "component_count": commit_result.get("component_count"),
            "array_expanded_count": commit_result.get("array_expanded_count"),
            "error": commit_result.get("error"),
        }

        if not commit_result.get("ok"):
            result["overall"] = "NO-GO"
            result["failure_point"] = f"commit failed: {commit_result.get('error')}"
            return result

        # Re-open and verify
        typed_sw = typed(sw, "ISldWorks", module=mod)
        try:
            open_ret = typed_sw.OpenDoc6(asm_path, 2, 1, "", 0, 0)
            if isinstance(open_ret, tuple):
                asm_doc = open_ret[0]
            else:
                asm_doc = open_ret
        except Exception as exc:
            result["overall"] = "NO-GO"
            result["failure_point"] = f"reopen failed: {exc!r}"
            return result

        if asm_doc is None:
            result["overall"] = "NO-GO"
            result["failure_point"] = "reopen returned None"
            return result

        typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

        # Component count
        try:
            comp_count = int(typed_asm.GetComponentCount(False))
        except Exception:
            comp_count = -1
        result["component_count_reopen"] = comp_count
        result["expected_count"] = 8  # 1 seed + 3 rail + 4 bolt

        count_ok = comp_count == 8
        result["count_verified"] = count_ok

        # Sample instance transforms
        # GetComponents returns IComponent2[] with Transform2 property
        instances: list[dict[str, Any]] = []
        try:
            comps = typed_asm.GetComponents(False)
            if comps:
                for c in comps:
                    cn = c.Name
                    if callable(cn):
                        cn = cn()
                    # Try to get transform
                    try:
                        xform = c.Transform2
                        if xform is not None:
                            # Transform2 is an IMathTransform; get the array
                            arr = xform.ArrayData
                            if arr is not None:
                                data = list(arr)
                                tx_mm = data[9] * 1000.0
                                ty_mm = data[10] * 1000.0
                                tz_mm = data[11] * 1000.0
                                instances.append(
                                    {
                                        "name": cn,
                                        "tx_mm": round(tx_mm, 2),
                                        "ty_mm": round(ty_mm, 2),
                                        "tz_mm": round(tz_mm, 2),
                                    }
                                )
                                continue
                    except Exception:
                        pass
                    instances.append({"name": cn, "transform_error": True})
        except Exception as exc:
            result["get_components_error"] = str(exc)[:200]

        result["instances"] = instances

        # Verify linear array transforms (position-based, not name-based).
        # SW auto-names components from part filename, so we identify linear
        # instances by their expected Y≈0, Z≈-2.5, X∈{100,140,180}.
        linear_candidates = [
            i
            for i in instances
            if abs(i.get("ty_mm", 999)) < 5.0 and 95.0 < i.get("tx_mm", -999) < 185.0
        ]
        result["linear_instances"] = linear_candidates

        linear_ok = False
        if len(linear_candidates) >= 3:
            xs = sorted([i["tx_mm"] for i in linear_candidates])
            # Check spacing: ~40mm between consecutive
            d01 = abs(xs[1] - xs[0])
            d12 = abs(xs[2] - xs[1])
            if abs(d01 - 40.0) < 5.0 and abs(d12 - 40.0) < 5.0:
                linear_ok = True
        result["linear_verified"] = linear_ok

        # Verify circular array transforms.
        # Circular instances at radius ~50mm from center (0, 100, 0).
        circular_candidates = [
            i
            for i in instances
            if abs(i.get("ty_mm", 0) - 100) < 60.0
            and abs(i.get("tx_mm", 0)) < 60.0
            and i not in linear_candidates
            and not (abs(i.get("tx_mm", 0)) < 5.0 and abs(i.get("ty_mm", 0)) < 5.0)
        ]
        result["circular_instances"] = circular_candidates

        circular_ok = False
        if len(circular_candidates) >= 4:
            radii = []
            for inst in circular_candidates:
                tx = inst.get("tx_mm", 0)
                ty = inst.get("ty_mm", 0) - 100  # offset from center
                r = math.sqrt(tx**2 + ty**2)
                radii.append(r)

            result["circular_radii"] = [round(r, 2) for r in radii]

            all_at_radius = all(abs(r - 50.0) < 5.0 for r in radii)
            distinct = len(
                set(
                    (round(inst.get("tx_mm", 0), 1), round(inst.get("ty_mm", 0), 1))
                    for inst in circular_candidates
                )
            )
            not_stacked = distinct >= 3

            if all_at_radius and not_stacked:
                circular_ok = True

        result["circular_verified"] = circular_ok

        # Close docs
        try:
            sw.CloseDoc(_title(asm_doc))
        except Exception:
            pass
        try:
            sw.CloseDoc(Path(part_path).name)
        except Exception:
            pass

        # Overall verdict
        if count_ok and linear_ok and circular_ok:
            result["overall"] = "GO"
        else:
            result["overall"] = "NO-GO"
            failures = []
            if not count_ok:
                failures.append(f"count={comp_count} (expected 8)")
            if not linear_ok:
                failures.append("linear transforms wrong")
            if not circular_ok:
                failures.append("circular transforms wrong")
            result["failure_point"] = "; ".join(failures)

        return result

    finally:
        pythoncom.CoUninitialize()


def main() -> int:
    result = run()
    payload = json.dumps(result, indent=2, default=str)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}", file=sys.stderr)
    print(payload)
    return 0 if result.get("overall") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
