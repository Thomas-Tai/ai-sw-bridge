"""W71 spike — Hole Table vanguard (the apex drawing-table recipe; LIVE seat).

InsertHoleTable2 is an IView method (same interface block as InsertBomTable4,
which production calls on the view object) requiring a DUAL prerequisite: a
drawing view (implicit — the method is on the view) AND a pre-selected datum
ORIGIN (a vertex/edge) before invocation.

    view.InsertHoleTable2(UseAnchorPoint, X, Y, AnchorType, StartValue,
                          TableTemplate) -> HoleTableAnnotation

Recipe MEASURED here (not guessed): the origin is selected via the W70
entity-attach doctrine — GetVisibleEntities2(None, swViewEntityType_Vertex=2)
-> IEntity.Select2(False, 0) (callout-free, immune to the SelectByID2 arg-8
wall). We escalate selection strategy per model view and report which works.

Fixture: 40x40x10 block + TWO Ø6 through-holes (cut-extrudes 20 mm apart).
Drawing carries front+top views; the hole table needs the view where the holes
read as circles (axis perpendicular to the view plane).

Witness: InsertHoleTable2 returns a HoleTableAnnotation (not None/int), and on
save->close->reopen a table annotation persists (GetFirstTableAnnotation walk +
GetTableAnnotationCount), QI-able to IHoleTableAnnotation.

Usage::

    C:/Python314/python.exe spikes/v0_2x/spike_hole_table.py
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

RESULTS_PATH = _REPO_ROOT / "spikes" / "v0_2x" / "_results" / "hole_table.json"

_SW_VIEW_ENTITY_EDGE = 1
_SW_VIEW_ENTITY_VERTEX = 2
_SW_VIEW_ENTITY_FACE = 3


def _find_hole_template() -> str:
    pats = [
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\*.sldholtbt",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\**\*.sldholtbt",
    ]
    for p in pats:
        hits = glob.glob(p, recursive=True)
        if hits:
            return hits[0]
    return ""


def build_two_hole_part(path: str) -> bool:
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W71_HoleTbl",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Base",
                "plane": "Front",
                "width": 40.0,
                "height": 40.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Base",
                "sketch": "SK_Base",
                "depth": 10.0,
            },
            {
                "type": "sketch_circle_on_face",
                "name": "SK_H1",
                "of_feature": "EX_Base",
                "face": "+z",
                "diameter": 6.0,
                "center": {"u": -10.0, "v": 0.0},
            },
            {"type": "cut_extrude_through_all", "name": "CUT_H1", "sketch": "SK_H1"},
            {
                "type": "sketch_circle_on_face",
                "name": "SK_H2",
                "of_feature": "EX_Base",
                "face": "+z",
                "diameter": 6.0,
                "center": {"u": 10.0, "v": 0.0},
            },
            {"type": "cut_extrude_through_all", "name": "CUT_H2", "sketch": "SK_H2"},
        ],
    }
    r = part_build(spec, save_as=path, save_format="current", no_dim=True)
    ok = getattr(r, "ok", None)
    if ok is None and isinstance(r, dict):
        ok = r.get("ok")
    return bool(ok) and os.path.isfile(path)


def _typed_views(drw_doc: Any, mod: Any) -> list[Any]:
    """All views (typed IView) via GetFirstView/GetNextView."""
    from ai_sw_bridge.com.earlybind import typed_qi
    from ai_sw_bridge.drawing.lifecycle import _SW_VIEW_ENTITY_EDGE  # noqa: F401

    out = []
    try:
        from ai_sw_bridge.com.earlybind import typed

        drw_typed = typed(drw_doc, "IDrawingDoc", module=mod)
        v = drw_typed.GetFirstView()
        while v is not None:
            tv = typed_qi(v, "IView", module=mod)
            out.append(tv)
            v = tv.GetNextView()
    except Exception:
        pass
    return out


def _visible(tv: Any, etype: int) -> list[Any]:
    try:
        raw = tv.GetVisibleEntities2(None, etype)
        return list(raw) if raw else []
    except Exception:
        return []


def run() -> dict[str, Any]:
    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.mutate import (
        sw_commit_drawing,
        sw_dry_run_drawing,
        sw_propose_drawing,
    )

    mod = wrapper_module()
    result: dict[str, Any] = {
        "spike": "w71_hole_table",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "attempts": [],
    }

    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    tmp = tempfile.mkdtemp(prefix="w71_holetbl_")
    part_path = os.path.join(tmp, "W71_HoleTbl.SLDPRT")
    drw_path = os.path.join(tmp, "W71_HoleTbl.SLDDRW")

    if not build_two_hole_part(part_path):
        result["overall"] = "ERROR"
        result["finding"] = "two-hole fixture build failed"
        return result
    result["part"] = part_path

    # Drawing with front + top views (one of them shows holes as circles).
    drawing_spec = {
        "kind": "drawing",
        "name": "hole_tbl",
        "model": part_path,
        "views": ["front", "top"],
        "sheet": {"template_size": "A3"},
    }
    dp = sw_propose_drawing(drawing_spec)
    if not dp.get("ok"):
        result["overall"] = "ERROR"
        result["finding"] = f"drawing propose failed: {dp.get('error')}"
        return result
    sw_dry_run_drawing(dp["proposal_id"])
    dc = sw_commit_drawing(dp["proposal_id"], drw_path)
    result["drawing_commit_ok"] = dc.get("ok")
    if not dc.get("ok"):
        result["overall"] = "ERROR"
        result["finding"] = f"drawing commit failed: {dc.get('error')}"
        return result

    template = _find_hole_template()
    result["hole_template"] = template or "(default '')"

    # Reopen part (resolve refs) + drawing.
    tsw = typed(sw, "ISldWorks", module=mod)
    try:
        tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    except Exception:
        pass
    ret = tsw.OpenDoc6(drw_path, 3, 1, "", 0, 0)
    drw_doc = ret[0] if isinstance(ret, tuple) else ret
    if drw_doc is None:
        result["overall"] = "ERROR"
        result["finding"] = "drawing reopen failed"
        return result

    views = _typed_views(drw_doc, mod)
    # Model views = those with visible vertices (the sheet view has none).
    model_views = [(tv, _visible(tv, _SW_VIEW_ENTITY_VERTEX)) for tv in views]
    model_views = [(tv, vs) for tv, vs in model_views if vs]

    placed = None
    placed_view_name = None
    for tv, verts in model_views:
        try:
            vname = tv.GetName2() or "?"
        except Exception:
            vname = "?"
        n_edges = len(_visible(tv, _SW_VIEW_ENTITY_EDGE))
        # Strategy A: origin vertex only.  Strategy B: origin vertex + a face.
        for strat in ("A_vertex", "B_vertex_face"):
            try:
                drw_doc.ClearSelection2(True)
            except Exception:
                pass
            ok_origin = False
            try:
                tent = typed_qi(verts[0], "IEntity", module=mod)
                ok_origin = bool(tent.Select2(False, 0))
            except Exception:
                ok_origin = False
            if strat == "B_vertex_face":
                faces = _visible(tv, _SW_VIEW_ENTITY_FACE)
                if faces:
                    try:
                        tf = typed_qi(faces[0], "IEntity", module=mod)
                        tf.Select2(True, 0)
                    except Exception:
                        pass
            try:
                ann = tv.InsertHoleTable2(False, 0.25, 0.18, 1, "", template)
            except Exception as exc:
                ann = None
                err = f"{type(exc).__name__}: {str(exc)[:90]}"
            else:
                err = None
            valid = ann is not None and not isinstance(ann, int)
            result["attempts"].append(
                {
                    "view": vname,
                    "n_edges": n_edges,
                    "n_verts": len(verts),
                    "strategy": strat,
                    "origin_selected": ok_origin,
                    "ret_repr": repr(ann)[:50],
                    "valid": valid,
                    "error": err,
                }
            )
            if valid:
                placed = ann
                placed_view_name = vname
                break
        if placed is not None:
            break

    result["placed"] = placed is not None
    result["placed_view"] = placed_view_name

    if placed is None:
        result["overall"] = "FAIL"
        result["finding"] = "InsertHoleTable2 returned None on every view/strategy"
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        return result

    # Persist + reopen witness.
    mdoc2 = typed(drw_doc, "IModelDoc2", module=mod)
    mdoc2.SaveAs3(drw_path, 0, 0)
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    time.sleep(0.3)
    try:
        tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    except Exception:
        pass
    ret = tsw.OpenDoc6(drw_path, 3, 1, "", 0, 0)
    drw2 = ret[0] if isinstance(ret, tuple) else ret

    reopen_tables = 0
    reopen_hole_tables = 0
    for tv in _typed_views(drw2, mod):
        try:
            cnt = tv.GetTableAnnotationCount()
        except Exception:
            cnt = 0
        try:
            ta = tv.GetFirstTableAnnotation()
            while ta is not None:
                reopen_tables += 1
                try:
                    typed_qi(ta, "IHoleTableAnnotation", module=mod)
                    reopen_hole_tables += 1
                except Exception:
                    pass
                try:
                    ta = ta.GetNext()
                except Exception:
                    break
        except Exception:
            pass
        reopen_tables = max(reopen_tables, cnt)
    result["reopen"] = {
        "table_annotations": reopen_tables,
        "hole_tables": reopen_hole_tables,
        "survives": reopen_tables >= 1,
    }
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass

    if reopen_tables >= 1:
        result["overall"] = "PASS"
        result["finding"] = (
            f"Hole Table PLACED on view {placed_view_name!r} "
            f"(strategy proved), survives reopen: "
            f"{reopen_tables} table(s), {reopen_hole_tables} QI'd IHoleTable"
        )
    else:
        result["overall"] = "FAIL"
        result["finding"] = (
            f"placed on {placed_view_name!r} but did NOT survive reopen "
            f"(tables={reopen_tables})"
        )
    return result


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    import pythoncom

    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        try:
            import win32com.client as w32

            w32.Dispatch("SldWorks.Application").CloseAllDocuments(True)
        except Exception:
            pass
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
