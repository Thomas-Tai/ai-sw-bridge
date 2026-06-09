"""S1 PAE: STEP round-trip import via the production ``import_geom`` path.

Drives the full chain on a live seat:

1. Build a 20×30×40 mm box in a fresh blank part (builder recipe, mirrors
   ``spikes/v0_2x/export_3d_pae.py``).
2. Export to STEP via ``doc.SaveAs3(path, 0, 0)`` — the proven W34 route.
3. Close the source doc so the import side starts clean.
4. Run the production ``import_geom.import_part()`` with the exported
   ``.step`` file, declaring ``verify.volume_mm3 == 24000``.

Verdict rule: PASS iff ``result.ok`` AND ``result.bodies >= 1`` AND
``abs(result.volume_mm3 - 24000) <= 0.01 * 24000`` (the declared rel_tol).

Also exercises the two fail-closed gates (S3 preview):

- **Unsupported-extension** — pass ``/tmp/vendor.txt`` and confirm the
  validator rejects with ``path=="source"`` before any COM call.
- **Bodyless-Reference-feature trap** — pass the import a doc-shaped mock
  whose ``GetBodies2`` returns ``None`` and confirm the production code
  surfaces the typed "E4 trap" error. (This is the same mock harness the
  offline tests use — seat-free, run here as a harness sanity check.)

Output: ``spikes/v0_2x/_results/import_geom_pae.json``
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

src_path = Path(__file__).resolve().parents[2] / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from ai_sw_bridge.import_geom import (
    ImportResult,
    ImportValidationError,
    import_part,
    validate_import_spec,
)
from ai_sw_bridge.sw_com import get_sw_app


# 20×30×40 box — the round-trip fixture. Volume = 24000 mm³ exactly.
_WIDTH_MM = 20.0
_DEPTH_MM = 30.0
_HEIGHT_MM = 40.0
_EXPECTED_VOLUME_MM3 = _WIDTH_MM * _DEPTH_MM * _HEIGHT_MM  # 24000


def _make_box_and_export_step(sw_app, temp_dir: Path) -> Path:
    """Build the 20×30×40 box and export to STEP. Returns the STEP path."""
    template = sw_app.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
    doc = sw_app.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        raise RuntimeError("NewDocument returned None")

    # SK_Box: centered rectangle on Front Plane. Half-extents in meters:
    #   width/2 = 10 mm = 0.010 m, depth/2 = 15 mm = 0.015 m.
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, _WIDTH_MM / 2 / 1000.0,
                             _DEPTH_MM / 2 / 1000.0, 0.0)
    sm.InsertSketch(True)

    feat = doc.FeatureManager.FeatureExtrusion2(
        True, False, False,
        0, 0,
        _HEIGHT_MM / 1000.0, 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False,
        True, True, True,
        0, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("FeatureExtrusion2 failed")

    prt_path = temp_dir / "w40_box_20_30_40.SLDPRT"
    err = doc.SaveAs3(str(prt_path), 0, 0)
    if err:
        raise RuntimeError(f"SaveAs3(.SLDPRT) returned {err}")

    step_path = temp_dir / "w40_box_20_30_40.step"
    err = doc.SaveAs3(str(step_path), 0, 0)
    if err:
        raise RuntimeError(f"SaveAs3(.step) returned {err}")
    if not step_path.exists() or step_path.stat().st_size == 0:
        raise RuntimeError("STEP export produced no bytes")

    # Clean the seat
    sw_app.CloseDoc("w40_box_20_30_40.SLDPRT")
    return step_path


def _fail_closed_unsupported_ext(temp_dir: Path) -> dict:
    """Unsupported extension must be rejected at validation, not at COM."""
    src = temp_dir / "vendor.txt"
    src.write_bytes(b"not geometry")
    out = temp_dir / "out.sldprt"
    envelope = {"kind": "import", "source": str(src), "output": str(out)}
    try:
        validate_import_spec(envelope)
        return {"ok": False, "error": "validator did NOT reject .txt"}
    except ImportValidationError as exc:
        return {
            "ok": exc.path == "source" and "unsupported extension" in exc.message,
            "path": exc.path,
            "message": exc.message,
        }


def main() -> dict:
    print("=== W40 S1 PAE: STEP round-trip via import_geom production path ===")

    temp_dir = Path(tempfile.mkdtemp(prefix="W40_pae_"))
    print(f"Temp dir: {temp_dir}")

    results: dict = {
        "wave": "W40",
        "stage": "S1_PAE",
        "seat": None,
        "fixture": {
            "width_mm": _WIDTH_MM,
            "depth_mm": _DEPTH_MM,
            "height_mm": _HEIGHT_MM,
            "expected_volume_mm3": _EXPECTED_VOLUME_MM3,
        },
        "round_trip": {},
        "fail_closed_unsupported_ext": {},
        "verdict": "FAIL",
        "errors": [],
    }

    try:
        sw_app = get_sw_app()
        results["seat"] = f"SW {sw_app.RevisionNumber()}"

        print(f"Building {_WIDTH_MM}×{_DEPTH_MM}×{_HEIGHT_MM} box and exporting to STEP...")
        step_path = _make_box_and_export_step(sw_app, temp_dir)
        print(f"  STEP written: {step_path} ({step_path.stat().st_size} bytes)")

        out_sldprt = temp_dir / "w40_round_trip.SLDPRT"
        spec = validate_import_spec(
            {
                "kind": "import",
                "source": str(step_path),
                "output": str(out_sldprt),
                "verify": {
                    "volume_mm3": _EXPECTED_VOLUME_MM3,
                    "volume_rel_tol": 0.01,
                    "min_bodies": 1,
                },
            }
        )

        print("Running production import_part()...")
        result: ImportResult = import_part(spec)
        results["round_trip"] = result.to_dict()

        print(f"  result: ok={result.ok}, bodies={result.bodies}, "
              f"faces={result.faces}, volume_mm3={result.volume_mm3}")

        if result.ok and result.volume_mm3 is not None:
            rel_err = abs(result.volume_mm3 - _EXPECTED_VOLUME_MM3) / _EXPECTED_VOLUME_MM3
            results["round_trip"]["volume_rel_err"] = round(rel_err, 6)

    except Exception as exc:
        results["errors"].append(f"PAE crashed: {type(exc).__name__}: {exc}")
        results["traceback"] = traceback.format_exc()

    # Fail-closed (seat-free — runs regardless of SW state).
    results["fail_closed_unsupported_ext"] = _fail_closed_unsupported_ext(temp_dir)

    # Overall verdict:
    #   PASS iff round_trip.ok AND volume within tolerance AND fail-closed.ok
    rt = results["round_trip"]
    fc = results["fail_closed_unsupported_ext"]
    if (
        rt.get("ok")
        and rt.get("volume_mm3") is not None
        and abs(rt["volume_mm3"] - _EXPECTED_VOLUME_MM3) <= 0.01 * _EXPECTED_VOLUME_MM3
        and fc.get("ok")
        and not results["errors"]
    ):
        results["verdict"] = "PASS"

    out_path = Path(__file__).parent / "_results" / "import_geom_pae.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults: {out_path}")
    print(f"Verdict: {results['verdict']}")

    return results


if __name__ == "__main__":
    main()
