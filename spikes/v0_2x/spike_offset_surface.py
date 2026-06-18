"""W66 offset-surface derisk spike (LIVE seat only — do NOT run offline).

Probes the offset_surface handler on a real SOLIDWORKS seat:
  Mode-B: select face → InsertOffsetSurface(Thickness, Reverse) (2-arg, Void)

PASS iff a new sheet body materializes (ΔSheetBodies ≥ +1) with positive
area (ΔArea > 0) AND survives save→reopen.

Fixture: fx.build_block (40×30×10 mm boss-extrude); offset the +Z top face
by 5 mm.
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
from ai_sw_bridge.features.offset_surface import (  # noqa: E402
    _sheet_body_count,
    _total_sheet_area_mm2,
    create_offset_surface,
)


def _select_top_face(doc):
    """Select the top face (z = +10mm) and return it."""
    import pythoncom
    from win32com.client import VARIANT

    null_disp = VARIANT(pythoncom.VT_DISPATCH, None)
    doc.Extension.SelectByID2(
        "", "FACE", 0.0, 0.0, 0.010, False, 0, null_disp, 0
    )
    face = doc.SelectionManager.GetSelectedObject6(1, -1)
    doc.ClearSelection2(True)
    return face


def main() -> None:
    sw = fx.connect()
    doc = fx.build_block(sw)
    face = _select_top_face(doc)
    if face is None:
        print("[offset_surface] FAIL — could not select top face")
        return
    print("[offset_surface] block built; top face acquired")

    count_before = _sheet_body_count(doc)
    area_before = _total_sheet_area_mm2(doc)
    nodes_before = fx.count_feature_nodes(doc)
    print(
        f"[offset_surface] before: sheet_bodies={count_before}, "
        f"area_mm2={area_before:.3f}, feature_nodes={nodes_before}"
    )

    ok, note = create_offset_surface(
        doc,
        {"offset_mm": 5.0, "reverse": False},
        {"face_entity": face},
    )
    print(f"[offset_surface] handler returned: ok={ok}, note={note!r}")

    count_after = _sheet_body_count(doc)
    area_after = _total_sheet_area_mm2(doc)
    nodes_after = fx.count_feature_nodes(doc)
    print(
        f"[offset_surface] after:  sheet_bodies={count_after} "
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
        print(f"[offset_surface] GetTypeName2 scan failed: {exc!r}")
    print(f"[offset_surface] feature types: {type_names}")

    if not ok:
        print("[offset_surface] FAIL — handler returned False")
        print("[offset_surface] direct-API diagnostic: attempting InsertOffsetSurface directly...")
        try:
            doc.ClearSelection2(True)
            face2 = _select_top_face(doc)
            if face2 is not None:
                from ai_sw_bridge.selection.live import select_entity
                select_entity(face2, mark=0)
                ios = doc.InsertOffsetSurface
                direct_result = ios(0.005, False) if callable(ios) else ios
                print(f"[offset_surface] direct InsertOffsetSurface(0.005, False) -> {direct_result!r}")
                direct_count = _sheet_body_count(doc)
                direct_area = _total_sheet_area_mm2(doc)
                print(f"[offset_surface] direct: sheet_bodies={direct_count}, area={direct_area:.3f}")
            else:
                print("[offset_surface] could not re-select top face for diagnostic")
        except Exception as exc:
            print(f"[offset_surface] direct diagnostic raised: {exc!r}")
        results = {
            "lane": "offset_surface",
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
        results_path = results_dir / "offset_surface.json"
        results_path.write_text(json.dumps(results, indent=2))
        print(f"[offset_surface] results written to {results_path}")
        return

    # Save and reopen survival check
    print("[offset_surface] saving and reopening...")
    doc2 = fx.save_and_reopen(sw, doc)
    count_reopen = _sheet_body_count(doc2)
    area_reopen = _total_sheet_area_mm2(doc2)
    nodes_reopen = fx.count_feature_nodes(doc2)
    print(
        f"[offset_surface] reopen: sheet_bodies={count_reopen}, "
        f"area_mm2={area_reopen:.3f}, feature_nodes={nodes_reopen}"
    )

    survived = count_reopen >= count_before + 1 and area_reopen > 0
    results = {
        "lane": "offset_surface",
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
    results_path = results_dir / "offset_surface.json"
    results_path.write_text(json.dumps(results, indent=2))
    print(f"[offset_surface] results written to {results_path}")

    if survived:
        print(
            f"[offset_surface] PASS — offset surface survived reopen "
            f"(bodies: {count_before} -> {count_reopen}, "
            f"area: {area_reopen:.3f} mm2)"
        )
    else:
        print("[offset_surface] FAIL — offset surface did NOT survive reopen")


if __name__ == "__main__":
    main()
