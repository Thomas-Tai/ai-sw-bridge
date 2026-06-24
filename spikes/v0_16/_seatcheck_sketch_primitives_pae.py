"""Seat-check (PAE) — drive the SHIPPED P1.7s handlers live on SW 2024.

Unlike the discovery spikes (which probed raw ISketchManager calls), this runs
the actual builder._build_sketch_* handlers — the code that ships — against a
fresh blank Part, exactly as build() would. For each of the seven primitives it
asserts the handler returns a BuiltFeature whose sketch feature (a) exists by
name in the tree and (b) incremented the feature count. PASS = all seven
materialise and are independently selectable by their assigned names.

Non-destructive: own blank Part via NewDocument, never saves, closes own doc.
Run with PYTHONPATH=<worktree>/src so the worktree handlers load.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge.spec import builder  # noqa: E402
from ai_sw_bridge.spec._build_context import BuildContext  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8

# The example-spec gallery (examples/sketch_primitives/spec.json), one per type.
FEATURES: list[dict[str, Any]] = [
    {
        "type": "sketch_line",
        "name": "SK_Line",
        "plane": "Front",
        "start": {"x": 0.0, "y": 0.0},
        "end": {"x": 20.0, "y": 20.0},
    },
    {
        "type": "sketch_arc",
        "name": "SK_Arc",
        "plane": "Front",
        "center": {"x": 30.0, "y": 0.0},
        "start": {"x": 40.0, "y": 0.0},
        "end": {"x": 30.0, "y": 10.0},
        "direction": "ccw",
    },
    {
        "type": "sketch_spline",
        "name": "SK_Spline",
        "plane": "Front",
        "points": [
            {"x": 0.0, "y": 30.0},
            {"x": 5.0, "y": 35.0},
            {"x": 10.0, "y": 32.0},
            {"x": 15.0, "y": 38.0},
            {"x": 20.0, "y": 30.0},
        ],
        "closed": False,
    },
    {
        "type": "sketch_slot",
        "name": "SK_Slot",
        "plane": "Front",
        "center": {"x": 30.0, "y": 30.0},
        "width": 6.0,
        "length": 20.0,
        "slot_type": "arc",
        "angle_deg": 0.0,
    },
    {
        "type": "sketch_polygon",
        "name": "SK_Polygon",
        "plane": "Front",
        "center": {"x": 50.0, "y": 30.0},
        "sides": 6,
        "radius": 8.0,
        "inscribed": True,
        "angle_deg": 0.0,
    },
    {
        "type": "sketch_ellipse",
        "name": "SK_Ellipse",
        "plane": "Front",
        "center": {"x": 70.0, "y": 30.0},
        "major_radius": 10.0,
        "minor_radius": 5.0,
        "angle_deg": 0.0,
    },
    {
        "type": "sketch_text",
        "name": "SK_Text",
        "plane": "Front",
        "position": {"x": 0.0, "y": 50.0},
        "content": "ai-sw-bridge",
        "height": 3.0,
        "font": "Arial",
        "angle_deg": 0.0,
    },
]


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _feature_count(doc: Any) -> int:
    gc = doc.GetFeatureCount
    return int(gc() if callable(gc) else gc)


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {"sw_revision": str(sw.RevisionNumber), "primitives": []}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument returned None"}
    title = _title(doc)
    ctx = BuildContext(sw=sw, doc=doc, no_dim=True)
    try:
        for feat in FEATURES:
            rec: dict[str, Any] = {"type": feat["type"], "name": feat["name"]}
            before = _feature_count(doc)
            try:
                bf = builder.HANDLERS[feat["type"]](ctx, feat)
                doc.ForceRebuild3(False)
                after = _feature_count(doc)
                doc.ClearSelection2(True)
                selectable = bool(doc.SelectByID(feat["name"], "SKETCH", 0.0, 0.0, 0.0))
                rec["count_delta"] = after - before
                rec["named_ok"] = bf.sw_object is not None and bf.name == feat["name"]
                rec["selectable_by_name"] = selectable
                rec["overall"] = "PASS" if (after > before and selectable) else "FAIL"
            except Exception as e:  # noqa: BLE001
                rec["error"] = repr(e)
                rec["overall"] = "FAIL"
            report["primitives"].append(rec)
            doc.ClearSelection2(True)
        passes = sum(1 for r in report["primitives"] if r["overall"] == "PASS")
        report["pass_count"] = passes
        report["overall"] = "PASS" if passes == len(FEATURES) else "PARTIAL"
        return report
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "sketch_primitives_pae.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
