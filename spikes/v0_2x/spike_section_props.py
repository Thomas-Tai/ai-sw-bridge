"""Spike W58 — section properties observe (READ-ONLY-SEAT) — go/no-go probe.

Tests ``IModelDocExtension.GetSectionProperties2`` on a KNOWN fixture
and asserts the returned values match analytic expectations within tolerance.

COM signature sourced from sldworksapi.chm (locally installed,
SW 2024 API Help, ``GetSectionProperties2 Method (IModelDocExtension)``):
  IModelDocExtension.GetSectionProperties2(Sections: VARIANT) -> VARIANT
  gen_py typelib 83A33D31-27C5-11CE-BFD4-00400513BB57x0x32x0.py, dispid=66.

Fixture: 20 mm × 20 mm × 20 mm cube (box centred on origin in X/Y, extruded
+Z from 0 to 20 mm).  Top face (+Z, at z = 20 mm) is selected.

Analytic values for a 20 mm × 20 mm square section (all SI):
  - area          = 0.020 × 0.020 = 4.000 × 10⁻⁴ m²
  - centroid      = (0, 0, 0.020) m  [model origin, box extrudes 0→+20mm in Z]
  - Ixx = Iyy     = b·h³/12 = 0.020 × (0.020)³ / 12 = 1.333... × 10⁻⁸ m⁴
  - Ixy           = 0  (symmetric square)
  - polar Jp      = Ixx + Iyy = 2.667 × 10⁻⁸ m⁴
  - principal Ix  = Iy = 1.333 × 10⁻⁸ m⁴  (square → already principal)

Discrimination gates:
  G1  status == 0  (success)
  G2  area_mm2 within 1 % of 400 mm²
  G3  centroid_mm[2] within 0.5 mm of 20 mm
  G4  |ixx_mm4 − 13333.33| < 200 mm⁴  (within 1.5 %)
  G5  |iyy_mm4 − 13333.33| < 200 mm⁴
  G6  |ixy_mm4| < 10 mm⁴  (near-zero product for symmetric square)
  G7  jp_mm4 within 1 % of 26666.67 mm⁴

Seat NOT yet fired.  W0 runs this spike during the handback session.

Usage (from repo root, with SOLIDWORKS 2024 running):
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_section_props.py
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "_results" / "section_props.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402
from ai_sw_bridge.observe_section import (
    read_section_props,
    sw_get_section_props,
)  # noqa: E402

# Analytic values for a 20 mm × 20 mm square section (see module docstring).
BOX_SIDE_M = 0.020  # 20 mm

_AREA_M2_ANALYTIC = BOX_SIDE_M**2  # 4.0e-4 m²
_CENTROID_Z_M_ANALYTIC = BOX_SIDE_M  # 0.020 m (top face)
_IXX_M4_ANALYTIC = BOX_SIDE_M * BOX_SIDE_M**3 / 12  # 1.333e-8 m⁴
_JP_M4_ANALYTIC = 2 * _IXX_M4_ANALYTIC  # 2.667e-8 m⁴

# Tolerance fractions / absolute values (in mm / mm⁴ after conversion).
_AREA_TOL_FRAC = 0.01  # 1 %
_CENTROID_Z_TOL_MM = 0.5  # 0.5 mm absolute
_IXX_TOL_MM4 = 200.0  # absolute mm⁴ — ~1.5 % of 13333
_IXY_ABS_MAX_MM4 = 10.0  # must be near zero for a symmetric square
_JP_TOL_FRAC = 0.01  # 1 %


def _find_part_template() -> str | None:
    import glob

    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\part.prtdot",
    ]:
        for m in glob.glob(pat):
            return m
    return None


def _retry(fn, *args, retries: int = 3, delay: float = 5.0, label: str = "") -> Any:
    for attempt in range(retries):
        try:
            return fn(*args)
        except Exception as exc:
            if attempt < retries - 1:
                print(
                    f"  [{label}] attempt {attempt + 1} failed: {exc!r}, retrying in {delay}s …"
                )
                time.sleep(delay)
            else:
                raise


def _make_box_part(sw_typed: Any, mod: Any, path: str) -> tuple[Any | None, str | None]:
    """Create a 20 mm cube part.  Box: X ∈ [−10, +10] mm, Y ∈ [−10, +10] mm,
    Z ∈ [0, +20] mm.  Returns (IModelDoc2 dispatch, error_or_None)."""
    try:
        doc = _retry(
            sw_typed.NewDocument,
            _find_part_template(),
            0,
            0,
            0,
            retries=3,
            delay=5.0,
            label="NewDocument",
        )
        if doc is None:
            return None, "NewDocument returned None"

        dt = typed(doc, "IModelDoc2", module=mod)
        half = BOX_SIDE_M / 2.0
        dt.SketchManager.InsertSketch(True)
        dt.SketchManager.CreateCenterRectangle(0, 0, 0, half, half, 0)
        dt.SketchManager.InsertSketch(True)

        dt.ClearSelection2(True)
        dt.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
        feat = dt.FeatureManager.FeatureExtrusion2(
            True,
            False,
            False,
            0,
            0,
            BOX_SIDE_M,
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            True,
            True,
            True,
            0,
            0,
            False,
        )
        if feat is None:
            return None, "FeatureExtrusion2 returned None"

        dt.ForceRebuild3(True)
        time.sleep(1)
        _retry(dt.SaveAs3, path, 0, 2, retries=2, delay=3.0, label="SaveAs3")
        return doc, None
    except Exception as exc:
        return None, f"exception: {exc!r}"


def _select_top_face(doc: Any, mod: Any) -> tuple[bool, str]:
    """Select the +Z face of the 20 mm cube (at z = +20 mm = 0.020 m)
    via ``IModelDocExtension.SelectByID2``."""
    try:
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        # Face at z = +20 mm; X=0, Y=0 samples the centre of the top face.
        ok = ext.SelectByID2("", "FACE", 0.0, 0.0, BOX_SIDE_M, False, 0, None, 0)
        return bool(ok), ""
    except Exception as exc:
        return False, f"SelectByID2: {exc!r}"


def _close_all(sw_typed: Any) -> None:
    try:
        sw_typed.CloseAllDocuments(True)
    except Exception:
        pass
    time.sleep(1)


def main() -> None:
    pythoncom.CoInitialize()
    sw = get_sw_app()
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)

    print("[S1] Closing all documents for a clean slate …")
    _close_all(sw_typed)
    time.sleep(2)

    result: dict[str, Any] = {
        "verdict": "PENDING",
        "raw_array": None,
        "parsed": None,
        "checks": {},
        "errors": [],
    }

    tmpdir = tempfile.mkdtemp(prefix="aisw_W58_")
    part_path = str(Path(tmpdir) / "box_20mm.sldprt")

    try:
        # ── Step 1: create 20 mm cube ──────────────────────────────────────
        print("[S1] Creating 20 mm cube part …")
        part_doc, err = _make_box_part(sw_typed, mod, part_path)
        if err:
            result["errors"].append(f"make_box: {err}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return
        print(f"[S1] Part saved: {part_path}")
        time.sleep(1)

        doc = get_active_doc(sw)
        if doc is None:
            result["errors"].append("no active doc after part creation")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        doc_typed = typed(doc, "IModelDoc2", module=mod)

        # ── Step 2: select the top (+Z) face ─────────────────────────────
        print("[S1] Selecting top (+Z) face via SelectByID2 …")
        doc_typed.ClearSelection2(True)
        time.sleep(0.5)
        ok_sel, sel_err = _select_top_face(doc, mod)
        if not ok_sel:
            result["errors"].append(f"face select failed: {sel_err}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return
        print("[S1]   Face selected OK.")
        time.sleep(0.5)

        # ── Step 3: call GetSectionProperties2(None) ─────────────────────
        # Passing None: use the already-selected face (per CHM: empty sections
        # array → SW uses current selection without adding new items).
        # Fallback to [] if None raises; W0 records which form works.
        print("[S1] Calling GetSectionProperties2(None) …")
        raw = None
        try:
            ext = typed(doc, "IModelDoc2", module=mod).Extension
            raw = ext.GetSectionProperties2(None)
        except Exception as exc_none:
            print(f"[S1]   GetSectionProperties2(None) raised: {exc_none!r}")
            print("[S1]   Retrying with GetSectionProperties2([]) …")
            try:
                # Re-select face (GetSectionProperties2 clears the selection set).
                doc_typed.ClearSelection2(True)
                time.sleep(0.3)
                ok_sel2, _ = _select_top_face(doc, mod)
                if ok_sel2:
                    time.sleep(0.3)
                    raw = typed(
                        doc, "IModelDoc2", module=mod
                    ).Extension.GetSectionProperties2([])
                    print("[S1]   [] form succeeded.")
            except Exception as exc_empty:
                result["errors"].append(
                    f"GetSectionProperties2 both forms failed: "
                    f"None->{exc_none!r}; []->{exc_empty!r}"
                )
                result["verdict"] = "NO-GO"
                _write_result(result)
                return

        if raw is None:
            result["errors"].append("GetSectionProperties2 returned None")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        # Serialise the raw array for the result JSON.
        try:
            result["raw_array"] = [float(raw[i]) for i in range(24)]
        except Exception as exc:
            result["raw_array"] = str(raw)
            result["errors"].append(f"raw_array serialise: {exc!r}")

        print(f"[S1]   raw[0]={raw[0]} (status), raw[1]={raw[1]:.6e} (area m²)")

        # ── Step 4: parse via the observe module ──────────────────────────
        props = read_section_props(raw)
        result["parsed"] = {k: v for k, v in props.items() if k != "errors"}
        if props["errors"]:
            result["errors"].extend(props["errors"])
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        # ── Step 5: discriminating checks ─────────────────────────────────
        area = props["area_mm2"]  # mm²
        cx = props["centroid_mm"]  # [x_mm, y_mm, z_mm]
        ixx = props["ixx_mm4"]
        iyy = props["iyy_mm4"]
        ixy = props["ixy_mm4"]
        jp = props["jp_mm4"]

        area_analytic_mm2 = _AREA_M2_ANALYTIC * 1e6
        ixx_analytic_mm4 = _IXX_M4_ANALYTIC * 1e12
        jp_analytic_mm4 = _JP_M4_ANALYTIC * 1e12
        centroid_z_analytic_mm = _CENTROID_Z_M_ANALYTIC * 1e3

        checks: dict[str, bool] = {}

        checks["G1_status_ok"] = props["status"] == 0
        checks["G2_area"] = (
            area is not None
            and abs(area - area_analytic_mm2) / area_analytic_mm2 < _AREA_TOL_FRAC
        )
        checks["G3_centroid_z"] = (
            cx is not None and abs(cx[2] - centroid_z_analytic_mm) < _CENTROID_Z_TOL_MM
        )
        checks["G4_ixx"] = (
            ixx is not None and abs(ixx - ixx_analytic_mm4) < _IXX_TOL_MM4
        )
        checks["G5_iyy"] = (
            iyy is not None and abs(iyy - ixx_analytic_mm4) < _IXX_TOL_MM4
        )
        checks["G6_ixy_near_zero"] = ixy is not None and abs(ixy) < _IXY_ABS_MAX_MM4
        checks["G7_jp"] = (
            jp is not None
            and abs(jp - jp_analytic_mm4) / jp_analytic_mm4 < _JP_TOL_FRAC
        )

        result["checks"] = {k: "PASS" if v else "FAIL" for k, v in checks.items()}
        all_pass = all(checks.values())
        result["verdict"] = "GREEN" if all_pass else "PARTIAL"

        for name, status in checks.items():
            icon = "[OK]" if checks[name] else "[FAIL]"
            print(f"[S1]   {icon}  {name}: {'PASS' if checks[name] else 'FAIL'}")

        if not all_pass:
            failed = [k for k, v in checks.items() if not v]
            result["errors"].append(f"failed gates: {failed}")
            # Print analytic vs actual for diagnosis.
            print(f"[S1]   area_mm2: got={area:.4f}, expected≈{area_analytic_mm2:.4f}")
            if cx:
                print(
                    f"[S1]   centroid_z_mm: got={cx[2]:.4f}, expected≈{centroid_z_analytic_mm:.4f}"
                )
            print(f"[S1]   ixx_mm4:  got={ixx:.2f}, expected≈{ixx_analytic_mm4:.2f}")
            print(f"[S1]   iyy_mm4:  got={iyy:.2f}, expected≈{ixx_analytic_mm4:.2f}")
            print(f"[S1]   ixy_mm4:  got={ixy:.6f}")
            print(f"[S1]   jp_mm4:   got={jp:.2f}, expected≈{jp_analytic_mm4:.2f}")

    except Exception as exc:
        result["errors"].append(f"top-level: {exc!r}")
        result["verdict"] = "NO-GO"
        import traceback

        traceback.print_exc()
    finally:
        try:
            sw_typed.CloseAllDocuments(True)
        except Exception:
            pass
        _write_result(result)
        print(f"\n[S1] VERDICT: {result['verdict']}")
        if result["errors"]:
            print(f"[S1] Errors: {result['errors']}")


def _write_result(result: dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[S1] Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
