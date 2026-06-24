"""Wave-17 Slice 1: Drawing dimension insertion de-risk.

HARD GO/NO-GO checkpoint. Characterizes whether model dimensions can be
inserted onto drawing views out-of-process.

Precondition: model must have dimensions. Even no_dim=True parts have
feature dimensions (extrusion depth, sketch width) in the feature tree.

Routes tested:
  A. IView.InsertModelAnnotations3 (view-level)
  B. ISheet.InsertModelAnnotations3 (sheet-level)
  C. IDrawingDoc.InsertModelAnnotations3 (drawing-level)

Liveness gate: dim count POST > PRE and > 0.
Insert-returns-clean-but-zero-dims = NO-GO.

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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_dims.json"

results: dict[str, Any] = {
    "spike": "w17_drawing_dims",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "routes": {},
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


def count_annotations(view: Any, label: str) -> int:
    """Try multiple methods to count annotations/dimensions on a view."""
    count = -1

    # Method 1: GetAnnotationCount
    try:
        c = view.GetAnnotationCount()
        if isinstance(c, tuple):
            c = c[0]
        gate(f"{label}_annotation_count", True, f"count={c}")
        count = c
    except Exception as e:
        gate(f"{label}_annotation_count", False, f"raised: {str(e)[:80]}")

    # Method 2: GetDisplayDimensions
    try:
        dims = view.GetDisplayDimensions()
        dim_count = len(dims) if dims else 0
        gate(f"{label}_display_dims", True, f"count={dim_count}")
        if count < 0:
            count = dim_count
    except Exception as e:
        gate(f"{label}_display_dims", False, f"raised: {str(e)[:80]}")

    # Method 3: GetDimensionCount
    try:
        dc = view.GetDimensionCount()
        if isinstance(dc, tuple):
            dc = dc[0]
        gate(f"{label}_dimension_count", True, f"count={dc}")
        if count < 0:
            count = dc
    except Exception as e:
        gate(f"{label}_dimension_count", False, f"raised: {str(e)[:80]}")

    # Method 4: GetAnnotations
    try:
        annots = view.GetAnnotations()
        ann_count = len(annots) if annots else 0
        gate(f"{label}_get_annotations", True, f"count={ann_count}")
        if count < 0:
            count = ann_count
    except Exception as e:
        gate(f"{label}_get_annotations", False, f"raised: {str(e)[:80]}")

    return count


def run() -> str:
    print("=" * 70)
    print("Wave-17 Slice 1: Drawing dimension insertion de-risk")
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
                d.CloseDoc
            except Exception:
                pass
    except Exception:
        pass

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # Build a part WITH dimensions (feature dims exist even in no_dim mode)
    print("\n--- Building dimensioned part ---")
    PART_PATH = str(_tmp / f"w17_dims_{_ts}_box.SLDPRT")
    PART_SPEC = {
        "schema_version": 1,
        "name": "DimBox",
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

    # Build with no_dim=True (feature dims still exist in tree)
    r = part_build(PART_SPEC, save_as=PART_PATH, save_format="current", no_dim=True)
    gate("build_part", r.ok and os.path.isfile(PART_PATH), f"ok={r.ok}")

    if not os.path.isfile(PART_PATH):
        save_results()
        return "WALL"

    # Create drawing + view
    print("\n--- Creating drawing with view ---")
    drwdots = glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT")
    if not drwdots:
        gate("template", False, "no .drwdot found")
        save_results()
        return "WALL"

    template = drwdots[0]

    # Open the part first
    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)

    doc_raw = sw.NewDocument(template, 0, 0.420, 0.297)
    gate("drawing_create", doc_raw is not None)

    if doc_raw is None:
        save_results()
        return "WALL"

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)

        # Create a front view
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

        # --- Pre-insert dim count ---
        print("\n--- Pre-insert annotation count ---")
        pre_count = count_annotations(view, "pre")
        results["pre_count"] = pre_count

        # Also check the sheet
        try:
            sheet_raw = drawing_doc.GetCurrentSheet()
            sheet = typed_qi(sheet_raw, "ISheet", module=mod) if sheet_raw else None
        except Exception:
            sheet = None

        # --- Route A: IView.InsertModelAnnotations3 ---
        print("\n--- Route A: IView.InsertModelAnnotations3 ---")
        route_a: dict[str, Any] = {"status": "NOT_TRIED"}
        try:
            # Signature: InsertModelAnnotations3(
            #   SourceType, AnnotationType, bDownloadFromModel,
            #   bInstanceOnly, bUseSheetScale, nViewType)
            # Try various parameter combos
            for params_label, params in [
                ("default", (0, 0, True, True, True, 0)),
                ("all_types", (0, -1, True, False, True, 0)),
                ("dims_only_1", (0, 1, True, False, True, 0)),
                ("dims_only_2", (1, 1, True, False, True, 0)),
            ]:
                try:
                    result = view.InsertModelAnnotations3(*params)
                    gate(
                        f"routeA_{params_label}",
                        True,
                        f"result={result}, type={type(result).__name__}",
                    )
                    route_a[params_label] = {"result": str(result)[:100]}

                    # Count after
                    post = count_annotations(view, f"postA_{params_label}")
                    route_a[f"{params_label}_post_count"] = post
                    if post > pre_count and post > 0:
                        route_a["status"] = "GO"
                        route_a["working_params"] = params_label
                        break
                except Exception as e:
                    gate(f"routeA_{params_label}", False, f"raised: {str(e)[:80]}")
                    route_a[params_label] = {"error": str(e)[:200]}
        except Exception as e:
            route_a["error"] = str(e)[:200]

        results["routes"]["A_view"] = route_a

        # --- Route B: ISheet.InsertModelAnnotations3 ---
        if route_a.get("status") != "GO" and sheet:
            print("\n--- Route B: ISheet.InsertModelAnnotations3 ---")
            route_b: dict[str, Any] = {"status": "NOT_TRIED"}
            try:
                for params_label, params in [
                    ("default", (0, 0, True, True, True, 0)),
                    ("all_types", (0, -1, True, False, True, 0)),
                    ("dims_only", (0, 1, True, False, True, 0)),
                ]:
                    try:
                        result = sheet.InsertModelAnnotations3(*params)
                        gate(f"routeB_{params_label}", True, f"result={result}")
                        route_b[params_label] = {"result": str(result)[:100]}

                        post = count_annotations(view, f"postB_{params_label}")
                        route_b[f"{params_label}_post_count"] = post
                        if post > pre_count and post > 0:
                            route_b["status"] = "GO"
                            route_b["working_params"] = params_label
                            break
                    except Exception as e:
                        gate(f"routeB_{params_label}", False, f"raised: {str(e)[:80]}")
                        route_b[params_label] = {"error": str(e)[:200]}
            except Exception as e:
                route_b["error"] = str(e)[:200]
            results["routes"]["B_sheet"] = route_b

        # --- Route C: IDrawingDoc.InsertModelAnnotations3 ---
        if route_a.get("status") != "GO":
            print("\n--- Route C: IDrawingDoc.InsertModelAnnotations3 ---")
            route_c: dict[str, Any] = {"status": "NOT_TRIED"}
            try:
                for params_label, params in [
                    ("default", (0, 0, True, True, True, 0)),
                    ("all_types", (0, -1, True, False, True, 0)),
                    ("dims_only", (0, 1, True, False, True, 0)),
                ]:
                    try:
                        result = drawing_doc.InsertModelAnnotations3(*params)
                        gate(f"routeC_{params_label}", True, f"result={result}")
                        route_c[params_label] = {"result": str(result)[:100]}

                        post = count_annotations(view, f"postC_{params_label}")
                        route_c[f"{params_label}_post_count"] = post
                        if post > pre_count and post > 0:
                            route_c["status"] = "GO"
                            route_c["working_params"] = params_label
                            break
                    except Exception as e:
                        gate(f"routeC_{params_label}", False, f"raised: {str(e)[:80]}")
                        route_c[params_label] = {"error": str(e)[:200]}
            except Exception as e:
                route_c["error"] = str(e)[:200]
            results["routes"]["C_drawing"] = route_c

        # --- Final post count ---
        print("\n--- Final post-insert annotation count ---")
        final_count = count_annotations(view, "final")
        results["final_count"] = final_count

        # --- Verdict ---
        print("\n--- Verdict ---")
        any_go = (
            route_a.get("status") == "GO"
            or results.get("routes", {}).get("B_sheet", {}).get("status") == "GO"
            or results.get("routes", {}).get("C_drawing", {}).get("status") == "GO"
            or (final_count > pre_count and final_count > 0)
        )

        if any_go:
            verdict = "GO"
            gate("OVERALL_GO", True, f"pre={pre_count}, final={final_count}")
        else:
            verdict = "NO-GO"
            gate(
                "OVERALL_NO_GO",
                False,
                f"pre={pre_count}, final={final_count} "
                f"(insert-but-zero or all routes wall)",
            )

        results["verdict"] = verdict
        return verdict

    finally:
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
        try:
            part_name = Path(PART_PATH).stem
            for suffix in (".SLDPRT", ".sldprt"):
                sw.CloseDoc(part_name + suffix)
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
