"""Seat-check: P1.1-seat — verify export format strings on a live SW seat.

Tests ``IModelDoc2.SaveAs3(path, 0, version)`` for every SAVEAS3_DIRECT format
in ``export/formats.py``. Each format uses the file extension to select the
SW exporter; this confirms the extension strings actually produce output files.

Non-destructive: builds its own box part, exports to a temp dir, cleans up.

Usage:  .venv-py310\Scripts\python spikes\v0_16\_seatcheck_export_formats.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from spike_earlybind_persist import connect_running_sw  # noqa: E402
from spike_persist_reference import build_single_box  # noqa: E402
from ai_sw_bridge.export.formats import (  # noqa: E402
    EXPORT_FORMATS,
    SaveMethod,
)

SW_DEFAULT_TEMPLATE_PART = 8


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _save_as3(doc: Any, path: str, version: int = 0) -> dict[str, Any]:
    """Attempt doc.SaveAs3 and report the result."""
    t0 = time.perf_counter()
    try:
        result = doc.SaveAs3(path, 0, version)
        elapsed = (time.perf_counter() - t0) * 1000.0
        file_exists = Path(path).exists()
        file_size = Path(path).stat().st_size if file_exists else 0
        return {
            "status": "OK" if result in (0, None) else f"returned {result}",
            "file_exists": file_exists,
            "file_size": file_size,
            "elapsed_ms": round(elapsed, 1),
        }
    except Exception as e:
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        }


def run() -> dict[str, Any]:
    result: dict[str, Any] = {}

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    # Build a simple box part
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    build = build_single_box(doc)
    if not build.get("built"):
        sw.CloseDoc(_title(doc))
        return {**result, "overall": "FAIL", "reason": f"box build failed: {build}"}

    # Save as .sldprt first (SaveAs3 needs a saved doc for some formats)
    tmp_dir = Path(tempfile.mkdtemp(prefix="aiswb_p11_"))
    part_path = tmp_dir / "export_test.sldprt"
    try:
        doc.SaveAs3(str(part_path), 0, 0)
    except Exception as e:
        sw.CloseDoc(_title(doc))
        return {**result, "overall": "FAIL", "reason": f"SaveAs3(sldprt) raised: {e}"}
    result["part_saved"] = str(part_path)

    # --- Test each SAVEAS3_DIRECT format ------------------------------------
    format_results: dict[str, dict[str, Any]] = {}
    saveas3_ok = 0
    saveas3_fail = 0

    for name, fmt in EXPORT_FORMATS.items():
        if fmt.save_method != SaveMethod.SAVEAS3_DIRECT:
            format_results[name] = {
                "skipped": True,
                "reason": f"save_method={fmt.save_method.value} (not SAVEAS3_DIRECT)",
            }
            continue

        out_path = tmp_dir / f"export_test{fmt.extension}"
        if out_path.exists():
            out_path.unlink()

        probe = _save_as3(doc, str(out_path), fmt.save_version)
        probe["format"] = name
        probe["extension"] = fmt.extension
        probe["save_version"] = fmt.save_version
        format_results[name] = probe

        if probe.get("file_exists"):
            saveas3_ok += 1
        else:
            saveas3_fail += 1

    result["formats"] = format_results
    result["saveas3_ok"] = saveas3_ok
    result["saveas3_fail"] = saveas3_fail

    # --- Verdict ------------------------------------------------------------
    # PASS if all SAVEAS3_DIRECT formats produced files
    direct_count = sum(
        1 for f in EXPORT_FORMATS.values()
        if f.save_method == SaveMethod.SAVEAS3_DIRECT
    )
    if saveas3_ok == direct_count:
        result["overall"] = "PASS"
        result["verdict_detail"] = (
            f"all {direct_count} SAVEAS3_DIRECT formats produced files; "
            "seat_confirmed=True for all. PDF and flat-pattern DXF remain SEAT-gated."
        )
    elif saveas3_ok > 0:
        result["overall"] = "PARTIAL"
        failed = [n for n, r in format_results.items() if not r.get("skipped") and not r.get("file_exists")]
        result["verdict_detail"] = (
            f"{saveas3_ok}/{direct_count} SAVEAS3_DIRECT formats OK; "
            f"failed: {', '.join(failed)}. Investigate per-format."
        )
    else:
        result["overall"] = "FAIL"
        result["verdict_detail"] = "no SAVEAS3_DIRECT formats produced files"

    # Cleanup
    sw.CloseDoc(_title(doc))
    result["cleanup"] = f"doc closed, temp dir at {tmp_dir}"
    return result


if __name__ == "__main__":
    report = run()
    out = Path(__file__).parent / "_results" / "p11_export_formats.json"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(json.dumps(report, indent=2, default=str))
    print(f"\nReport written to {out}")
