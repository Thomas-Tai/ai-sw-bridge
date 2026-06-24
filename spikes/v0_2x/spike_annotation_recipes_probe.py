"""W70 batch diagnostic — measure datum_tag / weld_symbol / balloon recipes.

The `note` lane proved Insert* returns a bare CDispatch that must be typed to
its specific interface BEFORE GetAnnotation/SetPosition resolve.  This probe
MEASURES the same recipe for the next three annotation types in ONE seat fire
(insert -> cast -> GetAnnotation -> SetPosition + reopen-persistence), so the
lanes are authored from measured truth, not guessed:

  datum_tag : InsertDatumTag2()              -> IDatumTag    (swDatumTag=2)
  weld      : InsertWeldSymbol3()            -> IWeldSymbol  (swWeldSymbol=8)
  balloon   : InsertBOMBalloon2(style,...)   -> INote        (swNote=6)

Writes spikes/v0_2x/_results/annotation_recipes_probe.json.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG))

RESULTS = (
    Path(__file__).resolve().parents[2]
    / "spikes"
    / "v0_2x"
    / "_results"
    / "annotation_recipes_probe.json"
)

_TYPE = {"datum_tag": 2, "weld": 8, "balloon": 6}


def _try(label: str, fn) -> dict[str, Any]:
    try:
        r = fn()
        return {"call": label, "ok": True, "return": repr(r)[:50]}
    except Exception as exc:
        return {
            "call": label,
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:90]}",
        }


def _build_part(p: str) -> bool:
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W70B",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "S",
                "plane": "Front",
                "width": 20.0,
                "height": 20.0,
            },
            {"type": "boss_extrude_blind", "name": "E", "sketch": "S", "depth": 10.0},
        ],
    }
    r = part_build(spec, no_dim=True, save_as=p)
    ok = getattr(r, "ok", None)
    if ok is None and isinstance(r, dict):
        ok = r.get("ok")
    return bool(ok) and os.path.isfile(p)


def _place_via_typed(
    probe: dict, raw_obj: Any, iface: str, mod: Any, typed_qi: Any, x: float, y: float
) -> None:
    """Mirror the note recipe: type the inserted obj, GetAnnotation, SetPosition."""
    probe["insert_is_none"] = raw_obj is None
    if raw_obj is None:
        return
    try:
        tobj = typed_qi(raw_obj, iface, module=mod)
        probe["typed_cast_ok"] = True
    except Exception as exc:
        probe["typed_cast_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        return
    try:
        ann = tobj.GetAnnotation()
        probe["getann_type"] = type(ann).__name__ if ann is not None else None
    except Exception as exc:
        probe["getann_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        return
    if ann is not None:
        probe["setposition"] = _try("SetPosition", lambda: ann.SetPosition(x, y, 0.0))


def _count_types(mdoc2_path: str, want: set[int]) -> dict[str, Any]:
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.sw_com import get_sw_app

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(mdoc2_path, 3, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    out: dict[str, Any] = {"ok": doc is not None, "counts": {}}
    if doc is None:
        return out
    try:
        ddoc = typed_qi(doc, "IDrawingDoc", module=mod)
        sheet = typed_qi(ddoc.GetCurrentSheet(), "ISheet", module=mod)
        for v_raw in sheet.GetViews() or []:
            if v_raw is None:
                continue
            v = typed_qi(v_raw, "IView", module=mod)
            for raw in v.GetAnnotations() or []:
                if raw is None:
                    continue
                try:
                    a = typed_qi(raw, "IAnnotation", module=mod)
                    t = a.GetType()
                    if t in want:
                        out["counts"][str(t)] = out["counts"].get(str(t), 0) + 1
                except Exception:
                    continue
    finally:
        try:
            tt = doc.GetTitle
            sw.CloseDoc(tt() if callable(tt) else tt)
        except Exception:
            pass
    return out


def main() -> int:
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.drawing.lifecycle import commit_drawing
    from ai_sw_bridge.sw_com import get_sw_app

    res: dict[str, Any] = {
        "spike": "annotation_recipes_probe",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "probes": {},
    }
    mod = wrapper_module()
    sw = get_sw_app()

    with tempfile.TemporaryDirectory(prefix="w70b_") as tmp:
        part = os.path.join(tmp, "W70B.sldprt")
        drw = os.path.join(tmp, "W70B.slddrw")
        if not _build_part(part):
            res["fatal"] = "part build failed"
            _w(res)
            return 1
        commit_drawing(
            sw,
            {"kind": "drawing", "name": "W70B", "model": part, "views": ["front"]},
            drw,
            mod=mod,
        )

        tsw = typed(sw, "ISldWorks", module=mod)
        ret = tsw.OpenDoc6(drw, 3, 1, "", 0, 0)
        doc = ret[0] if isinstance(ret, tuple) else ret
        if doc is None:
            res["fatal"] = "reopen None"
            _w(res)
            return 1
        save_path = os.path.join(tmp, "W70B_annot.slddrw")
        try:
            ddoc = typed_qi(doc, "IDrawingDoc", module=mod)
            mdoc2 = typed_qi(doc, "IModelDoc2", module=mod)
            sheet = typed_qi(ddoc.GetCurrentSheet(), "ISheet", module=mod)
            v = typed_qi(sheet.GetViews()[0], "IView", module=mod)
            vn = v.GetName2() or ""
            if vn:
                ddoc.ActivateView(vn)

            # Annotations like datum/weld/balloon attach to an entity — select a
            # projected view edge first (the no-selection probe returned None for
            # all three).  The coordinate-pick (SelectByID2 on the view outline)
            # missed every projected edge — they sit INSIDE the outline, not on
            # its bounding box.  Use IView.GetVisibleEntities2(None,
            # swViewEntityType_Edge=1) to fetch the actual projected model edges
            # as IEntity objects and select one via IEntity.Select2 (callout-free;
            # immune to the SelectByID2 arg-8 bare-None wall).
            ext = mdoc2.Extension
            _SW_VIEW_ENTITY_EDGE = 1

            def _select_edge() -> dict:
                try:
                    mdoc2.ClearSelection2(True)
                    if vn:
                        ddoc.ActivateView(vn)
                    raw = v.GetVisibleEntities2(None, _SW_VIEW_ENTITY_EDGE)
                    ents = list(raw) if raw else []
                    info: dict = {"n_edges": len(ents)}
                    if not ents:
                        info["ok"] = False
                        return info
                    tent = typed_qi(ents[0], "IEntity", module=mod)
                    ok = tent.Select2(False, 0)
                    cnt = mdoc2.SelectionManager.GetSelectedObjectCount2(-1)
                    info["ok"] = bool(ok)
                    info["sel_count"] = cnt
                    return info
                except Exception as exc:
                    return {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:80]}",
                    }

            res["edge_select_probe"] = _select_edge()

            # --- datum_tag: select edge -> InsertDatumTag2() ---
            p = res["probes"]["datum_tag"] = {}
            p["sel"] = _select_edge()
            dobj = None
            try:
                dobj = mdoc2.InsertDatumTag2()
                p["insert"] = {"ok": True, "return": repr(dobj)[:50]}
            except Exception as exc:
                p["insert"] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:90]}",
                }
            _place_via_typed(p, dobj, "IDatumTag", mod, typed_qi, 0.10, 0.10)

            # --- weld_symbol: select edge -> InsertWeldSymbol3() (no args) ---
            pw = res["probes"]["weld"] = {}
            pw["sel"] = _select_edge()
            wobj = None
            try:
                wobj = mdoc2.InsertWeldSymbol3()
                pw["insert"] = {"ok": True, "return": repr(wobj)[:50]}
            except Exception as exc:
                pw["insert"] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:90]}",
                }
            _place_via_typed(pw, wobj, "IWeldSymbol", mod, typed_qi, 0.12, 0.12)

            # --- balloon: select edge -> InsertBOMBalloon2(style,size,...) ---
            pb = res["probes"]["balloon"] = {}
            pb["sel"] = _select_edge()
            bobj = None
            try:
                # style=1 circular, size=2, upperTextStyle=1 (item number), no custom text
                bobj = mdoc2.InsertBOMBalloon2(1, 2, 1, "", 0, "")
                pb["insert"] = {"ok": True, "return": repr(bobj)[:50]}
            except Exception as exc:
                pb["insert"] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:90]}",
                }
            _place_via_typed(pb, bobj, "INote", mod, typed_qi, 0.14, 0.14)

            # save for persistence check
            try:
                mdoc2.SaveAs3(save_path, 0, 2)
            except Exception as exc:
                res["save_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        finally:
            try:
                tt = doc.GetTitle
                sw.CloseDoc(tt() if callable(tt) else tt)
            except Exception:
                pass

        if os.path.isfile(save_path):
            res["reopen_counts"] = _count_types(save_path, {2, 6, 8})

    res["summary"] = {
        k: (
            "PLACED"
            if res["probes"].get(k, {}).get("setposition", {}).get("ok")
            else "NEEDS_WORK"
        )
        for k in ("datum_tag", "weld", "balloon")
    }
    _w(res)
    return 0


def _w(res: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("SUMMARY:", res.get("summary"), file=sys.stderr)
    print("REOPEN:", res.get("reopen_counts"), file=sys.stderr)
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
