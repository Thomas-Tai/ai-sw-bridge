"""W52 export options derisk: byte-verify DWG, STL binary/ascii, STEP AP.

Three legs, each with its own byte-level GREEN criterion:

  1. DWG — SaveAs3_DIRECT with .dwg extension on a Drawing doc.
     GREEN: file starts with "AC10" (DWG version magic bytes).

  2. STL binary/ascii — SetUserPreferenceToggle(swSTLBinaryFormat, ...)
     BEFORE SaveAs3. binary=True → 80-byte header + uint32 tri count;
     binary=False → starts with "solid".
     GREEN: discriminator byte matches the requested mode.

  3. STEP AP203 vs AP214 — SetUserPreferenceIntegerValue(swStepExportAP, ...)
     BEFORE SaveAs3. step203 → FILE_SCHEMA names CONFIG_CONTROL_DESIGN;
     step214 → FILE_SCHEMA names AUTOMOTIVE_DESIGN or "AP214".
     GREEN: the FILE_SCHEMA string matches the requested AP.

Enum dump: the spike also dumps the real enum values for
swSTLBinaryFormat and swStepExportAP from swconst.tlb — these are
needed by the dispatch pre-save preference code.

Run: PYTHONPATH=<worktree>/src python spikes/v0_2x/export_options_derisk.py
"""

from __future__ import annotations

import json
import re
import struct
import sys
import tempfile
from pathlib import Path

src_path = Path(__file__).resolve().parents[2] / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

import pythoncom

from ai_sw_bridge.sw_com import get_sw_app
from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module


def _dump_export_enums(sw_app: object) -> dict:
    """Dump swSTLBinaryFormat and swStepExportAP enum values from swconst.tlb.

    These are the enum IDs that _apply_export_preferences needs. If the
    dump fails, the values stay None and the dispatch code will skip
    the preference setting (logged as a warning).
    """
    result: dict = {
        "swSTLBinaryFormat": None,
        "swStepAP": None,
    }
    targets = {k for k in result}
    # Project-native enum read: pythoncom.LoadTypeLib + iterate TKIND_ENUM
    # members. (gencache.EnsureModule regenerates makepy and fails 'CreateMutex'
    # in this seat env — and corrupts the gen_py state for later COM calls.)
    tlb_path = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\swconst.tlb")
    if not tlb_path.exists():
        for candidate in Path(r"C:\Program Files").rglob("swconst.tlb"):
            tlb_path = candidate
            break
    if not tlb_path.exists():
        result["error"] = "swconst.tlb not found"
        return result
    try:
        tlb = pythoncom.LoadTypeLib(str(tlb_path))
    except Exception as exc:
        result["error"] = f"LoadTypeLib failed: {type(exc).__name__}: {exc}"
        return result

    remaining = set(targets)
    candidates: dict = {}
    for i in range(tlb.GetTypeInfoCount()):
        try:
            info = tlb.GetTypeInfo(i)
            ta = info.GetTypeAttr()
        except Exception:
            continue
        if ta.typekind != pythoncom.TKIND_ENUM:
            continue
        for v in range(ta.cVars):
            try:
                vd = info.GetVarDesc(v)
                names = info.GetNames(vd.memid)
                nm = names[0] if names else None
                if not nm:
                    continue
                if nm in remaining:
                    result[nm] = vd.value
                    remaining.discard(nm)
                low = nm.lower()
                if "step" in low or "203" in low or "214" in low:
                    candidates[nm] = vd.value
            except Exception:
                continue
    result["_step_candidates"] = candidates
    if remaining:
        result["error"] = f"enums not found: {sorted(remaining)}"
    return result


_PART_SEQ = 0


def _create_box_part(sw_app: object, temp_dir: Path) -> tuple:
    """Create a simple box part. Returns (typed_doc, part_path)."""
    global _PART_SEQ
    _PART_SEQ += 1
    mod = wrapper_module()
    template = sw_app.GetUserPreferenceStringValue(8)
    if not template:
        raise RuntimeError("No part template found")

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
        raise RuntimeError("Box extrusion failed")

    # SaveAs3 / Extension members must go through the EARLY-BOUND typed doc —
    # the raw late-bound doc returned save-error 1 at the seat (the W52-B
    # late-binding rhyme). Return the typed doc so the legs' SaveAs3/Extension
    # calls inherit the fix. Note the fixed parenthesization of the err check.
    tdoc = typed(doc, "IModelDoc2", module=mod)
    # Unique filename per call — each leg builds a fresh part; reusing one name
    # collided with the still-open part from the previous leg (SaveAs3 error 1;
    # docs are intentionally left open per the CloseDoc-corrupts-COM lesson).
    part_path = temp_dir / f"W52_Box_{_PART_SEQ}.SLDPRT"
    err = tdoc.SaveAs3(str(part_path), 0, 0)
    if (int(err) if err is not None else 0) != 0:
        raise RuntimeError(f"SaveAs3 part: error {err}")

    return tdoc, part_path


