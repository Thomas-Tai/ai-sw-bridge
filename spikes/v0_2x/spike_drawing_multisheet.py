"""Wave-23 Slice 1: Drawing multi-sheet de-risk (HARD GO/NO-GO).

Characterises the SOLIDWORKS 2024 SP1 surface needed for one .SLDDRW to
carry multiple sheets, each with its own views:

  1. **Typelib dump** for ``IDrawingDoc.NewSheet*`` arity — probe candidates
     (``NewSheet4`` / ``NewSheet3`` / ``NewSheet2`` / ``NewSheet``) with the
     documented argument counts and record which one returns True out-of-
     process.
  2. **Per-sheet view routing** — ``IDrawingDoc.ActivateSheet(name)`` then
     ``CreateDrawViewFromModelView3``; confirm the view lands on the
     intended sheet by iterating ``ISheet.GetViews()`` / ``GetViewCount``
     per sheet.
  3. **Liveness gates** — ``GetSheetCount`` == N, ``GetSheetNames`` returns
     the names we created, AND each sheet's view count matches the spec.

HARD CHECKPOINT:
  GO    = all gates PASS; recipe is recorded below.
  NO-GO = any of (NewSheet* walls, ActivateSheet ignored, view lands on
          wrong sheet). Stop, DEFERRED.md row, do not brute-force.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_multisheet.json"

results: dict[str, Any] = {
    "spike": "w23_drawing_multisheet",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "verdict": "UNKNOWN",
    "typelib_dump": {},
    "per_sheet_routing": {},
    "recipe": None,
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


def _close_all_docs(sw: Any) -> None:
    try:
        docs = sw.GetDocuments()
        if docs:
            for d in docs:
                try:
                    t = d.GetTitle
                    t = t() if callable(t) else t
                    sw.CloseDoc(t)
                except Exception:
                    pass
    except Exception:
        pass


def _build_test_part(sw: Any, part_path: str) -> bool:
    """Build a tiny part (40x20x10 box) so view creation has something to
    project. Uses the proven W16 shape."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W23SpikeBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 40.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 10.0,
            },
        ],
    }
    r = part_build(spec, save_as=part_path, save_format="current", no_dim=True)
    return bool(r.ok) and os.path.isfile(part_path)


def _dump_newsheet_candidates(drawing_doc: Any, raw_doc: Any) -> dict[str, Any]:
    """Probe IDrawingDoc for NewSheet* variants; record which arities exist
    and which callable signatures work out-of-process.

    Returns a dict keyed by candidate name with {exists, arity, errors}.
    """
    candidates: dict[str, Any] = {}
    for name in ("NewSheet4", "NewSheet3", "NewSheet2", "NewSheet"):
        fn_typed = getattr(drawing_doc, name, None)
        fn_raw = getattr(raw_doc, name, None)
        candidates[name] = {
            "typed_exists": fn_typed is not None and not isinstance(fn_typed, int),
            "typed_callable": callable(fn_typed) if fn_typed is not None else False,
            "raw_exists": fn_raw is not None and not isinstance(fn_raw, int),
            "raw_callable": callable(fn_raw) if fn_raw is not None else False,
        }

    # Probe related surface
    for name in (
        "ActivateSheet",
        "GetSheetCount",
        "GetSheetNames",
        "GetCurrentSheet",
        "DeleteSheet",
    ):
        fn = getattr(drawing_doc, name, None)
        candidates[name] = {
            "exists": fn is not None and not isinstance(fn, int),
            "callable": callable(fn) if fn is not None else False,
        }

    # Discover every *Sheet* attribute on the raw doc (in case the CHM names
    # are wrong or a variant we missed exists)
    try:
        all_raw = [a for a in dir(raw_doc) if "Sheet" in a or "sheet" in a]
    except Exception as e:
        all_raw = [f"<dir failed: {e}>"]
    candidates["raw_sheet_attrs"] = all_raw

    try:
        all_typed = [a for a in dir(drawing_doc) if "Sheet" in a or "sheet" in a]
    except Exception as e:
        all_typed = [f"<dir failed: {e}>"]
    candidates["typed_sheet_attrs"] = all_typed
    return candidates


