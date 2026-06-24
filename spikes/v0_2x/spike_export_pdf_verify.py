"""Wave-25v Slice 1: PROVE PDF sheet-selection actually filters (page-count discrimination).

DISCRIMINATING PROBE: Build a 2-sheet drawing where sheets have OBVIOUSLY different
view counts, then use PDF PAGE COUNT (not byte size) to prove SetSheets filters.

Fixture:
  - Sheet "Solo": 1 view (front)
  - Sheet "Quad": 4 views (front, top, right, iso)

Expected behavior:
  - sheets:"all" -> 2 pages
  - sheets:["Solo"] -> 1 page
  - sheets:["Quad"] -> 1 page

If pages(solo) == 2 (== pages(all)), SetSheets is NOT filtering -> BUG.

HARD CHECKPOINT: Write export_pdf_verify.json with verdict (GREEN/BUG) + page counts.
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
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "export_pdf_verify.json"

results: dict[str, Any] = {
    "probe": "w25v_export_pdf_verify",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "verdict": "UNKNOWN",
    "page_counts": {},
    "pdf_paths": {},
    "page_counting_method": None,
    "trace": None,  # on BUG: where sheets was lost
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
        "name": "W25vVerifyBox",
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
    - Sheet "Solo": 1 view (front only)
    - Sheet "Quad": 4 views (front, top, right, iso)

    Returns the drawing file path, or None on failure.
    """
    from ai_sw_bridge.com.earlybind import typed_qi
    from ai_sw_bridge.drawing.lifecycle import commit_drawing

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    drw_path = str(_tmp / f"w25v_verify_drawing_{_ts}.SLDDRW")

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
        "filename": f"w25v_verify_drawing_{_ts}",
    }

    output_path = str(_tmp / f"w25v_verify_drawing_{_ts}.SLDDRW")

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

    # Verify sheet structure on reopen
    try:
        from ai_sw_bridge.com.sw_type_info import wrapper_module
        import win32com.client as w32

        mod = wrapper_module()
        tsw = typed_qi(sw, "ISldWorks", module=mod)

        open_ret = tsw.OpenDoc6(drawing_path, 3, 1, "", 0, 0)  # 3 = Drawing
        if isinstance(open_ret, tuple):
            doc_raw = open_ret[0]
        else:
            doc_raw = open_ret

        if doc_raw is not None and not isinstance(doc_raw, int):
            drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
            names = list(drawing_doc.GetSheetNames())
            gate(
                "drawing_sheet_names",
                names == ["Solo", "Quad"],
                f"expected ['Solo', 'Quad'], got {names}",
            )
            try:
                sw.CloseDoc(drawing_path)
            except Exception:
                pass
    except Exception as e:
        gate("drawing_sheet_names", False, f"could not verify: {e}")

    return drawing_path


def _count_pdf_pages(pdf_path: str) -> int:
    """Count PDF pages using structural analysis.

    Prefer PyPDF2/pypdf if available; fall back to raw byte scan for
    /Type /Page objects that are NOT /Pages (the root).

    Returns page count, or -1 on failure.
    """
    import re

    # Try pypdf/PyPDF2 first
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(pdf_path)
        count = len(reader.pages)
        results["page_counting_method"] = "pypdf.PdfReader.pages"
        return count
    except ImportError:
        pass

    try:
        from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(pdf_path)
        count = len(reader.pages)
        results["page_counting_method"] = "PyPDF2.PdfReader.pages"
        return count
    except ImportError:
        pass

    # Fallback: raw byte scan for /Type /Page (not /Pages)
    # This counts occurrences of "/Type /Page" that are NOT "/Type /Pages"
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()

        # Regex: b'/Type\s*/Page(?![s])' - matches /Type /Page but NOT /Type /Pages
        pattern = re.compile(rb"/Type\s*/Page(?![s])")
        matches = pattern.findall(data)
        count = len(matches)
        results["page_counting_method"] = "raw_byte_scan:/Type/Page(?![s])"
        return count
    except Exception as e:
        print(f"  [ERROR] PDF page count failed: {e}", file=sys.stderr)
        return -1