def _create_drawing(sw_app: object, part_path: Path, temp_dir: Path) -> tuple:
    """Create a simple drawing referencing the part. Returns (doc, drw_path)."""
    from ai_sw_bridge.com.earlybind import typed_qi

    mod = wrapper_module()

    templates = [
        r"C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\gb_a4.drwdot",
        r"C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\ansi (in).drwdot",
    ]
    drw_template = None
    for t in templates:
        if Path(t).exists():
            drw_template = t
            break

    if drw_template is None:
        for candidate in Path(r"C:\ProgramData").rglob("*.drwdot"):
            drw_template = str(candidate)
            break

    if drw_template is None:
        raise RuntimeError("No .DRWDOT drawing template found")

    drw_raw = sw_app.NewDocument(drw_template, 0, 0.420, 0.297)
    if drw_raw is None or isinstance(drw_raw, int):
        raise RuntimeError("NewDocument(drwdot) returned None")

    drawing_doc = typed_qi(drw_raw, "IDrawingDoc", module=mod)
    model_doc = typed_qi(drw_raw, "IModelDoc2", module=mod)

    view = drawing_doc.CreateDrawViewFromModelView3(
        str(part_path), "*Isometric", 0.15, 0.15, 0.0
    )

    drw_path = temp_dir / "W52_Box.SLDDRW"
    err = model_doc.SaveAs3(str(drw_path), 0, 0)
    if int(err) if err is not None else 0 != 0:
        raise RuntimeError(f"SaveAs3 drawing: error {err}")

    return model_doc, drw_path


# ---------------------------------------------------------------------------
# Byte verifiers
# ---------------------------------------------------------------------------

def verify_dwg(path: Path) -> dict:
    """DWG binary header: starts with 'AC10xx' (version string)."""
    result = {
        "format": "DWG", "path": str(path),
        "verdict": "NO-GO", "size_bytes": 0, "error": None,
    }
    if not path.exists():
        result["error"] = "File does not exist"
        return result

    size = path.stat().st_size
    result["size_bytes"] = size
    if size < 6:
        result["error"] = f"File too small: {size} bytes"
        return result

    with open(path, "rb") as f:
        header = f.read(6)

    magic = header[:4].decode("ascii", errors="replace")
    result["header_magic"] = magic

    if not magic.startswith("AC10"):
        result["error"] = f"Bad DWG magic: {magic!r} (expected AC10xx)"
        return result

    version = header[4:6].decode("ascii", errors="replace")
    result["dwg_version"] = f"AC10{version}"
    result["verdict"] = "GREEN"
    return result


