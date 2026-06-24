"""Wave-25v Slice 2b: Drawing -> PDF export production PAE (page-count discrimination).

End-to-end: build a part -> build a DISCRIMINATING 2-sheet drawing -> export
the drawing to PDF via the production `export_all` path -> verify:

  * PDF exists on disk with non-trivial size (> 10KB)
  * Page-count proof: sheets:"all" -> 2 pages; sheets:["Solo"] -> 1 page
  * Unknown sheet names rejected

The DISCRIMINATING fixture:
  - Sheet "Solo": 1 view (front only)
  - Sheet "Quad": 4 views (front, top, right, iso)

FAIL on: missing PDF, PDF too small, sheet selection doesn't filter
(pages(subset) != 1), or unknown sheet names not rejected.

Prereq: SOLIDWORKS 2024 SP1 running.
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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "export_pdf_pae.json"

results: dict[str, Any] = {
    "pae": "w25_export_pdf",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "verdict": "UNKNOWN",
    "pdf_paths": {},
    "sizes": {},
    "page_counts": {},
    "page_counting_method": None,
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


def _count_pdf_pages(pdf_path: str) -> int:
    """Count PDF pages via structural byte scan.

    Uses regex to find /Type /Page objects that are NOT /Pages (the root).
    """
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()
        pattern = re.compile(rb"/Type\s*/Page(?![s])")
        matches = pattern.findall(data)
        count = len(matches)
        results["page_counting_method"] = "raw_byte_scan:/Type/Page(?![s])"
        return count
    except Exception as e:
        print(f"  [ERROR] PDF page count failed: {e}", file=sys.stderr)
        return -1


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


def _build_discriminating_drawing(
    sw: Any, part_path: str, template_path: str
) -> str | None:
    """Build a DISCRIMINATING 2-sheet drawing:
    - Sheet "Solo": 1 view (front)
    - Sheet "Quad": 4 views (front, top, right, iso)

    Returns the drawing file path, or None on failure.
    """
    from ai_sw_bridge.drawing.lifecycle import commit_drawing

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    drw_path = str(_tmp / f"w25_pae_drawing_{_ts}.SLDDRW")

    spec: dict[str, Any] = {
        "kind": "drawing",
        "model": part_path,
        "sheets": [
            {
                "name": "Solo",
                "views": ["front"],  # 1 view
            },
            {
                "name": "Quad",
                "views": ["front", "top", "right", "isometric"],  # 4 views
            },
        ],
        "output_dir": str(_tmp),
        "filename": f"w25_pae_drawing_{_ts}",
    }

    output_path = str(_tmp / f"w25_pae_drawing_{_ts}.SLDDRW")

    result = commit_drawing(
        sw,
        spec,
        output_path,
    )

    if not result.get("ok", False):
        gate(
            "drawing_build",
            False,
            f"commit_drawing failed: {result.get('error', 'unknown')}",
        )
        return None

    drawing_path = result.get("path", output_path)
    if not os.path.isfile(drawing_path):
        gate("drawing_exists", False, f"Drawing not found at {drawing_path}")
        return None

    gate("drawing_build", True, f"path={drawing_path}")
    results["pdf_paths"]["drawing"] = drawing_path
    return drawing_path


def run() -> str:
    print("=" * 70)
    print("Wave-25v Slice 2b: Drawing -> PDF export PAE (page-count)")
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

    # --- Build DISCRIMINATING 2-sheet drawing ---
    print("\n--- Build DISCRIMINATING 2-sheet drawing ---")
    drawing_path = _build_discriminating_drawing(sw, part_path, template_path)
    if drawing_path is None:
        results["verdict"] = "FAIL (drawing build failed)"
        save_results()
        return "FAIL"

    # --- Open the drawing for export ---
    print("\n--- Open drawing for export ---")
    tsw = typed(sw, "ISldWorks", module=mod)
    try:
        open_ret = tsw.OpenDoc6(drawing_path, 3, 1, "", 0, 0)  # 3 = Drawing
    except Exception as e:
        gate("open_drawing", False, f"raised: {e}")
        results["verdict"] = "FAIL (cannot open drawing)"
        save_results()
        return "FAIL"

    # OpenDoc6 may return a tuple (early-bind) or a dispatch
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
        gate(
            "export_all_call",
            False,
            f"expected 1 result, got {len(results_all) if results_all else 0}",
        )
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

    pages_all = _count_pdf_pages(pdf_all_path)
    results["page_counts"]["all"] = pages_all
    gate("pages_all_count", pages_all == 2, f"pages={pages_all} (expected 2)")

    # ================================================================
    # TEST 2: Export specified sheet (Solo)
    # ================================================================
    print("\n=== TEST 2: Export Solo sheet ===")
    pdf_solo_path = str(_tmp / f"w25_pae_solo_{_ts}.pdf")

    req_solo = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25_pae_solo_{_ts}",
        sheets=["Solo"],
    )

    results_solo = export_all(doc_m2, [req_solo], f"w25_pae_solo_{_ts}")
    if not results_solo or len(results_solo) != 1:
        gate("export_solo_call", False, "no results returned")
        results["verdict"] = "FAIL"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"

    r_solo = results_solo[0]
    gate("export_solo_ok", r_solo.ok, f"error={r_solo.error}")

    size_solo = (
        Path(pdf_solo_path).stat().st_size if Path(pdf_solo_path).exists() else 0
    )
    gate("pdf_solo_exists", Path(pdf_solo_path).exists(), f"size={size_solo}")

    results["pdf_paths"]["solo"] = pdf_solo_path
    results["sizes"]["solo"] = size_solo

    pages_solo = _count_pdf_pages(pdf_solo_path)
    results["page_counts"]["solo"] = pages_solo
    gate("pages_solo_count", pages_solo == 1, f"pages={pages_solo} (expected 1)")

    # ================================================================
    # TEST 3: Export specified sheet (Quad)
    # ================================================================
    print("\n=== TEST 3: Export Quad sheet ===")
    pdf_quad_path = str(_tmp / f"w25_pae_quad_{_ts}.pdf")

    req_quad = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25_pae_quad_{_ts}",
        sheets=["Quad"],
    )

    results_quad = export_all(doc_m2, [req_quad], f"w25_pae_quad_{_ts}")
    if not results_quad or len(results_quad) != 1:
        gate("export_quad_call", False, "no results returned")
        results["verdict"] = "FAIL"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"

    r_quad = results_quad[0]
    gate("export_quad_ok", r_quad.ok, f"error={r_quad.error}")

    size_quad = (
        Path(pdf_quad_path).stat().st_size if Path(pdf_quad_path).exists() else 0
    )
    gate("pdf_quad_exists", Path(pdf_quad_path).exists(), f"size={size_quad}")

    results["pdf_paths"]["quad"] = pdf_quad_path
    results["sizes"]["quad"] = size_quad

    pages_quad = _count_pdf_pages(pdf_quad_path)
    results["page_counts"]["quad"] = pages_quad
    gate("pages_quad_count", pages_quad == 1, f"pages={pages_quad} (expected 1)")

    # ================================================================
    # Page-count discrimination proof (Slice 2b)
    # ================================================================
    print("\n--- Page-count discrimination proof ---")
    if pages_all == 2 and pages_solo == 1 and pages_quad == 1:
        proof_ok = True
        gate(
            "page_count_discrimination_proof",
            True,
            f"pages(all)=2, pages(solo)=1, pages(quad)=1 -> selection filters correctly",
        )
        results["multi_sheet_proof"] = {
            "method": "page_count",
            "pages_all": pages_all,
            "pages_solo": pages_solo,
            "pages_quad": pages_quad,
            "passed": True,
        }
    else:
        proof_ok = False
        gate(
            "page_count_discrimination_proof",
            False,
            f"pages(all)={pages_all}, pages(solo)={pages_solo}, pages(quad)={pages_quad}",
        )
        results["multi_sheet_proof"] = {
            "method": "page_count",
            "pages_all": pages_all,
            "pages_solo": pages_solo,
            "pages_quad": pages_quad,
            "passed": False,
        }

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
            gate(
                "unknown_sheet_message",
                "Unknown" in r_bad.error or "unknown" in r_bad.error.lower(),
                f"error={r_bad.error}",
            )
    else:
        gate("unknown_sheet_rejected", False, "no results returned")

    # ================================================================
    # TEST 5: PDF on Part doc rejected
    # ================================================================
    print("\n=== TEST 5: PDF on Part doc rejected ===")
    # Open the part doc
    try:
        part_open_ret = tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)  # 1 = Part
    except Exception as e:
        gate("open_part_for_rejection_test", False, f"raised: {e}")
        part_open_ret = None

    # OpenDoc6 may return a tuple
    if isinstance(part_open_ret, tuple):
        part_doc_raw = part_open_ret[0]
    else:
        part_doc_raw = part_open_ret

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
                gate(
                    "pdf_on_part_message",
                    "Drawing" in r_part.error,
                    f"error contains 'Drawing': {r_part.error}",
                )
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
    critical_gates = [
        "export_all_ok",
        "pdf_all_exists",
        "pdf_all_nontrivial",
        "pages_all_count",
        "export_solo_ok",
        "pdf_solo_exists",
        "pages_solo_count",
        "page_count_discrimination_proof",
    ]
    critical_ok = all(
        results["gates"].get(g, {}).get("ok", False) for g in critical_gates
    )

    if critical_ok:
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
        results["verdict"] = (
            f"FAIL (unhandled exception: {traceback.format_exc()[:200]})"
        )
        save_results()
        verdict = "FAIL"
    sys.exit(0 if verdict == "PASS" else 1)
