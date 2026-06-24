"""Spike v0.16 / WIZHOLE-DURABLE — place a wizard hole on a DURABLY-RESOLVED
face (persist-id + fingerprint), not a raw coordinate pick.

The two halves are each already seat-proven and shipped:
  * resolve_manifest_face (selection.live) — persist→fingerprint hierarchy to a
    live face entity (S-PERSIST / S-EARLYBIND GREEN).
  * the wizard-hole pipeline CreateDefinition(25)→typed_qi→InitializeHole→
    CreateFeature (spike_wizhole_v5 = PASS, shipped _create_wizard_hole).

The ONE unproven integration risk this spike isolates: in v1 the placement
sketch is created on a face selected by SelectByID("","FACE",x,y,z). For the
durable upgrade the face arrives as a resolved IEntity selected via
select_entity (IEntity.Select2). Does InsertSketch build the sketch on a face
selected that way, so the hole materializes? PASS proves the durable face-ref
placement path is sound; then _create_wizard_hole can adopt it.

Bonus durability check: capture the face ref, ForceRebuild3, THEN resolve — so
the persist token is exercised across a rebuild (the realistic case).

Non-destructive: own blank Part, never saves, closes own doc.
Usage:  .venv-py310\Scripts\python spikes\v0_16\spike_wizhole_durable.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge import mutate  # noqa: E402
from ai_sw_bridge.brep.interrogator import read_face_geometry  # noqa: E402
from ai_sw_bridge.com.earlybind import typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.selection import resolve_manifest_face, select_entity  # noqa: E402
from ai_sw_bridge.selection.live import capture_persist_id  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

BOX_W_M, BOX_H_M, BOX_D_M = 0.040, 0.040, 0.020
SW_DEFAULT_TEMPLATE_PART = 8

# Hole spec: ANSI Metric / Drill sizes — proven set from the wizhole work.
HOLE_TYPE = "hole"  # generic drilled hole
STANDARD = "ANSI Metric"
FASTENER = "Drill Sizes"
SIZE = "Ø6.0"  # Ø6.0 — a valid Drill Sizes entry (DB-confirmed)


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box(doc: Any) -> bool:
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
    )
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base = (
        True,
        False,
        False,
        0,
        0,
        BOX_D_M,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return feat is not None


def _capture_face_ref(doc: Any, x: float, y: float, z: float, role: str) -> dict | None:
    """Pick the face at (x,y,z), capture its persist token + fingerprint geom,
    and serialize a manifest-face dict (the durable face_ref)."""
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    if not doc.SelectByID("", "FACE", x, y, z):
        return None
    face = doc.SelectionManager.GetSelectedObject6(1, -1)
    if face is None:
        return None
    geom = read_face_geometry(face)
    if geom is None:
        return None
    pid = capture_persist_id(doc, face)
    ref: dict[str, Any] = {
        "normal": list(geom["normal"]),
        "centroid": list(geom["centroid"]),
        "area_mm2": geom["area_mm2"],
        "role_hint": role,
    }
    if pid is not None:
        ref["persist_id"] = base64.urlsafe_b64encode(pid).decode("ascii").rstrip("=")
    return ref


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    report: dict[str, Any] = {}
    try:
        report["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        report["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument None", **report}
    title = _title(doc)
    try:
        if not _build_box(doc):
            return {"overall": "FAIL", "reason": "box build failed", **report}
        doc.ForceRebuild3(False)

        # 1. Capture the +Z top face as a durable ref.
        face_ref = _capture_face_ref(doc, 0.0, 0.0, BOX_D_M, "+z_top")
        report["captured_ref"] = {
            "has_persist": face_ref is not None and "persist_id" in face_ref,
            "role": (face_ref or {}).get("role_hint"),
        }
        if face_ref is None:
            return {"overall": "FAIL", "reason": "could not capture face ref", **report}

        # 2. Rebuild THEN resolve — exercise the token across a rebuild.
        doc.ForceRebuild3(False)
        res = resolve_manifest_face(doc, face_ref)
        report["resolve"] = {
            "method": res.method,
            "resolved": res.entity is not None,
            "note": res.note,
        }
        if res.entity is None:
            return {"overall": "FAIL", "reason": "face unresolved", **report}

        # 3. Select the RESOLVED ENTITY (the novel step) and build the sketch on it.
        try:
            doc.ClearSelection2(True)
        except Exception:  # noqa: BLE001
            pass
        if not select_entity(res.entity):
            return {"overall": "FAIL", "reason": "select_entity(face) failed", **report}

        sk = doc.SketchManager
        sk.InsertSketch(True)
        px, py, pz = 0.005, 0.005, BOX_D_M  # on-face point offset from centre
        pt = sk.CreatePoint(px, py, pz)
        sk.InsertSketch(True)
        if pt is None:
            return {
                "overall": "FAIL",
                "reason": "CreatePoint None (sketch not on face?)",
                **report,
            }

        # 4. Resolve DB args and run the wizard pipeline.
        generic = mutate._WZD_GENERIC_HOLE_TYPES[HOLE_TYPE]
        # Find a valid size from the DB for this (standard, fastener).
        end_cond = mutate._WZD_END_CONDITIONS["through_all"]
        size = SIZE
        if size is None:
            hsd_app = sw
            try:
                hsd_raw = hsd_app.GetHoleStandardsData(generic)
                hsd = typed_qi(hsd_raw, "IHoleStandardsData", module=wrapper_module())
                # reuse mutate's resolver by probing the first size it accepts
            except Exception:  # noqa: BLE001
                hsd = None
            # Brute the resolver: try the known catalog via _resolve_hole_args with
            # a placeholder, then read the suggested sizes out of the error.
            ok0, si, fi, err0 = mutate._resolve_hole_args(
                generic, STANDARD, FASTENER, "__none__"
            )
            report["size_probe_error"] = err0
            # err0 lists available sizes; grab the first token after 'available: '
            size = None
            if err0 and "available:" in err0:
                tail = err0.split("available:", 1)[1].strip()
                first = tail.split(",")[0].strip()
                size = first or None
        report["size_used"] = size
        if not size:
            return {"overall": "FAIL", "reason": "no DB size resolved", **report}

        ok, std_idx, fast_idx, err = mutate._resolve_hole_args(
            generic, STANDARD, FASTENER, size
        )
        if not ok:
            return {"overall": "FAIL", "reason": f"resolve_hole_args: {err}", **report}

        def _select_point() -> bool:
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            m = getattr(pt, "Select2", None)
            if m is not None:
                try:
                    if m(False, 0):
                        return True
                except Exception:  # noqa: BLE001
                    pass
            return bool(doc.SelectByID("", "SKETCHPOINT", px, py, pz))

        if not _select_point():
            return {
                "overall": "FAIL",
                "reason": "could not select placement point",
                **report,
            }

        fm = doc.FeatureManager
        data = fm.CreateDefinition(mutate._SW_FM_HOLE_WZD)
        fd = typed_qi(data, "IWizardHoleFeatureData2", module=wrapper_module())
        fd.InitializeHole(generic, std_idx, fast_idx, size, end_cond)
        _select_point()
        feat = fm.CreateFeature(data)
        report["materialized"] = mutate._materialized(feat)
        report["overall"] = "PASS" if mutate._materialized(feat) else "FAIL"
        if report["overall"] != "PASS":
            report["reason"] = "CreateFeature did not materialize on resolved face"
        return report
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    pythoncom.CoInitialize()
    try:
        report = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "wizhole_durable.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if report.get("overall") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
