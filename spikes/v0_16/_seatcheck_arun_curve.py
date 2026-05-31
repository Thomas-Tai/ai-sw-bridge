"""Seat-check: A-run — verify interrogator curve-mid / arc-length reads.

Confirms on a live SW 2024 seat that ``brep.interrogator._read_curve_mid_and_arc``
returns true-curve data (source ``"curve"``) for curved edges, not just the
chord fallback.  A cylinder (circle sketch + extrude) produces both curved
(circular) and straight (extrusion-line) edges, giving a clear discrimination
signal.

Non-destructive: builds its own part, never touches the user's open documents.

Usage:  .venv-py310\Scripts\python spikes\v0_16\_seatcheck_arun_curve.py
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from spike_earlybind_persist import connect_running_sw  # noqa: E402
from ai_sw_bridge.brep.interrogator import (  # noqa: E402
    _read_curve_mid_and_arc,
    _read_curve_params,
    _walk_edges,
)

SW_DEFAULT_TEMPLATE_PART = 8
RADIUS_M = 0.010  # 10 mm
DEPTH_M = 0.020  # 20 mm


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_cylinder(sw: Any) -> Any:
    """Create a cylinder part (circle on Front Plane + blind extrude)."""
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return None

    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        sw.CloseDoc(_title(doc))
        return None

    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCircleByRadius(0.0, 0.0, 0.0, RADIUS_M)
    sk.InsertSketch(True)

    feat = doc.FeatureManager.FeatureExtrusion2(
        True, False, False, 0, 0, DEPTH_M, 0.0,
        False, False, False, False,
        0.0, 0.0, False, False, False, False,
        True, True, True, 0, 0.0, False,
    )
    if feat is None:
        sw.CloseDoc(_title(doc))
        return None
    return doc


def _classify_edge(start: tuple, end: tuple, length: float, source: str) -> str:
    """Classify an edge as straight or curved based on length/chord ratio."""
    chord = math.dist(start, end)
    if chord < 1e-9:
        return "closed-curve" if length > 1e-9 else "degenerate"
    ratio = length / chord if chord > 0 else 0.0
    if abs(ratio - 1.0) < 0.01:
        return "straight"
    return "curved"


def run() -> dict[str, Any]:
    result: dict[str, Any] = {}

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    doc = _build_cylinder(sw)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "cylinder build failed"}
    result["part"] = "cylinder (r=10mm, d=20mm)"

    # --- 1. Full pipeline via _walk_edges -----------------------------------
    edges = _walk_edges(doc, capture=False)
    result["total_edges"] = len(edges)

    edge_report: list[dict[str, Any]] = []
    curve_on_curved = 0
    curve_on_straight = 0
    for be in edges:
        cls = _classify_edge(be.start, be.end, be.length, be.curve_mid_source)
        edge_report.append({
            "idx": be.edge_idx,
            "body": be.body_id,
            "class": cls,
            "source": be.curve_mid_source,
            "length": round(be.length, 6),
            "chord": round(math.dist(be.start, be.end), 6),
            "midpoint": tuple(round(v, 6) for v in be.midpoint),
        })
        if be.curve_mid_source == "curve":
            if cls == "curved":
                curve_on_curved += 1
            else:
                curve_on_straight += 1

    result["edges"] = edge_report
    result["curve_source_on_curved_edges"] = curve_on_curved
    result["curve_source_on_straight_edges"] = curve_on_straight

    # --- 2. Direct API probe on first edge ----------------------------------
    direct_probe: dict[str, Any] = {}
    try:
        bodies = doc.GetBodies2(0, True)
        if bodies:
            raw_edges = bodies[0].GetEdges
            if callable(raw_edges):
                raw_edges = raw_edges()
            if raw_edges:
                e0 = raw_edges[0]
                cp = _read_curve_params(e0)
                direct_probe["GetCurveParams2"] = (
                    [round(v, 6) for v in cp] if cp else None
                )
                if cp:
                    cma = _read_curve_mid_and_arc(
                        e0, (cp[0], cp[1], cp[2]), (cp[3], cp[4], cp[5]),
                    )
                    if cma is not None:
                        mid, arc, src = cma
                        direct_probe["curve_mid_and_arc"] = {
                            "midpoint": tuple(round(v, 6) for v in mid),
                            "arc_length": round(arc, 6),
                            "source": src,
                        }
                    else:
                        direct_probe["curve_mid_and_arc"] = None
    except Exception as e:
        direct_probe["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    result["direct_probe"] = direct_probe

    # --- Verdict ------------------------------------------------------------
    has_curved_with_curve_source = any(
        e["class"] in ("curved", "closed-curve") and e["source"] == "curve"
        for e in edge_report
    )

    if has_curved_with_curve_source:
        result["overall"] = "PASS"
        result["verdict_detail"] = (
            f"curved edges return source='curve' ({curve_on_curved} edges); "
            f"straight edges also return source='curve' ({curve_on_straight} edges) "
            f"— correct: arc length = chord length for lines"
        )
    elif len(edges) > 0:
        result["overall"] = "PARTIAL"
        result["verdict_detail"] = (
            f"{len(edges)} edges probed but none returned source='curve'; "
            "all fell back to chord. Check IEdge.GetLength / ICurve.Evaluate."
        )
    else:
        result["overall"] = "FAIL"
        result["verdict_detail"] = "no edges found on the cylinder body"

    sw.CloseDoc(_title(doc))
    result["cleanup"] = "doc closed"
    return result


if __name__ == "__main__":
    report = run()
    out = Path(__file__).parent / "_results" / "arun_curve.json"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(json.dumps(report, indent=2, default=str))
    print(f"\nReport written to {out}")