def _try_newsheet(
    drawing_doc: Any,
    raw_doc: Any,
    sheet_name: str,
    width_m: float,
    height_m: float,
) -> dict[str, Any]:
    """Try each NewSheet* candidate with makepy-authoritative signatures.

    Signatures from the sldworks.tlb gen_py wrapper (NOT from the CHM —
    the CHM order swaps PaperSize/TemplateIn vs the actual IDL):

      NewSheet (Name, PaperSize:I4, TemplateIn:I4, Scale1:R8, Scale2:R8)
               -> LPDISPATCH (an ISheet) -- legacy, does NOT take FirstAngle.
      NewSheet2(+ FirstAngle:BOOL, TemplateName:BSTR, Width:R8, Height:R8)
               -> BOOL
      NewSheet3(+ PropertyViewName:BSTR) -> BOOL
      NewSheet4(+ ZoneLeftMargin, ZoneRightMargin, ZoneTopMargin,
                  ZoneBottomMargin: R8, ZoneRow: I4, ZoneCol: I4) -> BOOL

    PaperSize enum: 8 = swDwgPaperAsize (210x297), 11 = swDwgPaperA3size,
                    0 is INVALID per TLB (it's an enum, not a flag).
    TemplateIn enum: 0 = swDwgTemplateNone, 1 = swDwgTemplateCustom.
    FirstAngle: VARIANT_BOOL (True/False).

    We try NewSheet3 first (the most common documented shape) then fall back.
    """
    attempts: list[dict[str, Any]] = []

    # PaperSize enum values (swDwgPaperSizes_e)
    PAPER_A3 = 11
    PAPER_A4 = 8
    TEMPLATE_NONE = 0
    TEMPLATE_CUSTOM = 1

    paper_size = PAPER_A3 if width_m > 0.3 else PAPER_A4

    for label, doc in (("typed", drawing_doc), ("raw", raw_doc)):
        # --- NewSheet3: 10 args ---
        try:
            ok = doc.NewSheet3(
                sheet_name,
                paper_size,  # PaperSize (I4)
                TEMPLATE_CUSTOM,  # TemplateIn (I4) -- custom size
                1.0,  # Scale1 (R8)
                1.0,  # Scale2 (R8)
                True,  # FirstAngle (BOOL)
                "",  # TemplateName (BSTR)
                width_m,  # Width (R8, metres)
                height_m,  # Height (R8, metres)
                "",  # PropertyViewName (BSTR)
            )
            return {
                "method_used": "NewSheet3",
                "arity": 10,
                "via": label,
                "ok": bool(ok),
                "error": None,
                "signature": (
                    "NewSheet3(Name, PaperSize:I4, TemplateIn:I4, Scale1:R8, "
                    "Scale2:R8, FirstAngle:BOOL, TemplateName:BSTR, "
                    "Width:R8, Height:R8, PropertyViewName:BSTR) -> BOOL"
                ),
            }
        except Exception as e:
            attempts.append(
                {
                    "method": "NewSheet3",
                    "via": label,
                    "arity": 10,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    for label, doc in (("typed", drawing_doc), ("raw", raw_doc)):
        # --- NewSheet2: 9 args ---
        try:
            ok = doc.NewSheet2(
                sheet_name,
                paper_size,
                TEMPLATE_CUSTOM,
                1.0,
                1.0,
                True,
                "",
                width_m,
                height_m,
            )
            return {
                "method_used": "NewSheet2",
                "arity": 9,
                "via": label,
                "ok": bool(ok),
                "error": None,
                "signature": (
                    "NewSheet2(Name, PaperSize:I4, TemplateIn:I4, Scale1:R8, "
                    "Scale2:R8, FirstAngle:BOOL, TemplateName:BSTR, "
                    "Width:R8, Height:R8) -> BOOL"
                ),
            }
        except Exception as e:
            attempts.append(
                {
                    "method": "NewSheet2",
                    "via": label,
                    "arity": 9,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    for label, doc in (("typed", drawing_doc), ("raw", raw_doc)):
        # --- NewSheet4: 16 args (adds zone margins/row/col) ---
        try:
            ok = doc.NewSheet4(
                sheet_name,
                paper_size,
                TEMPLATE_CUSTOM,
                1.0,
                1.0,
                True,
                "",
                width_m,
                height_m,
                "",  # PropertyViewName
                0.0,
                0.0,
                0.0,
                0.0,  # zone margins
                0,
                0,  # zone row/col
            )
            return {
                "method_used": "NewSheet4",
                "arity": 16,
                "via": label,
                "ok": bool(ok),
                "error": None,
                "signature": (
                    "NewSheet4(+ PropertyViewName:BSTR, ZoneL/R/T/B:R8, "
                    "ZoneRow:I4, ZoneCol:I4) -> BOOL"
                ),
            }
        except Exception as e:
            attempts.append(
                {
                    "method": "NewSheet4",
                    "via": label,
                    "arity": 16,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    for label, doc in (("typed", drawing_doc), ("raw", raw_doc)):
        # --- NewSheet: 5 args, returns LPDISPATCH (ISheet) not BOOL ---
        try:
            raw_sheet = doc.NewSheet(
                sheet_name,
                paper_size,
                TEMPLATE_CUSTOM,
                1.0,
                1.0,
            )
            # NewSheet returns an ISheet dispatch (not BOOL) -- a non-None
            # non-int return means success.
            ok = raw_sheet is not None and not isinstance(raw_sheet, int)
            return {
                "method_used": "NewSheet",
                "arity": 5,
                "via": label,
                "ok": bool(ok),
                "returned_type": type(raw_sheet).__name__,
                "error": None,
                "signature": (
                    "NewSheet(Name, PaperSize:I4, TemplateIn:I4, Scale1:R8, "
                    "Scale2:R8) -> LPDISPATCH (ISheet)"
                ),
            }
        except Exception as e:
            attempts.append(
                {
                    "method": "NewSheet",
                    "via": label,
                    "arity": 5,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    return {
        "method_used": None,
        "arity": None,
        "via": None,
        "ok": False,
        "error": "ALL NewSheet* candidates walled",
        "attempts": attempts,
    }


def _per_sheet_view_counts(drawing_doc: Any, mod: Any) -> list[dict[str, Any]]:
    """Iterate all sheets, activate each, count views. Returns
    [{name, view_count, view_names}] per sheet.

    ISheet exposes ``GetViews()`` (array of IView dispatches) — there is no
    ``ISheet.GetViewCount()`` (that name lives on IDrawingDoc). The count is
    ``len(GetViews())``.
    """
    from ai_sw_bridge.com.earlybind import typed_qi

    counts: list[dict[str, Any]] = []
    try:
        n = drawing_doc.GetSheetCount()
    except Exception as e:
        return [{"error": f"GetSheetCount failed: {e}"}]

    try:
        names = list(drawing_doc.GetSheetNames())
    except Exception as e:
        return [{"error": f"GetSheetNames failed: {e}"}]

    for name in names:
        try:
            drawing_doc.ActivateSheet(name)
        except Exception as e:
            counts.append({"name": name, "error": f"ActivateSheet failed: {e}"})
            continue
        raw = drawing_doc.GetCurrentSheet()
        if raw is None or isinstance(raw, int):
            counts.append({"name": name, "error": "GetCurrentSheet returned None"})
            continue
        try:
            sheet = typed_qi(raw, "ISheet", module=mod)
            vnames: list[str] = []
            try:
                views_arr = sheet.GetViews()
                if views_arr:
                    for v in views_arr:
                        try:
                            tv = typed_qi(v, "IView", module=mod)
                            vnames.append(tv.GetName2() or "<unnamed>")
                        except Exception:
                            vnames.append("<non-IView>")
                vc = len(vnames)
            except Exception as e:
                vnames = [f"<GetViews error: {e}>"]
                vc = -1
            counts.append(
                {
                    "name": name,
                    "view_count": vc,
                    "view_names": vnames,
                }
            )
        except Exception as e:
            counts.append({"name": name, "error": f"ISheet probe failed: {e}"})
    return counts


def run() -> str:
    print("=" * 70)
    print("Wave-23 Slice 1: Drawing multi-sheet de-risk (HARD GO/NO-GO)")
    print("=" * 70)

    import tempfile
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    _close_all_docs(sw)

    # --- Part build ---
    print("\n--- Build test part ---")
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    part_path = str(_tmp / f"w23_spike_box_{_ts}.SLDPRT")
    part_ok = _build_test_part(sw, part_path)
    if not gate("part_build", part_ok, f"path={part_path}"):
        results["verdict"] = "NO-GO (prereq part build failed)"
        save_results()
        return "NO-GO"

    # --- Find drawing template ---
    print("\n--- Drawing template discovery ---")
    drwdots = []
    for pat in (
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot",
    ):
        drwdots.extend(glob.glob(pat))
    drwdots = sorted(set(drwdots))
    if not gate("drwdot_found", bool(drwdots), f"count={len(drwdots)}"):
        results["verdict"] = "NO-GO (no drawing template)"
        save_results()
        return "NO-GO"
    template_path = drwdots[0]

    # --- Open drawing doc + dump typelib candidates ---
    print("\n--- IDrawingDoc typelib dump (NewSheet* arity) ---")
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        doc_raw = tsw.NewDocument(template_path, 0, 0.420, 0.297)  # A3
    except Exception as e:
        gate("newdocument", False, f"raised: {e}")
        results["verdict"] = "NO-GO (NewDocument failed)"
        save_results()
        return "NO-GO"

    if doc_raw is None or isinstance(doc_raw, int):
        gate("newdocument", False, f"returned {doc_raw!r}")
        results["verdict"] = "NO-GO (NewDocument returned None)"
        save_results()
        return "NO-GO"
    gate("newdocument", True, f"type={type(doc_raw).__name__}")

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
    except Exception as e:
        gate("qi_idrawingdoc", False, f"raised: {e}")
        results["verdict"] = "NO-GO (QI to IDrawingDoc failed)"
        save_results()
        return "NO-GO"
    gate("qi_idrawingdoc", True, f"type={type(drawing_doc).__name__}")

    results["typelib_dump"] = _dump_newsheet_candidates(drawing_doc, doc_raw)

    # --- Sheet 1: baseline (NewDocument already created it) ---
    print("\n--- Baseline sheet 1 ---")
    try:
        n1 = drawing_doc.GetSheetCount()
        names1 = list(drawing_doc.GetSheetNames())
        gate("sheet1_count", n1 == 1, f"GetSheetCount()={n1}")
        gate("sheet1_names", len(names1) == 1, f"GetSheetNames()={names1}")
    except Exception as e:
        gate("sheet1_baseline", False, f"raised: {e}")
        results["verdict"] = "NO-GO"
        save_results()
        return "NO-GO"

    # Place one view on sheet 1 BEFORE creating sheet 2 (to test routing)
    try:
        v1_raw = drawing_doc.CreateDrawViewFromModelView3(
            part_path, "*Front", 0.10, 0.15, 0.0
        )
        v1_ok = v1_raw is not None and not isinstance(v1_raw, int)
        gate("sheet1_place_front", v1_ok, f"returned type={type(v1_raw).__name__}")
    except Exception as e:
        gate("sheet1_place_front", False, f"raised: {e}")
        results["verdict"] = "NO-GO (cannot place any view)"
        save_results()
        return "NO-GO"

    # --- Add sheet 2 ---
    print("\n--- NewSheet* probe + sheet 2 creation ---")
    probe = _try_newsheet(drawing_doc, doc_raw, "DetailSheet", 0.210, 0.297)
    results["typelib_dump"]["NewSheet_probe"] = probe
    if not gate(
        "NewSheet_succeeded",
        probe["ok"] is True and probe["method_used"] is not None,
        f"method={probe['method_used']} arity={probe['arity']}",
    ):
        results["verdict"] = "NO-GO (NewSheet* walled)"
        save_results()
        return "NO-GO"

    # --- Add sheet 3 ---
    print("\n--- NewSheet* probe + sheet 3 creation ---")
    probe3 = _try_newsheet(drawing_doc, doc_raw, "Overview", 0.420, 0.297)
    results["typelib_dump"]["NewSheet_probe_3"] = probe3
    if not gate(
        "NewSheet_3_succeeded",
        probe3["ok"] is True and probe3["method_used"] is not None,
        f"method={probe3['method_used']}",
    ):
        results["verdict"] = "NO-GO (NewSheet for sheet 3 failed)"
        save_results()
        return "NO-GO"

    # --- Liveness: 3 sheets with the right names ---
    print("\n--- Sheet count + names after creation ---")
    try:
        n_after = drawing_doc.GetSheetCount()
        names_after = list(drawing_doc.GetSheetNames())
        gate("sheet_count_3", n_after == 3, f"GetSheetCount()={n_after}")
        gate(
            "sheet_names_include_new",
            "DetailSheet" in names_after and "Overview" in names_after,
            f"names={names_after}",
        )
    except Exception as e:
        gate("sheets_after_creation", False, f"raised: {e}")
        results["verdict"] = "NO-GO (cannot read sheet state)"
        save_results()
        return "NO-GO"

    # --- Per-sheet view routing (THE LOAD-BEARING TEST) ---
    print("\n--- Per-sheet view routing (ActivateSheet + CreateView) ---")
    # At this point sheet 1 has 1 view (Front). Sheets 2 and 3 have 0.
    # Place a view on "DetailSheet" (sheet 2) via ActivateSheet.
    routing_errors: list[str] = []
    try:
        ok2 = drawing_doc.ActivateSheet("DetailSheet")
        gate("activate_detail", bool(ok2), f"ActivateSheet returned {ok2!r}")
    except Exception as e:
        gate("activate_detail", False, f"raised: {e}")
        routing_errors.append(f"ActivateSheet(DetailSheet) raised {e}")

    try:
        v2_raw = drawing_doc.CreateDrawViewFromModelView3(
            part_path, "*Top", 0.10, 0.15, 0.0
        )
        v2_ok = v2_raw is not None and not isinstance(v2_raw, int)
        gate("sheet2_place_top", v2_ok, f"returned type={type(v2_raw).__name__}")
    except Exception as e:
        gate("sheet2_place_top", False, f"raised: {e}")
        routing_errors.append(f"CreateView on DetailSheet raised {e}")

    try:
        ok3 = drawing_doc.ActivateSheet("Overview")
        gate("activate_overview", bool(ok3), f"ActivateSheet returned {ok3!r}")
    except Exception as e:
        gate("activate_overview", False, f"raised: {e}")
        routing_errors.append(f"ActivateSheet(Overview) raised {e}")

    try:
        v3_raw = drawing_doc.CreateDrawViewFromModelView3(
            part_path, "*Isometric", 0.25, 0.15, 0.0
        )
        v3_ok = v3_raw is not None and not isinstance(v3_raw, int)
        gate(
            "sheet3_place_isometric",
            v3_ok,
            f"returned type={type(v3_raw).__name__}",
        )
    except Exception as e:
        gate("sheet3_place_isometric", False, f"raised: {e}")
        routing_errors.append(f"CreateView on Overview raised {e}")

    # --- Per-sheet view COUNTS (the liveness gate) ---
    print("\n--- Per-sheet view count verification ---")
    per_sheet = _per_sheet_view_counts(drawing_doc, mod)
    results["per_sheet_routing"] = {
        "sheets": per_sheet,
        "routing_errors": routing_errors,
    }

    counts_by_name: dict[str, int] = {}
    for s in per_sheet:
        if "error" in s:
            counts_by_name[s.get("name", "?")] = -1
        else:
            counts_by_name[s["name"]] = s["view_count"]

    expected = {
        names1[0]: 1,  # sheet 1: only the Front view
        "DetailSheet": 1,  # sheet 2: only the Top view
        "Overview": 1,  # sheet 3: only the Isometric view
    }
    routing_ok = True
    for name, want in expected.items():
        have = counts_by_name.get(name, -1)
        if not gate(
            f"sheet_view_count[{name}]",
            have == want,
            f"expected {want}, got {have}",
        ):
            routing_ok = False

    if routing_errors:
        routing_ok = False

    # --- Verdict ---
    if routing_ok and not routing_errors:
        results["verdict"] = "GO"
        results["recipe"] = {
            "new_sheet_method": probe["method_used"],
            "new_sheet_arity": probe["arity"],
            "routing_sequence": [
                "IDrawingDoc.NewSheet*(name, ...) -> bool",
                "IDrawingDoc.ActivateSheet(name) -> bool  "
                "(BEFORE every view/dim/bom on that sheet)",
                "IDrawingDoc.CreateDrawViewFromModelView3(...) "
                "(lands on active sheet)",
            ],
            "liveness_gates": [
                "GetSheetCount() == N",
                "GetSheetNames() contains all requested names",
                "per-sheet ISheet.GetViewCount() matches spec",
            ],
        }
        print(f"\n>>> VERDICT: GO (recipe recorded)")
    else:
        results["verdict"] = "NO-GO"
        print(f"\n>>> VERDICT: NO-GO (per-sheet routing failed)")

    save_results()
    # Always close the doc
    try:
        t = doc_raw.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass
    return results["verdict"]


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception:
        traceback.print_exc()
        results["verdict"] = (
            f"NO-GO (unhandled exception: {traceback.format_exc()[:200]})"
        )
        save_results()
        verdict = "NO-GO"
    sys.exit(0 if verdict == "GO" else 1)
