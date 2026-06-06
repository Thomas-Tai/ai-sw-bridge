"""PAE W35 — clearance (min-distance) production acceptance.

Builds two assemblies via COM helpers, then runs sw_get_clearance
(production module) to validate end-to-end:

  1. GAP-10 assembly: two 20mm cubes, faces 10mm apart
     → min_distance_mm == 10.0 (within tolerance)
  2. GAP-25 assembly: two 20mm cubes, faces 25mm apart
     → min_distance_mm == 25.0 (tracks, proves discrimination)
  3. Part doc → fail-closed typed error

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/clearance_pae.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "clearance_pae.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app, SW_DOC_PART  # noqa: E402
from ai_sw_bridge.observe_clearance import sw_get_clearance  # noqa: E402

BOX_SIZE_M = 0.020
GAP_10MM_M = 0.010
GAP_25MM_M = 0.025
TOLERANCE_MM = 0.5


def _find_asm_template() -> str | None:
    import glob
    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.asmdot",
    ]:
        for m in glob.glob(pat):
            return m
    return None


def _make_block_part(sw_typed: Any, mod: Any, path: str) -> tuple[Any | None, str | None]:
    """Create a 20mm cube part. Returns (doc, error)."""
    try:
        doc = sw_typed.NewDocument(
            r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT",
            0, 0, 0,
        )
        if doc is None:
            return None, "NewDocument(part) returned None"
        dt = typed(doc, "IModelDoc2", module=mod)

        dt.SketchManager.InsertSketch(True)
        half = BOX_SIZE_M / 2.0
        dt.SketchManager.CreateCenterRectangle(0, 0, 0, half, half, 0)
        dt.SketchManager.InsertSketch(True)

        dt.ClearSelection2(True)
        dt.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
        feat = dt.FeatureManager.FeatureExtrusion2(
            True, False, False, 0, 0,
            BOX_SIZE_M, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0,
            False,
        )
        if feat is None:
            return None, "FeatureExtrusion2 returned None"

        dt.SaveAs3(path, 0, 2)
        return doc, None
    except Exception as exc:
        return None, f"exception: {exc!r}"


def _get_component_names(asm_doc: Any, mod: Any) -> list[str]:
    """Get Name2 of all components in the assembly."""
    names: list[str] = []
    try:
        asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)
        comps = asm_typed.GetComponents(True)
        if comps is None:
            return names
        if not isinstance(comps, (list, tuple)):
            comps = (comps,)
        for comp in comps:
            try:
                name = comp.Name2
                if callable(name):
                    name = name()
                names.append(str(name))
            except Exception:
                pass
    except Exception:
        pass
    return names


def _build_assembly(
    sw_typed: Any, mod: Any,
    part_path: str, asm_template: str,
    gap_m: float, label: str,
) -> tuple[Any, Any, list[str], str | None]:
    """Build a 2-component assembly with known gap.

    Returns (asm_doc, asm_typed, component_names, error).
    """
    # Pre-open part (MANDATORY)
    open_ret = sw_typed.OpenDoc6(part_path, SW_DOC_PART, 1, "", 0, 0)
    part_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
    if part_doc is None:
        return None, None, [], "OpenDoc6(part) returned None"

    asm_doc = sw_typed.NewDocument(asm_template, 0, 0, 0)
    if asm_doc is None:
        return None, None, [], "NewDocument(asm) returned None"

    asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)

    # Component A at origin
    comp_a = asm_typed.AddComponent4(part_path, "", 0.0, 0.0, 0.0)
    if comp_a is None or isinstance(comp_a, int):
        return None, None, [], "AddComponent4(A) returned None"

    # Component B at (BOX_SIZE + gap) — faces are gap apart
    offset_m = BOX_SIZE_M + gap_m
    comp_b = asm_typed.AddComponent4(part_path, "", offset_m, 0.0, 0.0)
    if comp_b is None or isinstance(comp_b, int):
        return None, None, [], "AddComponent4(B) returned None"

    print(f"  [{label}] Placed A@origin, B@{offset_m*1000:.0f}mm (gap={gap_m*1000:.0f}mm)")

    doc_typed = typed(asm_doc, "IModelDoc2", module=mod)
    try:
        doc_typed.ForceRebuild3(True)
    except Exception:
        pass
    time.sleep(2)

    names = _get_component_names(asm_doc, mod)
    print(f"  [{label}] Component names: {names}")

    return asm_doc, asm_typed, names, None


def main() -> None:
    pythoncom.CoInitialize()
    sw = get_sw_app()
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)

    # Clean slate
    try:
        sw_typed.CloseAllDocuments(True)
    except Exception:
        pass
    time.sleep(2)

    result: dict[str, Any] = {
        "verdict": "PENDING",
        "gap_10mm": {
            "measured_mm": None,
            "expected_mm": 10.0,
            "ok": False,
            "error": None,
        },
        "gap_25mm": {
            "measured_mm": None,
            "expected_mm": 25.0,
            "ok": False,
            "error": None,
        },
        "part_doc_fail": {
            "ok": False,
            "error": None,
            "note": "fail-closed typed error expected",
        },
        "gates": [],
        "errors": [],
    }

    tmpdir = tempfile.mkdtemp(prefix="aisw_W35_pae_")
    part_path = str(Path(tmpdir) / "block_20mm.sldprt")

    try:
        # ── Create block part ───────────────────────────────────────────
        print("[PAE] Creating block part …")
        part_doc, err = _make_block_part(sw_typed, mod, part_path)
        if err:
            result["errors"].append(f"make_part: {err}")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        asm_templ = _find_asm_template()
        if not asm_templ:
            result["errors"].append("no ASMDOT template")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        # ── GAP-10 assembly ─────────────────────────────────────────────
        print("[PAE] Building GAP-10 assembly …")
        asm1_doc, asm1_typed, names1, err1 = _build_assembly(
            sw_typed, mod, part_path, asm_templ,
            GAP_10MM_M, "gap10mm",
        )
        if err1:
            result["errors"].append(f"gap10mm_build: {err1}")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        if len(names1) < 2:
            result["errors"].append(f"gap10mm: only {len(names1)} components found")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        # Use production sw_get_clearance(doc, ...) — pass doc directly to avoid active-doc race
        print("[PAE] Running sw_get_clearance on gap-10 assembly …")
        cl1 = sw_get_clearance(asm1_doc, names1[0], names1[1])
        result["gap_10mm"]["error"] = cl1.get("error")
        if cl1.get("ok") and cl1.get("clearance"):
            result["gap_10mm"]["measured_mm"] = cl1["clearance"]["min_distance_mm"]
            d1 = cl1["clearance"]["min_distance_mm"]
            if d1 is not None and abs(d1 - 10.0) < TOLERANCE_MM:
                result["gap_10mm"]["ok"] = True

        print(f"[PAE] GAP-10: measured={result['gap_10mm']['measured_mm']}mm, "
              f"ok={result['gap_10mm']['ok']}, error={result['gap_10mm']['error']}")

        # ── GAP-25 assembly ─────────────────────────────────────────────
        print("[PAE] Building GAP-25 assembly …")
        asm2_doc, asm2_typed, names2, err2 = _build_assembly(
            sw_typed, mod, part_path, asm_templ,
            GAP_25MM_M, "gap25mm",
        )
        if err2:
            result["errors"].append(f"gap25mm_build: {err2}")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        if len(names2) < 2:
            result["errors"].append(f"gap25mm: only {len(names2)} components found")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        print("[PAE] Running sw_get_clearance on gap-25 assembly …")
        cl2 = sw_get_clearance(asm2_doc, names2[0], names2[1])
        result["gap_25mm"]["error"] = cl2.get("error")
        if cl2.get("ok") and cl2.get("clearance"):
            result["gap_25mm"]["measured_mm"] = cl2["clearance"]["min_distance_mm"]
            d2 = cl2["clearance"]["min_distance_mm"]
            if d2 is not None and abs(d2 - 25.0) < TOLERANCE_MM:
                result["gap_25mm"]["ok"] = True

        print(f"[PAE] GAP-25: measured={result['gap_25mm']['measured_mm']}mm, "
              f"ok={result['gap_25mm']['ok']}, error={result['gap_25mm']['error']}")

        # ── Part doc → fail-closed ──────────────────────────────────────
        # Call sw_get_clearance on part_doc directly — should fail with typed error
        print("[PAE] Testing fail-closed on part doc …")
        try:
            part_result = sw_get_clearance(part_doc, "nonexistent_a", "nonexistent_b")
            result["part_doc_fail"]["error"] = part_result.get("error")
            result["part_doc_fail"]["ok"] = (
                not part_result.get("ok")
                and "assembly document" in str(part_result.get("error", ""))
            )
        except Exception as exc:
            result["part_doc_fail"]["error"] = f"exception: {exc!r}"
            result["part_doc_fail"]["ok"] = False

        print(f"[PAE] Part doc: ok={result['part_doc_fail']['ok']}, "
              f"error={result['part_doc_fail']['error']}")

        # ── GATES ───────────────────────────────────────────────────────
        d1 = result["gap_10mm"]["measured_mm"]
        d2 = result["gap_25mm"]["measured_mm"]

        gate1 = result["gap_10mm"]["ok"]
        result["gates"].append(f"gap10mm_matches (==10.0mm +-0.5): {gate1} (measured={d1}mm)")

        gate2 = result["gap_25mm"]["ok"]
        result["gates"].append(f"gap25mm_matches (==25.0mm +-0.5): {gate2} (measured={d2}mm)")

        gate3 = d1 is not None and d2 is not None and d1 != d2
        result["gates"].append(f"discrimination (d1 != d2): {gate3} ({d1} vs {d2})")

        gate4 = result["part_doc_fail"]["ok"]
        result["gates"].append(f"part_doc_fail_closed: {gate4}")

        gate5 = (
            not result["gap_10mm"]["error"]
            and not result["gap_25mm"]["error"]
        )
        result["gates"].append(f"no_measurement_errors: {gate5}")

        if all([gate1, gate2, gate3, gate4, gate5]):
            result["verdict"] = "PASS"
        else:
            result["verdict"] = "FAIL"

    except Exception as exc:
        result["errors"].append(f"top-level: {exc!r}")
        result["verdict"] = "FAIL"
    finally:
        # Cleanup
        try:
            sw_typed.CloseAllDocuments(True)
        except Exception:
            pass
        _write_result(result)
        print(f"\n[PAE] VERDICT: {result['verdict']}")
        for gate in result["gates"]:
            print(f"  {gate}")


def _write_result(result: dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[PAE] Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()