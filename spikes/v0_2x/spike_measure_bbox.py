"""Spike W30 — measure + bbox (perception axis, cont.) — go/no-go probe.

Tests two independent read-only capabilities:

(A) Bounding box — LOW risk:
    1. Build a 20×30×40mm box (non-cube to detect axis swaps).
    2. IModelDocExtension.GetBox(options) → 6 doubles (m).
    3. VERIFY: dx,dy,dz == 20,30,40mm (±rebuild noise), NOT degenerate.
    Also test IPartDoc.GetPartBox (existing impl) for comparison.

(B) Measure — MEDIUM risk (the real de-risk):
    1. Build the same 20×30×40mm box.
    2. Select two opposite corner vertices (using durable select_entity infra).
    3. IModelDocExtension.CreateMeasure() → IMeasure → Calculate(None).
    4. VERIFY: Distance = √(20²+30²+40²) = 53.85mm (±tolerance).
    Distance==0 or marshaling exception = NO-GO for measure.

HARD CHECKPOINT: bbox and measure ship INDEPENDENTLY.
If measure walls, SHIP BBOX ALONE + DEFERRED.md row for measure.

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_measure_bbox.py
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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "measure_bbox.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.selection.live import select_entity  # noqa: E402

# Box dimensions (non-cube to detect axis swaps)
DX_MM = 20.0
DY_MM = 30.0
DZ_MM = 40.0
DX_M = DX_MM / 1000.0
DY_M = DY_MM / 1000.0
DZ_M = DZ_MM / 1000.0

# Expected diagonal distance (mm)
EXPECTED_DIAGONAL_MM = math.sqrt(DX_MM**2 + DY_MM**2 + DZ_MM**2)
TOLERANCE_MM = 0.1  # Allow rebuild noise

SW_DOC_PART = 1


# ── Helpers ────────────────────────────────────────────────────────────────

def _find_part_template() -> str | None:
    import glob
    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\part.prtdot",
    ]:
        for m in glob.glob(pat):
            return m
    return None


def _retry(fn, *args, retries=3, delay=5, label=""):
    """Retry a COM call with backoff."""
    for attempt in range(retries):
        try:
            return fn(*args)
        except Exception as exc:
            if attempt < retries - 1:
                print(f"  [{label}] Attempt {attempt+1} failed: {exc!r}, retrying in {delay}s …")
                time.sleep(delay)
            else:
                raise


def _make_box_part(sw_typed: Any, mod: Any, path: str) -> tuple[Any | None, str | None]:
    """Create a 20×30×40mm box part. Returns (doc, error)."""
    try:
        doc = _retry(
            sw_typed.NewDocument,
            _find_part_template(),
            0, 0, 0,
            retries=3, delay=5, label="part_new",
        )
        if doc is None:
            return None, "NewDocument(part) returned None"
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
            True, False, False, 0, 0,
            DZ_M, 0.0,  # DZ is extrusion depth
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0,
            False,
        )
        if feat is None:
            return None, "FeatureExtrusion2 returned None"

        _retry(dt.SaveAs3, path, 0, 2, retries=2, delay=3, label="part_save")
        return doc, None
    except Exception as exc:
        return None, f"exception: {exc!r}"


def _probe_bbox_ext(doc: Any, mod: Any, dt: Any) -> dict[str, Any]:
    """Probe bounding-box APIs.

    Tests:
      - IPartDoc.GetPartBox(True) — existing implementation
      - IModelDocExtension.GetBox(options) — dispatch approach

    Returns dict with results and measured vs expected.
    """
    result: dict[str, Any] = {
        "verdict": "PENDING",
        "partbox": {"raw": None, "dx_mm": None, "dy_mm": None, "dz_mm": None, "error": None},
        "ext_getbox": {"raw": None, "dx_mm": None, "dy_mm": None, "dz_mm": None, "error": None},
        "expected": {"dx_mm": DX_MM, "dy_mm": DY_MM, "dz_mm": DZ_MM},
        "errors": [],
    }

    # ── IPartDoc.GetPartBox(True) ───────────────────────────────────────
    try:
        part_typed = typed(doc, "IPartDoc", module=mod)
        box = part_typed.GetPartBox(True)
        result["partbox"]["raw"] = list(box) if box else None
        if box and len(box) == 6:
            x_min, y_min, z_min = float(box[0]), float(box[1]), float(box[2])
            x_max, y_max, z_max = float(box[3]), float(box[4]), float(box[5])
            dx = (x_max - x_min) * 1000.0
            dy = (y_max - y_min) * 1000.0
            dz = (z_max - z_min) * 1000.0
            result["partbox"]["dx_mm"] = dx
            result["partbox"]["dy_mm"] = dy
            result["partbox"]["dz_mm"] = dz
            result["partbox"]["x_min_mm"] = x_min * 1000.0
            result["partbox"]["x_max_mm"] = x_max * 1000.0
            result["partbox"]["y_min_mm"] = y_min * 1000.0
            result["partbox"]["y_max_mm"] = y_max * 1000.0
            result["partbox"]["z_min_mm"] = z_min * 1000.0
            result["partbox"]["z_max_mm"] = z_max * 1000.0
    except Exception as exc:
        result["partbox"]["error"] = f"{exc!r}"
        result["errors"].append(f"GetPartBox: {exc!r}")

    # ── IModelDocExtension.GetBox(options) ────────────────────────────────
    # swBoundingBoxOptions_e: 0=tight (visible), 1=system (all)
    try:
        ext = dt.Extension
        if ext is None:
            result["ext_getbox"]["error"] = "Extension is None"
        else:
            # Try GetBox(0) — tight bbox
            box2 = ext.GetBox(0)
            result["ext_getbox"]["raw"] = list(box2) if box2 else None
            if box2 and len(box2) == 6:
                x_min, y_min, z_min = float(box2[0]), float(box2[1]), float(box2[2])
                x_max, y_max, z_max = float(box2[3]), float(box2[4]), float(box2[5])
                dx = (x_max - x_min) * 1000.0
                dy = (y_max - y_min) * 1000.0
                dz = (z_max - z_min) * 1000.0
                result["ext_getbox"]["dx_mm"] = dx
                result["ext_getbox"]["dy_mm"] = dy
                result["ext_getbox"]["dz_mm"] = dz
                result["ext_getbox"]["x_min_mm"] = x_min * 1000.0
                result["ext_getbox"]["x_max_mm"] = x_max * 1000.0
                result["ext_getbox"]["y_min_mm"] = y_min * 1000.0
                result["ext_getbox"]["y_max_mm"] = y_max * 1000.0
                result["ext_getbox"]["z_min_mm"] = z_min * 1000.0
                result["ext_getbox"]["z_max_mm"] = z_max * 1000.0
    except Exception as exc:
        result["ext_getbox"]["error"] = f"{exc!r}"
        result["errors"].append(f"Extension.GetBox: {exc!r}")

    # ── VERDICT: match expected dimensions? ──────────────────────────────
    # Prefer GetPartBox (existing impl), but verify GetBox works too
    pb = result["partbox"]
    eg = result["ext_getbox"]

    pb_match = (
        pb["dx_mm"] is not None
        and abs(pb["dx_mm"] - DX_MM) < TOLERANCE_MM
        and abs(pb["dy_mm"] - DY_MM) < TOLERANCE_MM
        and abs(pb["dz_mm"] - DZ_MM) < TOLERANCE_MM
    )
    eg_match = (
        eg["dx_mm"] is not None
        and abs(eg["dx_mm"] - DX_MM) < TOLERANCE_MM
        and abs(eg["dy_mm"] - DY_MM) < TOLERANCE_MM
        and abs(eg["dz_mm"] - DZ_MM) < TOLERANCE_MM
    )

    if pb_match:
        result["verdict"] = "GREEN"
        result["preferred_api"] = "IPartDoc.GetPartBox(True)"
        result["note"] = "GetPartBox matches expected dimensions"
    elif eg_match:
        result["verdict"] = "GREEN"
        result["preferred_api"] = "IModelDocExtension.GetBox(0)"
        result["note"] = "Extension.GetBox matches expected (GetPartBox may have issues)"
    elif pb["dx_mm"] is not None and pb["dx_mm"] > 0:
        result["verdict"] = "PARTIAL"
        result["note"] = f"bbox returned but dimensions mismatch: got {pb['dx_mm']},{pb['dy_mm']},{pb['dz_mm']}"
    else:
        result["verdict"] = "NO-GO"
        result["note"] = "bbox returned degenerate or None"

    return result


def _get_vertices(doc: Any, dt: Any, mod: Any) -> list[Any]:
    """Get all vertices from the part body."""
    vertices: list[Any] = []
    try:
        bodies = doc.GetBodies2(0, True)  # swSolidBody=0
        if bodies:
            for body in bodies:
                try:
                    verts = body.GetVertices()
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
        # IEntity.GetPoint returns (x, y, z) in metres
        pt = vertex.GetPoint
        if callable(pt):
            pt = pt()
        if pt and len(pt) >= 3:
            return (float(pt[0]), float(pt[1]), float(pt[2]))
    except Exception:
        pass
    return None


def _find_corner_vertices(vertices: list[Any]) -> tuple[Any | None, Any | None]:
    """Find two opposite corner vertices of the 20×30×40mm box.

    Looking for:
      - Vertex at (−10, −15, 0) or near origin corner
      - Vertex at (+10, +15, 40) or opposite corner
    Returns (corner1, corner2).
    """
    half_x = DX_M / 2.0
    half_y = DY_M / 2.0
    half_z = DZ_M / 2.0  # Actually the extrusion goes from 0 to DZ_M

    # For a centered sketch extruded +DZ:
    # Min corner: (-half_x, -half_y, 0)
    # Max corner: (+half_x, +half_y, DZ_M)

    min_corner = None
    max_corner = None
    min_coords = (-half_x, -half_y, 0.0)
    max_coords = (half_x, half_y, DZ_M)

    tolerance = 0.001  # 1mm tolerance for matching

    for v in vertices:
        coords = _vertex_coords(v)
        if coords is None:
            continue
        # Check if near min corner
        if (
            abs(coords[0] - min_coords[0]) < tolerance
            and abs(coords[1] - min_coords[1]) < tolerance
            and abs(coords[2] - min_coords[2]) < tolerance
        ):
            min_corner = v
        # Check if near max corner
        if (
            abs(coords[0] - max_coords[0]) < tolerance
            and abs(coords[1] - max_coords[1]) < tolerance
            and abs(coords[2] - max_coords[2]) < tolerance
        ):
            max_corner = v

    return min_corner, max_corner


def _probe_measure(doc: Any, dt: Any, mod: Any) -> dict[str, Any]:
    """Probe IMeasure API.

    Tests:
      - IModelDocExtension.CreateMeasure() → IMeasure
      - Select two vertices via select_entity
      - IMeasure.Calculate(None) → read Distance, DeltaX/Y/Z

    Returns dict with results and measured vs expected diagonal.
    """
    result: dict[str, Any] = {
        "verdict": "PENDING",
        "measure": {
            "distance_mm": None,
            "delta_x_mm": None,
            "delta_y_mm": None,
            "delta_z_mm": None,
            "error": None,
        },
        "expected": {"diagonal_mm": EXPECTED_DIAGONAL_MM},
        "selection": {"vertex_count": None, "corner1_found": False, "corner2_found": False},
        "errors": [],
    }

    # ── Get vertices ────────────────────────────────────────────────────
    vertices = _get_vertices(doc, dt, mod)
    result["selection"]["vertex_count"] = len(vertices)
    print(f"  [measure] Found {len(vertices)} vertices")

    if len(vertices) < 2:
        result["errors"].append("part has < 2 vertices")
        result["verdict"] = "NO-GO"
        return result

    # ── Find opposite corners ───────────────────────────────────────────
    v1, v2 = _find_corner_vertices(vertices)
    result["selection"]["corner1_found"] = v1 is not None
    result["selection"]["corner2_found"] = v2 is not None

    if v1 is None or v2 is None:
        result["errors"].append("could not find opposite corner vertices")
        result["verdict"] = "NO-GO"
        return result

    print(f"  [measure] Found corner vertices")

    # ── Clear selection ──────────────────────────────────────────────────
    try:
        dt.ClearSelection2(True)
    except Exception:
        pass

    # ── Select both vertices ─────────────────────────────────────────────
    # select_entity uses IEntity.Select2(append, mark)
    ok1 = select_entity(v1, append=False, mark=0)
    ok2 = select_entity(v2, append=True, mark=0)

    if not ok1:
        result["errors"].append("select_entity(v1) failed")
        result["verdict"] = "NO-GO"
        return result
    if not ok2:
        result["errors"].append("select_entity(v2) failed")
        result["verdict"] = "NO-GO"
        return result

    print(f"  [measure] Selected both vertices")

    # ── Verify selection count ───────────────────────────────────────────
    try:
        sel_mgr = dt.SelectionManager
        count = sel_mgr.GetSelectedObjectCount2(-1)
        if count != 2:
            result["errors"].append(f"selection count = {count}, expected 2")
            result["verdict"] = "NO-GO"
            return result
    except Exception as exc:
        result["errors"].append(f"SelectionManager check: {exc!r}")
        result["verdict"] = "NO-GO"
        return result

    # ── CreateMeasure ────────────────────────────────────────────────────
    measure = None
    try:
        ext = dt.Extension
        measure = ext.CreateMeasure
        if callable(measure):
            measure = measure()
        if measure is None:
            # Try as property
            measure = ext.CreateMeasure
    except Exception as exc:
        result["measure"]["error"] = f"CreateMeasure: {exc!r}"
        result["errors"].append(f"CreateMeasure: {exc!r}")
        result["verdict"] = "NO-GO"
        return result

    if measure is None:
        result["measure"]["error"] = "CreateMeasure returned None"
        result["errors"].append("CreateMeasure returned None")
        result["verdict"] = "NO-GO"
        return result

    print(f"  [measure] Got IMeasure object")

    # ── Calculate ────────────────────────────────────────────────────────
    try:
        # Calculate(None) — measure currently selected entities
        ret = measure.Calculate
        if callable(ret):
            ret(None)
        else:
            # Property access
            pass
    except Exception as exc:
        result["measure"]["error"] = f"Calculate: {exc!r}"
        result["errors"].append(f"Calculate: {exc!r}")
        result["verdict"] = "NO-GO"
        return result

    print(f"  [measure] Calculate called")

    # ── Read Distance ────────────────────────────────────────────────────
    try:
        dist = measure.Distance
        if callable(dist):
            dist = dist()
        if dist is not None and dist != -1.0:
            result["measure"]["distance_mm"] = float(dist) * 1000.0
    except Exception as exc:
        result["errors"].append(f"Distance read: {exc!r}")

    # ── Read DeltaX/Y/Z ──────────────────────────────────────────────────
    try:
        dx = measure.DeltaX
        if callable(dx):
            dx = dx()
        if dx is not None and dx != -1.0:
            result["measure"]["delta_x_mm"] = float(dx) * 1000.0
    except Exception:
        pass

    try:
        dy = measure.DeltaY
        if callable(dy):
            dy = dy()
        if dy is not None and dy != -1.0:
            result["measure"]["delta_y_mm"] = float(dy) * 1000.0
    except Exception:
        pass

    try:
        dz = measure.DeltaZ
        if callable(dz):
            dz = dz()
        if dz is not None and dz != -1.0:
            result["measure"]["delta_z_mm"] = float(dz) * 1000.0
    except Exception:
        pass

    print(f"  [measure] distance_mm={result['measure']['distance_mm']}")

    # ── VERDICT ────────────────────────────────────────────────────────
    dist_mm = result["measure"]["distance_mm"]

    if dist_mm is None:
        result["verdict"] = "NO-GO"
        result["note"] = "Distance read returned None or -1"
    elif dist_mm == 0.0:
        result["verdict"] = "NO-GO"
        result["note"] = "Distance = 0 (Calculate succeeded but no measurement)"
    elif abs(dist_mm - EXPECTED_DIAGONAL_MM) < TOLERANCE_MM:
        result["verdict"] = "GREEN"
        result["note"] = f"Distance matches expected diagonal (within {TOLERANCE_MM}mm)"
    else:
        result["verdict"] = "PARTIAL"
        result["note"] = f"Distance={dist_mm}mm, expected={EXPECTED_DIAGONAL_MM}mm"

    return result


# ── Main ────────────────────────────────────────────────────────────────

def main() -> None:
    pythoncom.CoInitialize()
    sw = get_sw_app()
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)

    result: dict[str, Any] = {
        "verdict": "PENDING",
        "bbox": None,
        "measure": None,
        "overall": "PENDING",
        "errors": [],
    }

    tmpdir = tempfile.mkdtemp(prefix="aisw_W30_")
    part_path = str(Path(tmpdir) / "box_20x30x40.sldprt")

    try:
        # ── Step 1: Create box part ──────────────────────────────────────
        print("[S1] Creating 20×30×40mm box part …")
        doc, err = _make_box_part(sw_typed, mod, part_path)
        if err:
            result["errors"].append(f"make_part: {err}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return
        print(f"[S1] Part saved: {part_path}")

        dt = typed(doc, "IModelDoc2", module=mod)

        # Force rebuild to ensure geometry is computed
        try:
            dt.ForceRebuild3(True)
        except Exception:
            pass
        time.sleep(1)

        # ── Step 2: Probe BBOX ───────────────────────────────────────────
        print("[S1] Probing bounding-box APIs …")
        bbox_result = _probe_bbox_ext(doc, mod, dt)
        result["bbox"] = bbox_result
        result["errors"].extend(bbox_result.get("errors", []))
        print(f"[S1] bbox verdict: {bbox_result['verdict']}")
        print(f"  GetPartBox: dx={bbox_result['partbox']['dx_mm']}, "
              f"dy={bbox_result['partbox']['dy_mm']}, dz={bbox_result['partbox']['dz_mm']}")
        if bbox_result["ext_getbox"]["dx_mm"]:
            print(f"  Ext.GetBox: dx={bbox_result['ext_getbox']['dx_mm']}, "
                  f"dy={bbox_result['ext_getbox']['dy_mm']}, dz={bbox_result['ext_getbox']['dz_mm']}")

        # ── Step 3: Probe MEASURE ────────────────────────────────────────
        print("[S1] Probing IMeasure API …")
        measure_result = _probe_measure(doc, dt, mod)
        result["measure"] = measure_result
        result["errors"].extend(measure_result.get("errors", []))
        print(f"[S1] measure verdict: {measure_result['verdict']}")
        print(f"  Distance: {measure_result['measure']['distance_mm']}mm "
              f"(expected: {EXPECTED_DIAGONAL_MM}mm)")

        # ── Overall verdict ──────────────────────────────────────────────
        bbox_ok = result["bbox"]["verdict"] == "GREEN"
        measure_ok = result["measure"]["verdict"] == "GREEN"

        if bbox_ok and measure_ok:
            result["overall"] = "GREEN"
            result["note"] = "Both bbox and measure GREEN — ship both"
        elif bbox_ok and not measure_ok:
            result["overall"] = "PARTIAL"
            result["note"] = "bbox GREEN, measure NO-GO — ship bbox only, DEFER measure"
        elif not bbox_ok and measure_ok:
            result["overall"] = "PARTIAL"
            result["note"] = "measure GREEN, bbox NO-GO — unexpected, ship measure only"
        else:
            result["overall"] = "NO-GO"
            result["note"] = "Both bbox and measure NO-GO"

        # ── Confirmed APIs ───────────────────────────────────────────────
        result["confirmed_sigs"] = {
            "bbox": {
                "api": "IPartDoc.GetPartBox(True)",
                "return": "6-tuple (xmin,ymin,zmin,xmax,ymax,zmax) in metres",
                "fallback": "IModelDocExtension.GetBox(options) — options=0 tight, 1 system",
            },
            "measure": {
                "api": "IModelDocExtension.CreateMeasure() → IMeasure",
                "calculate": "IMeasure.Calculate(None) — measure selected entities",
                "props": "Distance, DeltaX, DeltaY, DeltaZ (metres, -1 when N/A)",
                "selection": "select_entity(vertex) via IEntity.Select2(append, mark)",
            },
        }

    except Exception as exc:
        result["errors"].append(f"top-level: {exc!r}")
        result["overall"] = "NO-GO"
    finally:
        # Cleanup
        try:
            sw_typed.CloseAllDocuments(True)
        except Exception:
            pass
        _write_result(result)
        print(f"\n[S1] OVERALL: {result['overall']}")
        print(f"[S1] bbox: {result['bbox']['verdict'] if result['bbox'] else 'N/A'}")
        print(f"[S1] measure: {result['measure']['verdict'] if result['measure'] else 'N/A'}")


def _write_result(result: dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[S1] Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()