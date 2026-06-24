"""W68 fillet face/full-round — ENHANCED binding diagnostic (W0 seat probe).

The lane spike proved BOTH the marks-only pre-selection path AND a bare
``SetFaces(which, [face])`` ghost (CreateFeature -> None, dVol=0), with
SetFaces raising no exception.  That leaves the question: do the faces ever
BIND to the FeatureData, or do they bind but CreateFeature is walled?

This probe instruments ``GetFaceCount(WhichFaceList)`` (a real getter on
ISimpleFilletFeatureData2) before/after FIVE distinct binding methods, on a
FRESH CreateDefinition each time.  Ghosts do not mutate the body, so all
methods share one fixture; we break on the first method whose CreateFeature
actually redistributes material (|dVol| > eps).

Methods (each: fresh CreateDefinition(1) -> Initialize(type) -> <bind> ->
GetFaceCount readback -> CreateFeature):
  m0 preselect_marks   pre-select faces via select_entity(mark) BEFORE define
  m1 access_setfaces   AccessSelections(doc,null) -> SetFaces(which,[face])
  m2 access_isetfaces  AccessSelections -> ISetFaces(which,1,[face]) (typed)
  m3 setfaces_variant  SetFaces(which, VARIANT(VT_ARRAY|VT_DISPATCH,[face]))
  m4 isetfaces_plain   ISetFaces(which,1,[face]) (typed, no access)

The decisive signal is count_after: 0 everywhere => binding never takes
(OOP face-set wall / Route-C); >0 but CreateFeature None => binding works,
creation walled.

Usage:  C:/Python314/python.exe spikes/v0_2x/spike_fillet_diag.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2] / "src"))
sys.path.insert(0, str(_HERE.parent))

RESULTS_PATH = _HERE.parents[1] / "_results" / "fillet_diag.json"

import pythoncom
from win32com.client import VARIANT

from _feature_spike_fixtures import build_block

# reuse the lane spike's fixtures/capture helpers (importing does not run main)
from spike_fillet_face_fullround import (
    _block_face_refs,
    _build_slab_on_block,
    _slab_face_refs,
    _null_disp,
    _volume_mm3,
)
from ai_sw_bridge.com.earlybind import typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.selection.live import resolve_manifest_face, select_entity

_SW_FM_FILLET = 1


def _safe(fn: Any) -> Any:
    try:
        v = fn()
        return v() if callable(v) else v
    except Exception as exc:  # noqa: BLE001
        return f"ERR:{type(exc).__name__}:{exc}"


def _new_fd(fm: Any, type_id: int) -> tuple[Any, Any]:
    data = fm.CreateDefinition(_SW_FM_FILLET)
    fd = typed_qi(data, "ISimpleFilletFeatureData2", module=wrapper_module())
    init_ok = fd.Initialize(type_id)
    return fd, init_ok


def _resolve(doc: Any, refs: list[dict]) -> list[Any]:
    out = []
    for ref in refs:
        try:
            res = resolve_manifest_face(doc, ref)
            out.append(getattr(res, "entity", None))
        except Exception as exc:  # noqa: BLE001
            out.append(f"ERR:{exc!r}")
    return out


def _bind_and_create(
    doc: Any,
    fm: Any,
    type_id: int,
    which_list: tuple[int, ...],
    refs: list[dict],
    method: str,
) -> dict:
    rec: dict = {"method": method}
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    # m0 pre-selects on the model BEFORE the definition exists.
    if method == "preselect_marks":
        faces = _resolve(doc, refs)
        for i, (face, which) in enumerate(zip(faces, which_list)):
            if not hasattr(face, "Select2") and not callable(
                getattr(face, "Select2", None)
            ):
                pass
            try:
                select_entity(face, append=(i > 0), mark=which)
            except Exception as exc:  # noqa: BLE001
                rec.setdefault("preselect_err", []).append(f"{which}:{exc!r}")

    fd, init_ok = _new_fd(fm, type_id)
    rec["init_ok"] = init_ok
    rec["type_prop"] = _safe(lambda: fd.Type)

    access_ok = None
    if method.startswith("access_"):
        access_ok = _safe(lambda: fd.AccessSelections(doc, _null_disp()))
    rec["access_ok"] = access_ok

    rec["sets"] = []
    if method != "preselect_marks":
        faces = _resolve(doc, refs)
        for face, which in zip(faces, which_list):
            s: dict = {
                "which": which,
                "face_ok": not (face is None or isinstance(face, str)),
            }
            s["count_before"] = _safe(lambda w=which: fd.GetFaceCount(w))
            try:
                if method in ("access_setfaces",):
                    fd.SetFaces(which, [face])
                elif method in ("setfaces_variant",):
                    fd.SetFaces(
                        which,
                        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [face]),
                    )
                elif method in ("access_isetfaces", "isetfaces_plain"):
                    fd.ISetFaces(which, 1, [face])
                s["set_exc"] = None
            except Exception as exc:  # noqa: BLE001
                s["set_exc"] = repr(exc)
            s["count_after"] = _safe(lambda w=which: fd.GetFaceCount(w))
            rec["sets"].append(s)
    else:
        # readback what pre-selection populated
        for which in which_list:
            rec["sets"].append(
                {
                    "which": which,
                    "count_after": _safe(lambda w=which: fd.GetFaceCount(w)),
                }
            )

    vol_before = _volume_mm3(doc)
    feat = _safe(lambda: fm.CreateFeature(fd))
    rec["feature_return"] = (feat if isinstance(feat, str) else repr(feat))[:90]
    rec["feature_ok"] = (
        not isinstance(feat, str)
        and feat is not None
        and not isinstance(feat, (int, bool))
    )

    if method.startswith("access_"):
        _safe(lambda: fd.ReleaseSelectionAccess())

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    vol_after = _volume_mm3(doc)
    rec["d_vol_mm3"] = round(vol_after - vol_before, 6)
    rec["materialized"] = abs(vol_after - vol_before) > 1e-6
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    return rec


_METHODS = (
    "preselect_marks",
    "access_setfaces",
    "access_isetfaces",
    "setfaces_variant",
    "isetfaces_plain",
)


def _run_type(
    doc: Any, fm: Any, type_id: int, which_list: tuple[int, ...], refs: list[dict]
) -> dict:
    out: dict = {"type_id": type_id, "which_list": list(which_list), "attempts": []}
    for method in _METHODS:
        rec = _bind_and_create(doc, fm, type_id, which_list, refs, method)
        out["attempts"].append(rec)
        if rec.get("materialized"):
            out["WINNER"] = method
            break
    return out


def run() -> dict:
    result: dict = {"spike_id": "W68_fillet_diag"}
    from ai_sw_bridge.sw_com import get_sw_app

    sw = get_sw_app()
    if sw is None:
        return {**result, "overall": "ERROR", "reason": "get_sw_app None"}
    try:
        # FACE fillet (sets 1,2) on a fresh block
        doc_a = build_block(sw)
        fm_a = doc_a.FeatureManager
        pair = _block_face_refs(doc_a)
        if pair is None:
            result["face"] = {"error": "could not capture block faces"}
        else:
            result["face"] = _run_type(doc_a, fm_a, 2, (1, 2), list(pair))

        # FULL-ROUND (sets 3,4,5) on a slab-on-block
        doc_b = build_block(sw)
        fm_b = doc_b.FeatureManager
        if not _build_slab_on_block(doc_b):
            result["full_round"] = {"error": "slab build failed"}
        else:
            triple = _slab_face_refs(doc_b)
            if triple is None:
                result["full_round"] = {"error": "could not capture slab faces"}
            else:
                result["full_round"] = _run_type(
                    doc_b, fm_b, 3, (3, 4, 5), list(triple)
                )

        result["overall"] = "DONE"
        result["face_winner"] = result.get("face", {}).get("WINNER", "NONE")
        result["full_round_winner"] = result.get("full_round", {}).get("WINNER", "NONE")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    return result


def main() -> None:
    pythoncom.CoInitialize()
    try:
        result = run()
    except Exception as exc:  # noqa: BLE001
        result = {
            "spike_id": "W68_fillet_diag",
            "overall": "ERROR",
            "reason": repr(exc),
            "trace": traceback.format_exc(),
        }
    finally:
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(result, indent=2, default=lambda o: f"<{type(o).__name__}>"),
        encoding="utf-8",
    )
    print(f"overall: {result.get('overall')}", file=sys.stderr)
    print(
        f"face_winner: {result.get('face_winner')}  full_round_winner: {result.get('full_round_winner')}",
        file=sys.stderr,
    )
    print(f"results -> {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
