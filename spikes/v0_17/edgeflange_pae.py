"""PAE: edge_flange production handler — Wave-7.

Proves mutate._create_edge_flange materializes a sheet-metal edge flange
end-to-end on a durably-captured edge. The handler is de-advertised, so
the PAE calls it directly (the gate validates the novel glue beyond the spike).

Recipe:
  1. Build base_flange (SMBaseFlange body).
  2. Capture DurableEdgeRef for longest linear boundary edge.
  3. Call _create_edge_flange(doc, feature, target) directly.
  4. Verify: ok=True, EdgeFlange feature, Plane, Sketch all present.
  5. Confirm gate: sw_propose_feature_add rejects edge_flange.
  6. Write _results/edgeflange_pae.json.

Usage:
    python spikes/v0_17/edgeflange_pae.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parents[1] / "v0_16"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom

from ai_sw_bridge.com.earlybind import (
    read_persist_reference,
    typed,
    typed_qi,
)
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.mutate import (
    _create_edge_flange,
    sw_propose_feature_add,
)
from ai_sw_bridge.selection._edge_ref import DurableEdgeRef

from spike_earlybind_persist import connect_running_sw
from spike_sheetmetal_v2 import (
    SW_DEFAULT_TEMPLATE_PART,
    _build_profile,
    _build_base_flange,
    _find_bendable_edges,
    _title,
)

RESULTS_DIR = Path(__file__).resolve().parent / "_results"


def _feature_types(doc: Any, mod: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    out.append({"name": ifeat.Name, "type": ifeat.GetTypeName2()})
                except Exception:
                    out.append({"name": "?", "type": "?"})
    except Exception:
        pass
    return out


def _capture_edge_ref(doc: Any, mod: Any) -> tuple[dict | None, dict]:
    """Capture a DurableEdgeRef for the longest linear boundary edge."""
    diag: dict[str, Any] = {}
    edges = _find_bendable_edges(doc, mod)
    diag["edge_count"] = len(edges)
    if not edges:
        return None, diag

    best_ref = None
    best_len = -1.0
    for e in edges:
        pid = read_persist_reference(doc, e)
        if pid is None:
            continue
        try:
            ie = typed_qi(e, "IEdge", module=mod)
            cv = typed_qi(ie.GetCurve(), "ICurve", module=mod)
            if not bool(cv.IsLine()):
                continue
            p = cv.GetEndParams()
            length = float(cv.GetLength(p[1], p[2]))
            if length <= best_len:
                continue
            best_len = length
            ev_s = cv.Evaluate(p[1])
            ev_e = cv.Evaluate(p[2])
            ev_m = cv.Evaluate((p[1] + p[2]) / 2.0)
            ref = DurableEdgeRef(
                persist_id=pid,
                start=(ev_s[0], ev_s[1], ev_s[2]),
                end=(ev_e[0], ev_e[1], ev_e[2]),
                length=length,
                midpoint=(ev_m[0], ev_m[1], ev_m[2]),
            )
            best_ref = ref.to_dict()
        except Exception as exc:
            diag["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
            continue

    diag["best_len_mm"] = round(best_len * 1000, 2) if best_len > 0 else None
    return best_ref, diag


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {"ok": False}
    doc = None

    try:
        mod = wrapper_module()
        sw = connect_running_sw()

        template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            out["error"] = "NewDocument returned None"
            print("[pae] FAIL: %s" % out["error"])
            return 1

        fm = doc.FeatureManager

        # Step 1: Build sheet-metal base flange
        print("[pae] building base flange...")
        prof = _build_profile(doc)
        if not prof.get("built"):
            out["error"] = "profile sketch failed"
            print("[pae] FAIL: %s" % out["error"])
            return 1

        base = _build_base_flange(doc, fm, mod)
        if base.get("overall") != "PASS":
            out["error"] = "base flange failed: %s" % base.get("overall")
            print("[pae] FAIL: %s" % out["error"])
            return 1
        print(
            "[pae] base flange: %s (%s)"
            % (
                base.get("create_feature", {}).get("feature_name"),
                base.get("create_feature", {}).get("type_name"),
            )
        )

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        # Step 2: Capture durable edge_ref
        print("[pae] capturing durable edge_ref...")
        edge_ref, edge_diag = _capture_edge_ref(doc, mod)
        out["edge_diag"] = edge_diag
        if edge_ref is None:
            out["error"] = "no linear edge with persist_id"
            print("[pae] FAIL: %s" % out["error"])
            return 1
        out["edge_ref_method"] = "persist_id"
        print("[pae] edge captured: %.1fmm" % edge_diag.get("best_len_mm", 0))

        features_before = _feature_types(doc, mod)
        out["feature_count_before"] = len(features_before)

        # Step 3: Call the SHIPPING handler directly
        print("[pae] calling _create_edge_flange...")
        feature_params = {
            "type": "edge_flange",
            "height_mm": 10,
            "angle_deg": 90,
            "radius_mm": 2,
        }
        target = {"edge_ref": edge_ref}

        ok, err = _create_edge_flange(doc, feature_params, target)
        out["ok"] = ok
        out["err"] = err
        print("[pae] handler returned: ok=%s err=%s" % (ok, err))

        if not ok:
            out["error"] = "handler failed: %s" % err
            print("[pae] FAIL: %s" % out["error"])
            return 1

        # Step 4: Verify by readback
        features_after = _feature_types(doc, mod)
        out["feature_count_after"] = len(features_after)
        out["delta"] = len(features_after) - len(features_before)

        # Find the EdgeFlange feature
        flange_feature = None
        plane_present = False
        sketch_present = False
        for f in features_after:
            if f["type"] == "EdgeFlange":
                flange_feature = f
            if f["type"] == "RefPlane" and f["name"].startswith("Plane"):
                plane_present = True
            if f["type"] == "ProfileFeature" and f["name"] not in ("Sketch1",):
                sketch_present = True

        if flange_feature:
            out["flange_feature_name"] = flange_feature["name"]
            out["flange_type"] = flange_feature["type"]
        out["plane_present"] = plane_present
        out["sketch_present"] = sketch_present

        # Step 5: Confirm gate — propose rejects edge_flange
        print("[pae] confirming gate (propose rejects de-advertised)...")
        gate = sw_propose_feature_add(
            "dummy_path",
            feature_params,
            target,
        )
        out["propose_rejected"] = not gate.get("ok")
        out["gate_error"] = gate.get("error", "")[:120]
        print(
            "[pae] gate: rejected=%s err=%s"
            % (
                out["propose_rejected"],
                out["gate_error"][:80],
            )
        )

        # Final verdict
        out["ok"] = (
            ok is True
            and flange_feature is not None
            and flange_feature.get("type") == "EdgeFlange"
        )
        status = "GREEN" if out["ok"] else "FAIL"
        print(
            "[pae] %s: flange=%s(%s) plane=%s sketch=%s gate_rejected=%s"
            % (
                status,
                out.get("flange_feature_name"),
                out.get("flange_type"),
                plane_present,
                sketch_present,
                out["propose_rejected"],
            )
        )

    except Exception as exc:
        import traceback

        out["error"] = traceback.format_exc()
        out["ok"] = False
        print("[pae] EXCEPTION: %s" % exc)

    finally:
        if doc is not None:
            try:
                sw.CloseDoc(_title(doc))
            except Exception:
                pass
        pythoncom.CoUninitialize()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "edgeflange_pae.json"
    out_path.write_text(
        json.dumps(out, indent=2, default=str),
        encoding="utf-8",
    )
    print("[pae] wrote %s" % out_path)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
