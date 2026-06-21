"""Seat-proof — linear_pattern direction-2 + multi-seed (LIVE seat).

Fires the PRODUCTION handler ``mutate._create_linear_pattern(doc, feature,
target)`` in the two new closed-form modes added this session:

  * Probe A (dir-2): one seed boss at the top centre, patterned 2x in X
    (spacing 10mm) AND 2x in Y (spacing 8mm) -> 4 instances (1 seed + 3 new).
  * Probe B (multi-seed): two seed bosses patterned together 2x in X ->
    +2 new bosses.

Both are ADDITIVE -> witness ΔVol > 0 AND ΔFaces > 0.  Block 40x30x10mm
(x:-20..20, y:-15..15, z top=10).  Top edges: +Y side runs along X (point
(0,15,10)mm); +X side runs along Y (point (20,0,10)mm).

Usage::

    C:/Python314/python.exe spikes/v0_2x/spike_linear_pattern_dir2.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_SRC))

import pythoncom  # noqa: E402

from _feature_spike_fixtures import build_block, connect, top_face  # noqa: E402
from ai_sw_bridge.features import verify  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parents[2] / "spikes" / "v0_2x" / "_results" / "linear_pattern_dir2.json"

_BLIND = 0


def _feat_name(feat: Any) -> str | None:
    try:
        n = feat.Name
        return str(n() if callable(n) else n)
    except Exception:
        return None


def _build_seed_boss(doc: Any, cx: float, cy: float, r: float = 0.003, h: float = 0.005) -> str | None:
    """Build a boss (radius r, height h) at sketch (cx,cy) on the top face.
    Returns the boss feature name."""
    try:
        face = top_face(doc)
        face.Select2(False, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCircleByRadius(cx, cy, 0.0, r)
        doc.SketchManager.InsertSketch(True)
        doc.ClearSelection2(True)
        seed_sketch = doc.FeatureByPositionReverse(0)
        if seed_sketch is not None:
            seed_sketch.Select2(False, 0)
        boss = doc.FeatureManager.FeatureExtrusion2(
            True, False, False, _BLIND, 0, h, 0.0, False, False, False, False,
            0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0, False,
        )
        doc.ClearSelection2(True)
        return _feat_name(boss) if boss is not None else None
    except Exception as e:
        print(f"[seed_boss] {e!r}", file=sys.stderr)
        return None


def _probe(label: str, sw: Any, feature: dict, target_fn) -> dict:
    out: dict[str, Any] = {"label": label, "feature": feature}
    doc = build_block(sw)
    try:
        target = target_fn(doc)
        if target is None:
            out["verdict"] = "ERROR"
            out["reason"] = "seed/target build failed"
            return out
        out["target"] = target
        f0, v0 = verify.solid_metrics(doc)
        ok, note = mutate._create_linear_pattern(doc, feature, target)
        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass
        f1, v1 = verify.solid_metrics(doc)
        out["handler_ok"] = ok
        out["handler_note"] = note
        out["before"] = {"faces": f0, "vol": v0}
        out["after"] = {"faces": f1, "vol": v1}
        out["delta"] = {"faces": f1 - f0, "vol": v1 - v0}
        geom = (f1 - f0) > 0 and (v1 - v0) > 1e-9
        out["verdict"] = "GO" if (ok and geom) else ("NO_OP" if not ok else "GHOST")
        return out
    finally:
        try:
            sw.CloseDoc(doc.GetTitle if not callable(doc.GetTitle) else doc.GetTitle())
        except Exception:
            pass


def _target_dir2(doc: Any) -> dict | None:
    seed = _build_seed_boss(doc, 0.0, 0.0)
    if seed is None:
        return None
    return {
        "seed": seed,
        "direction": {"x": 0.0, "y": 15.0, "z": 10.0},    # +Y-side top edge -> X dir
        "direction2": {"x": 20.0, "y": 0.0, "z": 10.0},   # +X-side top edge -> Y dir
    }


def _target_multiseed(doc: Any) -> dict | None:
    # seeds 20mm apart in X; pattern in Y so instances never collide.
    s1 = _build_seed_boss(doc, -0.010, 0.0)
    s2 = _build_seed_boss(doc, 0.010, 0.0)
    if s1 is None or s2 is None:
        return None
    return {
        "seeds": [s1, s2],
        "direction": {"x": 20.0, "y": 0.0, "z": 10.0},    # +X-side top edge -> Y dir
    }


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"spike": "linear_pattern_dir2", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    sw = connect()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    a = _probe("dir2", sw, {"type": "linear_pattern", "count": 2, "spacing_mm": 10.0, "count2": 2, "spacing2_mm": 8.0}, _target_dir2)
    b = _probe("multiseed", sw, {"type": "linear_pattern", "count": 2, "spacing_mm": 10.0}, _target_multiseed)
    result["dir2"] = a
    result["multiseed"] = b
    both = a.get("verdict") == "GO" and b.get("verdict") == "GO"
    result["overall"] = "PASS" if both else "FAIL"
    result["finding"] = (
        f"dir2={a.get('verdict')} (Δvol={a.get('delta', {}).get('vol')}, Δfaces={a.get('delta', {}).get('faces')}); "
        f"multiseed={b.get('verdict')} (Δvol={b.get('delta', {}).get('vol')}, Δfaces={b.get('delta', {}).get('faces')})"
    )
    return result


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", ""), file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
