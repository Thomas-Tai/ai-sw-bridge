"""PAE W27 — interference detection production acceptance.

Builds two assemblies via the proven ai-sw-assembly CLI, then runs
detect_interference via the observe CLI:

  1. OVERLAP assembly: two 20mm cubes at 10mm offset → count > 0
  2. CLEARANCE assembly: two 20mm cubes at 50mm offset → count == 0

Discrimination gate (W21 doctrine): detector MUST distinguish clash
from clearance.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/interference_pae.py
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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "interference_pae.json"

# Import COM helpers for direct assembly creation (avoid CLI dependency)
import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.observe_interference import sw_get_interference  # noqa: E402

BOX_SIZE_M = 0.020
OVERLAP_OFFSET_M = 0.010
CLEARANCE_OFFSET_M = 0.050
SW_DOC_PART = 1


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


def _build_assembly(
    sw_typed: Any, mod: Any,
    part_path: str, asm_template: str,
    offset_m: float, label: str,
) -> tuple[Any, Any, str | None]:
    """Open new assembly, place two copies of part. Returns (asm_doc, asm_typed, error)."""
    # Pre-open part (MANDATORY)
    open_ret = sw_typed.OpenDoc6(part_path, SW_DOC_PART, 1, "", 0, 0)
    part_doc = open_ret[0] if isinstance(open_ret, tuple) else open_ret
    if part_doc is None:
        return None, None, "OpenDoc6(part) returned None"

    asm_doc = sw_typed.NewDocument(asm_template, 0, 0, 0)
    if asm_doc is None:
        return None, None, "NewDocument(asm) returned None"

    asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)

    comp_a = asm_typed.AddComponent4(part_path, "", 0.0, 0.0, 0.0)
    if comp_a is None or isinstance(comp_a, int):
        return None, None, "AddComponent4(A) returned None"

    comp_b = asm_typed.AddComponent4(part_path, "", offset_m, 0.0, 0.0)
    if comp_b is None or isinstance(comp_b, int):
        return None, None, "AddComponent4(B) returned None"

    print(f"  [{label}] Placed components at 0 and {offset_m*1000:.0f}mm")

    doc_typed = typed(asm_doc, "IModelDoc2", module=mod)
    try:
        doc_typed.ForceRebuild3(True)
    except Exception:
        pass
    time.sleep(2)

    return asm_doc, asm_typed, None


def main() -> None:
    pythoncom.CoInitialize()
    sw = get_sw_app()
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)

    result: dict[str, Any] = {
        "verdict": "PENDING",
        "overlap": {"count": None, "volume_mm3": None, "components": []},
        "clearance": {"count": None},
        "errors": [],
        "gates": [],
    }

    tmpdir = tempfile.mkdtemp(prefix="aisw_W27_pae_")
    part_path = str(Path(tmpdir) / "block_20mm.sldprt")
    asm_overlap_path = str(Path(tmpdir) / "overlap_asm.sldasm")
    asm_clearance_path = str(Path(tmpdir) / "clearance_asm.sldasm")

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

        # ── OVERLAP assembly ────────────────────────────────────────────
        print("[PAE] Building OVERLAP assembly …")
        asm_doc, asm_typed, err = _build_assembly(
            sw_typed, mod, part_path, asm_templ,
            OVERLAP_OFFSET_M, "overlap",
        )
        if err:
            result["errors"].append(f"overlap_build: {err}")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        # Save overlap assembly
        doc_typed = typed(asm_doc, "IModelDoc2", module=mod)
        try:
            doc_typed.SaveAs3(asm_overlap_path, 0, 2)
        except Exception:
            pass

        # Run interference detection via sw_get_interference
        print("[PAE] Running interference detection on overlap …")
        intf_result = sw_get_interference(asm_doc)
        result["overlap"]["count"] = intf_result.get("interference_count", 0)
        result["overlap"]["errors"] = intf_result.get("error")
        if intf_result.get("interferences"):
            for inf in intf_result["interferences"]:
                result["overlap"]["volume_mm3"] = inf.get("interference_volume_mm3")
                result["overlap"]["components"] = inf.get("components", [])
                break  # first interference

        print(f"[PAE] Overlap: count={result['overlap']['count']}, "
              f"volume={result['overlap']['volume_mm3']}, "
              f"components={result['overlap']['components']}")

        # ── CLEARANCE assembly ──────────────────────────────────────────
        print("[PAE] Building CLEARANCE assembly …")
        asm_doc2, asm_typed2, err2 = _build_assembly(
            sw_typed, mod, part_path, asm_templ,
            CLEARANCE_OFFSET_M, "clearance",
        )
        if err2:
            result["errors"].append(f"clearance_build: {err2}")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        # Save clearance assembly
        doc_typed2 = typed(asm_doc2, "IModelDoc2", module=mod)
        try:
            doc_typed2.SaveAs3(asm_clearance_path, 0, 2)
        except Exception:
            pass

        # Run interference detection on clearance
        print("[PAE] Running interference detection on clearance …")
        intf_result2 = sw_get_interference(asm_doc2)
        result["clearance"]["count"] = intf_result2.get("interference_count", 0)
        result["clearance"]["errors"] = intf_result2.get("error")

        print(f"[PAE] Clearance: count={result['clearance']['count']}")

        # ── DISCRIMINATION GATE ────────────────────────────────────────
        oc = result["overlap"]["count"]
        cc = result["clearance"]["count"]
        ov = result["overlap"]["volume_mm3"]
        comps = result["overlap"]["components"]

        # Gate 1: overlap count > 0
        gate1 = oc is not None and oc > 0
        result["gates"].append(f"overlap_count>0: {gate1} (count={oc})")

        # Gate 2: clearance count == 0
        gate2 = cc is not None and cc == 0
        result["gates"].append(f"clearance_count==0: {gate2} (count={cc})")

        # Gate 3: overlap has positive volume
        gate3 = ov is not None and ov > 0
        result["gates"].append(f"overlap_volume>0: {gate3} (volume_mm3={ov})")

        # Gate 4: overlap has 2 components
        gate4 = comps is not None and len(comps) >= 2
        result["gates"].append(f"overlap_components>=2: {gate4} (components={comps})")

        # Gate 5: no errors in detection
        gate5 = not result["overlap"]["errors"] and not result["clearance"]["errors"]
        result["gates"].append(f"no_detection_errors: {gate5}")

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