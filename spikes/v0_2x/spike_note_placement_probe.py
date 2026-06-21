"""W70 diagnostic — measure the InsertNote placement recipe (LIVE seat).

InsertNote succeeds; placing it raises DISP_E_MEMBERNOTFOUND on both the raw
GetAnnotation() dispatch and a typed_qi(IAnnotation) proxy.  Rather than guess
again, MEASURE: dump the FUNCDESC of the note + its annotation, then try every
placement variant and record which one actually moves it.

Writes spikes/v0_2x/_results/note_placement_probe.json.
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

RESULTS = Path(__file__).resolve().parents[2] / "spikes" / "v0_2x" / "_results" / "note_placement_probe.json"


def _funcdesc(obj: Any, name_filter: tuple[str, ...]) -> dict[str, Any]:
    """Dump method names (filtered) + their arity from an object's typeinfo."""
    out: dict[str, Any] = {"matched": [], "error": None}
    try:
        oleobj = getattr(obj, "_oleobj_", None)
        if oleobj is None:
            out["error"] = "no _oleobj_"
            return out
        ti = oleobj.GetTypeInfo()
        ta = ti.GetTypeAttr()
        for i in range(ta[6]):
            fd = ti.GetFuncDesc(i)
            nm = ti.GetNames(fd[0])
            if nm and any(f.lower() in nm[0].lower() for f in name_filter):
                out["matched"].append({"name": nm[0], "arity": len(fd[2]) if fd[2] else 0})
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _try(label: str, fn) -> dict[str, Any]:
    try:
        r = fn()
        return {"call": label, "ok": True, "return": repr(r)[:60]}
    except Exception as exc:
        return {"call": label, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:80]}"}


def _build_part(p: str) -> bool:
    from ai_sw_bridge.spec.builder import build as part_build
    spec = {"schema_version": 1, "name": "W70P", "features": [
        {"type": "sketch_rectangle_on_plane", "name": "S", "plane": "Front", "width": 20.0, "height": 20.0},
        {"type": "boss_extrude_blind", "name": "E", "sketch": "S", "depth": 10.0}]}
    r = part_build(spec, no_dim=True, save_as=p)
    ok = getattr(r, "ok", None)
    if ok is None and isinstance(r, dict):
        ok = r.get("ok")
    return bool(ok) and os.path.isfile(p)


def main() -> int:
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.drawing.lifecycle import commit_drawing
    from ai_sw_bridge.sw_com import get_sw_app

    res: dict[str, Any] = {"spike": "note_placement_probe", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "attempts": []}
    mod = wrapper_module()
    sw = get_sw_app()

    with tempfile.TemporaryDirectory(prefix="w70p_") as tmp:
        part = os.path.join(tmp, "W70P.sldprt")
        drw = os.path.join(tmp, "W70P.slddrw")
        if not _build_part(part):
            res["fatal"] = "part build failed"
            _w(res); return 1
        commit_drawing(sw, {"kind": "drawing", "name": "W70P", "model": part, "views": ["front"]}, drw, mod=mod)

        tsw = typed(sw, "ISldWorks", module=mod)
        ret = tsw.OpenDoc6(drw, 3, 1, "", 0, 0)
        doc = ret[0] if isinstance(ret, tuple) else ret
        if doc is None:
            res["fatal"] = "reopen returned None"; _w(res); return 1
        try:
            ddoc = typed_qi(doc, "IDrawingDoc", module=mod)
            mdoc2 = typed_qi(doc, "IModelDoc2", module=mod)
            sheet = typed_qi(ddoc.GetCurrentSheet(), "ISheet", module=mod)
            views = sheet.GetViews()
            v = typed_qi(views[0], "IView", module=mod)
            vn = v.GetName2() or ""
            if vn:
                ddoc.ActivateView(vn)

            note = mdoc2.InsertNote("PROBE_TEXT")
            res["note_is_none"] = note is None
            res["note_type"] = type(note).__name__
            res["note_funcdesc"] = _funcdesc(note, ("position", "annotation", "setname"))

            # Raw note placement variants
            res["attempts"].append(_try("raw_note.SetPosition(x,y,z)", lambda: note.SetPosition(0.15, 0.15, 0.0)))

            raw_ann = None
            try:
                raw_ann = note.GetAnnotation()
            except Exception as exc:
                res["getannotation_error"] = f"{type(exc).__name__}: {exc}"
            res["raw_ann_type"] = type(raw_ann).__name__ if raw_ann is not None else None
            if raw_ann is not None:
                res["raw_ann_funcdesc"] = _funcdesc(raw_ann, ("position",))
                res["attempts"].append(_try("raw_ann.SetPosition(x,y,z)", lambda: raw_ann.SetPosition(0.16, 0.16, 0.0)))
                res["attempts"].append(_try("raw_ann.SetPosition2(x,y,z)", lambda: raw_ann.SetPosition2(0.17, 0.17, 0.0)))
                try:
                    tann = typed_qi(raw_ann, "IAnnotation", module=mod)
                    res["typed_ann_ok"] = True
                    res["attempts"].append(_try("typed_ann.SetPosition(x,y,z)", lambda: tann.SetPosition(0.18, 0.18, 0.0)))
                    res["attempts"].append(_try("typed_ann.SetPosition2(x,y,z)", lambda: tann.SetPosition2(0.19, 0.19, 0.0)))
                except Exception as exc:
                    res["typed_ann_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"

            # typed note path: typed_qi(note,"INote") then GetAnnotation
            try:
                tnote = typed_qi(note, "INote", module=mod)
                tann2 = tnote.GetAnnotation()
                res["tnote_getann_type"] = type(tann2).__name__ if tann2 is not None else None
                if tann2 is not None:
                    res["attempts"].append(_try("tnote.GetAnnotation().SetPosition", lambda: tann2.SetPosition(0.20, 0.20, 0.0)))
                    try:
                        tann2b = typed_qi(tann2, "IAnnotation", module=mod)
                        res["attempts"].append(_try("typed(tnote.GetAnnotation()).SetPosition2", lambda: tann2b.SetPosition2(0.21, 0.21, 0.0)))
                    except Exception:
                        pass
            except Exception as exc:
                res["tnote_error"] = f"{type(exc).__name__}: {str(exc)[:100]}"

            res["winners"] = [a["call"] for a in res["attempts"] if a.get("ok")]
        finally:
            try:
                t = doc.GetTitle
                sw.CloseDoc(t() if callable(t) else t)
            except Exception:
                pass
    _w(res)
    return 0 if res.get("winners") else 1


def _w(res: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("WINNERS:", res.get("winners"), file=sys.stderr)
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
