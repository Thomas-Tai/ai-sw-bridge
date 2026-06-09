"""W42 disambiguation probe — does the W7 edge_flange actually create geometry?

S2-v2 NO-GO: even the W7-proven chain returned edge_flange ok=True with ZERO
B-rep delta (4800mm3/6faces -> 4800mm3/6faces), yet edgeflange_pae.py reports
Edge-Flange1(EdgeFlange) present + GREEN. The W7 proof is feature-node presence,
NOT geometry. This probe resolves the contradiction by replicating the EXACT,
unmodified edgeflange_pae flow (same helpers, same params height_mm=10) and
injecting ONLY topological telemetry + feature error-state extraction.

Branching (per W0 contract):
  * dVol > 0 AND dFaces > 0  -> W7 handler is sound; the S2 harness is the
    fracture (NOT this probe, which mirrors the bare PAE). Fix S2, ship W42.
  * dVol == 0                -> the shipped edge_flange creates an errored/
    ghost feature node; freeze edge_flange, ticket it, decouple dxf_flat.

Writes spikes/v0_2x/_results/edgeflange_brep_probe.json.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _p in (_HERE.parents[2] / "src", _HERE.parents[1] / "v0_15",
           _HERE.parents[1] / "v0_16", _HERE.parents[1] / "v0_17"):
    sys.path.insert(0, str(_p))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.mutate import _create_edge_flange  # noqa: E402

from spike_earlybind_persist import connect_running_sw  # noqa: E402
from spike_sheetmetal_v2 import (  # noqa: E402
    SW_DEFAULT_TEMPLATE_PART,
    _build_profile,
    _build_base_flange,
)
from edgeflange_pae import _capture_edge_ref  # noqa: E402

_SW_SOLID_BODY = 0


def _metrics(doc: Any, mod: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"vol_mm3": 0.0, "faces": 0, "bodies": 0}
    try:
        pdoc = typed(doc, "IPartDoc", module=mod)
        bodies = pdoc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:160]
        return out
    if not bodies:
        return out
    out["bodies"] = len(bodies)
    for b in bodies:
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                out["vol_mm3"] += float(mp[3]) * 1e9
        except Exception:
            pass
        try:
            raw = b.GetFaceCount
            out["faces"] += raw() if callable(raw) else int(raw)
        except Exception:
            try:
                out["faces"] += len(b.GetFaces() or [])
            except Exception:
                pass
    out["vol_mm3"] = round(out["vol_mm3"], 3)
    return out


def _edgeflange_feature_state(doc: Any, mod: Any) -> dict[str, Any]:
    """Find the EdgeFlange feature node + read its error/suppression state."""
    st: dict[str, Any] = {"present": False}
    try:
        raw = doc.GetFeatureCount
        count = raw(True) if callable(raw) else int(raw)
    except Exception:
        return st
    for i in range(count):
        try:
            feat = doc.FeatureByPositionReverse(i)
        except Exception:
            break
        if feat is None:
            break
        try:
            tn = feat.GetTypeName2
            tn = tn() if callable(tn) else str(tn)
        except Exception:
            try:
                tn = feat.GetTypeName
                tn = tn() if callable(tn) else str(tn)
            except Exception:
                tn = ""
        if tn != "EdgeFlange":
            continue
        st["present"] = True
        try:
            nm = feat.Name
            st["name"] = nm() if callable(nm) else str(nm)
        except Exception:
            st["name"] = "?"
        tf = typed(feat, "IFeature", module=mod)
        # Try every plausible error-state accessor; guard each (out-param risk).
        for meth in ("GetErrorCode2", "GetErrorCode"):
            try:
                fn = getattr(tf, meth, None)
                if fn is not None:
                    st[meth] = fn()
            except Exception as exc:
                st[meth + "_exc"] = f"{type(exc).__name__}: {exc}"[:100]
        try:
            st["is_suppressed"] = bool(tf.IsSuppressed())
        except Exception:
            pass
        break
    return st


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {"wave": "W42", "step": "edgeflange_brep_disambiguation"}
    doc = None
    sw = None
    try:
        mod = wrapper_module()
        sw = connect_running_sw()
        template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        fm = doc.FeatureManager

        # EXACT edgeflange_pae build chain.
        prof = _build_profile(doc)
        base = _build_base_flange(doc, fm, mod)
        out["base_flange"] = base.get("overall")
        if base.get("overall") != "PASS":
            out["error"] = "base flange failed"
            raise SystemExit(_finish(out))
        doc.ForceRebuild3(False)

        before = _metrics(doc, mod)
        out["before"] = before
        print("[probe] before: vol=%s faces=%s" % (before["vol_mm3"], before["faces"]))

        edge_ref, edge_diag = _capture_edge_ref(doc, mod)
        out["edge_diag"] = edge_diag
        if edge_ref is None:
            out["error"] = "no edge captured"
            raise SystemExit(_finish(out))

        # EXACT edgeflange_pae params (height_mm=10, angle_deg=90, radius_mm=2).
        ok_ef, ef_err = _create_edge_flange(
            doc,
            {"type": "edge_flange", "height_mm": 10, "angle_deg": 90, "radius_mm": 2},
            {"edge_ref": edge_ref},
        )
        out["edge_flange_ok"] = ok_ef
        out["edge_flange_err"] = ef_err
        doc.ForceRebuild3(False)

        # Rebuild-error signal: EditRebuild3 returns False on rebuild error.
        try:
            out["edit_rebuild3_ok"] = bool(doc.EditRebuild3())
        except Exception as exc:
            out["edit_rebuild3_exc"] = f"{type(exc).__name__}: {exc}"[:120]

        after = _metrics(doc, mod)
        out["after"] = after
        d_vol = round(after["vol_mm3"] - before["vol_mm3"], 3)
        d_faces = after["faces"] - before["faces"]
        out["delta"] = {"vol_mm3": d_vol, "faces": d_faces}
        out["bend_in_3d"] = d_vol > 0 and d_faces > 0
        print("[probe] after:  vol=%s faces=%s -> dVol=%s dFaces=%s"
              % (after["vol_mm3"], after["faces"], d_vol, d_faces))

        out["edgeflange_feature"] = _edgeflange_feature_state(doc, mod)
        print("[probe] edgeflange feature: %s" % out["edgeflange_feature"])

        if out["bend_in_3d"]:
            out["verdict"] = "HANDLER_SOUND_HARNESS_FRACTURE"
        else:
            out["verdict"] = "GHOST_FEATURE_SHIPPED_NOOP"
        print("[probe] VERDICT: %s" % out["verdict"])

    except SystemExit:
        raise
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()
        print("[probe] EXCEPTION: %s" % exc)
    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        pythoncom.CoUninitialize()
    return _finish(out)


def _finish(out: dict) -> int:
    res = Path(__file__).resolve().parent / "_results"
    res.mkdir(parents=True, exist_ok=True)
    p = res / "edgeflange_brep_probe.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[probe] wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
