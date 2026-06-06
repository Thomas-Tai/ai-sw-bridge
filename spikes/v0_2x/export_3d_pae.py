"""S3 PAE: production-path 3D neutral export (STEP, IGES, STL).

Tests the actual dispatch.py _export_one path for each GREEN format,
verifies the bytes per format, and confirms the doc-type fail-closed
(Drawing→STEP rejected).

Following W33 PAE pattern (export_dxf_pae.py).
"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

src_path = Path(__file__).resolve().parents[2] / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from ai_sw_bridge.sw_com import get_sw_app
from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.export.dispatch import ExportRequest, _export_one


# --- Parser helpers (same as spike, proven) ---

def parse_step(path: Path) -> dict:
    """Parse STEP and return entity counts."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "CARTESIAN_POINT": text.count("CARTESIAN_POINT"),
        "ADVANCED_FACE": text.count("ADVANCED_FACE"),
        "CLOSED_SHELL": text.count("CLOSED_SHELL"),
        "has_header": "ISO-10303-21;" in text,
        "has_file_schema": "FILE_SCHEMA" in text,
    }


def parse_iges(path: Path) -> dict:
    """Parse IGES and return section counts."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    d_lines = [l for l in lines if len(l) >= 73 and l[72] == "D"]
    p_lines = [l for l in lines if len(l) >= 73 and l[72] == "P"]
    t_lines = [l for l in lines if len(l) >= 73 and l[72] == "T"]
    return {
        "DE_entities": len(d_lines) // 2,
        "P_lines": len(p_lines),
        "T_lines": len(t_lines),
    }


def parse_stl(path: Path) -> dict:
    """Parse STL and return triangle count."""
    with open(path, "rb") as f:
        header = f.read(100)
    if header.startswith(b"solid"):
        text = path.read_text(encoding="utf-8", errors="replace")
        return {"mode": "ascii", "triangles": text.count("facet normal")}
    with open(path, "rb") as f:
        f.read(80)
        tri = struct.unpack("<I", f.read(4))[0]
    return {"mode": "binary", "triangles": tri}


def create_test_part(sw_app, temp_dir: Path) -> Path:
    """Create a 30×30×20mm box extrusion and save it."""
    template = sw_app.GetUserPreferenceStringValue(8)
    doc = sw_app.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        raise RuntimeError("NewDocument returned None")

    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0, 0, 0, 0.015, 0.015, 0.0)
    sm.InsertSketch(True)

    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True, False, False,
        0, 0,
        0.020, 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False,
        True, True, True,
        0,
        0.0,
        False,
    )
    if feat is None:
        raise RuntimeError("FeatureExtrusion2 failed")

    part_path = temp_dir / "W34_PAE_Box.SLDPRT"
    doc.SaveAs3(str(part_path), 0, 0)
    return part_path


def main():
    """S3 PAE main."""
    print("=== W34 S3 PAE: 3D Neutral Export (production path) ===")

    temp_dir = Path(tempfile.mkdtemp(prefix="W34_pae_"))
    print(f"Temp directory: {temp_dir}")

    sw_app = get_sw_app()
    try:
        rev = sw_app.RevisionNumber()
    except Exception:
        rev = "?"
    print(f"SW app acquired (rev: {rev})")

    results = {"formats": {}, "doc_type_tests": {}, "errors": []}

    try:
        print("Creating test part...")
        part_path = create_test_part(sw_app, temp_dir)
        print(f"Part created: {part_path}")

        doc = sw_app.ActiveDoc
        if doc is None:
            results["errors"].append("No active doc after part creation")
            return results

        # --- Test each GREEN format via production path ---
        green_formats = [
            ("step214", parse_step),
            ("iges", parse_iges),
            ("stl", parse_stl),
        ]

        for fmt_name, parser in green_formats:
            print(f"Testing {fmt_name}...")
            req = ExportRequest(format=fmt_name, output_dir=temp_dir)
            result = _export_one(doc, req, "W34_PAE_Box")

            fmt_result = {
                "format": fmt_name,
                "ok": result.ok,
                "path": result.path,
                "error": result.error,
            }

            if result.ok:
                out_path = Path(result.path)
                if out_path.exists() and out_path.stat().st_size > 0:
                    parsed = parser(out_path)
                    fmt_result["size_bytes"] = out_path.stat().st_size
                    fmt_result["parsed"] = parsed
                    fmt_result["verdict"] = "PASS"
                else:
                    fmt_result["verdict"] = "FAIL"
                    fmt_result["error"] = "File missing or empty after export"
            else:
                fmt_result["verdict"] = "FAIL"

            results["formats"][fmt_name] = fmt_result

        # --- Doc-type fail-closed test: Drawing→STEP rejected ---
        print("Testing doc-type fail-closed (Drawing->STEP rejected)...")
        # We need a Drawing doc for this test. Create one.
        drawing_template = sw_app.GetUserPreferenceStringValue(10)  # swDefaultDrawingTemplate
        if drawing_template:
            drawing_doc = sw_app.NewDocument(drawing_template, 0, 0.0, 0.0)
            if drawing_doc is not None:
                req = ExportRequest(format="step214", output_dir=temp_dir)
                result = _export_one(drawing_doc, req, "TestDrawing")

                doc_type_result = {
                    "test": "drawing_to_step_rejected",
                    "ok": not result.ok,  # Should be False (rejected)
                    "expected_error_substring": "Part (.SLDPRT) or Assembly",
                    "actual_error": result.error,
                    "verdict": "PASS" if (not result.ok and result.error and "Part (.SLDPRT) or Assembly" in result.error) else "FAIL",
                }
                results["doc_type_tests"]["drawing_to_step"] = doc_type_result
            else:
                results["doc_type_tests"]["drawing_to_step"] = {
                    "verdict": "SKIP",
                    "error": "Could not create drawing document",
                }
        else:
            results["doc_type_tests"]["drawing_to_step"] = {
                "verdict": "SKIP",
                "error": "No drawing template found",
            }

    except Exception as exc:
        results["errors"].append(f"PAE failed: {type(exc).__name__}: {exc}")
        import traceback
        results["traceback"] = traceback.format_exc()
        print(f"! PAE failed: {exc}")

    # Write results
    results_path = Path(__file__).parent / "_results" / "export_3d_pae.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults written to: {results_path}")

    # Print summary
    print("\n=== FORMAT RESULTS ===")
    for fmt_name, fmt_result in results.get("formats", {}).items():
        verdict = fmt_result.get("verdict", "?")
        parsed = fmt_result.get("parsed", {})
        print(f"  {fmt_name}: {verdict} — {parsed}")

    print("\n=== DOC-TYPE TESTS ===")
    for test_name, test_result in results.get("doc_type_tests", {}).items():
        print(f"  {test_name}: {test_result.get('verdict', '?')}")

    if results.get("errors"):
        print("\n=== ERRORS ===")
        for err in results["errors"]:
            print(f"  {err}")

    return results


if __name__ == "__main__":
    main()