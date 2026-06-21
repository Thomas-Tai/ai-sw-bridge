"""W68 spike — ``sketch_driven_pattern`` seat probe (LIVE seat only).

Builds a block fixture, adds a seed boss on the top face, creates a
reference sketch with ~3 points, then fires the handler and probes:

  * FeatureSketchDrivenPattern return (DISPATCH or None)
  * GetTypeName2 of the new pattern node (UNKNOWN — likely
    "LocalSketchPattern" / "SketchDrivenPattern" — log it)
  * ΔVol > 0 AND ΔFaces > 0 (ADDITIVE_SOLID gate)
  * save→reopen survival
  * the reference-sketch selection mark (1/2/4?) that actually works
  * whether UseCentroid changes the anchoring

Usage::

    C:/Python314/python.exe spikes/v0_2x/spike_sketch_driven_pattern.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pythoncom

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from _feature_spike_fixtures import (  # noqa: E402
    build_block,
    connect,
    count_feature_nodes,
    save_and_reopen,
    top_face,
)

RESULTS_PATH = _REPO_ROOT / "spikes" / "v0_2x" / "_results" / "sketch_driven_pattern.json"

_BLIND = 0


def _null_disp() -> Any:
    from win32com.client import VARIANT
    return VARIANT(pythoncom.VT_DISPATCH, None)


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


def _solid_metrics(doc: Any) -> tuple[int, float]:
    """(face_count, volume_mm3) over solid bodies."""
    from ai_sw_bridge.features import verify
    return verify.solid_metrics(doc)


def _build_seed_boss(doc: Any) -> str | None:
    """Add a small boss on the top face of the block (5mm circle, 5mm tall).

    Returns the boss feature name, or None on failure.
    """
    try:
        face = top_face(doc)
        face.Select2(False, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCircleByRadius(0.005, 0.005, 0.0, 0.003)
        doc.SketchManager.InsertSketch(True)
        doc.ClearSelection2(True)
        doc.FeatureManager.FeatureExtrusion2(
            True, False, False, _BLIND, 0,
            0.005, 0.0, False, False, False, False,
            0.0, 0.0, False, False, False, False,
            True, True, True, 0, 0.0, False,
        )
        doc.ClearSelection2(True)
        return "Boss-Extrude2"
    except Exception as e:
        print(f"[seed_boss] FAILED: {e!r}", file=sys.stderr)
        return None


def _build_ref_sketch(doc: Any) -> str | None:
    """Add a reference sketch on the top face with ~3 points.

    The sketch holds the pattern-point locations. Returns the sketch
    name, or None on failure.
    """
    try:
        face = top_face(doc)
        face.Select2(False, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreatePoint(-0.010, -0.008, 0.0)
        doc.SketchManager.CreatePoint(0.010, -0.008, 0.0)
        doc.SketchManager.CreatePoint(0.0, 0.008, 0.0)
        doc.SketchManager.InsertSketch(True)
        doc.ClearSelection2(True)
        return "Sketch3"
    except Exception as e:
        print(f"[ref_sketch] FAILED: {e!r}", file=sys.stderr)
        return None


def _dump_feature_tree(doc: Any) -> list[dict[str, Any]]:
    """Dump feature tree for diagnostics."""
    result = []
    try:
        feats = doc.FeatureManager.GetFeatures(False)
        if feats:
            for f in feats:
                result.append({
                    "name": _feat_name(f),
                    "type": _type_name(f),
                })
    except Exception:
        pass
    return result


def _find_pattern_node(doc: Any) -> tuple[str | None, str | None]:
    """Find a sketch-driven pattern node in the feature tree.

    Returns ``(name, type_name)`` or ``(None, None)``.
    """
    try:
        feats = doc.FeatureManager.GetFeatures(False)
        if not feats:
            return None, None
        for f in feats:
            tn = _type_name(f)
            if tn and any(tok in tn.lower() for tok in (
                "sketchdrivenpattern", "localsketchpattern", "sketchpattern",
                "drivenpattern",
            )):
                return _feat_name(f), tn
    except Exception:
        pass
    return None, None


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike": "w68_sketch_driven_pattern",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    sw = connect()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    doc = build_block(sw)
    result["block"] = "40x30x10 mm"

    seed_name = _build_seed_boss(doc)
    result["seed_boss"] = seed_name
    if not seed_name:
        result["overall"] = "ERROR"
        result["finding"] = "seed boss build failed"
        return result

    sketch_name = _build_ref_sketch(doc)
    result["ref_sketch"] = sketch_name
    if not sketch_name:
        result["overall"] = "ERROR"
        result["finding"] = "reference sketch build failed"
        return result

    faces_before, vol_before = _solid_metrics(doc)
    nodes_before = count_feature_nodes(doc)
    result["before"] = {
        "faces": faces_before,
        "vol_mm3": vol_before,
        "nodes": nodes_before,
    }

    from ai_sw_bridge.features.sketch_driven_pattern import create_sketch_driven_pattern

    ok, note = create_sketch_driven_pattern(
        doc,
        {
            "seed_name": seed_name,
            "sketch_name": sketch_name,
            "use_centroid": True,
            "geom_pattern": False,
        },
        {},
    )
    result["handler_ok"] = ok
    result["handler_note"] = note

    faces_after, vol_after = _solid_metrics(doc)
    nodes_after = count_feature_nodes(doc)
    result["after"] = {
        "faces": faces_after,
        "vol_mm3": vol_after,
        "nodes": nodes_after,
    }
    result["delta"] = {
        "faces": faces_after - faces_before,
        "vol_mm3": vol_after - vol_before,
        "nodes": nodes_after - nodes_before,
    }

    pat_name, pat_type = _find_pattern_node(doc)
    result["pattern_node"] = {"name": pat_name, "type_name": pat_type}
    result["feature_tree"] = _dump_feature_tree(doc)

    if ok and (faces_after - faces_before) > 0 and (vol_after - vol_before) > 0:
        print("[save_and_reopen]", file=sys.stderr)
        try:
            doc2 = save_and_reopen(sw, doc)
            faces_reopen, vol_reopen = _solid_metrics(doc2)
            nodes_reopen = count_feature_nodes(doc2)
            pat_name_r, pat_type_r = _find_pattern_node(doc2)
            result["reopen"] = {
                "faces": faces_reopen,
                "vol_mm3": vol_reopen,
                "nodes": nodes_reopen,
                "pattern_node": {"name": pat_name_r, "type_name": pat_type_r},
                "survives": (
                    faces_reopen >= faces_after and vol_reopen > 0
                ),
            }
        except Exception as e:
            result["reopen"] = {"error": str(e)[:200]}
        result["overall"] = "PASS"
        result["finding"] = (
            f"sketch_driven_pattern: +{faces_after - faces_before} faces, "
            f"+{vol_after - vol_before:.3f} mm3, "
            f"type_name={pat_type!r}"
        )
    else:
        result["overall"] = "NO_OP" if not ok else "GHOST"
        result["finding"] = (
            f"handler_ok={ok}, delta_faces={faces_after - faces_before}, "
            f"delta_vol={vol_after - vol_before:.3f}, "
            f"note={note!r}"
        )

    return result


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}", file=sys.stderr)
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", ""), file=sys.stderr)
    print(payload)
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
