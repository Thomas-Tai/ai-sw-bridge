"""W42 S2 (v2): flat-pattern DXF of a BENT part — built on the W7-proven chain.

S2-v1 NO-GO root cause (isolated by export_dxf_flat_probe.py): the edge flange
silently no-opped (B-rep delta = 0) because the naive longest-linear-edge
capture handed InsertSheetMetalEdgeFlange2 a degenerate profile. The export was
never the bottleneck.

v2 fixes the FIXTURE: it reuses the exact W7 edge-flange PAE build chain
(_build_profile + _build_base_flange + _capture_edge_ref/_find_bendable_edges +
_create_edge_flange) that GREENs Edge-Flange1, then bolts on the dxf_flat export.

Per the W0 contract, the B-rep topology checkpoint GATES the export:

    assert delta_volume_mm3 > 0 AND delta_faces > 0   (the bend exists in 3D)

Only once the bend is strictly verified in 3D do we export the flat pattern and
compare against the flat-plate baseline (S1: 4 entities / 20151 bytes / layer 0).

Verdict GREEN iff: edge flange materialized (ΔVol>0 AND ΔFaces>0) AND export ok
AND the unfolded DXF differs from the flat plate (entity_count > 4 OR a bend
layer is present).

Output: spikes/v0_2x/_results/export_dxf_flat_s2.json
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
_V15 = _HERE.parents[1] / "v0_15"
_V16 = _HERE.parents[1] / "v0_16"
_V17 = _HERE.parents[1] / "v0_17"
for _p in (_SRC, _V15, _V16, _V17):
    sys.path.insert(0, str(_p))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.export.dispatch import _flat_pattern_dxf  # noqa: E402
from ai_sw_bridge.export.formats import EXPORT_FORMATS  # noqa: E402
from ai_sw_bridge.mutate import _create_edge_flange  # noqa: E402
from ai_sw_bridge.cli.export_dxf_flat import _parse_dxf_entities  # noqa: E402

# The W7-proven sheet-metal build chain + edge capture.
from spike_earlybind_persist import connect_running_sw  # noqa: E402
from spike_sheetmetal_v2 import (  # noqa: E402
    SW_DEFAULT_TEMPLATE_PART,
    _build_profile,
    _build_base_flange,
    _title,
)
from edgeflange_pae import _capture_edge_ref  # noqa: E402

_FLAT_PLATE_BASELINE_ENTITIES = 4  # S1 base-flange flat plate
_SW_SOLID_BODY = 0  # swBodyType_e.swSolidBody


def _body_metrics(doc: Any, mod: Any) -> dict[str, Any]:
    """Face count + volume (mm3) of every solid body (the W41 idiom)."""
    out: dict[str, Any] = {"bodies": [], "total_volume_mm3": 0.0, "total_faces": 0}
    try:
        pdoc = typed(doc, "IPartDoc", module=mod)
        bodies = pdoc.GetBodies2(_SW_SOLID_BODY, True)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return out
    if not bodies:
        return out
    for b in bodies:
        rec: dict[str, Any] = {}
        try:
            mp = b.GetMassProperties(1.0)
            rec["volume_mm3"] = round(float(mp[3]) * 1e9, 3) if mp and len(mp) > 3 else None
        except Exception:
            rec["volume_mm3"] = None
        fc = None
        try:
            raw = b.GetFaceCount
            fc = raw() if callable(raw) else int(raw)
        except Exception:
            try:
                faces = b.GetFaces()
                fc = len(faces) if faces else 0
            except Exception:
                fc = None
        rec["faces"] = fc
        out["bodies"].append(rec)
        if rec.get("volume_mm3"):
            out["total_volume_mm3"] += rec["volume_mm3"]
        if rec.get("faces"):
            out["total_faces"] += rec["faces"]
    out["total_volume_mm3"] = round(out["total_volume_mm3"], 3)
    out["body_count"] = len(bodies)
    return out


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "wave": "W42",
        "step": "S2_bent_fixture_v2",
        "format": "dxf_flat",
        "flat_plate_baseline_entities": _FLAT_PLATE_BASELINE_ENTITIES,
        "ok": False,
        "verdict": "FAIL",
    }
    doc = None
    sw = None
    try:
        mod = wrapper_module()
        sw = connect_running_sw()

        # --- Build the base flange via the W7-proven chain ---
        template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            out["error"] = "NewDocument returned None"
            raise SystemExit(_finish(out))
        fm = doc.FeatureManager

        print("[s2] building base flange (W7 chain)...")
        prof = _build_profile(doc)
        if not prof.get("built"):
            out["error"] = "profile sketch failed"
            raise SystemExit(_finish(out))
        base = _build_base_flange(doc, fm, mod)
        if base.get("overall") != "PASS":
            out["error"] = f"base flange failed: {base.get('overall')}"
            raise SystemExit(_finish(out))
        doc.ForceRebuild3(False)

        # --- AXIS-1 checkpoint: metrics BEFORE the edge flange ---
        before = _body_metrics(doc, mod)
        out["brep_before"] = before
        print("[s2] before: bodies=%s vol=%s faces=%s" % (
            before.get("body_count"), before.get("total_volume_mm3"),
            before.get("total_faces")))

        # --- Capture a BENDABLE boundary edge (W7 _find_bendable_edges) ---
        edge_ref, edge_diag = _capture_edge_ref(doc, mod)
        out["edge_diag"] = edge_diag
        if edge_ref is None:
            out["error"] = "no bendable edge captured"
            raise SystemExit(_finish(out))
        print("[s2] edge captured: %.1f mm" % (edge_diag.get("best_len_mm") or 0.0))

        # --- Materialize the edge flange (the bend) ---
        ok_ef, ef_err = _create_edge_flange(
            doc,
            {"type": "edge_flange", "height_mm": 20, "angle_deg": 90, "radius_mm": 2},
            {"edge_ref": edge_ref},
        )
        out["edge_flange_ok"] = ok_ef
        out["edge_flange_err"] = ef_err
        if not ok_ef:
            out["error"] = f"edge flange handler returned not-ok: {ef_err}"
            raise SystemExit(_finish(out))
        doc.ForceRebuild3(False)

        # --- AXIS-1 checkpoint: metrics AFTER + the GATING assertion ---
        after = _body_metrics(doc, mod)
        out["brep_after"] = after
        d_vol = round((after.get("total_volume_mm3") or 0)
                      - (before.get("total_volume_mm3") or 0), 3)
        d_faces = (after.get("total_faces") or 0) - (before.get("total_faces") or 0)
        out["brep_delta"] = {"volume_mm3": d_vol, "faces": d_faces}
        bend_in_3d = d_vol > 0 and d_faces > 0
        out["bend_exists_in_3d"] = bend_in_3d
        print("[s2] AXIS1 checkpoint: d_vol=%s d_faces=%s -> bend_in_3d=%s"
              % (d_vol, d_faces, bend_in_3d))
        if not bend_in_3d:
            out["error"] = (
                "B-rep checkpoint FAILED: the edge flange did not change the "
                f"3D body (d_vol={d_vol}, d_faces={d_faces}). Abort before export."
            )
            out["verdict"] = "NO-GO"
            raise SystemExit(_finish(out))

        # --- Save the bent part so the flat-pattern export has a SourceFile ---
        tmp = Path(tempfile.mkdtemp(prefix="w42_s2v2_"))
        part_path = tmp / "W42_bent_fixture.SLDPRT"
        err = doc.SaveAs3(str(part_path), 0, 0)
        if (int(err) if err is not None else 0) != 0:
            out["error"] = f"SaveAs3(bent part) returned {err}"
            raise SystemExit(_finish(out))

        # --- Export the flat pattern of the (verified) BENT part ---
        print("[s2] exporting flat-pattern DXF of the bent part...")
        dxf_path = tmp / "W42_bent_flat.dxf"
        exp = _flat_pattern_dxf(doc, EXPORT_FORMATS["dxf_flat"], dxf_path)
        out["export"] = exp.to_dict()
        if not exp.ok:
            out["error"] = f"flat-pattern export failed: {exp.error}"
            raise SystemExit(_finish(out))

        # --- Verify-the-BYTES vs the flat-plate baseline ---
        ent = _parse_dxf_entities(dxf_path.read_text(encoding="utf-8", errors="replace"))
        out["dxf_verify"] = {
            "entities_section_found": ent["entities_section_found"],
            "entity_count": ent["entity_count"],
            "entity_types": ent["entity_types"],
            "layers": ent["layers"],
            "has_bend_layer": ent["has_bend_layer"],
            "file_size_bytes": dxf_path.stat().st_size,
        }
        out["bend_dxf_path"] = str(dxf_path)

        grew = ent["entity_count"] > _FLAT_PLATE_BASELINE_ENTITIES
        out["entity_count_exceeds_flat_plate"] = grew
        out["ok"] = bool(
            exp.ok and ent["entities_section_found"]
            and (grew or ent["has_bend_layer"])
        )
        out["verdict"] = "GREEN" if out["ok"] else "NO-GO"
        print("[s2] %s: entities=%d(>%d=%s) bend_layer=%s size=%d layers=%s" % (
            out["verdict"], ent["entity_count"], _FLAT_PLATE_BASELINE_ENTITIES,
            grew, ent["has_bend_layer"], dxf_path.stat().st_size, ent["layers"]))

    except SystemExit:
        raise
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()
        print("[s2] EXCEPTION: %s" % exc)
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
    p = res / "export_dxf_flat_s2.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[s2] wrote {p}")
    print(f"[s2] verdict: {out.get('verdict')}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
