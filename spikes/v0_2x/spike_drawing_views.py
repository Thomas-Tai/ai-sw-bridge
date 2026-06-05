"""Wave-16 Slice 2: Drawing view creation characterization.

Build a small assembly, create a drawing, try inserting standard views
via CreateDrawViewFromModelView3. Characterize the API surface.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

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
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_views.json"
)

results: dict[str, Any] = {
    "spike": "w16_drawing_views",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "characterization": {},
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
    print("Wave-16 Slice 2: Drawing view creation characterization")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # Close all docs
    try:
        for d in (sw.GetDocuments() or []):
            try:
                d.CloseDoc
            except Exception:
                pass
    except Exception:
        pass

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # Build two simple parts
    print("\n--- Building parts ---")
    PART_A = str(_tmp / f"w16_views_{_ts}_a.SLDPRT")
    PART_B = str(_tmp / f"w16_views_{_ts}_b.SLDPRT")

    for label, path, w in [("a", PART_A, 40.0), ("b", PART_B, 30.0)]:
        spec = {
            "schema_version": 1,
            "name": f"View{label.upper()}",
            "features": [
                {"type": "sketch_rectangle_on_plane", "name": "SK",
                 "plane": "Front", "width": w, "height": 20.0},
                {"type": "boss_extrude_blind", "name": "EX",
                 "sketch": "SK", "depth": 10.0},
            ],
        }
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
        gate(f"build_{label}", r.ok and os.path.isfile(path), f"ok={r.ok}")

    if not (os.path.isfile(PART_A) and os.path.isfile(PART_B)):
        save_results()
        return "WALL"

    # Build assembly
    print("\n--- Building assembly ---")
    from ai_sw_bridge.mutate import (
        sw_propose_assembly, sw_dry_run_assembly, sw_commit_assembly,
    )

    ASM_PATH = str(_tmp / f"w16_views_{_ts}.SLDASM")
    asm_spec = {
        "kind": "assembly",
        "name": "view_test",
        "components": [
            {"id": "a", "part": PART_A, "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": PART_B, "transform": {"xyz_mm": [0, 0, 15]}},
        ],
        "mates": [
            {
                "type": "coincident",
                "alignment": "aligned",
                "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
                "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
            },
        ],
    }

    p = sw_propose_assembly(asm_spec)
    d = sw_dry_run_assembly(p["proposal_id"])
    c = sw_commit_assembly(p["proposal_id"], ASM_PATH)
    gate("assembly_commit", c.get("ok", False),
         f"mates={c.get('mate_count')}")

    if not c.get("ok"):
        save_results()
        return "WALL"

    # Close all docs for clean drawing creation
    try:
        for doc in (sw.GetDocuments() or []):
            try:
                doc.CloseDoc
            except Exception:
                pass
    except Exception:
        pass

    # Create drawing
    print("\n--- Creating drawing ---")
    import glob
    drwdots = glob.glob(
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT"
    )
    if not drwdots:
        drwdots = glob.glob(
            r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot"
        )
    template = drwdots[0] if drwdots else None

    if template is None:
        gate("drawing_template", False, "no .drwdot found")
        save_results()
        return "WALL"

    # Open the assembly first (needed for view creation)
    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)

    # Create drawing
    doc_raw = sw.NewDocument(template, 0, 0.420, 0.297)  # A3 landscape
    gate("drawing_create", doc_raw is not None,
         f"type={type(doc_raw).__name__ if doc_raw else None}")

    if doc_raw is None:
        save_results()
        return "WALL"

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
        gate("drawing_qi", drawing_doc is not None,
             f"type={type(drawing_doc).__name__}")

        # Check initial sheet/views
        sheets = drawing_doc.GetSheetNames()
        gate("initial_sheets", sheets is not None and len(sheets) > 0,
             f"sheets={list(sheets) if sheets else []}")

        # --- Characterize view creation ---
        print("\n--- View creation characterization ---")
        model_path = ASM_PATH

        # View names to try
        view_names = ["*Front", "*Top", "*Right", "*Isometric"]
        created_views = []

        for i, view_name in enumerate(view_names):
            x = 0.1 + i * 0.12
            y = 0.15
            try:
                view = drawing_doc.CreateDrawViewFromModelView3(
                    model_path, view_name, x, y, 0.0
                )
                view_ok = view is not None and not isinstance(view, int)
                gate(f"view_{view_name.lstrip('*')}", view_ok,
                     f"type={type(view).__name__ if view else None}")
                if view_ok:
                    created_views.append(view_name)
            except Exception as e:
                gate(f"view_{view_name.lstrip('*')}", False,
                     f"raised: {str(e)[:100]}")

        results["characterization"]["model_path"] = model_path
        results["characterization"]["created_views"] = created_views
        results["characterization"]["api_method"] = (
            "CreateDrawViewFromModelView3"
        )

        # Check total view count
        try:
            # GetFirstView returns the first view on the sheet
            first_view = drawing_doc.GetFirstView()
            if first_view:
                ft = typed(first_view, "IView", module=mod)
                view_count = 0
                v = ft
                while v is not None:
                    view_count += 1
                    try:
                        next_v = v.GetNextView()
                        v = typed(next_v, "IView", module=mod) if next_v else None
                    except Exception:
                        break
                gate("view_count", view_count > 0,
                     f"count={view_count}")
                results["characterization"]["view_count"] = view_count
            else:
                gate("view_count", False, "GetFirstView returned None")
        except Exception as e:
            gate("view_count", False, f"raised: {str(e)[:100]}")

        # Save the drawing
        print("\n--- Save drawing ---")
        DRW_PATH = str(_tmp / f"w16_views_{_ts}.SLDDRW")
        try:
            doc_raw.SaveAs3(DRW_PATH, 0, 2)
            gate("drawing_save", os.path.isfile(DRW_PATH),
                 f"path={DRW_PATH}")
        except Exception as e:
            gate("drawing_save", False, f"raised: {str(e)[:100]}")

        # Overall
        all_pass = (
            len(created_views) > 0
            and os.path.isfile(DRW_PATH)
        )
        gate("OVERALL", all_pass,
             f"views_created={len(created_views)}, saved={os.path.isfile(DRW_PATH)}")

        return "GREEN" if all_pass else "PARTIAL"

    finally:
        # Close drawing
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
        # Close assembly
        try:
            asm_name = Path(ASM_PATH).stem
            for suffix in (".SLDASM", ".sldasm"):
                sw.CloseDoc(asm_name + suffix)
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
        verdict = "WALL"
    finally:
        results["verdict"] = verdict
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict == "GREEN" else 1)
