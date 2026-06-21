"""W68 FACE fillet — certification probe (W0 seat, Option-1 split).

The binding diagnostic proved the face-set wall was a makepy SAFEARRAY-of-
IDispatch marshaling boundary, NOT a Parasolid refusal: SetFaces with a bare
Python list silently no-ops (GetFaceCount stays 0), but SetFaces with a typed
``VARIANT(VT_ARRAY|VT_DISPATCH, [face])`` binds (GetFaceCount -> 1) and the
kernel builds the fillet (dVol != 0).  CreateFeature raised DISP_E_MEMBERNOTFOUND
on its RETURN even though the solid was built — COM return-marshaling noise to
be swallowed; the volume delta + reopen survival are the real witnesses.

This probe certifies the FACE fillet shippable:
  * block fixture, 2 adjacent face-sets (top + +x side)
  * Initialize(swFaceFillet=2), DefaultRadius=3mm
  * SetFaces via VARIANT array, assert GetFaceCount==1 per set
  * CreateFeature wrapped (swallow the -2147352573 return noise)
  * DURABILITY GATE: |dVol| > eps AND GetTypeName2 ~ fillet AND survives
    save/close/reopen with the volume delta preserved.

Verdict PASS only if the reopened doc still carries the volume delta and a
fillet-typed feature.  Usage: C:/Python314/python.exe spikes/v0_2x/spike_fillet_face_cert.py
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

RESULTS_PATH = _HERE.parents[1] / "_results" / "fillet_face_cert.json"

import pythoncom
from win32com.client import VARIANT

from _feature_spike_fixtures import build_block, save_and_reopen
from spike_fillet_face_fullround import (
    _block_face_refs,
    _volume_mm3,
    _type_name,
    _latest_feature,
)
from ai_sw_bridge.com.earlybind import typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.selection.live import resolve_manifest_face

_SW_FM_FILLET = 1
_SW_FACE_FILLET = 2
_MEMBER_NOT_FOUND = -2147352573


def _face_array(face: Any) -> Any:
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [face])


def _find_feature_type(doc: Any, substr: str) -> str | None:
    """Walk GetFeatures(False), re-typing each node, return the GetTypeName2 of
    the first node whose type contains ``substr`` (case-insensitive).  Needed
    because GetFeatures()[-1] is the scene-lighting node, not the newest geom.
    """
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return None
    if not feats:
        return None
    for f in feats:
        tn = _type_name(f)
        if tn and substr.lower() in tn.lower():
            return tn
    return None


def run() -> dict:
    result: dict = {"spike_id": "W68_fillet_face_cert"}
    from ai_sw_bridge.sw_com import get_sw_app
    sw = get_sw_app()
    if sw is None:
        return {**result, "overall": "ERROR", "reason": "get_sw_app None"}

    try:
        doc = build_block(sw)
        pair = _block_face_refs(doc)
        if pair is None:
            return {**result, "overall": "ERROR", "reason": "could not capture block faces"}

        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_FILLET)
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=wrapper_module())
        result["init_ok"] = fd.Initialize(_SW_FACE_FILLET)
        fd.DefaultRadius = 0.003  # 3 mm

        # bind the two face-sets via the VARIANT-array fix
        bind: list[dict] = []
        for ref, which in zip(pair, (1, 2)):
            res = resolve_manifest_face(doc, ref)
            entity = getattr(res, "entity", None)
            rec = {"which": which, "resolved": entity is not None}
            if entity is not None:
                fd.SetFaces(which, _face_array(entity))
            try:
                rec["count_after"] = fd.GetFaceCount(which)
            except Exception as exc:  # noqa: BLE001
                rec["count_after"] = f"ERR:{exc!r}"
            bind.append(rec)
        result["bind"] = bind
        if any(b.get("count_after") != 1 for b in bind):
            return {**result, "overall": "FAIL", "reason": "face-sets did not bind (count != 1)"}

        vol_before = _volume_mm3(doc)
        result["vol_before_mm3"] = round(vol_before, 6)

        # CreateFeature — swallow the DISP_E_MEMBERNOTFOUND return noise.
        create_note = "ok"
        feat = None
        try:
            feat = fm.CreateFeature(fd)
            result["feature_return"] = repr(feat)[:90]
        except pythoncom.com_error as exc:
            hr = exc.args[0] if exc.args else None
            create_note = f"com_error swallowed hr={hr}"
            if hr != _MEMBER_NOT_FOUND:
                create_note = f"UNEXPECTED com_error hr={hr} ({exc!r})"
        except Exception as exc:  # noqa: BLE001
            create_note = f"UNEXPECTED {type(exc).__name__}: {exc}"
        result["create_note"] = create_note
        # type-name witness — read off the RETURNED feature handle (the
        # GetFeatures()[-1] node is scene lighting, not the fillet)
        result["returned_feature_type"] = _type_name(feat) if feat is not None else None

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass
        vol_after = _volume_mm3(doc)
        result["vol_after_mm3"] = round(vol_after, 6)
        result["d_vol_mm3"] = round(vol_after - vol_before, 6)
        result["materialized"] = abs(vol_after - vol_before) > 1e-6

        # corroborate by walking the tree for a Fillet-typed node
        result["tree_fillet_type"] = _find_feature_type(doc, "fillet")

        # DURABILITY GATE — save / close / reopen
        try:
            doc2 = save_and_reopen(sw, doc)
            if doc2 is not None:
                result["survives_reopen"] = True
                result["vol_after_reopen_mm3"] = round(_volume_mm3(doc2), 6)
                result["reopen_feature_type"] = _find_feature_type(doc2, "fillet")
            else:
                result["survives_reopen"] = False
        except Exception as exc:  # noqa: BLE001
            result["survives_reopen"] = False
            result["reopen_error"] = f"{type(exc).__name__}: {exc}"

        # verdict — type witness from the returned handle OR the tree walk
        tname = (result.get("returned_feature_type") or result.get("tree_fillet_type") or "").lower()
        type_ok = "fillet" in tname
        reopen_vol = result.get("vol_after_reopen_mm3")
        reopen_preserved = (
            result.get("survives_reopen")
            and reopen_vol is not None
            and abs(float(reopen_vol) - vol_after) < 1e-3
        )
        rtname = (result.get("reopen_feature_type") or "").lower()
        reopen_type_ok = "fillet" in rtname
        if result["materialized"] and type_ok and reopen_preserved and reopen_type_ok:
            result["overall"] = "PASS"
        elif result["materialized"] and type_ok:
            result["overall"] = "WEAK_PASS"
        else:
            result["overall"] = "FAIL"
        result["finding"] = (
            f"materialized={result['materialized']} dVol={result.get('d_vol_mm3')} "
            f"type={result.get('returned_feature_type')} reopen={result.get('survives_reopen')} "
            f"reopen_type={result.get('reopen_feature_type')}"
        )
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
        result = {"spike_id": "W68_fillet_face_cert", "overall": "ERROR",
                  "reason": repr(exc), "trace": traceback.format_exc()}
    finally:
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=lambda o: f"<{type(o).__name__}>"), encoding="utf-8")
    print(f"overall: {result.get('overall')}", file=sys.stderr)
    print(f"finding: {result.get('finding')}", file=sys.stderr)
    print(f"results -> {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
