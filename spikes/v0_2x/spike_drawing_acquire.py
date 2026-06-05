"""Wave-16 Slice 1: Drawing doc acquisition de-risk.

HARD GO/NO-GO checkpoint. Characterizes whether IDrawingDoc is acquirable
out-of-process via late-bound COM on SW 2024 SP1.

Routes tested:
  1. Template discovery (glob .drwdot + GetUserPreferenceStringValue)
  2. Route A: typed QI — NewDocument(drwdot) → typed_qi(IDrawingDoc)
  3. Route B: late-bind — dynamic.Dispatch on the doc
  4. Route C: typelib scan for alternate creation methods
  5. Liveness gate: call IDrawingDoc members (GetSheetNames, GetFirstView)

If ALL routes wall → NO-GO. Characterize + stop.
If ANY route works → GO. Record working path.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_acquire.json"
)

results: dict[str, Any] = {
    "spike": "w16_drawing_acquire",
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


def run() -> str:
    print("=" * 70)
    print("Wave-16 Slice 1: Drawing doc acquisition de-risk")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # --- Template discovery ---
    print("\n--- Template discovery ---")

    # Glob for .drwdot
    drwdot_patterns = [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\**\*.drwdot",
    ]
    drwdots: list[str] = []
    for pat in drwdot_patterns:
        drwdots.extend(glob.glob(pat, recursive=True))
    drwdots = list(set(drwdots))

    gate("drwdot_found", len(drwdots) > 0,
         f"found {len(drwdots)}: {drwdots}")

    # Try GetUserPreferenceStringValue for default drawing template
    # swDefaultTemplateDrawing = 20 (from SW API docs)
    default_template = None
    try:
        default_template = sw.GetUserPreferenceStringValue(20)
        gate("default_template_string", bool(default_template),
             f"value={default_template!r}")
    except Exception as e:
        gate("default_template_string", False, f"raised: {e}")

    if default_template and os.path.isfile(default_template):
        drwdots.append(default_template)
        drwdots = list(set(drwdots))

    template_path = drwdots[0] if drwdots else None
    results["routes"]["template"] = {
        "glob_matches": drwdots,
        "default_template": default_template,
        "selected": template_path,
    }

    if template_path is None:
        gate("template_available", False,
             "NO .drwdot template found — cannot proceed")
        save_results()
        results["verdict"] = "NO-GO"
        return "NO-GO"

    gate("template_available", True, f"using {template_path}")

    # --- Route A: NewDocument + typed QI ---
    print("\n--- Route A: typed QI ---")
    route_a: dict[str, Any] = {"status": "NOT_TRIED"}
    try:
        # Close all docs first
        try:
            docs = sw.GetDocuments()
            if docs:
                for d in docs:
                    try:
                        d.CloseDoc
                    except Exception:
                        pass
        except Exception:
            pass

        tsw = typed(sw, "ISldWorks", module=mod)
        doc_raw = tsw.NewDocument(template_path, 0, 0.210, 0.297)
        # A3 paper: 210mm x 297mm (in metres)

        doc_ok = doc_raw is not None and not isinstance(doc_raw, int)
        gate("routeA_newdocument", doc_ok,
             f"type={type(doc_raw).__name__ if doc_raw else None}")

        if doc_ok:
            route_a["newdocument"] = "OK"
            route_a["doc_type"] = type(doc_raw).__name__

            # Check document type
            try:
                doc_type = doc_raw.GetType()
                route_a["gettype"] = doc_type
                gate("routeA_gettype", doc_type == 3,
                     f"GetType()={doc_type} (expect 3=swDocDRAWING)")
            except Exception as e:
                route_a["gettype_error"] = str(e)

            # typed QI to IDrawingDoc
            try:
                drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
                qi_ok = drawing_doc is not None
                gate("routeA_qi_idrawingdoc", qi_ok,
                     f"type={type(drawing_doc).__name__}")
                route_a["qi_status"] = "OK" if qi_ok else "None"
            except Exception as e:
                gate("routeA_qi_idrawingdoc", False, f"raised: {e}")
                route_a["qi_error"] = str(e)[:200]

            # Close the doc
            try:
                t = doc_raw.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
        else:
            route_a["newdocument"] = "FAILED"

    except Exception as e:
        gate("routeA", False, f"raised: {e}")
        route_a["error"] = str(e)[:200]

    results["routes"]["A_typed_qi"] = route_a

    # --- Route B: late-bind (dynamic) ---
    print("\n--- Route B: late-bind ---")
    route_b: dict[str, Any] = {"status": "NOT_TRIED"}
    try:
        # Close all docs
        try:
            for d in (sw.GetDocuments() or []):
                try:
                    d.CloseDoc
                except Exception:
                    pass
        except Exception:
            pass

        doc_raw2 = sw.NewDocument(template_path, 0, 0.210, 0.297)
        doc2_ok = doc_raw2 is not None and not isinstance(doc_raw2, int)
        gate("routeB_newdocument", doc2_ok,
             f"type={type(doc_raw2).__name__ if doc_raw2 else None}")

        if doc2_ok:
            route_b["newdocument"] = "OK"

            # Try dynamic dispatch
            try:
                from win32com.client import dynamic
                drawing_doc2 = dynamic.Dispatch(doc_raw2)
                route_b["dynamic_dispatch"] = type(drawing_doc2).__name__
                gate("routeB_dynamic_dispatch", True,
                     f"type={type(drawing_doc2).__name__}")
            except Exception as e:
                gate("routeB_dynamic_dispatch", False, f"raised: {e}")
                route_b["dynamic_error"] = str(e)[:200]

            # Try closing
            try:
                t = doc_raw2.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
        else:
            route_b["newdocument"] = "FAILED"

    except Exception as e:
        route_b["error"] = str(e)[:200]

    results["routes"]["B_late_bind"] = route_b

    # --- Route C: typelib scan for alternate creation methods ---
    print("\n--- Route C: typelib scan ---")
    route_c: dict[str, Any] = {"status": "NOT_TRIED"}
    try:
        tsw_c = typed(sw, "ISldWorks", module=mod)
        # Check for drawing-related methods on ISldWorks
        drawing_methods = []
        for name in dir(sw):
            lower = name.lower()
            if any(kw in lower for kw in ["draw", "newdraw", "createdraw"]):
                drawing_methods.append(name)

        route_c["drawing_related_methods"] = drawing_methods
        gate("routeC_typelib_scan", len(drawing_methods) > 0,
             f"found: {drawing_methods}")

        # Try any promising methods
        for method_name in drawing_methods:
            if "new" in method_name.lower() or "create" in method_name.lower():
                try:
                    val = getattr(sw, method_name)
                    route_c[method_name] = {
                        "type": type(val).__name__,
                        "callable": callable(val)
                        and not isinstance(val, (int, float, bool, str)),
                    }
                except Exception as e:
                    route_c[method_name] = {"error": str(e)[:100]}

    except Exception as e:
        route_c["error"] = str(e)[:200]

    results["routes"]["C_typelib_scan"] = route_c

    # --- Liveness gate: reopen a drawing doc and call IDrawingDoc members ---
    print("\n--- Liveness gate ---")
    liveness: dict[str, Any] = {"status": "NOT_TRIED"}
    try:
        # Close all docs
        try:
            for d in (sw.GetDocuments() or []):
                try:
                    d.CloseDoc
                except Exception:
                    pass
        except Exception:
            pass

        doc_raw3 = sw.NewDocument(template_path, 0, 0.210, 0.297)
        if doc_raw3 and not isinstance(doc_raw3, int):
            liveness["newdocument"] = "OK"

            # Try GetSheetNames
            try:
                sheets = doc_raw3.GetSheetNames()
                liveness["getsheetnames"] = (
                    list(sheets) if sheets else []
                )
                gate("liveness_getsheetnames", True,
                     f"sheets={liveness['getsheetnames']}")
            except Exception as e:
                gate("liveness_getsheetnames", False, f"raised: {e}")
                liveness["getsheetnames_error"] = str(e)[:200]

            # Try GetFirstView
            try:
                view = doc_raw3.GetFirstView()
                liveness["getfirstview"] = (
                    type(view).__name__ if view else None
                )
                gate("liveness_getfirstview", view is not None,
                     f"type={liveness['getfirstview']}")
            except Exception as e:
                gate("liveness_getfirstview", False, f"raised: {e}")
                liveness["getfirstview_error"] = str(e)[:200]

            # Try GetCurrentSheet
            try:
                sheet = doc_raw3.GetCurrentSheet()
                liveness["getcurrentsheet"] = (
                    type(sheet).__name__ if sheet else None
                )
                gate("liveness_getcurrentsheet", sheet is not None,
                     f"type={liveness['getcurrentsheet']}")
            except Exception as e:
                gate("liveness_getcurrentsheet", False, f"raised: {e}")
                liveness["getcurrentsheet_error"] = str(e)[:200]

            # Try typed QI + member call
            try:
                drawing_doc3 = typed_qi(
                    doc_raw3, "IDrawingDoc", module=mod
                )
                if drawing_doc3:
                    sheets2 = drawing_doc3.GetSheetNames()
                    liveness["typed_getsheetnames"] = (
                        list(sheets2) if sheets2 else []
                    )
                    gate("liveness_typed_members", True,
                         f"sheets={liveness['typed_getsheetnames']}")
                else:
                    gate("liveness_typed_members", False, "QI returned None")
            except Exception as e:
                gate("liveness_typed_members", False, f"raised: {e}")
                liveness["typed_error"] = str(e)[:200]

            # Close
            try:
                t = doc_raw3.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
        else:
            gate("liveness_newdocument", False, "NewDocument returned None")

    except Exception as e:
        liveness["error"] = str(e)[:200]

    results["routes"]["liveness"] = liveness

    # --- Overall verdict ---
    print("\n--- Verdict ---")
    any_go = (
        route_a.get("qi_status") == "OK"
        or route_b.get("dynamic_dispatch") is not None
        or liveness.get("getsheetnames") is not None
    )

    if any_go:
        verdict = "GO"
        gate("OVERALL_GO", True, "at least one route acquires IDrawingDoc")
    else:
        verdict = "NO-GO"
        gate("OVERALL_NO_GO", False,
             "all routes failed — IDrawingDoc not acquirable out-of-process")

    results["verdict"] = verdict
    return verdict


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
