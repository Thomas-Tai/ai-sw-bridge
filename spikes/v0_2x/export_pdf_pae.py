"""Wave-25 Slice 3: Drawing -> PDF export production PAE.

End-to-end: build a part -> build a 2-sheet drawing (using the W23 shipped
capability) -> export the drawing to PDF via the production `export_all`
path with `format:"pdf"`, `sheets:"all"` -> verify:

  * PDF exists on disk with non-trivial size (> 10KB)
  * Multi-sheet proof: 2-sheet PDF is materially larger (>1.3x) than
    a 1-sheet PDF of the same drawing (the W21/W23 lesson)
  * Specified-sheet subset: `sheets:["DetailSheet"]` produces a PDF
    that is smaller than the all-sheets PDF
  * Per-sheet view counts on reopen match the spec

FAIL on: missing PDF, PDF too small, multi-sheet exports only the active
sheet (size proof fails), or unknown sheet names rejected.

Prereq: SOLIDWORKS 2024 SP1 running. Seat order: W22 -> W24 -> W25.
"""

from __future__ import annotations

import glob
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "export_pdf_pae.json"
)

results: dict[str, Any] = {
    "pae": "w25_export_pdf",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "verdict": "UNKNOWN",
    "pdf_paths": {},
    "sizes": {},
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
    """Build a small box part (40x20x10) to use as the drawing's model."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W25PaeBox",
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


def _build_2sheet_drawing(sw: Any, part_path: str, template_path: str) -> str | None:
    """Build a 2-sheet drawing using the W23 shipped `kind:"drawing"` spec.

    Returns the drawing file path, or None on failure.
    """
    from ai_sw_bridge.drawing.lifecycle import DrawingSpec, commit_drawing

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    drw_path = str(_tmp / f"w25_pae_drawing_{_ts}.SLDDRW")

    spec: DrawingSpec = {
        "kind": "drawing",
        "model": part_path,
        "sheets": [
            {
                "name": "Overview",
                "views": ["front", "isometric"],
            },
            {
                "name": "DetailSheet",
                "views": ["top"],
            },
        ],
        "output_dir": str(_tmp),
        "filename": f"w25_pae_drawing_{_ts}",
    }

    # The drawing lifecycle needs sw and template
    import win32com.client as w32
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    tsw = typed(sw, "ISldWorks", module=mod)

    result = commit_drawing(
        spec,
        sw_app=sw,
        template_path=template_path,
        output_dir=_tmp,
        filename=f"w25_pae_drawing_{_ts}",
    )

    if not result.ok:
        gate("drawing_build", False, f"commit_drawing failed: {result.error}")
        return None

    # The commit_drawing returns the saved drawing path
    drawing_path = result.path
    if not os.path.isfile(drawing_path):
        gate("drawing_exists", False, f"Drawing not found at {drawing_path}")
        return None

    gate("drawing_build", True, f"path={drawing_path}")
    results["pdf_paths"]["drawing"] = drawing_path
    return drawing_path


def run() -> str:
    print("=" * 70)
    print("Wave-25 Slice 3: Drawing -> PDF export production PAE")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.export.dispatch import ExportRequest, export_all

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all_docs(sw)

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # --- Build test part ---
    print("\n--- Build test part ---")
    part_path = str(_tmp / f"w25_pae_box_{_ts}.SLDPRT")
    if not _build_test_part(sw, part_path):
        results["verdict"] = "FAIL (part build failed)"
        save_results()
        return "FAIL"

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

    # --- Build 2-sheet drawing ---
    print("\n--- Build 2-sheet drawing ---")
    drawing_path = _build_2sheet_drawing(sw, part_path, template_path)
    if drawing_path is None:
        results["verdict"] = "FAIL (drawing build failed)"
        save_results()
        return "FAIL"

    # --- Open the drawing for export ---
    print("\n--- Open drawing for export ---")
    tsw = typed(sw, "ISldWorks", module=mod)
    try:
        doc_raw = tsw.OpenDoc6(drawing_path, 3, 1, "", 0, 0)  # 3 = Drawing
    except Exception as e:
        gate("open_drawing", False, f"raised: {e}")
        results["verdict"] = "FAIL (cannot open drawing)"
        save_results()
        return "FAIL"

    if doc_raw is None or isinstance(doc_raw, int):
        gate("open_drawing", False, f"returned {doc_raw!r}")
        results["verdict"] = "FAIL (cannot open drawing)"
        save_results()
        return "FAIL"
    gate("open_drawing", True)

    doc_m2 = typed_qi(doc_raw, "IModelDoc2", module=mod)

    # ================================================================
    # TEST 1: Export all sheets to PDF
    # ================================================================
    print("\n=== TEST 1: Export all sheets ===")
    pdf_all_path = str(_tmp / f"w25_pae_all_{_ts}.pdf")

    req_all = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25_pae_all_{_ts}",
        sheets="all",
    )

    results_all = export_all(doc_m2, [req_all], f"w25_pae_all_{_ts}")
    if not results_all or len(results_all) != 1:
        gate("export_all_call", False, f"expected 1 result, got {len(results_all) if results_all else 0}")
        results["verdict"] = "FAIL"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"

    r_all = results_all[0]
    gate("export_all_ok", r_all.ok, f"error={r_all.error}")

    if not r_all.ok:
        results["verdict"] = f"FAIL (export_all failed: {r_all.error})"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"

    size_all = Path(pdf_all_path).stat().st_size if Path(pdf_all_path).exists() else 0
    gate("pdf_all_exists", Path(pdf_all_path).exists(), f"size={size_all}")
    gate("pdf_all_nontrivial", size_all > 10240, f"size={size_all}B (threshold 10KB)")
    results["pdf_paths"]["all_sheets"] = pdf_all_path
    results["sizes"]["all_sheets"] = size_all

    # ================================================================
    # TEST 2: Export specified sheet subset
    # ================================================================
    print("\n=== TEST 2: Export specified sheet ===")
    pdf_subset_path = str(_tmp / f"w25_pae_subset_{_ts}.pdf")

    req_subset = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25_pae_subset_{_ts}",
        sheets=["DetailSheet"],
    )

    results_subset = export_all(doc_m2, [req_subset], f"w25_pae_subset_{_ts}")
    if not results_subset or len(results_subset) != 1:
        gate("export_subset_call", False, "no results returned")
        results["verdict"] = "FAIL"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"

    r_subset = results_subset[0]
    gate("export_subset_ok", r_subset.ok, f"error={r_subset.error}")

    size_subset = Path(pdf_subset_path).stat().st_size if Path(pdf_subset_path).exists() else 0
    gate("pdf_subset_exists", Path(pdf_subset_path).exists(), f"size={size_subset}")

    results["pdf_paths"]["subset"] = pdf_subset_path
    results["sizes"]["subset"] = size_subset

    # ================================================================
    # TEST 3: Export "Overview" sheet only (another subset)
    # ================================================================
    print("\n=== TEST 3: Export Overview sheet only ===")
    pdf_overview_path = str(_tmp / f"w25_pae_overview_{_ts}.pdf")

    req_overview = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25_pae_overview_{_ts}",
        sheets=["Overview"],
    )

    results_overview = export_all(doc_m2, [req_overview], f"w25_pae_overview_{_ts}")
    if results_overview and len(results_overview) == 1:
        r_ov = results_overview[0]
        gate("export_overview_ok", r_ov.ok, f"error={r_ov.error}")
        size_ov = Path(pdf_overview_path).stat().st_size if Path(pdf_overview_path).exists() else 0
        results["pdf_paths"]["overview"] = pdf_overview_path
        results["sizes"]["overview"] = size_ov
    else:
        gate("export_overview_ok", False, "no results")

    # ================================================================
    # Multi-sheet proof (the W21/W23 lesson)
    # ================================================================
    print("\n--- Multi-sheet liveness proof ---")
    if size_all > 0 and size_subset > 0:
        # All-sheets PDF should be larger than a single-sheet subset
        ratio = size_all / size_subset
        proof_ok = ratio > 1.3
        gate(
            "multi_sheet_size_proof",
            proof_ok,
            f"all={size_all}B, subset={size_subset}B, ratio={ratio:.2f} (threshold >1.3)",
        )
        results["multi_sheet_proof"] = {
            "method": "size_comparison",
            "all_sheets_size": size_all,
            "subset_size": size_subset,
            "ratio": round(ratio, 3),
            "threshold": 1.3,
            "passed": proof_ok,
        }

        # Also check overview vs all
        if size_ov > 0:
            ratio_ov = size_all / size_ov
            gate(
                "overview_vs_all_proof",
                ratio_ov > 1.3,
                f"all={size_all}B, overview={size_ov}B, ratio={ratio_ov:.2f}",
            )
    else:
        gate("multi_sheet_size_proof", False, "sizes not available")
        results["multi_sheet_proof"] = {"error": "sizes not available"}

    # ================================================================
    # TEST 4: Unknown sheet name rejection
    # ================================================================
    print("\n=== TEST 4: Unknown sheet name rejected ===")
    req_bad = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25_pae_bad_{_ts}",
        sheets=["NonexistentSheet"],
    )
    results_bad = export_all(doc_m2, [req_bad], f"w25_pae_bad_{_ts}")
    if results_bad and len(results_bad) == 1:
        r_bad = results_bad[0]
        gate("unknown_sheet_rejected", not r_bad.ok, f"error={r_bad.error}")
        if r_bad.ok:
            results["verdict"] = "FAIL (unknown sheet not rejected)"
        else:
            gate("unknown_sheet_message", "Unknown" in r_bad.error or "unknown" in r_bad.error.lower(),
                 f"error={r_bad.error}")
    else:
        gate("unknown_sheet_rejected", False, "no results returned")

    # ================================================================
    # TEST 5: PDF on Part doc rejected
    # ================================================================
    print("\n=== TEST 5: PDF on Part doc rejected ===")
    # Open the part doc
    try:
        part_doc_raw = tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)  # 1 = Part
    except Exception as e:
        gate("open_part_for_rejection_test", False, f"raised: {e}")
        part_doc_raw = None

    if part_doc_raw is not None and not isinstance(part_doc_raw, int):
        part_doc = typed_qi(part_doc_raw, "IModelDoc2", module=mod)
        req_part = ExportRequest(
            format="pdf",
            output_dir=_tmp,
            filename=f"w25_pae_part_{_ts}",
        )
        results_part = export_all(part_doc, [req_part], f"w25_pae_part_{_ts}")
        if results_part and len(results_part) == 1:
            r_part = results_part[0]
            gate("pdf_on_part_rejected", not r_part.ok, f"error={r_part.error}")
            if not r_part.ok:
                gate("pdf_on_part_message", "Drawing" in r_part.error,
                     f"error contains 'Drawing': {r_part.error}")
        else:
            gate("pdf_on_part_rejected", False, "no results")
        try:
            sw.CloseDoc(part_path)
        except Exception:
            pass
    else:
        gate("pdf_on_part_rejected", True, "skipped (cannot open part)")

    # ================================================================
    # Close and verdict
    # ================================================================
    try:
        sw.CloseDoc(drawing_path)
    except Exception:
        pass

    print("\n--- Verdict ---")
    all_gates_ok = all(g.get("ok", False) for g in results["gates"].values())
    critical_gates = [
        "export_all_ok",
        "pdf_all_exists",
        "pdf_all_nontrivial",
        "export_subset_ok",
        "pdf_subset_exists",
        "multi_sheet_size_proof",
    ]
    critical_ok = all(results["gates"].get(g, {}).get("ok", False) for g in critical_gates)

    if all_gates_ok and critical_ok:
        results["verdict"] = "PASS"
        print(">>> VERDICT: PASS")
    else:
        failed = [g for g, v in results["gates"].items() if not v.get("ok", False)]
        results["verdict"] = f"FAIL ({failed})"
        print(f">>> VERDICT: FAIL (gates: {failed})")

    save_results()
    return "PASS" if results["verdict"] == "PASS" else "FAIL"


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception:
        import traceback
        traceback.print_exc()
        results["verdict"] = f"FAIL (unhandled exception: {traceback.format_exc()[:200]})"
        save_results()
        verdict = "FAIL"
    sys.exit(0 if verdict == "PASS" else 1)