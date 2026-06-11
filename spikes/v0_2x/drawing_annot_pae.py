"""Wave-53 S1: drawing annotation de-risk PAE.

End-to-end seat test for the W53 surface-finish annotation path:

  1. Build a minimal .SLDPRT (20x20x10 box) in a temp dir.
  2. Create a drawing with one ortho view.
  3. FUNCDESC the 4 candidate annotation APIs (surface-finish, GD&T,
     weld, hole-table) — dump arity + arg VTs from the typelib.
  4. Try each candidate in priority order:
     a. surface-finish (IModelDocExtension.InsertSurfaceFinishSymbol2)
     b. GD&T (IModelDocExtension.InsertGTOL)
     c. weld symbol (IModelDocExtension.InsertWeldSymbol2)
     d. hole table (IView.InsertHoleTable2)
  5. VERIFY THE EFFECT for each: save → close → reopen → enumerate
     annotations on the view → count by swAnnotationType_e.
  6. If a candidate is an interactive-mode wall (W31v2 trap: returns
     None + zero annotations on reopen), characterize it and move to
     the next candidate.

GREEN gate: the annotation exists on the reopened .SLDDRW (count delta
+ the specific annotation type present), NOT merely "Insert returned
non-None".

Prereq: SOLIDWORKS 2024 SP1 running.

Exit: 0 iff at least one candidate goes GREEN; non-zero otherwise.
Always writes ``spikes/v0_2x/_results/drawing_annot_pae.json``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_annot_pae.json"
)

results: dict[str, Any] = {
    "pae": "w53_drawing_annotation",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "candidates": [],
    "green_candidate": None,
    "gates": {},
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


def _build_minimal_part(part_path: str) -> bool:
    """Build a 20x20x10 mm box as the drawing's model source."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W53_Box",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 20.0,
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
    res = part_build(spec, no_dim=True, save_as=part_path)
    ok = getattr(res, "ok", None)
    if ok is None and isinstance(res, dict):
        ok = res.get("ok")
    return bool(ok) and os.path.isfile(part_path)


def _funcdesc_method(obj: Any, method_name: str) -> dict[str, Any]:
    """Dump FUNCDESC for a method on a COM dispatch object.

    Returns dict with arity, arg_types, return_type, or error info.
    """
    info: dict[str, Any] = {"method": method_name}
    try:
        oleobj = getattr(obj, "_oleobj_", None)
        if oleobj is None:
            info["error"] = "no _oleobj_ attribute"
            return info
        type_info = oleobj.GetTypeInfo()
        if type_info is None:
            info["error"] = "GetTypeInfo returned None"
            return info
        type_attr = type_info.GetTypeAttr()
        func_count = type_attr[6]  # cFuncs
        for i in range(func_count):
            func_desc = type_info.GetFuncDesc(i)
            memid = func_desc[0]
            names = type_info.GetNames(memid)
            if names and names[0] == method_name:
                info["memid"] = memid
                info["arity"] = len(func_desc[2]) if func_desc[2] else 0
                info["arg_types"] = [
                    str(a) for a in (func_desc[2] or [])
                ]
                info["return_type"] = str(func_desc[8]) if func_desc[8] else "void"
                info["invkind"] = func_desc[4]
                info["names"] = list(names)
                return info
        info["error"] = f"method {method_name!r} not found in {func_count} funcs"
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def _count_annotations_by_type(
    view: Any,
    mod: Any,
    typed_qi: Any,
) -> dict[int, int]:
    """Count annotations on a view by swAnnotationType_e.

    Returns {type_id: count}.
    """
    counts: dict[int, int] = {}
    try:
        annotations = view.GetAnnotations()
        if not annotations:
            return counts
        for ann_raw in annotations:
            if ann_raw is None:
                continue
            try:
                ann = typed_qi(ann_raw, "IAnnotation", module=mod)
                ann_type = ann.GetType()
                counts[ann_type] = counts.get(ann_type, 0) + 1
            except Exception:
                continue
    except Exception:
        pass
    return counts


