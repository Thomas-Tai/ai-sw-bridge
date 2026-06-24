"""W66 planar-surface derisk spike (LIVE seat only — do NOT run offline).

Probes the planar_surface handler on a real SOLIDWORKS seat:
  Mode-B: select sketch boundary → InsertPlanarRefSurface() (0-arg, Boolean)

PASS iff a new sheet body materializes (ΔSheetBodies ≥ +1) with positive
area (ΔArea > 0) AND survives save→reopen.

Fixture: fx.build_block (40×30×10 mm boss-extrude) + a closed rectangle
sketch on the top face as the planar boundary.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import _feature_spike_fixtures as fx  # noqa: E402
from ai_sw_bridge.features.planar_surface import (  # noqa: E402
    _sheet_body_count,
    _total_sheet_area_mm2,
    create_planar_surface,
)


def _select_top_face(doc):
    """Select the top face (z = +10mm) and return it."""
    import pythoncom
    from win32com.client import VARIANT

    null_disp = VARIANT(pythoncom.VT_DISPATCH, None)
    doc.Extension.SelectByID2("", "FACE", 0.0, 0.0, 0.010, False, 0, null_disp, 0)
    face = doc.SelectionManager.GetSelectedObject6(1, -1)
    doc.ClearSelection2(True)
    return face


def _seed_planar_sketch(doc):
    """Create a closed rectangle sketch on the top face of the block.

    Returns the sketch name ("Sketch2"). The rectangle is inset from
    the block edges (±15×10 mm inside the ±20×15 mm top face).
    """
    face = _select_top_face(doc)
    if face is None:
        raise RuntimeError("could not select top face for planar sketch")
    face.Select2(False, 0)
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(
        -0.015,
        -0.010,
        0.0,
        0.015,
        0.010,
        0.0,
    )
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    return "Sketch2"


def main() -> None:
    sw = fx.connect()
    doc = fx.build_block(sw)
    sketch_name = _seed_planar_sketch(doc)
    print(f"[planar_surface] block built; sketch {sketch_name!r} seeded on top face")

    count_before = _sheet_body_count(doc)
    area_before = _total_sheet_area_mm2(doc)
    nodes_before = fx.count_feature_nodes(doc)
    print(
        f"[planar_surface] before: sheet_bodies={count_before}, "
        f"area_mm2={area_before:.3f}, feature_nodes={nodes_before}"
    )

    ok, note = create_planar_surface(doc, {}, {"boundary": sketch_name})
    print(f"[planar_surface] handler returned: ok={ok}, note={note!r}")

    count_after = _sheet_body_count(doc)
    area_after = _total_sheet_area_mm2(doc)
    nodes_after = fx.count_feature_nodes(doc)
    print(
        f"[planar_surface] after:  sheet_bodies={count_after} "
        f"(delta={count_after - count_before}), "
        f"area_mm2={area_after:.3f} (delta={area_after - area_before:.3f}), "
        f"feature_nodes={nodes_after} (delta={nodes_after - nodes_before})"
    )

    # A7 GetTypeName2 diagnostic on new features
    type_names = []
    try:
        feats = doc.FeatureManager.GetFeatures(False)
        if feats:
            for feat in feats:
                try:
                    tname = feat.GetTypeName2()
                    type_names.append(tname)
                except Exception:
                    try:
                        tname = feat.GetTypeName
                        if callable(tname):
                            tname = tname()
                        type_names.append(str(tname))
                    except Exception:
                        pass
    except Exception as exc:
        print(f"[planar_surface] GetTypeName2 scan failed: {exc!r}")
    print(f"[planar_surface] feature types: {type_names}")

    if not ok:
        print("[planar_surface] FAIL — handler returned False")
        print(
            "[planar_surface] direct-API diagnostic: attempting InsertPlanarRefSurface directly..."
        )
        try:
            doc.ClearSelection2(True)
            feat = doc.FeatureByName(sketch_name)
            if feat:
                feat.Select2(False, 0)
                ips = doc.InsertPlanarRefSurface
                direct_result = ips() if callable(ips) else ips
                print(
                    f"[planar_surface] direct InsertPlanarRefSurface -> {direct_result!r}"
                )
                direct_count = _sheet_body_count(doc)
                direct_area = _total_sheet_area_mm2(doc)
                print(
                    f"[planar_surface] direct: sheet_bodies={direct_count}, area={direct_area:.3f}"
                )
            else:
                print(f"[planar_surface] FeatureByName({sketch_name!r}) returned None")
        except Exception as exc:
            print(f"[planar_surface] direct diagnostic raised: {exc!r}")
        results = {
            "lane": "planar_surface",
            "handler_ok": False,
            "note": note,
            "sheet_bodies_before": count_before,
            "sheet_bodies_after": count_after,
            "area_before_mm2": area_before,
            "area_after_mm2": area_after,
            "feature_nodes_before": nodes_before,
            "feature_nodes_after": nodes_after,
            "type_names": type_names,
        }
        results_dir = Path(__file__).resolve().parent / "_results"
        results_dir.mkdir(exist_ok=True)
        results_path = results_dir / "planar_surface.json"
        results_path.write_text(json.dumps(results, indent=2))
        print(f"[planar_surface] results written to {results_path}")
        return

    # Save and reopen survival check
    print("[planar_surface] saving and reopening...")
    doc2 = fx.save_and_reopen(sw, doc)
    count_reopen = _sheet_body_count(doc2)
    area_reopen = _total_sheet_area_mm2(doc2)
    nodes_reopen = fx.count_feature_nodes(doc2)
    print(
        f"[planar_surface] reopen: sheet_bodies={count_reopen}, "
        f"area_mm2={area_reopen:.3f}, feature_nodes={nodes_reopen}"
    )

    survived = count_reopen >= count_before + 1 and area_reopen > 0
    results = {
        "lane": "planar_surface",
        "handler_ok": ok,
        "note": note,
        "sheet_bodies_before": count_before,
        "sheet_bodies_after": count_after,
        "sheet_bodies_reopen": count_reopen,
        "area_before_mm2": area_before,
        "area_after_mm2": area_after,
        "area_reopen_mm2": area_reopen,
        "feature_nodes_before": nodes_before,
        "feature_nodes_after": nodes_after,
        "feature_nodes_reopen": nodes_reopen,
        "survived_reopen": survived,
        "type_names": type_names,
    }
    results_dir = Path(__file__).resolve().parent / "_results"
    results_dir.mkdir(exist_ok=True)
    results_path = results_dir / "planar_surface.json"
    results_path.write_text(json.dumps(results, indent=2))
    print(f"[planar_surface] results written to {results_path}")

    if survived:
        print(
            f"[planar_surface] PASS — planar surface survived reopen "
            f"(bodies: {count_before} -> {count_reopen}, "
            f"area: {area_reopen:.3f} mm2)"
        )
    else:
        print("[planar_surface] FAIL — planar surface did NOT survive reopen")


if __name__ == "__main__":
    main()
