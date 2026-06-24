"""Wave-33 Slice 3: Production PAE for DXF export.

Tests the production export path for DXF:
  1. Build a dimensioned part → drawing → export DXF via production path
     → parse the .dxf → assert real entity counts (≥ the view's edges)
  2. Test part→DXF attempt → assert fail-closed ValueError

Expected:
  - DXF file on disk with non-zero size
  - Entity count ≥ 4 (front view of a box has 4 lines)
  - Part/Assembly → DXF: ValueError with doc-type mismatch message

HARD CHECKPOINT:
  Header-only DXF / no rejection on part→DXF = FAIL.
"""

from __future__ import annotations

import glob
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "export_dxf_pae.json"

# swDocumentTypes_e
SW_DOC_PART = 1
SW_DOC_DRAWING = 3

results: dict[str, Any] = {
    "probe": "w33_export_dxf_pae",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "verdict": "UNKNOWN",
    "dxf_paths": {},
    "entity_counts": {},
    "dxf_size_bytes": {},
    "doc_type_rejection": None,
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


def _close_all_docs(sw: Any) -> None:
    """Close all open documents."""
    try:
        docs = sw.GetDocuments()
        if docs:
            for d in docs:
                try:
                    t = d.GetTitle
                    t = t() if callable(t) else t
                    sw.CloseDoc(t)
                except Exception:
                    pass
    except Exception:
        pass


def _build_test_part(sw: Any, part_path: str) -> bool:
    """Build a small box part (40x20x10) for drawing model."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W33PAEBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 40.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 10.0,
            },
        ],
    }
    r = part_build(spec, save_as=part_path, save_format="current", no_dim=True)
    return bool(r.ok) and os.path.isfile(part_path)


def _parse_dxf_entities(dxf_path: str) -> dict[str, int]:
    """Parse a DXF file and count entity types."""
    entity_types = [
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
        "CIRCLE",
        "ARC",
        "SPLINE",
        "ELLIPSE",
        "POINT",
        "TEXT",
        "MTEXT",
    ]
    counts: dict[str, int] = {et: 0 for et in entity_types}
    total_entities = 0

    try:
        with open(dxf_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        lines = content.split("\n")
        prev_line = ""
        for line in lines:
            stripped = line.strip()
            if prev_line == "0" and stripped.upper() in entity_types:
                counts[stripped.upper()] = counts.get(stripped.upper(), 0) + 1
                total_entities += 1
            prev_line = stripped

        counts["_total_geometry"] = total_entities

    except Exception as e:
        counts["_error"] = str(e)

    return counts


def run() -> str:
    print("=" * 70)
    print("Wave-33 Slice 3: Production PAE for DXF export")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.drawing.lifecycle import commit_drawing
    from ai_sw_bridge.export.dispatch import ExportRequest, export_all

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all_docs(sw)

    tsw = typed(sw, "ISldWorks", module=mod)

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # --- Build test part ---
    print("\n--- Build test part ---")
    part_path = str(_tmp / f"w33_pae_box_{_ts}.SLDPRT")
    if not _build_test_part(sw, part_path):
        results["verdict"] = "FAIL (part build failed)"
        save_results()
        return "FAIL"
    gate("part_build", True, f"path={part_path}")

    # --- Find drawing template ---
    print("\n--- Drawing template ---")
    drwdots = []
    for pat in (
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot",
    ):
        drwdots.extend(glob.glob(pat))
    drwdots = sorted(set(drwdots))
    if not drwdots:
        results["verdict"] = "FAIL (no drawing template)"
        save_results()
        return "FAIL"
    template_path = drwdots[0]
    gate("template_found", True, f"path={template_path}")

    # ================================================================
    # TEST 1: Drawing -> DXF (production path)
    # ================================================================
    print("\n=== TEST 1: Drawing -> DXF via production path ===")

    # Build drawing using production commit_drawing
    drawing_spec: dict[str, Any] = {
        "kind": "drawing",
        "model": part_path,
        "sheets": [
            {
                "name": "Sheet1",
                "views": ["front"],  # 1 view = 4 lines
            },
        ],
        "output_dir": str(_tmp),
        "filename": f"w33_pae_drawing_{_ts}",
    }

    drawing_output_path = str(_tmp / f"w33_pae_drawing_{_ts}.SLDDRW")

    drawing_result = commit_drawing(sw, drawing_spec, drawing_output_path)
    if not drawing_result.get("ok", False):
        gate(
            "drawing_build",
            False,
            f"commit_drawing failed: {drawing_result.get('error', 'unknown')}",
        )
        results["verdict"] = "FAIL (drawing build failed)"
        save_results()
        return "FAIL"
    gate("drawing_build", True, f"path={drawing_output_path}")

    drawing_path = drawing_result.get("path", drawing_output_path)
    results["dxf_paths"]["drawing"] = drawing_path

    # Open the drawing
    try:
        open_ret = tsw.OpenDoc6(drawing_path, SW_DOC_DRAWING, 1, "", 0, 0)
    except Exception as e:
        gate("open_drawing", False, f"raised: {e}")
        results["verdict"] = "FAIL (cannot open drawing)"
        save_results()
        return "FAIL"

    if isinstance(open_ret, tuple):
        doc_raw = open_ret[0]
    else:
        doc_raw = open_ret

    if doc_raw is None or isinstance(doc_raw, int):
        gate("open_drawing", False, f"returned {doc_raw!r}")
        results["verdict"] = "FAIL (cannot open drawing)"
        save_results()
        return "FAIL"
    gate("open_drawing", True)

    doc_m2 = typed_qi(doc_raw, "IModelDoc2", module=mod)

    # Export to DXF via production path
    dxf_path = str(_tmp / f"w33_pae_dxf_{_ts}.dxf")

    req = ExportRequest(
        format="dxf",
        output_dir=_tmp,
        filename=f"w33_pae_dxf_{_ts}",
        sheets="all",
    )

    export_results = export_all(doc_m2, [req], f"w33_pae_dxf_{_ts}")
    if not export_results or len(export_results) != 1:
        gate(
            "export_call",
            False,
            f"expected 1 result, got {len(export_results) if export_results else 0}",
        )
        results["verdict"] = "FAIL"
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        save_results()
        return "FAIL"

    r = export_results[0]
    gate("export_ok", r.ok, f"error={r.error}")

    if not r.ok:
        results["verdict"] = f"FAIL (DXF export failed: {r.error})"
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        save_results()
        return "FAIL"

    if not Path(dxf_path).exists():
        gate("dxf_exists", False, f"path={dxf_path}")
        results["verdict"] = "FAIL (DXF not created)"
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        save_results()
        return "FAIL"
    gate("dxf_exists", True, f"path={dxf_path}")

    # Check file size
    dxf_size = Path(dxf_path).stat().st_size
    results["dxf_size_bytes"]["drawing"] = dxf_size
    gate("dxf_size", dxf_size > 100, f"size={dxf_size} bytes")

    # Parse DXF entities
    counts = _parse_dxf_entities(dxf_path)
    results["entity_counts"]["drawing"] = counts
    total_geo = counts.get("_total_geometry", 0)
    line_count = counts.get("LINE", 0)
    gate(
        "entity_count",
        total_geo >= 4 or line_count >= 4,
        f"total={total_geo}, lines={line_count}",
    )

    # Close drawing
    try:
        sw.CloseDoc(drawing_path)
    except Exception:
        pass

    # ================================================================
    # TEST 2: Part -> DXF (fail-closed)
    # ================================================================
    print("\n=== TEST 2: Part -> DXF (fail-closed) ===")
    _close_all_docs(sw)

    # Open the part
    try:
        open_ret = tsw.OpenDoc6(part_path, SW_DOC_PART, 1, "", 0, 0)
    except Exception as e:
        gate("open_part", False, f"raised: {e}")
        results["verdict"] = "FAIL (cannot open part)"
        save_results()
        return "FAIL"

    if isinstance(open_ret, tuple):
        part_doc_raw = open_ret[0]
    else:
        part_doc_raw = open_ret

    if part_doc_raw is None or isinstance(part_doc_raw, int):
        gate("open_part", False, f"returned {part_doc_raw!r}")
        results["verdict"] = "FAIL (cannot open part)"
        save_results()
        return "FAIL"
    gate("open_part", True)

    part_doc_m2 = typed_qi(part_doc_raw, "IModelDoc2", module=mod)

    # Attempt DXF export on part (should fail-closed)
    dxf_part_path = str(_tmp / f"w33_pae_part_dxf_{_ts}.dxf")

    req_part = ExportRequest(
        format="dxf",
        output_dir=_tmp,
        filename=f"w33_pae_part_dxf_{_ts}",
    )

    export_part_results = export_all(part_doc_m2, [req_part], f"w33_pae_part_dxf_{_ts}")
    if not export_part_results or len(export_part_results) != 1:
        gate("export_part_call", False, "no results returned")
        results["verdict"] = "FAIL"
        try:
            sw.CloseDoc(part_path)
        except Exception:
            pass
        save_results()
        return "FAIL"

    r_part = export_part_results[0]

    # The export should fail-closed with a doc-type mismatch error
    if r_part.ok:
        gate(
            "part_dxf_rejected",
            False,
            f"Part→DXF succeeded unexpectedly! path={r_part.path}",
        )
        results["verdict"] = "FAIL (Part→DXF should be rejected)"
        results["doc_type_rejection"] = {
            "expected": "ValueError with doc-type mismatch",
            "actual": f"ok=True, path={r_part.path}",
        }
        try:
            sw.CloseDoc(part_path)
        except Exception:
            pass
        save_results()
        return "FAIL"

    # Check the error message contains doc-type info
    error_msg = r_part.error or ""
    has_doc_type_error = (
        "Drawing (.SLDDRW)" in error_msg
        or "doc type is" in error_msg
        or "1=Part" in error_msg
    )
    gate("part_dxf_error_msg", has_doc_type_error, f"error={error_msg}")
    results["doc_type_rejection"] = {
        "ok": r_part.ok,
        "error": error_msg,
        "expected": "Drawing (.SLDDRW) document required",
    }

    # Verify no DXF was created for part
    if Path(dxf_part_path).exists():
        gate(
            "part_dxf_not_created",
            False,
            f"DXF file created despite rejection: {dxf_part_path}",
        )
        results["verdict"] = "FAIL (Part→DXF created file despite rejection)"
        try:
            sw.CloseDoc(part_path)
        except Exception:
            pass
        save_results()
        return "FAIL"
    gate("part_dxf_not_created", True, "no DXF file for part")

    # Close part
    try:
        sw.CloseDoc(part_path)
    except Exception:
        pass

    # ================================================================
    # VERDICT
    # ================================================================
    print("\n--- Verdict ---")

    drawing_ok = results["gates"].get("entity_count", {}).get("ok", False)
    doc_type_ok = results["gates"].get("part_dxf_rejected", {}).get(
        "ok", True
    ) and results["gates"].get("part_dxf_error_msg", {}).get("ok", False)

    if drawing_ok and doc_type_ok:
        results["verdict"] = "PASS"
        print(
            ">>> VERDICT: PASS (DXF export production path works + doc-type fail-closed)"
        )
    else:
        fail_reasons = []
        if not drawing_ok:
            fail_reasons.append("DXF entity count insufficient")
        if not doc_type_ok:
            fail_reasons.append("Part→DXF rejection failed")
        results["verdict"] = f"FAIL ({'; '.join(fail_reasons)})"
        print(f">>> VERDICT: FAIL ({'; '.join(fail_reasons)})")

    save_results()
    return results["verdict"]


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception:
        import traceback

        traceback.print_exc()
        results["verdict"] = (
            f"FAIL (unhandled exception: {traceback.format_exc()[:200]})"
        )
        save_results()
        verdict = "FAIL"
    sys.exit(0 if verdict in ("PASS", "GREEN") else 1)
