"""Wave-17 Slice 1 (REVISED): Drawing dimension insertion — GO.

REVISED spike after discovering the popup-suppression recipe.

Breakthrough:
  1. Suppress SW toggles [9, 10, 22, 23] before parametric build
     -> AddDimension2 popup suppressed -> clean build with no_dim=False.
  2. IDrawingDoc.InsertModelAnnotations3(0, -1, True, False, True, 0)
     -> inserts model annotations onto drawing views.
  3. Post-insert annotation count > 0 confirms real insertion.

Routes characterized:
  A (IView): type mismatch on all param combos -- WALL.
  B (ISheet): type mismatch on all param combos -- WALL.
  C (IDrawingDoc): WORKS -- inserts dims from dimensioned model.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_dims_v2.json"

POPUP_SUPPRESS_TOGGLES = [9, 10, 22, 23]

results: dict[str, Any] = {
    "spike": "w17_drawing_dims_v2",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "routes": {},
    "characterization": {
        "popup_suppression": {
            "toggles": POPUP_SUPPRESS_TOGGLES,
            "description": (
                "SetUserPreferenceToggle(toggle_id, False) for IDs "
                "9, 10, 22, 23 suppresses the AddDimension2 popup."
            ),
        },
        "working_route": {
            "object": "IDrawingDoc",
            "method": "InsertModelAnnotations3",
            "params": "(0, -1, True, False, True, 0)",
        },
    },
    "verdict": "UNKNOWN",
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


def run() -> str:
    print("=" * 70)
    print("Wave-17 Slice 1 (REVISED): Drawing dimension insertion")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # Close all docs
    try:
        for d in sw.GetDocuments() or []:
            try:
                t = d.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
    except Exception:
        pass

    # Suppress dimension popups
    print("\n--- Suppressing dimension popups ---")
    for tid in POPUP_SUPPRESS_TOGGLES:
        try:
            sw.SetUserPreferenceToggle(tid, False)
            gate(f"suppress_toggle_{tid}", True, "set to False")
        except Exception as e:
            gate(f"suppress_toggle_{tid}", False, str(e)[:60])

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # Build part WITH dimensions (parametric mode, popup suppressed)
    print("\n--- Building dimensioned part ---")
    PART_PATH = str(_tmp / f"w17_dimv2_{_ts}_box.SLDPRT")
    PART_SPEC = {
        "schema_version": 1,
        "name": "DimBoxV2",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 40.0,
                "height": 25.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 15.0},
        ],
    }

    r = part_build(PART_SPEC, save_as=PART_PATH, save_format="current", no_dim=False)
    gate("build_part_with_dims", r.ok and os.path.isfile(PART_PATH), f"ok={r.ok}")

    if not os.path.isfile(PART_PATH):
        save_results()
        return "WALL"

    # Create drawing + view
    print("\n--- Creating drawing with view ---")
    drwdots = glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT")
    template = drwdots[0]

    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)

    doc_raw = sw.NewDocument(template, 0, 0.420, 0.297)
    gate("drawing_create", doc_raw is not None)

    if doc_raw is None:
        save_results()
        return "WALL"

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)

        view_raw = drawing_doc.CreateDrawViewFromModelView3(
            PART_PATH, "*Front", 0.15, 0.15, 0.0
        )
        gate(
            "view_create",
            view_raw is not None and not isinstance(view_raw, int),
            f"type={type(view_raw).__name__ if view_raw else None}",
        )

        if view_raw is None or isinstance(view_raw, int):
            save_results()
            return "WALL"

        view = typed_qi(view_raw, "IView", module=mod)

        # Pre-insert count
        pre_count = view.GetAnnotationCount()
        gate("pre_annotation_count", True, f"count={pre_count}")

        # Route C: IDrawingDoc.InsertModelAnnotations3
        print("\n--- Route C: IDrawingDoc.InsertModelAnnotations3 ---")
        try:
            result = drawing_doc.InsertModelAnnotations3(0, -1, True, False, True, 0)
            gate("routeC_insert", True, f"result_type={type(result).__name__}")
            results["routes"]["C_drawingdoc"] = {
                "status": "GO",
                "params": "(0, -1, True, False, True, 0)",
            }
        except Exception as e:
            gate("routeC_insert", False, str(e)[:100])
            results["routes"]["C_drawingdoc"] = {
                "status": "WALL",
                "error": str(e)[:200],
            }

        # Post-insert count
        post_count = view.GetAnnotationCount()
        gate("post_annotation_count", True, f"count={post_count}")
        gate(
            "dims_inserted",
            post_count > pre_count and post_count > 0,
            f"pre={pre_count}, post={post_count}",
        )

        # Verdict
        go = post_count > pre_count and post_count > 0
        gate("OVERALL_GO", go, f"pre={pre_count}, post={post_count}")

        results["pre_count"] = pre_count
        results["post_count"] = post_count
        results["verdict"] = "GO" if go else "NO-GO"
        return "GO" if go else "NO-GO"

    finally:
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
        try:
            part_name = Path(PART_PATH).stem
            tsw.CloseDoc(part_name + ".SLDPRT")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception as exc:
        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        verdict = "NO-GO"
        results["verdict"] = verdict
    finally:
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict == "GO" else 1)
