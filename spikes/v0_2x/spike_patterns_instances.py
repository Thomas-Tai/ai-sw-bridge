"""Spike W21 S4 — instance-count verification via geometry delta.

Closes the ONE open gap from S1/S3: proves pattern instances are real
(N>1 disjoint bodies), not hollow feature-tree entries.

Strategy: for each route, build a base plate + small rectangular boss
seed (Extrusion type), measure solid-body volume and face count before
and after the pattern, compute instance_ratio = volume_delta / seed_volume.

Expected:
  linear count=3:   ratio ≈ 2.0  (N-1 = 2 extra instances)
  circular count=4: ratio ≈ 3.0  (N-1 = 3 extra instances)
  mirror:           ratio ≈ 1.0  (1 mirrored copy)

Minimum bar: volume strictly increases AND face_count strictly increases
(refutes the hollow-pattern hypothesis).

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_patterns_instances.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "patterns_instances.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.mutate import (  # noqa: E402
    _create_circular_pattern,
    _create_linear_pattern,
    _create_mirror_feature,
)

from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8


def _title(d: Any) -> str:
    t = d.GetTitle
    if isinstance(t, tuple):
        return str(t[0])
    if callable(t):
        return str(t())
    return str(t)


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


def _get_volume_mm3(doc: Any) -> float | None:
    """Measure solid-body volume in mm³ via CreateMassProperty."""
    try:
        ext = doc.Extension
        mp = ext.CreateMassProperty
        if mp is None:
            return None
        vol_m3 = float(mp.Volume)
        return vol_m3 * 1e9  # m³ → mm³
    except Exception:
        return None


def _get_face_count(doc: Any) -> int | None:
    """Count total faces across all solid bodies."""
    try:
        bodies = doc.GetBodies2(0, True)  # swSolidBody=0
        if not bodies:
            return 0
        total = 0
        for body in bodies:
            faces = body.GetFaces()
            if faces:
                total += len(faces)
        return total
    except Exception:
        return None


def _get_body_count(doc: Any) -> int | None:
    """Count solid bodies."""
    try:
        bodies = doc.GetBodies2(0, True)
        return len(bodies) if bodies else 0
    except Exception:
        return None


def _build_base_and_seed(doc: Any, mod: Any) -> dict[str, Any]:
    """Build a base plate + small rectangular boss seed (Extrusion type).

    Base plate: 40×40×5mm on Front Plane.
    Seed: 5×5×10mm rectangular boss at (12mm, 0) — offset from center
          so pattern instances are clearly disjoint.
    """
    out: dict[str, Any] = {}
    fm = doc.FeatureManager

    # Base plate: 40×40mm rectangle, 5mm extrusion
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCornerRectangle(-0.02, -0.02, 0, 0.02, 0.02, 0)
        doc.SketchManager.InsertSketch(True)
        f = fm.FeatureExtrusion3(
            True,
            False,
            False,
            0,
            0,
            0.005,
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            True,
            True,
            True,
            0.0,
            0.0,
            False,
        )
        if f:
            f.Name = "Base_Plate"
            out["base"] = "Base_Plate"
    except Exception as e:
        out["base_error"] = f"{type(e).__name__}: {e}"
        return out

    # Seed: 5×5mm rectangle at (12mm, 0), 10mm extrusion
    try:
        # Select top face of base plate (z = 5mm)
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        if not ext.SelectByID2("", "FACE", 0.012, 0.0, 0.005, False, 0, None, 0):
            out["seed_error"] = "could not select top face"
            return out
        doc.SketchManager.InsertSketch(True)
        # 5×5mm rectangle centered at (12mm, 0) in sketch coords
        doc.SketchManager.CreateCornerRectangle(0.0095, -0.0025, 0, 0.0145, 0.0025, 0)
        doc.SketchManager.InsertSketch(True)
        f = fm.FeatureExtrusion3(
            True,
            False,
            False,
            0,
            0,
            0.01,
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            True,
            True,
            True,
            0.0,
            0.0,
            False,
        )
        if f:
            f.Name = "Seed_Boss"
            out["seed"] = "Seed_Boss"
            out["seed_type"] = _type_name(f)
    except Exception as e:
        out["seed_error"] = f"{type(e).__name__}: {e}"

    doc.ForceRebuild3(False)
    return out


def _build_ref_axis(doc: Any, fm: Any) -> bool:
    """Create Axis1 from Front Plane × Right Plane."""
    try:
        doc.ClearSelection2(True)
        feats = fm.GetFeatures(True)
        front = right = None
        for feat in feats:
            n = _feat_name(feat)
            if n == "Front Plane":
                front = feat
            elif n == "Right Plane":
                right = feat
        if front and right:
            front.Select2(False, 0)
            right.Select2(True, 0)
            doc.InsertAxis2(True)
            return True
    except Exception:
        pass
    return False


def _probe_route(sw: Any, mod: Any, route: str, count: int) -> dict[str, Any]:
    """Build geometry, measure seed volume, apply pattern, measure delta."""
    result: dict[str, Any] = {"route": route}

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["error"] = "NewDocument returned None"
        result["instances_verified"] = False
        return result

    fm = doc.FeatureManager
    geom = _build_base_and_seed(doc, mod)
    result["geometry"] = geom

    if not geom.get("seed"):
        result["error"] = f"geometry build failed: {geom}"
        result["instances_verified"] = False
        sw.CloseDoc(_title(doc))
        return result

    # Measure seed volume: vol_with_seed - vol_base
    # First, measure base-only by temporarily suppressing the seed
    # Actually, easier: measure total now, the seed volume is the delta
    # from when it was added. We can compute it from total - base_est.
    # Simpler: measure volume BEFORE pattern = V_total (base + seed).
    # Seed volume = V_total - V_base. We'll get V_base from a separate doc.

    # Build a base-only doc to get base volume
    doc_base = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc_base:
        fm_base = doc_base.FeatureManager
        try:
            doc_base.SelectByID("Front Plane", "PLANE", 0, 0, 0)
            doc_base.SketchManager.InsertSketch(True)
            doc_base.SketchManager.CreateCornerRectangle(-0.02, -0.02, 0, 0.02, 0.02, 0)
            doc_base.SketchManager.InsertSketch(True)
            fm_base.FeatureExtrusion3(
                True,
                False,
                False,
                0,
                0,
                0.005,
                0.0,
                False,
                False,
                False,
                False,
                0.0,
                0.0,
                False,
                False,
                False,
                False,
                True,
                True,
                True,
                0.0,
                0.0,
                False,
            )
            doc_base.ForceRebuild3(False)
            vol_base = _get_volume_mm3(doc_base)
            result["volume_base_only_mm3"] = vol_base
        except Exception as e:
            result["base_volume_error"] = str(e)[:200]
            vol_base = None
        sw.CloseDoc(_title(doc_base))

    # Measure before pattern
    doc.ForceRebuild3(False)
    vol_before = _get_volume_mm3(doc)
    faces_before = _get_face_count(doc)
    bodies_before = _get_body_count(doc)
    result["volume_before_mm3"] = vol_before
    result["faces_before"] = faces_before
    result["bodies_before"] = bodies_before

    # Compute seed volume
    seed_vol = None
    if vol_before is not None and vol_base is not None:
        seed_vol = vol_before - vol_base
        result["seed_volume_mm3"] = seed_vol

    # Build ref axis for circular pattern
    if route == "circular":
        _build_ref_axis(doc, fm)

    # Apply pattern
    if route == "linear":
        feature = {"type": "linear_pattern", "spacing_mm": 15.0, "count": count}
        target = {"seed": "Seed_Boss", "direction": {"x": 0, "y": 20, "z": 5}}
        ok, err = _create_linear_pattern(doc, feature, target)
    elif route == "circular":
        feature = {
            "type": "circular_pattern",
            "count": count,
            "angle_deg": 360,
            "equal_spacing": True,
        }
        target = {"seed": "Seed_Boss", "axis": "Axis1"}
        ok, err = _create_circular_pattern(doc, feature, target)
    elif route == "mirror":
        feature = {"type": "mirror_feature"}
        target = {"seed": "Seed_Boss", "plane": "Right Plane"}
        ok, err = _create_mirror_feature(doc, feature, target)
    else:
        ok, err = False, f"unknown route {route}"

    result["handler_ok"] = ok
    result["handler_error"] = err

    # Measure after pattern
    doc.ForceRebuild3(False)
    vol_after = _get_volume_mm3(doc)
    faces_after = _get_face_count(doc)
    bodies_after = _get_body_count(doc)
    result["volume_after_mm3"] = vol_after
    result["faces_after"] = faces_after
    result["bodies_after"] = bodies_after

    # Compute instance ratio
    vol_delta = None
    ratio = None
    if vol_before is not None and vol_after is not None:
        vol_delta = vol_after - vol_before
        result["volume_delta_mm3"] = vol_delta
    if vol_delta is not None and seed_vol is not None and seed_vol > 0:
        ratio = vol_delta / seed_vol
        result["instance_ratio"] = round(ratio, 3)

    # Verify pattern type name exists in tree
    has_pattern_type = False
    feats = fm.GetFeatures(True)
    if feats:
        for feat in feats:
            tn = _type_name(feat)
            if tn and any(t in tn for t in ("LPattern", "CirPattern", "MirrorPattern")):
                has_pattern_type = True
                result["pattern_type_name"] = tn
                break
    result["pattern_type_found"] = has_pattern_type

    # Expected ratio: N-1 extra instances
    expected_ratio = count - 1 if route != "mirror" else 1

    # Verify instances — minimum bar from dispatch:
    # volume STRICTLY increased AND face_count strictly increased
    # (refutes the "1 instance / hollow" hypothesis).
    # The exact N-1 ratio only holds for fully disjoint instances;
    # when the seed overlaps the rotation axis, instances share volume.
    faces_grew = (faces_after or 0) > (faces_before or 0)
    volume_grew = (vol_delta or 0) > 0

    # Strict ratio check (for disjoint geometry)
    ratio_close = (
        ratio is not None
        and abs(ratio - expected_ratio) / max(expected_ratio, 0.01) < 0.15
    )

    # Minimum bar: volume and faces both grew (refutes hollow pattern)
    min_bar_pass = ok and volume_grew and faces_grew and has_pattern_type

    result["faces_grew"] = faces_grew
    result["volume_grew"] = volume_grew
    result["expected_ratio"] = expected_ratio
    result["ratio_within_15pct"] = ratio_close
    result["min_bar_pass"] = min_bar_pass

    # Verdict: use strict ratio if it passes, otherwise fall back to minimum bar
    verified = ratio_close or min_bar_pass
    result["instances_verified"] = verified
    result["verification_method"] = (
        "strict_ratio" if ratio_close else ("minimum_bar" if min_bar_pass else "FAILED")
    )
    result["rounded_N"] = round((ratio or 0) + 1) if ratio is not None else None

    sw.CloseDoc(_title(doc))
    return result


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "w21_s4_instance_verification",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

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

    # Probe each route
    routes = [
        ("linear", 3),
        ("circular", 4),
        ("mirror", 1),  # mirror = 1 copy
    ]

    all_verified = True
    for route_name, count in routes:
        print(f"--- {route_name.upper()} (count={count}) ---", file=sys.stderr)
        probe = _probe_route(sw, mod, route_name, count)
        result[route_name] = probe
        verified = probe.get("instances_verified", False)
        ratio = probe.get("instance_ratio")
        rounded_n = probe.get("rounded_N")
        print(
            f"  handler_ok={probe.get('handler_ok')}, "
            f"ratio={ratio}, rounded_N={rounded_n}, "
            f"verified={verified}",
            file=sys.stderr,
        )
        if not verified:
            all_verified = False

    result["overall"] = "GREEN" if all_verified else "RED"
    result["summary"] = {
        r: result[r].get("instances_verified", False)
        for r in ("linear", "circular", "mirror")
    }

    # Diagnostic: test circular pattern variants on SEPARATE fresh documents
    print("--- CIRCULAR DIAGNOSTIC (fresh docs) ---", file=sys.stderr)
    diag = {}
    diag_template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    for variant_name, feature_dict in [
        (
            "A_count4_eq360",
            {
                "type": "circular_pattern",
                "count": 4,
                "angle_deg": 360,
                "equal_spacing": True,
            },
        ),
        (
            "B_count2_eq360",
            {
                "type": "circular_pattern",
                "count": 2,
                "angle_deg": 360,
                "equal_spacing": True,
            },
        ),
        (
            "C_count4_neq90",
            {
                "type": "circular_pattern",
                "count": 4,
                "angle_deg": 90.0,
                "equal_spacing": False,
            },
        ),
        (
            "D_count6_eq360",
            {
                "type": "circular_pattern",
                "count": 6,
                "angle_deg": 360,
                "equal_spacing": True,
            },
        ),
    ]:
        d = sw.NewDocument(diag_template, 0, 0.0, 0.0)
        if d is None:
            continue
        fm_d = d.FeatureManager
        try:
            d.SelectByID("Front Plane", "PLANE", 0, 0, 0)
            d.SketchManager.InsertSketch(True)
            d.SketchManager.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
            d.SketchManager.InsertSketch(True)
            f = fm_d.FeatureExtrusion3(
                True,
                False,
                False,
                0,
                0,
                0.01,
                0.0,
                False,
                False,
                False,
                False,
                0.0,
                0.0,
                False,
                False,
                False,
                False,
                True,
                True,
                True,
                0.0,
                0.0,
                False,
            )
            if f:
                f.Name = "Box_Seed"
            d.ForceRebuild3(False)
            _build_ref_axis(d, fm_d)

            vol_b = _get_volume_mm3(d)
            faces_b = _get_face_count(d)

            ok, err = _create_circular_pattern(
                d, feature_dict, {"seed": "Box_Seed", "axis": "Axis1"}
            )
            d.ForceRebuild3(False)

            vol_a = _get_volume_mm3(d)
            faces_a = _get_face_count(d)

            delta = (vol_a or 0) - (vol_b or 0)
            ratio = round(delta / (vol_b or 1), 3) if vol_b else None
            diag[variant_name] = {
                "count": feature_dict["count"],
                "equal_spacing": feature_dict.get("equal_spacing", True),
                "angle_deg": feature_dict.get("angle_deg", 360),
                "handler_ok": ok,
                "volume_before": vol_b,
                "volume_after": vol_a,
                "delta_mm3": delta,
                "faces_before": faces_b,
                "faces_after": faces_a,
                "ratio": ratio,
            }
            print(
                f"  {variant_name}: ok={ok}, delta={delta:.0f}, ratio={ratio}, faces={faces_b}->{faces_a}",
                file=sys.stderr,
            )
        except Exception as e:
            diag[variant_name] = {"error": str(e)[:200]}
        sw.CloseDoc(_title(d))

    result["circular_diagnostic"] = diag

    return result


def _diagnose_circular(sw: Any, mod: Any) -> dict[str, Any]:
    """Diagnostic: try circular pattern with the S3 PAE geometry (Box_Seed)."""
    diag: dict[str, Any] = {}

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        diag["error"] = "NewDocument None"
        return diag

    fm = doc.FeatureManager

    # Build S3-style geometry: box + ref_axis
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
        doc.SketchManager.InsertSketch(True)
        f = fm.FeatureExtrusion3(
            True,
            False,
            False,
            0,
            0,
            0.01,
            0.0,
            False,
            False,
            False,
            False,
            0.0,
            0.0,
            False,
            False,
            False,
            False,
            True,
            True,
            True,
            0.0,
            0.0,
            False,
        )
        if f:
            f.Name = "Box_Seed"
        doc.ForceRebuild3(False)
        diag["seed_type"] = _type_name(f) if f else "?"
    except Exception as e:
        diag["build_error"] = str(e)[:200]
        sw.CloseDoc(_title(doc))
        return diag

    # Build ref axis
    _build_ref_axis(doc, fm)

    # Verify axis exists and is selectable
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    doc.ClearSelection2(True)
    axis_ok = ext.SelectByID2("Axis1", "AXIS", 0, 0, 0, False, 1, None, 0)
    diag["axis_selectable"] = axis_ok

    # Measure volume before
    vol_before = _get_volume_mm3(doc)
    faces_before = _get_face_count(doc)
    diag["volume_before_mm3"] = vol_before
    diag["faces_before"] = faces_before

    # Try circular pattern with Box_Seed (S3 geometry)
    feature = {
        "type": "circular_pattern",
        "count": 4,
        "angle_deg": 360,
        "equal_spacing": True,
    }
    target = {"seed": "Box_Seed", "axis": "Axis1"}
    ok, err = _create_circular_pattern(doc, feature, target)
    diag["handler_ok"] = ok
    diag["handler_error"] = err

    doc.ForceRebuild3(False)

    vol_after = _get_volume_mm3(doc)
    faces_after = _get_face_count(doc)
    diag["volume_after_mm3"] = vol_after
    diag["faces_after"] = faces_after

    vol_delta = (vol_after or 0) - (vol_before or 0)
    diag["volume_delta_mm3"] = vol_delta
    diag["faces_grew"] = (faces_after or 0) > (faces_before or 0)

    # Also try with explicit angle = 2*pi (not equal_spacing)
    if vol_delta == 0 or True:  # always run diagnostic variants
        # Delete any existing CirPattern
        feats = fm.GetFeatures(True)
        for feat in feats:
            tn = _type_name(feat)
            if tn and "CirPattern" in tn:
                try:
                    feat.Select2(False, 0)
                    doc.EditDelete(True, 0, 0)
                except Exception:
                    pass
        doc.ForceRebuild3(False)

        # Variant A: equal_spacing=False, angle_deg=90 (angle between instances)
        print("  variant A: equal_spacing=False, angle_deg=90...", file=sys.stderr)
        featureA = {
            "type": "circular_pattern",
            "count": 4,
            "angle_deg": 90.0,
            "equal_spacing": False,
        }
        targetA = {"seed": "Box_Seed", "axis": "Axis1"}
        okA, errA = _create_circular_pattern(doc, featureA, targetA)
        doc.ForceRebuild3(False)
        volA = _get_volume_mm3(doc)
        facesA = _get_face_count(doc)
        diag["variant_A"] = {
            "desc": "equal_spacing=False, angle_deg=90, count=4",
            "handler_ok": okA,
            "volume_mm3": volA,
            "faces": facesA,
            "delta_mm3": (volA or 0) - (vol_before or 0),
            "ratio": round(((volA or 0) - (vol_before or 0)) / (vol_before or 1), 3),
        }

        # Delete and try variant B: count=5 (maybe count includes seed?)
        feats = fm.GetFeatures(True)
        for feat in feats:
            tn = _type_name(feat)
            if tn and "CirPattern" in tn:
                try:
                    feat.Select2(False, 0)
                    doc.EditDelete(True, 0, 0)
                except Exception:
                    pass
        doc.ForceRebuild3(False)

        print(
            "  variant B: count=5, equal_spacing=True, angle_deg=360...",
            file=sys.stderr,
        )
        featureB = {
            "type": "circular_pattern",
            "count": 5,
            "angle_deg": 360.0,
            "equal_spacing": True,
        }
        targetB = {"seed": "Box_Seed", "axis": "Axis1"}
        okB, errB = _create_circular_pattern(doc, featureB, targetB)
        doc.ForceRebuild3(False)
        volB = _get_volume_mm3(doc)
        facesB = _get_face_count(doc)
        diag["variant_B"] = {
            "desc": "count=5, equal_spacing=True, angle_deg=360",
            "handler_ok": okB,
            "volume_mm3": volB,
            "faces": facesB,
            "delta_mm3": (volB or 0) - (vol_before or 0),
            "ratio": round(((volB or 0) - (vol_before or 0)) / (vol_before or 1), 3),
        }

    sw.CloseDoc(_title(doc))
    return diag


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}", file=sys.stderr)
    print(payload)
    return 0 if result.get("overall") == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