def run() -> str:
    print("=" * 70)
    print("Wave-25v Slice 1: PROVE PDF sheet-selection filters (page-count)")
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
    part_path = str(_tmp / f"w25v_verify_box_{_ts}.SLDPRT")
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
    gate("template_found", True, f"path={template_path}")

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
    # TEST 1: Export ALL sheets to PDF (sheets:"all")
    # ================================================================
    print("\n=== TEST 1: Export ALL sheets ===")
    pdf_all_path = str(_tmp / f"w25v_verify_all_{_ts}.pdf")

    req_all = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25v_verify_all_{_ts}",
        sheets="all",
    )

    results_all = export_all(doc_m2, [req_all], f"w25v_verify_all_{_ts}")
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

    if not Path(pdf_all_path).exists():
        gate("pdf_all_exists", False, f"path={pdf_all_path}")
        results["verdict"] = "FAIL (PDF all not created)"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"
    gate("pdf_all_exists", True, f"path={pdf_all_path}")

    pages_all = _count_pdf_pages(pdf_all_path)
    results["pdf_paths"]["all"] = pdf_all_path
    results["page_counts"]["all"] = pages_all
    gate("pages_all_count", pages_all == 2, f"pages={pages_all} (expected 2)")

    # ================================================================
    # TEST 2: Export Solo sheet ONLY (sheets:["Solo"])
    # ================================================================
    print("\n=== TEST 2: Export Solo sheet ONLY ===")
    pdf_solo_path = str(_tmp / f"w25v_verify_solo_{_ts}.pdf")

    req_solo = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25v_verify_solo_{_ts}",
        sheets=["Solo"],
    )

    results_solo = export_all(doc_m2, [req_solo], f"w25v_verify_solo_{_ts}")
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

    if not r_solo.ok:
        results["verdict"] = f"FAIL (export_solo failed: {r_solo.error})"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"

    if not Path(pdf_solo_path).exists():
        gate("pdf_solo_exists", False, f"path={pdf_solo_path}")
        results["verdict"] = "FAIL (PDF solo not created)"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"
    gate("pdf_solo_exists", True, f"path={pdf_solo_path}")

    pages_solo = _count_pdf_pages(pdf_solo_path)
    results["pdf_paths"]["solo"] = pdf_solo_path
    results["page_counts"]["solo"] = pages_solo
    gate("pages_solo_count", pages_solo == 1, f"pages={pages_solo} (expected 1)")

    # ================================================================
    # TEST 3: Export Quad sheet ONLY (sheets:["Quad"])
    # ================================================================
    print("\n=== TEST 3: Export Quad sheet ONLY ===")
    pdf_quad_path = str(_tmp / f"w25v_verify_quad_{_ts}.pdf")

    req_quad = ExportRequest(
        format="pdf",
        output_dir=_tmp,
        filename=f"w25v_verify_quad_{_ts}",
        sheets=["Quad"],
    )

    results_quad = export_all(doc_m2, [req_quad], f"w25v_verify_quad_{_ts}")
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

    if not r_quad.ok:
        results["verdict"] = f"FAIL (export_quad failed: {r_quad.error})"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"

    if not Path(pdf_quad_path).exists():
        gate("pdf_quad_exists", False, f"path={pdf_quad_path}")
        results["verdict"] = "FAIL (PDF quad not created)"
        save_results()
        try:
            sw.CloseDoc(drawing_path)
        except Exception:
            pass
        return "FAIL"
    gate("pdf_quad_exists", True, f"path={pdf_quad_path}")

    pages_quad = _count_pdf_pages(pdf_quad_path)
    results["pdf_paths"]["quad"] = pdf_quad_path
    results["page_counts"]["quad"] = pages_quad
    gate("pages_quad_count", pages_quad == 1, f"pages={pages_quad} (expected 1)")

    # ================================================================
    # HARD CHECKPOINT: Discrimination gate
    # ================================================================
    print("\n--- HARD CHECKPOINT: Discrimination ---")

    # GREEN: pages(all)=2, pages(solo)=1, pages(quad)=1 -> SetSheets filters
    # BUG: pages(solo)=2 or pages(quad)=2 -> sheets NOT filtering

    if pages_all == 2 and pages_solo == 1 and pages_quad == 1:
        results["verdict"] = "GREEN"
        print(">>> VERDICT: GREEN (sheet selection filters correctly)")
        print(
            f"    pages(all)={pages_all}, pages(solo)={pages_solo}, pages(quad)={pages_quad}"
        )
    else:
        results["verdict"] = "BUG"
        print(">>> VERDICT: BUG (sheet selection NOT filtering!)")
        print(
            f"    pages(all)={pages_all}, pages(solo)={pages_solo}, pages(quad)={pages_quad}"
        )

        # Trace: find where sheets selection is lost
        # Prime suspect: SetSheets mode logic in _export_pdf
        trace_info = {
            "suspect": "SetSheets mode mapping in _export_pdf",
            "expected": "sheets:['Solo'] -> mode=3 (specified) + names=['Solo']",
            "actual_page_counts": {
                "all": pages_all,
                "solo": pages_solo,
                "quad": pages_quad,
            },
            "hypothesis": "sheets:['Solo'] may be reaching SetSheets as mode=1 (all) instead of mode=3 (specified)",
        }
        results["trace"] = trace_info

    # ================================================================
    # Close and save
    # ================================================================
    try:
        sw.CloseDoc(drawing_path)
    except Exception:
        pass

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
    sys.exit(0 if verdict in ("GREEN", "PASS") else 1)
