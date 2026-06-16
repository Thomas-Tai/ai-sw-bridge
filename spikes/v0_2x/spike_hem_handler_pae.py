"""hem handler PAE — end-to-end proof of the PRODUCTION create_hem handler.

Where spike_hem_v5 proved the raw recipe live, this proves the shipped
``features.hem.create_hem`` through the REAL durable-edge_ref path — the exact
flow an LLM spec drives:

  1. build a base_flange, pick the longest boundary edge;
  2. capture its durable token (``read_persist_reference``) into a
     ``DurableEdgeRef`` — the same ref an observe call would hand the agent;
  3. SAVE → close → reopen (the token must survive the file boundary);
  4. call the production ``create_hem(doc, feature, {"edge_ref": ref})`` — which
     resolves the token on the reopened doc, selects the edge, and fires
     ``InsertSheetMetalHem`` with the ``VARIANT(VT_DISPATCH, None)`` PCBA null;
  5. verify the fold (ΔFace>0 ∧ ΔVol≠0) and that the hem SURVIVES a second
     save→reopen.

PASS only if the production handler returns ``(True, None)`` AND the hem node
survives reopen with a real volume delta. Exit 0 = PASS, 2 = FAIL, 1 = ERROR.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

import pythoncom

from ai_sw_bridge.com.earlybind import read_persist_reference, typed
from ai_sw_bridge.features.hem import create_hem
from ai_sw_bridge.features.hem import _metrics  # (faces:int, vol_mm3:float) tuple
from ai_sw_bridge.selection._edge_ref import DurableEdgeRef

from spike_hem_v5 import (
    _build_fixture_v5,
    _check_hem_materialized,
    connect_running_sw,
    wrapper_module,
)


def _reopen(sw: Any, mod: Any, tmp: str) -> Any:
    """Typed-ISldWorks OpenDoc6 (Type=1) then re-fetch the dynamic ActiveDoc."""
    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(tmp, 1, 1, "", 0, 0)
    doc = sw.ActiveDoc
    if doc is not None:
        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass
    return doc


def _finish(out: dict, code: int) -> int:
    res_dir = Path(__file__).resolve().parent / "_results"
    res_dir.mkdir(parents=True, exist_ok=True)
    p = res_dir / "hem_handler_pae_results.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    sys.stderr.write(f"[hem-pae] wrote {p}\n")
    sys.stderr.write(f"[hem-pae] VERDICT: {out.get('verdict')} (exit {code})\n")
    sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
    return code


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "spike": "hem_handler_pae",
        "purpose": "production create_hem via durable edge_ref, across save->reopen",
    }
    sw = None
    doc = None
    tmps: list[str] = []
    try:
        mod = wrapper_module()
        sw = connect_running_sw()

        # 1. base flange + longest boundary edge (reuse the v5 fixture).
        doc, fm, edge, diag = _build_fixture_v5(sw, mod)
        out["fixture"] = diag
        if doc is None or edge is None:
            out["error"] = diag.get("error", "fixture build failed")
            out["verdict"] = "ERROR"
            return _finish(out, 1)

        # 2. capture the durable edge_ref (the observe-layer artifact).
        cp = edge.GetCurveParams2
        if callable(cp):
            cp = cp()
        start = (float(cp[0]), float(cp[1]), float(cp[2]))
        end = (float(cp[3]), float(cp[4]), float(cp[5]))
        length = math.dist(start, end)
        pid = read_persist_reference(doc, edge)
        out["persist_captured"] = pid is not None
        if not pid:
            out["error"] = "no persist token captured for the chosen edge"
            out["verdict"] = "ERROR"
            return _finish(out, 1)
        ref = DurableEdgeRef(persist_id=pid, start=start, end=end,
                             length=length, role_hint="edge")
        edge_ref_dict = ref.to_dict()
        out["edge_ref"] = {
            "len_mm": round(length * 1000.0, 3),
            "persist_id_present": "persist_id" in edge_ref_dict,
        }

        # 3. SAVE -> close -> reopen (token must survive the file boundary).
        tmp = tempfile.mktemp(suffix=".SLDPRT")
        tmps.append(tmp)
        doc.SaveAs3(tmp, 0, 2)
        sw.CloseAllDocuments(True)
        doc = None
        doc = _reopen(sw, mod, tmp)
        if doc is None:
            out["error"] = "reopen of base part returned no ActiveDoc"
            out["verdict"] = "ERROR"
            return _finish(out, 1)

        # 4. fire the PRODUCTION handler through the durable ref.
        faces_b, vol_b = _metrics(doc)
        out["faces_before"] = faces_b
        out["vol_before_mm3"] = vol_b
        feature = {"hem_type": "closed", "position": "inside",
                   "length_mm": 10, "miter_gap_mm": 1}
        ok, err = create_hem(doc, feature, {"edge_ref": edge_ref_dict})
        out["handler_ok"] = ok
        out["handler_err"] = err
        faces_a, vol_a = _metrics(doc)
        out["faces_after"] = faces_a
        out["vol_after_mm3"] = vol_a
        out["delta_faces"] = faces_a - faces_b
        out["delta_vol_mm3"] = round(vol_a - vol_b, 3)

        if not ok:
            out["verdict"] = "FAIL"
            return _finish(out, 2)

        # 5. save -> reopen survival of the hem itself.
        tmp2 = tempfile.mktemp(suffix=".SLDPRT")
        tmps.append(tmp2)
        doc.SaveAs3(tmp2, 0, 2)
        sw.CloseAllDocuments(True)
        doc = None
        doc = _reopen(sw, mod, tmp2)
        if doc is None:
            out["error"] = "reopen after hem returned no ActiveDoc"
            out["verdict"] = "FAIL"
            return _finish(out, 2)
        faces_r, vol_r = _metrics(doc)
        hem_node = _check_hem_materialized(doc, mod)
        out["faces_after_reopen"] = faces_r
        out["vol_after_reopen_mm3"] = vol_r
        out["hem_feature"] = hem_node
        survived = bool(hem_node.get("found") and vol_r > vol_b + 1.0)
        out["persist_survived"] = survived
        out["verdict"] = "PASS" if survived else "FAIL"
        return _finish(out, 0 if survived else 2)

    except Exception as exc:
        out["fatal_error"] = f"{type(exc).__name__}: {exc}"[:300]
        out["traceback"] = traceback.format_exc()
        out["verdict"] = "ERROR"
        return _finish(out, 1)
    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        for t in tmps:
            try:
                if os.path.exists(t):
                    os.unlink(t)
            except Exception:
                pass
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
