"""PAE W30 — bounding_box + measure production acceptance.

Builds a 20×30×40mm box part, then runs the W30 observe tools:

  1. observe bounding_box → assert dx=20, dy=30, dz=40mm
  2. Select opposite corner vertices → observe measure_selection
     → assert distance = √(20²+30²+40²)=53.85mm

Discrimination gate (W21 doctrine): bbox must match expected dimensions;
measure must match expected diagonal (within tolerance).

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/measure_bbox_pae.py
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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "measure_bbox_pae.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.observe_bbox import sw_get_bbox_from_doc  # noqa: E402
from ai_sw_bridge.observe_measure import sw_get_measure_from_doc  # noqa: E402
from ai_sw_bridge.selection.live import select_entity  # noqa: E402

# Box dimensions
DX_MM = 20.0
DY_MM = 30.0
DZ_MM = 40.0
DX_M = DX_MM / 1000.0
DY_M = DY_MM / 1000.0
DZ_M = DZ_MM / 1000.0

EXPECTED_DIAGONAL_MM = math.sqrt(DX_MM**2 + DY_MM**2 + DZ_MM**2)
TOLERANCE_MM = 0.1

SW_DOC_PART = 1


# ── Helpers ────────────────────────────────────────────────────────────────


def _find_part_template() -> str | None:
    import glob

    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT",
    ]:
        for m in glob.glob(pat):
            return m
    return None


def _make_box_part(
    sw_typed: Any, mod: Any, path: str
) -> tuple[Any, Any | None, str | None]:
    """Create a 20×30×40mm box part. Returns (doc, typed_doc, error)."""
    try:
        doc = sw_typed.NewDocument(_find_part_template(), 0, 0, 0)
        if doc is None:
            return None, None, "NewDocument(part) returned None"
        dt = typed(doc, "IModelDoc2", module=mod)

        # Sketch: centered rectangle
        dt.SketchManager.InsertSketch(True)
        half_x = DX_M / 2.0
        half_y = DY_M / 2.0
        dt.SketchManager.CreateCenterRectangle(0, 0, 0, half_x, half_y, 0)
        dt.SketchManager.InsertSketch(True)

        # Extrude
        dt.ClearSelection2(True)
        dt.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
        feat = dt.FeatureManager.FeatureExtrusion2(
            True,
            False,
            False,
            0,
            0,
            DZ_M,
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
            return None, None, "FeatureExtrusion2 returned None"

        dt.SaveAs3(path, 0, 2)
        return doc, dt, None
    except Exception as exc:
        return None, None, f"exception: {exc!r}"


def _get_vertices(doc: Any) -> list[Any]:
    """Get all vertices from the part body."""
    vertices: list[Any] = []
    try:
        # GetBodies2 is on IPartDoc, not IModelDoc2
        # Try direct access first (late-bound or IPartDoc)
        bodies = doc.GetBodies2
        if callable(bodies):
            bodies = bodies(0, True)  # swSolidBody=0
        else:
            # Try as property on IModelDoc2's underlying doc
            bodies = doc.GetBodies2(0, True)
        if bodies:
            for body in bodies:
                try:
                    verts = body.GetVertices
                    if callable(verts):
                        verts = verts()
                    if verts:
                        for v in verts:
                            vertices.append(v)
                except Exception:
                    pass
    except Exception:
        pass
    return vertices


def _vertex_coords(vertex: Any) -> tuple[float, float, float] | None:
    """Get vertex coordinates (m)."""
    try:
        pt = vertex.GetPoint
        if callable(pt):
            pt = pt()
        if pt and len(pt) >= 3:
            return (float(pt[0]), float(pt[1]), float(pt[2]))
    except Exception:
        pass
    return None


def _find_corner_vertices(vertices: list[Any]) -> tuple[Any | None, Any | None]:
    """Find opposite corner vertices."""
    half_x = DX_M / 2.0
    half_y = DY_M / 2.0
    tolerance = 0.001

    min_corner = None
    max_corner = None
    min_coords = (-half_x, -half_y, 0.0)
    max_coords = (half_x, half_y, DZ_M)

    for v in vertices:
        coords = _vertex_coords(v)
        if coords is None:
            continue
        if (
            abs(coords[0] - min_coords[0]) < tolerance
            and abs(coords[1] - min_coords[1]) < tolerance
            and abs(coords[2] - min_coords[2]) < tolerance
        ):
            min_corner = v
        if (
            abs(coords[0] - max_coords[0]) < tolerance
            and abs(coords[1] - max_coords[1]) < tolerance
            and abs(coords[2] - max_coords[2]) < tolerance
        ):
            max_corner = v

    return min_corner, max_corner


# ── Main ────────────────────────────────────────────────────────────────


def main() -> None:
    pythoncom.CoInitialize()
    sw = get_sw_app()
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)

    result: dict[str, Any] = {
        "verdict": "PENDING",
        "bbox": {"ok": None, "dx_mm": None, "dy_mm": None, "dz_mm": None},
        "measure": {"ok": None, "distance_mm": None},
        "gates": [],
        "errors": [],
    }

    tmpdir = tempfile.mkdtemp(prefix="aisw_W30_pae_")
    part_path = str(Path(tmpdir) / "box_20x30x40.sldprt")

    try:
        # ── Create box part ───────────────────────────────────────────
        print("[PAE] Creating 20×30×40mm box part …")
        doc, dt, err = _make_box_part(sw_typed, mod, part_path)
        if err:
            result["errors"].append(f"make_part: {err}")
            result["verdict"] = "FAIL"
            _write_result(result)
            return
        print(f"[PAE] Part saved: {part_path}")

        try:
            dt.ForceRebuild3(True)
        except Exception:
            pass
        time.sleep(1)

        # ── Test bounding_box ────────────────────────────────────────────
        print("[PAE] Testing bounding_box …")
        bbox_result = sw_get_bbox_from_doc(dt)  # pass typed doc
        result["bbox"]["ok"] = bbox_result.get("ok")
        bb = bbox_result.get("bounding_box", {})
        result["bbox"]["dx_mm"] = bb.get("dx_mm")
        result["bbox"]["dy_mm"] = bb.get("dy_mm")
        result["bbox"]["dz_mm"] = bb.get("dz_mm")

        print(
            f"[PAE] bbox: dx={result['bbox']['dx_mm']}, dy={result['bbox']['dy_mm']}, dz={result['bbox']['dz_mm']}"
        )

        # Gate 1: bbox ok=True
        gate1 = bbox_result.get("ok") is True
        result["gates"].append(f"bbox_ok: {gate1}")

        # Gate 2: dx=20mm
        gate2 = (
            result["bbox"]["dx_mm"] is not None
            and abs(result["bbox"]["dx_mm"] - DX_MM) < TOLERANCE_MM
        )
        result["gates"].append(
            f"bbox_dx={DX_MM}mm: {gate2} (got {result['bbox']['dx_mm']})"
        )

        # Gate 3: dy=30mm
        gate3 = (
            result["bbox"]["dy_mm"] is not None
            and abs(result["bbox"]["dy_mm"] - DY_MM) < TOLERANCE_MM
        )
        result["gates"].append(
            f"bbox_dy={DY_MM}mm: {gate3} (got {result['bbox']['dy_mm']})"
        )

        # Gate 4: dz=40mm
        gate4 = (
            result["bbox"]["dz_mm"] is not None
            and abs(result["bbox"]["dz_mm"] - DZ_MM) < TOLERANCE_MM
        )
        result["gates"].append(
            f"bbox_dz={DZ_MM}mm: {gate4} (got {result['bbox']['dz_mm']})"
        )

        # ── Test measure_selection ────────────────────────────────────────
        print("[PAE] Testing measure_selection …")

        # Get vertices - use doc (IPartDoc) not dt (IModelDoc2)
        vertices = _get_vertices(doc)  # pass raw doc for GetBodies2
        if len(vertices) < 2:
            result["errors"].append("part has < 2 vertices")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        # Find corners
        v1, v2 = _find_corner_vertices(vertices)
        if v1 is None or v2 is None:
            result["errors"].append("could not find opposite corner vertices")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        # Clear and select
        try:
            dt.ClearSelection2(True)
        except Exception:
            pass

        ok1 = select_entity(v1, append=False, mark=0)
        ok2 = select_entity(v2, append=True, mark=0)

        if not ok1 or not ok2:
            result["errors"].append(f"selection failed: v1={ok1}, v2={ok2}")
            result["verdict"] = "FAIL"
            _write_result(result)
            return

        print(f"[PAE] Selected corner vertices")

        # Run measure - pass typed doc
        measure_result = sw_get_measure_from_doc(dt)
        result["measure"]["ok"] = measure_result.get("ok")
        ms = measure_result.get("measure", {})
        result["measure"]["distance_mm"] = ms.get("distance_mm")

        print(f"[PAE] measure: distance={result['measure']['distance_mm']}mm")

        # Gate 5: measure ok=True
        gate5 = measure_result.get("ok") is True
        result["gates"].append(f"measure_ok: {gate5}")

        # Gate 6: distance = expected diagonal
        gate6 = (
            result["measure"]["distance_mm"] is not None
            and abs(result["measure"]["distance_mm"] - EXPECTED_DIAGONAL_MM)
            < TOLERANCE_MM
        )
        result["gates"].append(
            f"measure_distance={EXPECTED_DIAGONAL_MM:.2f}mm: {gate6} (got {result['measure']['distance_mm']})"
        )

        # ── VERDICT ───────────────────────────────────────────────────────
        if all([gate1, gate2, gate3, gate4, gate5, gate6]):
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
