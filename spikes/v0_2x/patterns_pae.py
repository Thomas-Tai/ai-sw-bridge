"""W21 Production PAE — linear_pattern + circular_pattern + mirror_feature.

Exercises the three pattern handlers directly on a live SW part:

  1. Build a part with a box seed (Extrusion type) + ref_axis.
  2. Call _create_linear_pattern → verify LPattern.
  3. Call _create_circular_pattern → verify CirPattern.
  4. Call _create_mirror_feature → verify MirrorPattern.
  5. Save .SLDPRT, re-open, verify all three present.

Prereq: SOLIDWORKS 2024 SP1 running.
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

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "patterns_pae.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.mutate import (  # noqa: E402
    _create_circular_pattern,
    _create_linear_pattern,
    _create_mirror_feature,
)

from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8

results: dict[str, Any] = {
    "pae": "w21_patterns",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
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


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _feat_name(feat: Any) -> str | None:
    try:
        n = feat.Name
        return str(n() if callable(n) else n)
    except Exception:
        return None


def _feat_count(fm: Any) -> int:
    _feats = fm.GetFeatures(True)
    return len(_feats) if _feats else 0


def _title(d: Any) -> str:
    t = d.GetTitle
    if isinstance(t, tuple):
        return str(t[0])
    if callable(t):
        return str(t())
    return str(t)


def run() -> str:
    print("=" * 70)
    print("W21: Pattern features production PAE")
    print("=" * 70)

    sw = connect_running_sw()
    mod = wrapper_module()

    # Close all docs
    try:
        docs = sw.GetDocuments()
        if docs:
            for d in docs:
                try:
                    sw.CloseDoc(_title(d))
                except Exception:
                    pass
    except Exception:
        pass

    # Create new part
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        gate("new_doc", False, "NewDocument returned None")
        return "RED"
    gate("new_doc", True, "")

    fm = doc.FeatureManager

    # Build box seed (Extrusion type)
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
        doc.SketchManager.InsertSketch(True)
        f = fm.FeatureExtrusion3(
            True, False, False, 0, 0, 0.01, 0.0,
            False, False, False, False, 0.0, 0.0,
            False, False, False, False,
            True, True, True, 0.0, 0.0, False,
        )
        if f:
            f.Name = "Box_Seed"
        doc.ForceRebuild3(False)
        seed_type = _type_name(f) if f else "?"
        gate("build_box", f is not None, f"type={seed_type}")
    except Exception as e:
        gate("build_box", False, str(e)[:200])
        return "RED"

    # Build ref axis (Front Plane x Right Plane = Y axis)
    try:
        doc.ClearSelection2(True)
        feats = fm.GetFeatures(True)
        front_plane = right_plane = None
        for feat in feats:
            n = _feat_name(feat)
            if n == "Front Plane":
                front_plane = feat
            elif n == "Right Plane":
                right_plane = feat
        if front_plane and right_plane:
            front_plane.Select2(False, 0)
            right_plane.Select2(True, 0)
            doc.InsertAxis2(True)
        gate("build_axis", True, "Axis1 (Front x Right)")
    except Exception as e:
        gate("build_axis", False, str(e)[:200])

    count_before = _feat_count(fm)
    gate("feature_count_before", True, str(count_before))

    # LINEAR PATTERN
    print("\n--- Linear Pattern ---")
    linear_feature = {"type": "linear_pattern", "spacing_mm": 5.0, "count": 3}
    linear_target = {"seed": "Box_Seed", "direction": {"x": 0, "y": 10, "z": 10}}
    try:
        ok, err = _create_linear_pattern(doc, linear_feature, linear_target)
        count_after_linear = _feat_count(fm)
        gate("linear_handler", ok, err or f"delta={count_after_linear - count_before}")

        # Verify type name
        has_linear = False
        feats = fm.GetFeatures(True)
        if feats:
            for feat in feats:
                tn = _type_name(feat)
                if tn and "LPattern" in tn:
                    has_linear = True
                    gate("linear_type", True, tn)
                    break
        if not has_linear:
            gate("linear_type", False, "LPattern not found")
    except Exception as e:
        gate("linear_handler", False, str(e)[:200])

    # CIRCULAR PATTERN
    print("\n--- Circular Pattern ---")
    circ_feature = {"type": "circular_pattern", "count": 4, "angle_deg": 360, "equal_spacing": True}
    circ_target = {"seed": "Box_Seed", "axis": "Axis1"}
    try:
        ok, err = _create_circular_pattern(doc, circ_feature, circ_target)
        count_after_circ = _feat_count(fm)
        gate("circular_handler", ok, err or f"delta={count_after_circ - count_after_linear}")

        has_circ = False
        feats = fm.GetFeatures(True)
        if feats:
            for feat in feats:
                tn = _type_name(feat)
                if tn and "CirPattern" in tn:
                    has_circ = True
                    gate("circular_type", True, tn)
                    break
        if not has_circ:
            gate("circular_type", False, "CirPattern not found")
    except Exception as e:
        gate("circular_handler", False, str(e)[:200])

    # MIRROR FEATURE
    print("\n--- Mirror Feature ---")
    mirror_feature = {"type": "mirror_feature"}
    mirror_target = {"seed": "Box_Seed", "plane": "Right Plane"}
    try:
        ok, err = _create_mirror_feature(doc, mirror_feature, mirror_target)
        count_after_mirror = _feat_count(fm)
        gate("mirror_handler", ok, err or f"delta={count_after_mirror - count_after_circ}")

        has_mirror = False
        feats = fm.GetFeatures(True)
        if feats:
            for feat in feats:
                tn = _type_name(feat)
                if tn and "MirrorPattern" in tn:
                    has_mirror = True
                    gate("mirror_type", True, tn)
                    break
        if not has_mirror:
            gate("mirror_type", False, "MirrorPattern not found")
    except Exception as e:
        gate("mirror_handler", False, str(e)[:200])

    # SAVE + REOPEN
    print("\n--- Save + Reopen ---")
    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge-w21"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    part_path = tmp_dir / "w21_patterns_pae.sldprt"
    try:
        doc.SaveAs3(str(part_path), 0, 0)
        gate("save", True, str(part_path))

        # Close
        sw.CloseDoc(_title(doc))

        # Reopen using the production pattern: typed ISldWorks + plain 0 for errors/warnings
        tsw = typed(sw, "ISldWorks", module=mod)
        doc2_raw = tsw.OpenDoc6(str(part_path), 1, 1, "", 0, 0)
        # Typed wrapper may return tuple (doc, errors, warnings) for byref params
        doc2 = doc2_raw[0] if isinstance(doc2_raw, tuple) else doc2_raw
        if doc2 is None:
            gate("reopen", False, "OpenDoc6 returned None")
        else:
            gate("reopen", True, "")
            fm2 = doc2.FeatureManager
            has_l = has_c = has_m = False
            feats = fm2.GetFeatures(True)
            if feats:
                for feat in feats:
                    tn = _type_name(feat)
                    if tn:
                        if "LPattern" in tn:
                            has_l = True
                        if "CirPattern" in tn:
                            has_c = True
                        if "MirrorPattern" in tn:
                            has_m = True
            gate("reopen_linear", has_l, f"LPattern found={has_l}")
            gate("reopen_circular", has_c, f"CirPattern found={has_c}")
            gate("reopen_mirror", has_m, f"MirrorPattern found={has_m}")
            gate("file_exists", part_path.exists(), f"size={part_path.stat().st_size}")

            sw.CloseDoc(_title(doc2))
    except Exception as e:
        gate("save_reopen", False, str(e)[:200])

    # Overall
    all_pass = all(g["ok"] for g in results["gates"].values())
    results["verdict"] = "GREEN" if all_pass else "RED"
    pass_count = sum(1 for g in results["gates"].values() if g["ok"])
    total_count = len(results["gates"])
    gate("OVERALL_GREEN", all_pass, f"{pass_count}/{total_count} gates pass")

    return results["verdict"]


def main() -> int:
    pythoncom.CoInitialize()
    try:
        verdict = run()
    finally:
        pythoncom.CoUninitialize()
    save_results()
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
