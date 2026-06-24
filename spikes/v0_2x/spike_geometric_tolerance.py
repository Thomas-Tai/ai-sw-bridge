"""W70 seat-proof — drawing ``geometric_tolerance`` (GD&T FCF) annotation (LIVE seat).

Drives the PRODUCTION ``commit_drawing`` path with an
``annotations.geometric_tolerance`` block so it seat-proves the real
``_apply_entity_attached_annotation`` handler (GetVisibleEntities2 ->
IEntity.Select2 -> InsertGtol -> typed_qi(obj,"IGtol") ->
SetFrameValues(1,...) -> GetAnnotation().SetPosition), NOT a raw probe.
Then reopens the .SLDDRW and counts ``swGTol=5`` annotations.

  GREEN := commit_ok AND reopened drawing has >= 1 swGTol annotation.

GTOL-specific risk this fire measures: an EMPTY feature-control-frame can be
culled by SW on save. The handler gives frame 1 a tolerance value
(SetFrameValues) to keep it non-empty; the reopen count is the witness that
this is sufficient.

swAnnotationType_e (seat-verified, swconst.tlb): 2 datumTag, 5 GTol, 6 note,
7 SFSymbol, 8 weld.

Usage (seat must be UP)::
    C:/Python314/python.exe spikes/v0_2x/spike_geometric_tolerance.py
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

RESULTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "spikes"
    / "v0_2x"
    / "_results"
    / "drawing_gtol.json"
)

_KIND = "geometric_tolerance"
_SW_TYPE = 5  # swAnnotationType_e.swGTol
_RESULT_KEY = "gtol_annotations"


def _build_minimal_part(part_path: str) -> bool:
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W70_Box",
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


def _count_type(view: Any, mod: Any, typed_qi: Any) -> int:
    n = 0
    try:
        anns = view.GetAnnotations()
        if not anns:
            return 0
        for raw in anns:
            if raw is None:
                continue
            try:
                ann = typed_qi(raw, "IAnnotation", module=mod)
                if ann.GetType() == _SW_TYPE:
                    n += 1
            except Exception:
                continue
    except Exception:
        pass
    return n


def _reopen_count(drawing_path: str) -> dict[str, Any]:
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.sw_com import get_sw_app

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(drawing_path, 3, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    out: dict[str, Any] = {"ok": False, "total": 0, "errors": []}
    if doc is None:
        out["errors"].append("OpenDoc6 returned None")
        return out
    try:
        ddoc = typed_qi(doc, "IDrawingDoc", module=mod)
        sheet = typed_qi(ddoc.GetCurrentSheet(), "ISheet", module=mod)
        for v_raw in sheet.GetViews() or []:
            if v_raw is None:
                continue
            try:
                v = typed_qi(v_raw, "IView", module=mod)
                out["total"] += _count_type(v, mod, typed_qi)
            except Exception as exc:
                out["errors"].append(f"view: {exc!r}")
        out["ok"] = out["total"] >= 1
    finally:
        try:
            t = doc.GetTitle
            sw.CloseDoc(t() if callable(t) else t)
        except Exception:
            pass
    return out


def main() -> int:
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.drawing.lifecycle import commit_drawing
    from ai_sw_bridge.sw_com import get_sw_app

    result: dict[str, Any] = {
        "spike": f"w70_{_KIND}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    mod = wrapper_module()
    sw = get_sw_app()

    with tempfile.TemporaryDirectory(prefix="w70_gtol_") as tmp:
        part_path = os.path.join(tmp, "W70_Box.sldprt")
        drawing_path = os.path.join(tmp, "W70_gtol.slddrw")

        if not _build_minimal_part(part_path):
            result["overall"] = "ERROR"
            result["finding"] = "part build failed"
            _write(result)
            return 1

        spec = {
            "kind": "drawing",
            "name": "W70_gtol_Test",
            "model": part_path,
            "views": ["front"],
            "annotations": {
                _KIND: [{"view": "front", "x": 0.16, "y": 0.16, "tolerance": "0.05"}],
            },
        }
        try:
            commit = commit_drawing(sw, spec, drawing_path, mod=mod)
        except Exception as exc:
            result["overall"] = "ERROR"
            result["finding"] = f"commit_drawing raised: {type(exc).__name__}: {exc}"
            _write(result)
            return 1
        result["commit_ok"] = commit.get("ok", False)
        result["apply_result"] = commit.get(_RESULT_KEY) or _dig(commit, _RESULT_KEY)

        reopen = _reopen_count(drawing_path)
        result["reopen"] = reopen
        green = bool(commit.get("ok")) and reopen.get("ok")
        result["overall"] = "PASS" if green else "FAIL"
        result["finding"] = (
            f"commit_ok={commit.get('ok')}, gtol_on_reopen={reopen.get('total')}"
        )
        _write(result)
        return 0 if green else 1


def _dig(commit: dict, key: str) -> Any:
    for k in ("sheets", "sheet_results", "results"):
        v = commit.get(k)
        if isinstance(v, list):
            for s in v:
                if isinstance(s, dict) and s.get(key):
                    return s[key]
    return None


def _write(result: dict) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", ""), file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