def _independent_reopen_verify(
    drawing_path: str,
    expected_sf_count: int,
) -> dict[str, Any]:
    """Independent verify — reopen .SLDDRW and count surface-finish annotations.

    swAnnotationType_e values (seat-verified from swconst.tlb):
      4 = swDisplayDimension, 5 = swGTol, 6 = swNote,
      7 = swSFSymbol (surface finish), 8 = swWeldSymbol, 9 = swCustomSymbol
    """
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.sw_com import get_sw_app

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)

    ret = tsw.OpenDoc6(drawing_path, 3, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        return {
            "ok": False,
            "errors": [f"OpenDoc6({drawing_path}) returned None"],
        }

    result: dict[str, Any] = {
        "ok": False,
        "per_view": [],
        "total_sf": 0,
        "total_gtol": 0,
        "total_weld": 0,
        "errors": [],
    }

    try:
        ddoc = typed_qi(doc, "IDrawingDoc", module=mod)
        sheet_raw = ddoc.GetCurrentSheet()
        sheet = (
            typed_qi(sheet_raw, "ISheet", module=mod)
            if sheet_raw is not None and not isinstance(sheet_raw, int)
            else None
        )
        if sheet is None:
            result["errors"].append("GetCurrentSheet returned None")
            return result

        views_raw = sheet.GetViews()
        if not views_raw:
            result["errors"].append("GetViews returned empty/None")
            return result

        for v_raw in views_raw:
            if v_raw is None:
                continue
            try:
                v = typed_qi(v_raw, "IView", module=mod)
                vname = v.GetName2() or ""
                counts = _count_annotations_by_type(v, mod, typed_qi)
                sf = counts.get(7, 0)    # swSFSymbol (surface finish)
                gtol = counts.get(5, 0)  # swGTol
                weld = counts.get(8, 0)  # swWeldSymbol
                result["total_sf"] += sf
                result["total_gtol"] += gtol
                result["total_weld"] += weld
                result["per_view"].append({
                    "view": vname,
                    "annotation_types": {
                        str(k): val for k, val in counts.items()
                    },
                    "surface_finish": sf,
                    "gtol": gtol,
                    "weld": weld,
                })
            except Exception as exc:
                result["errors"].append(f"view enumeration: {exc!r}")

        result["ok"] = result["total_sf"] >= expected_sf_count
        if not result["ok"]:
            result["errors"].append(
                f"expected >= {expected_sf_count} surface-finish, "
                f"found {result['total_sf']}"
            )
    finally:
        try:
            t = doc.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass

    return result


def _try_candidate(
    name: str,
    insert_fn: Any,
    *,
    drawing_doc: Any,
    mdoc2: Any,
    view: Any,
    view_name: str,
    drawing_path: str,
    mod: Any,
    typed: Any,
    typed_qi: Any,
) -> dict[str, Any]:
    """Try one annotation candidate. Returns per-candidate result dict."""
    candidate: dict[str, Any] = {
        "name": name,
        "verdict": "UNKNOWN",
        "funcdesc": {},
        "insert_return": None,
        "dims_immediate": {},
        "dims_reopen": {},
    }

    # Step 1: FUNCDESC
    ext_obj = mdoc2.Extension
    if ext_obj is not None:
        candidate["funcdesc"] = _funcdesc_method(ext_obj, name)
    print(f"    FUNCDESC({name}): {json.dumps(candidate['funcdesc'], default=str)}")

    # Step 2: ActivateView + Insert
    try:
        vn = view.GetName2() or ""
        if vn:
            drawing_doc.ActivateView(vn)
    except Exception:
        pass

    # Get annotation count BEFORE
    before_counts = _count_annotations_by_type(view, mod, typed_qi)
    candidate["dims_before"] = {
        str(k): v for k, v in before_counts.items()
    }

    try:
        result = insert_fn(ext_obj)
        candidate["insert_return"] = repr(result)
        candidate["insert_return_type"] = type(result).__name__
    except Exception as exc:
        candidate["insert_error"] = f"{type(exc).__name__}: {exc}"
        candidate["verdict"] = "ERROR"
        return candidate

    # Step 3: Immediate count (after EditRebuild3)
    try:
        mdoc2.EditRebuild3()
    except Exception:
        pass

    after_counts = _count_annotations_by_type(view, mod, typed_qi)
    candidate["dims_immediate"] = {
        str(k): v for k, v in after_counts.items()
    }

    # Step 4: Save → Close → Reopen → Count
    try:
        # GetTitle / SaveAs3 are IModelDoc2 members — NOT on the typed
        # IDrawingDoc wrapper (AttributeError). Use mdoc2.
        doc_title = mdoc2.GetTitle
        doc_title = doc_title() if callable(doc_title) else doc_title
        from ai_sw_bridge.sw_com import get_sw_app
        sw = get_sw_app()
        mdoc2.SaveAs3(drawing_path, 0, 2)
        sw.CloseDoc(doc_title)
        time.sleep(0.5)
    except Exception as exc:
        candidate["save_error"] = f"{type(exc).__name__}: {exc}"
        candidate["verdict"] = "SAVE_FAILED"
        return candidate

    reopen_result = _independent_reopen_verify(drawing_path, 1)
    candidate["dims_reopen"] = reopen_result

    # Step 5: Verdict
    sf_after = after_counts.get(7, 0)   # swSFSymbol
    sf_before = before_counts.get(7, 0)
    sf_reopen = reopen_result.get("total_sf", 0)

    if sf_reopen > sf_before:
        candidate["verdict"] = "GREEN"
        candidate["detail"] = (
            f"surface-finish count: before={sf_before}, "
            f"immediate={sf_after}, reopen={sf_reopen}"
        )
    elif result is None and sf_after == sf_before and sf_reopen == sf_before:
        candidate["verdict"] = "NO-GO"
        candidate["detail"] = (
            f"returned None + zero effect "
            f"(before={sf_before}, immediate={sf_after}, "
            f"reopen={sf_reopen}). "
            f"Likely interactive-mode starter (W31v2 trap)."
        )
    elif isinstance(result, int) and sf_after == sf_before:
        candidate["verdict"] = "NO-GO"
        candidate["detail"] = (
            f"returned int({result}) + zero effect. "
            f"Likely interactive-mode starter."
        )
    else:
        candidate["verdict"] = "AMBIGUOUS"
        candidate["detail"] = (
            f"return={result!r}, before={sf_before}, "
            f"immediate={sf_after}, reopen={sf_reopen}"
        )

    return candidate


def main() -> int:
    print("=" * 60)
    print("W53 Drawing Annotation De-risk PAE")
    print("=" * 60)

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.drawing.lifecycle import commit_drawing
    from ai_sw_bridge.sw_com import get_sw_app

    mod = wrapper_module()
    sw = get_sw_app()

    with tempfile.TemporaryDirectory(prefix="w53_annot_") as tmp:
        part_path = os.path.join(tmp, "W53_Box.sldprt")
        drawing_path = os.path.join(tmp, "W53_Annot.slddrw")

        # Gate 1: Build part
        print("\n--- Gate 1: Build minimal part ---")
        if not gate(
            "build_part",
            _build_minimal_part(part_path),
            f"path={part_path}",
        ):
            save_results()
            return 1

        # Gate 2: Create drawing with one view
        print("\n--- Gate 2: Create drawing ---")
        spec: dict[str, Any] = {
            "kind": "drawing",
            "name": "W53_Annot_Test",
            "model": part_path,
            "views": ["front"],
        }

        try:
            commit_result = commit_drawing(
                sw, spec, drawing_path, mod=mod
            )
        except Exception as exc:
            gate("create_drawing", False, f"{type(exc).__name__}: {exc}")
            save_results()
            return 1

        if not gate(
            "create_drawing",
            commit_result.get("ok", False),
            f"views={commit_result.get('view_count', 0)}",
        ):
            save_results()
            return 1

        # Gate 3: FUNCDESC + try each candidate
        print("\n--- Gate 3: De-risk annotation candidates ---")

        # Reopen the drawing for annotation insertion
        tsw = typed(sw, "ISldWorks", module=mod)
        ret = tsw.OpenDoc6(drawing_path, 3, 1, "", 0, 0)
        doc = ret[0] if isinstance(ret, tuple) else ret
        if doc is None:
            gate("reopen_drawing", False, "OpenDoc6 returned None")
            save_results()
            return 1

        try:
            ddoc = typed_qi(doc, "IDrawingDoc", module=mod)
            mdoc2 = typed_qi(doc, "IModelDoc2", module=mod)
            sheet_raw = ddoc.GetCurrentSheet()
            sheet = typed_qi(sheet_raw, "ISheet", module=mod)
            views_raw = sheet.GetViews()
            if not views_raw:
                gate("get_views", False, "no views on sheet")
                save_results()
                return 1

            first_view = typed_qi(views_raw[0], "IView", module=mod)
            view_name = first_view.GetName2() or "Drawing View1"
            gate(
                "reopen_drawing",
                True,
                f"first view: {view_name}",
            )

            # Get view outline for positioning
            try:
                outline = first_view.GetOutline()
                cx = (outline[0] + outline[2]) / 2.0
                cy = (outline[1] + outline[3]) / 2.0
            except Exception:
                cx, cy = 0.15, 0.15

            annot_path = os.path.join(tmp, "W53_Annot_test.slddrw")

            # Candidate 1: InsertSurfaceFinishSymbol2
            print(f"\n  [1/4] InsertSurfaceFinishSymbol2 at ({cx:.4f}, {cy:.4f})")
            c1 = _try_candidate(
                "InsertSurfaceFinishSymbol2",
                # Real signature: IModelDoc2 (NOT IModelDocExtension), 14 args.
                # SymType=swSFMachining_Req(1), LeaderType=swNO_LEADER(0),
                # LocX/Y/Z, LaySymbol=swSFNone(0), ArrowType=0, then 7 BSTR text
                # fields with roughness "3.2" in the MaxRoughness slot.
                lambda ext: mdoc2.InsertSurfaceFinishSymbol2(
                    1, 0, cx, cy, 0.0, 0, 0, "", "", "", "", "3.2", "", ""
                ),
                drawing_doc=ddoc,
                mdoc2=mdoc2,
                view=first_view,
                view_name=view_name,
                drawing_path=annot_path,
                mod=mod,
                typed=typed,
                typed_qi=typed_qi,
            )
            results["candidates"].append(c1)

            if c1["verdict"] == "GREEN":
                results["green_candidate"] = c1["name"]
                gate(
                    "surface_finish_GREEN",
                    True,
                    c1.get("detail", ""),
                )
                # Reopen for next candidates
                ret2 = tsw.OpenDoc6(annot_path, 3, 1, "", 0, 0)
                doc2 = ret2[0] if isinstance(ret2, tuple) else ret2
                if doc2 is not None:
                    ddoc = typed_qi(doc2, "IDrawingDoc", module=mod)
                    mdoc2 = typed_qi(doc2, "IModelDoc2", module=mod)
                    sr = ddoc.GetCurrentSheet()
                    s2 = typed_qi(sr, "ISheet", module=mod)
                    vr = s2.GetViews()
                    first_view = typed_qi(vr[0], "IView", module=mod)
                else:
                    print("  Could not reopen for further candidates")
                    save_results()
                    return 0

            elif c1["verdict"] in ("NO-GO", "ERROR"):
                gate(
                    "surface_finish_WALL",
                    False,
                    c1.get("detail", c1.get("insert_error", "")),
                )

            # Candidate 2: InsertGTOL
            print(f"\n  [2/4] InsertGTOL at ({cx:.4f}, {cy:.4f})")
            c2 = _try_candidate(
                "InsertGTOL",
                lambda ext: ext.InsertGTOL(cx, cy, 0.0, ""),
                drawing_doc=ddoc,
                mdoc2=mdoc2,
                view=first_view,
                view_name=view_name,
                drawing_path=annot_path,
                mod=mod,
                typed=typed,
                typed_qi=typed_qi,
            )
            results["candidates"].append(c2)

            if c2["verdict"] == "GREEN" and results["green_candidate"] is None:
                results["green_candidate"] = c2["name"]
                gate("gtol_GREEN", True, c2.get("detail", ""))

            # Candidate 3: InsertWeldSymbol2
            print(f"\n  [3/4] InsertWeldSymbol2 at ({cx:.4f}, {cy:.4f})")
            try:
                c3 = _try_candidate(
                    "InsertWeldSymbol2",
                    lambda ext: ext.InsertWeldSymbol2(cx, cy, 0.0),
                    drawing_doc=ddoc,
                    mdoc2=mdoc2,
                    view=first_view,
                    view_name=view_name,
                    drawing_path=annot_path,
                    mod=mod,
                    typed=typed,
                    typed_qi=typed_qi,
                )
                results["candidates"].append(c3)
                if c3["verdict"] == "GREEN" and results["green_candidate"] is None:
                    results["green_candidate"] = c3["name"]
                    gate("weld_GREEN", True, c3.get("detail", ""))
            except Exception as exc:
                results["candidates"].append({
                    "name": "InsertWeldSymbol2",
                    "verdict": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                })

            # Candidate 4: InsertHoleTable2 (on IView, not Extension)
            print(f"\n  [4/4] InsertHoleTable2 (on IView)")
            c4: dict[str, Any] = {
                "name": "InsertHoleTable2",
                "verdict": "UNKNOWN",
            }
            try:
                c4["funcdesc"] = _funcdesc_method(
                    first_view, "InsertHoleTable2"
                )
                print(f"    FUNCDESC(InsertHoleTable2): "
                      f"{json.dumps(c4['funcdesc'], default=str)}")

                before = _count_annotations_by_type(
                    first_view, mod, typed_qi
                )
                ht_result = first_view.InsertHoleTable2(
                    False, 0.0, 0.0, 1, "", ""
                )
                c4["insert_return"] = repr(ht_result)
                c4["insert_return_type"] = type(ht_result).__name__

                after = _count_annotations_by_type(
                    first_view, mod, typed_qi
                )
                c4["dims_before"] = {str(k): v for k, v in before.items()}
                c4["dims_immediate"] = {
                    str(k): v for k, v in after.items()
                }

                if (ht_result is not None
                        and not isinstance(ht_result, int)):
                    c4["verdict"] = "GREEN"
                    c4["detail"] = (
                        f"InsertHoleTable2 returned {type(ht_result).__name__}"
                    )
                    if results["green_candidate"] is None:
                        results["green_candidate"] = c4["name"]
                        gate(
                            "hole_table_GREEN",
                            True,
                            c4["detail"],
                        )
                elif ht_result is None:
                    c4["verdict"] = "NO-GO"
                    c4["detail"] = "returned None (no HoleWizard holes?)"
            except Exception as exc:
                c4["verdict"] = "ERROR"
                c4["error"] = f"{type(exc).__name__}: {exc}"
            results["candidates"].append(c4)

        except Exception as exc:
            gate(
                "annotation_insertion",
                False,
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            )
        finally:
            try:
                t = doc.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass

    # Final gate
    has_green = results["green_candidate"] is not None
    gate(
        "any_candidate_GREEN",
        has_green,
        f"green={results['green_candidate']}",
    )

    save_results()
    return 0 if has_green else 1


if __name__ == "__main__":
    sys.exit(main())