def verify_stl(path: Path, expected_mode: str) -> dict:
    """STL discriminator: binary starts with 80-byte header; ASCII with 'solid'."""
    result = {
        "format": "STL", "path": str(path),
        "verdict": "NO-GO", "size_bytes": 0,
        "expected_mode": expected_mode, "actual_mode": None,
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

    with open(path, "rb") as f:
        header = f.read(84)

    if header.startswith(b"solid"):
        actual = "ascii"
        result["actual_mode"] = "ascii"
        text = path.read_text(encoding="utf-8", errors="replace")
        facet_count = text.count("facet normal")
        result["facet_count"] = facet_count
        if facet_count < 4:
            result["error"] = f"Only {facet_count} facets"
            return result
    else:
        actual = "binary"
        result["actual_mode"] = "binary"
        if size < 84:
            result["error"] = f"Too small for binary: {size} < 84"
            return result
        tri_count = struct.unpack("<I", header[80:84])[0]
        result["triangle_count"] = tri_count
        expected_size = 80 + 4 + (tri_count * 50)
        if tri_count < 1:
            result["error"] = "Triangle count = 0"
            return result
        if size < expected_size:
            result["error"] = f"Size {size} < expected {expected_size}"
            return result

    if actual != expected_mode:
        result["error"] = (
            f"Mode mismatch: expected {expected_mode}, got {actual}"
        )
        return result

    result["verdict"] = "GREEN"
    return result


def verify_step_ap(path: Path, expected_ap: str) -> dict:
    """STEP FILE_SCHEMA discriminator: AP203 vs AP214."""
    result = {
        "format": "STEP", "path": str(path),
        "verdict": "NO-GO", "size_bytes": 0,
        "expected_ap": expected_ap, "actual_schema": None,
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

    text = path.read_text(encoding="utf-8", errors="replace")
    if "ISO-10303-21;" not in text:
        result["error"] = "Missing ISO-10303-21 header"
        return result

    match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'", text)
    if not match:
        result["error"] = "Cannot parse FILE_SCHEMA"
        return result

    schema_name = match.group(1).upper()
    result["actual_schema"] = schema_name

    if expected_ap == "AP203":
        if "CONFIG_CONTROL_DESIGN" not in schema_name and "AP203" not in schema_name:
            result["error"] = (
                f"Expected AP203 (CONFIG_CONTROL_DESIGN), got: {schema_name}"
            )
            return result
    elif expected_ap == "AP214":
        if (
            "AUTOMOTIVE_DESIGN" not in schema_name
            and "AP214" not in schema_name
        ):
            result["error"] = (
                f"Expected AP214 (AUTOMOTIVE_DESIGN), got: {schema_name}"
            )
            return result

    result["verdict"] = "GREEN"
    return result


# ---------------------------------------------------------------------------
# Legs
# ---------------------------------------------------------------------------

def leg_dwg(sw_app: object, temp_dir: Path) -> dict:
    """Leg 1: DWG export from a Drawing doc."""
    result = {"leg": "DWG", "verdict": "NO-GO", "error": None}
    try:
        part_doc, part_path = _create_box_part(sw_app, temp_dir)
        drw_doc, drw_path = _create_drawing(sw_app, part_path, temp_dir)

        dwg_path = temp_dir / "W52_Box.dwg"
        err = drw_doc.SaveAs3(str(dwg_path), 0, 0)
        err_code = int(err) if err is not None else 0
        if err_code != 0:
            result["error"] = f"SaveAs3(.dwg) returned error {err_code}"
            return result

        verify = verify_dwg(dwg_path)
        result["verify"] = verify
        result["verdict"] = verify["verdict"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def leg_stl_binary(sw_app: object, temp_dir: Path) -> dict:
    """Leg 2a: STL binary (default)."""
    result = {"leg": "STL_binary", "verdict": "NO-GO", "error": None}
    try:
        doc, part_path = _create_box_part(sw_app, temp_dir)

        stl_path = temp_dir / "W52_Box_bin.stl"
        err = doc.SaveAs3(str(stl_path), 0, 0)
        err_code = int(err) if err is not None else 0
        if err_code != 0:
            result["error"] = f"SaveAs3(.stl binary) returned error {err_code}"
            return result

        verify = verify_stl(stl_path, "binary")
        result["verify"] = verify
        result["verdict"] = verify["verdict"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def leg_stl_ascii(sw_app: object, temp_dir: Path) -> dict:
    """Leg 2b: STL ASCII — set toggle BEFORE SaveAs3."""
    result = {"leg": "STL_ascii", "verdict": "NO-GO", "error": None}
    try:
        doc, part_path = _create_box_part(sw_app, temp_dir)

        toggle_id = _find_enum("swSTLBinaryFormat")
        if toggle_id is not None:
            # App-level + late-bound: SetUserPreferenceToggle Type-mismatches on
            # the early-bound typed Extension (makepy mistypes the bool arg).
            sw_app.SetUserPreferenceToggle(toggle_id, False)
        else:
            result["warning"] = (
                "swSTLBinaryFormat ID unknown; ASCII mode not guaranteed"
            )

        stl_path = temp_dir / "W52_Box_ascii.stl"
        err = doc.SaveAs3(str(stl_path), 0, 0)
        err_code = int(err) if err is not None else 0
        if err_code != 0:
            result["error"] = f"SaveAs3(.stl ascii) returned error {err_code}"
            return result

        verify = verify_stl(stl_path, "ascii")
        result["verify"] = verify
        result["verdict"] = verify["verdict"]

        if toggle_id is not None:
            sw_app.SetUserPreferenceToggle(toggle_id, True)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def leg_step_ap203(sw_app: object, temp_dir: Path) -> dict:
    """Leg 3a: STEP AP203 — set AP preference BEFORE SaveAs3."""
    result = {"leg": "STEP_AP203", "verdict": "NO-GO", "error": None}
    try:
        doc, part_path = _create_box_part(sw_app, temp_dir)

        ap_id = _find_enum("swStepAP")
        ap203_val = 203  # swStepAP takes the literal AP number
        if ap_id is not None:
            sw_app.SetUserPreferenceIntegerValue(ap_id, ap203_val)
        else:
            result["warning"] = "swStepAP ID unknown; AP203 not guaranteed"

        step_path = temp_dir / "W52_Box_ap203.step"
        err = doc.SaveAs3(str(step_path), 0, 0)
        err_code = int(err) if err is not None else 0
        if err_code != 0:
            result["error"] = f"SaveAs3(.step AP203) returned error {err_code}"
            return result

        verify = verify_step_ap(step_path, "AP203")
        result["verify"] = verify
        result["verdict"] = verify["verdict"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def leg_step_ap214(sw_app: object, temp_dir: Path) -> dict:
    """Leg 3b: STEP AP214 — set AP preference BEFORE SaveAs3."""
    result = {"leg": "STEP_AP214", "verdict": "NO-GO", "error": None}
    try:
        doc, part_path = _create_box_part(sw_app, temp_dir)

        ap_id = _find_enum("swStepAP")
        ap214_val = 214  # swStepAP takes the literal AP number
        if ap_id is not None:
            sw_app.SetUserPreferenceIntegerValue(ap_id, ap214_val)
        else:
            result["warning"] = "swStepAP ID unknown; AP214 not guaranteed"

        step_path = temp_dir / "W52_Box_ap214.step"
        err = doc.SaveAs3(str(step_path), 0, 0)
        err_code = int(err) if err is not None else 0
        if err_code != 0:
            result["error"] = f"SaveAs3(.step AP214) returned error {err_code}"
            return result

        verify = verify_step_ap(step_path, "AP214")
        result["verify"] = verify
        result["verdict"] = verify["verdict"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


# ---------------------------------------------------------------------------
# Enum cache (populated by _dump_export_enums, used by legs)
# ---------------------------------------------------------------------------
_ENUM_CACHE: dict = {}


def _find_enum(name: str) -> int | None:
    """Look up an enum value from the dump cache."""
    return _ENUM_CACHE.get(name)


def main() -> None:
    """W52 export options derisk: all legs."""
    print("=== W52 Export Options Derisk ===")

    temp_dir = Path(tempfile.mkdtemp(prefix="W52_export_"))
    print(f"Temp directory: {temp_dir}")

    sw_app = get_sw_app()
    try:
        rev = sw_app.RevisionNumber()
    except Exception:
        rev = "?"
    print(f"SW app acquired (rev: {rev})")

    results: dict = {
        "wave": "W52",
        "route": "SaveAs3_DIRECT + pre-save preferences",
        "temp_dir": str(temp_dir),
        "enum_dump": {},
        "legs": {},
        "summary": {},
        "errors": [],
    }

    print("\n--- Dumping swconst.tlb export enums ---")
    enum_dump = _dump_export_enums(sw_app)
    results["enum_dump"] = enum_dump
    global _ENUM_CACHE
    _ENUM_CACHE = {k: v for k, v in enum_dump.items() if k != "error"}
    for k, v in enum_dump.items():
        print(f"  {k} = {v}")

    legs = [
        ("DWG", leg_dwg),
        ("STL_binary", leg_stl_binary),
        ("STL_ascii", leg_stl_ascii),
        ("STEP_AP203", leg_step_ap203),
        ("STEP_AP214", leg_step_ap214),
    ]

    for leg_name, leg_fn in legs:
        print(f"\n--- Leg: {leg_name} ---")
        try:
            leg_result = leg_fn(sw_app, temp_dir)
        except Exception as exc:
            leg_result = {
                "leg": leg_name, "verdict": "NO-GO",
                "error": f"{type(exc).__name__}: {exc}",
            }
        results["legs"][leg_name] = leg_result
        results["summary"][leg_name] = leg_result.get("verdict", "NO-GO")
        verdict = leg_result.get("verdict", "NO-GO")
        print(f"  verdict: {verdict}")
        if leg_result.get("error"):
            print(f"  error: {leg_result['error']}")

    results_path = Path(__file__).parent / "_results" / "export_options_derisk.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults written to: {results_path}")
    print("\n=== SUMMARY ===")
    for leg_name, verdict in results["summary"].items():
        print(f"  {leg_name}: {verdict}")
    if results["errors"]:
        print("\n=== ERRORS ===")
        for err in results["errors"]:
            print(f"  {err}")


if __name__ == "__main__":
    main()
