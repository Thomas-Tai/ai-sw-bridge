"""S1 spike: 3D neutral export GO/NO-GO (STEP, IGES, STL).

Build a simple PART with a box extrusion, export via SaveAs3_DIRECT,
verify the BYTES per format (NOT just file-exists).

Uses ai_sw_bridge COM helpers (get_sw_app, typed) — proven on seat.

W34 dispatch requirements:
  - STEP: parse ISO-10303-21 header + FILE_SCHEMA + entities
  - IGES: parse S/G/D/P section structure + T terminate line
  - STL: binary 80-byte header + UINT32 count at offset 80
"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

# Add src to PYTHONPATH for ai_sw_bridge imports
src_path = Path(__file__).resolve().parents[2] / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from ai_sw_bridge.sw_com import get_sw_app
from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module


def create_test_part(sw_app, temp_dir: Path) -> tuple:
    """Create a part with box extrusion. Returns (doc, part_path)."""
    template = sw_app.GetUserPreferenceStringValue(8)  # swDefaultPartTemplate
    if not template:
        raise RuntimeError("No part template found")

    doc = sw_app.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        raise RuntimeError("NewDocument returned None")

    print("  NewDocument OK")

    # Select front plane
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)

    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0, 0, 0, 0.015, 0.015, 0.0)
    sm.InsertSketch(True)

    print("  Sketch created")

    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,  # 1-3
        0,
        0,  # 4-5
        0.020,
        0.0,  # 6-7
        False,
        False,
        False,
        False,  # 8-11
        0.0,
        0.0,  # 12-13
        False,
        False,
        False,
        False,  # 14-17
        True,
        True,
        True,  # 18-20
        0,  # 21
        0.0,  # 22  PropagateFeatureToParts
        False,  # 23  CornerExtendType
    )
    if feat is None:
        raise RuntimeError("Boss extrusion failed")

    print("  Extrusion created")

    part_path = temp_dir / "W34_Box.SLDPRT"
    err = doc.SaveAs3(str(part_path), 0, 0)
    print(f"  SaveAs3: {err}")

    return doc, part_path


def parse_step_file(path: Path) -> dict:
    """Parse STEP file and verify real geometry."""
    result = {
        "format": "STEP",
        "path": str(path),
        "verdict": "NO-GO",
        "size_bytes": 0,
        "counts": {},
        "error": None,
    }

    if not path.exists():
        result["error"] = "File does not exist"
        return result

    size = path.stat().st_size
    result["size_bytes"] = size

    if size == 0:
        result["error"] = "File is empty"
        return result

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["error"] = f"Cannot read: {exc}"
        return result

    if "ISO-10303-21;" not in text:
        result["error"] = "Missing ISO-10303-21 header"
        return result
    if "FILE_SCHEMA" not in text:
        result["error"] = "Missing FILE_SCHEMA"
        return result

    cp = text.count("CARTESIAN_POINT")
    af = text.count("ADVANCED_FACE")
    ms = text.count("MANIFOLD_SOLID_BREP")
    cs = text.count("CLOSED_SHELL")

    result["counts"] = {
        "CARTESIAN_POINT": cp,
        "ADVANCED_FACE": af,
        "MANIFOLD_SOLID_BREP": ms,
        "CLOSED_SHELL": cs,
    }

    if cp < 4:
        result["error"] = f"Header-only: only {cp} CARTESIAN_POINTs"
        return result
    if cs < 1:
        result["error"] = "No CLOSED_SHELL"
        return result

    result["verdict"] = "GREEN"
    return result


def parse_iges_file(path: Path) -> dict:
    """Parse IGES file (80-column card format) and verify real geometry."""
    result = {
        "format": "IGES",
        "path": str(path),
        "verdict": "NO-GO",
        "size_bytes": 0,
        "counts": {},
        "error": None,
    }

    if not path.exists():
        result["error"] = "File does not exist"
        return result

    size = path.stat().st_size
    result["size_bytes"] = size

    if size == 0:
        result["error"] = "File is empty"
        return result

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["error"] = f"Cannot read: {exc}"
        return result

    lines = text.splitlines()

    t_lines = [l for l in lines if len(l) >= 73 and l[72] == "T"]
    if not t_lines:
        result["error"] = "Missing T (Terminate) marker"
        return result

    d_lines = [l for l in lines if len(l) >= 73 and l[72] == "D"]
    de_count = len(d_lines) // 2
    p_lines = [l for l in lines if len(l) >= 73 and l[72] == "P"]
    g_lines = [l for l in lines if len(l) >= 73 and l[72] == "G"]
    s_lines = [l for l in lines if len(l) >= 73 and l[72] == "S"]

    result["counts"] = {
        "S_lines": len(s_lines),
        "G_lines": len(g_lines),
        "D_lines": len(d_lines),
        "P_lines": len(p_lines),
        "T_lines": len(t_lines),
        "DE_entities": de_count,
    }

    if de_count < 1:
        result["error"] = "No Directory Entry entities"
        return result
    if len(p_lines) < 1:
        result["error"] = "No Parameter Data lines"
        return result

    result["verdict"] = "GREEN"
    return result


def parse_stl_file(path: Path) -> dict:
    """Parse STL (ASCII or binary) and verify triangle count."""
    result = {
        "format": "STL",
        "path": str(path),
        "verdict": "NO-GO",
        "size_bytes": 0,
        "counts": {},
        "error": None,
        "mode": None,
    }

    if not path.exists():
        result["error"] = "File does not exist"
        return result

    size = path.stat().st_size
    result["size_bytes"] = size

    if size == 0:
        result["error"] = "File is empty"
        return result

    try:
        with open(path, "rb") as f:
            header = f.read(100)

        if header.startswith(b"solid"):
            result["mode"] = "ascii"
            text = path.read_text(encoding="utf-8", errors="replace")
            facet_count = text.count("facet normal")
            loop_count = text.count("outer loop")
            vertex_count = text.count("vertex")
            result["counts"] = {
                "facets": facet_count,
                "loops": loop_count,
                "vertices": vertex_count,
            }
            if facet_count < 1:
                result["error"] = "No 'facet normal' blocks"
                return result
            if facet_count < 4:
                result["error"] = f"Only {facet_count} facets (expected >=4)"
                return result
            result["verdict"] = "GREEN"
        else:
            result["mode"] = "binary"
            if size < 84:
                result["error"] = f"Too small: {size} < 84 bytes"
                return result
            with open(path, "rb") as f:
                f.read(80)
                tri_count = struct.unpack("<I", f.read(4))[0]
            result["counts"] = {"triangles": tri_count}
            if tri_count < 1:
                result["error"] = "Triangle count = 0"
                return result
            if tri_count < 4:
                result["error"] = f"Only {tri_count} triangles (expected >=4)"
                return result
            expected_size = 80 + 4 + (tri_count * 50)
            if size < expected_size:
                result["error"] = f"Size mismatch: {size} < expected {expected_size}"
                return result
            result["verdict"] = "GREEN"
    except Exception as exc:
        result["error"] = f"Cannot read: {exc}"

    return result


def export_and_verify(doc, temp_dir: Path) -> dict:
    """Export part to STEP/IGES/STL and verify each format."""
    results = {
        "formats": {},
        "summary": {},
        "confirmed_extensions": {},
        "route": "SaveAs3_DIRECT",
    }

    tests = [
        ("STEP", ".step"),
        ("STEP_alias", ".stp"),
        ("IGES", ".iges"),
        ("IGES_alias", ".igs"),
        ("STL", ".stl"),
    ]

    for fmt_name, ext in tests:
        out_path = temp_dir / f"W34_Box{ext}"
        if out_path.exists():
            out_path.unlink()

        try:
            err = doc.SaveAs3(str(out_path), 0, 0)
            err_code = int(err) if err is not None else 0
        except Exception as exc:
            results["formats"][fmt_name] = {
                "format": fmt_name,
                "extension": ext,
                "verdict": "NO-GO",
                "error": f"SaveAs3 raised {type(exc).__name__}: {exc}",
            }
            continue

        if err_code != 0:
            results["formats"][fmt_name] = {
                "format": fmt_name,
                "extension": ext,
                "verdict": "NO-GO",
                "error": f"SaveAs3 returned error code {err_code}",
            }
            continue

        if fmt_name.startswith("STEP"):
            parse_result = parse_step_file(out_path)
        elif fmt_name.startswith("IGES"):
            parse_result = parse_iges_file(out_path)
        elif fmt_name == "STL":
            parse_result = parse_stl_file(out_path)
        else:
            parse_result = {"verdict": "NO-GO", "error": "Unknown format"}

        parse_result["extension"] = ext
        parse_result["route"] = "SaveAs3_DIRECT"
        results["formats"][fmt_name] = parse_result

        if not fmt_name.endswith("_alias"):
            base_fmt = fmt_name.lower()
            results["summary"][base_fmt] = parse_result["verdict"]
            if parse_result["verdict"] == "GREEN":
                results["confirmed_extensions"][base_fmt] = ext

    return results


def main():
    """S1 spike main: create test part, export, verify."""
    print("=== W34 S1 Spike: 3D Neutral Export ===")

    temp_dir = Path(tempfile.mkdtemp(prefix="W34_spike_"))
    print(f"Temp directory: {temp_dir}")

    # Use ai_sw_bridge helpers (handles ROT-attach + CoInitialize)
    sw_app = get_sw_app()
    # get_sw_app returns cached ISldWorks (early-bind method, must call it)
    try:
        rev = sw_app.RevisionNumber()
    except Exception:
        rev = (
            sw_app.RevisionNumber
            if not callable(getattr(sw_app, "RevisionNumber", None))
            else "?"
        )
    print(f"SW app acquired (rev: {rev})")

    results = {"formats": {}, "summary": {}, "errors": []}

    try:
        print("Creating test part (box extrusion)...")
        doc, part_path = create_test_part(sw_app, temp_dir)
        print(f"Part created: {part_path}")

        print("Exporting and verifying...")
        export_results = export_and_verify(doc, temp_dir)

        results["formats"] = export_results["formats"]
        results["summary"] = export_results["summary"]
        results["confirmed_extensions"] = export_results["confirmed_extensions"]
        results["route"] = export_results["route"]
        results["test_part"] = str(part_path)
        results["temp_dir"] = str(temp_dir)

    except Exception as exc:
        results["errors"].append(f"Spike failed: {type(exc).__name__}: {exc}")
        import traceback

        results["traceback"] = traceback.format_exc()
        print(f"! Spike failed: {exc}")
        print(results.get("traceback", ""))

    finally:
        # NOTE: Do NOT call CloseAllDocuments — it corrupts the COM session
        # (see reference_close_corrupts_com.md in memory)
        pass

    # Write results
    results_path = Path(__file__).parent / "_results" / "export_3d.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults written to: {results_path}")
    print("\n=== SUMMARY ===")
    for fmt, status in results.get("summary", {}).items():
        print(f"  {fmt}: {status}")
    if results.get("errors"):
        print("\n=== ERRORS ===")
        for err in results["errors"]:
            print(f"  {err}")

    return results


if __name__ == "__main__":
    main()
