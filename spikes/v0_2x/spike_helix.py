"""W62 helix derisk spike — Mode-B probe on the live seat (DO NOT RUN offline).

Mode-A is QUARANTINED: the SW2024 swconst harvest exposes NO swFeatureNameID
for helix (DLL reflection 2026-06-17). Like composite, IHelixFeatureData is
edit-only via IFeature.GetDefinition(); no creation enum exists.

Probes the operative path:

  Mode-B: select Sketch2 via Extension.SelectByID2 → ``doc.InsertHelix(
    ConstantPitch:bool, Reverse:bool, Dimension:bool, Clockwise:bool,
    DefinedBy:int, Pitch:double, Revolution:double, Height:double,
    StartAngle:double, Diameter:double)`` — 10 args, returns void.

Verify: a new Helix feature node via ``IFeatureManager.GetFeatures(False)``
type-name filter (no ΔVol — a helix is a reference curve), with the
callable-or-property guard on ``GetTypeName``/``GetTypeName2`` (some surface
forms auto-invoke as a property — same trap class as FirstFeature,
InsertCompositeCurve).

** DO NOT RUN OFFLINE — requires a live SOLIDWORKS seat. **
"""

from __future__ import annotations

import json
import logging
import math
import sys
import traceback
from pathlib import Path
from typing import Any

import pythoncom
from win32com.client import VARIANT

logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import _feature_spike_fixtures as fx  # noqa: E402

# -- Helix parameters (W0-tunable on the seat) --------------------------------

HELIX_PITCH_MM = 5.0
HELIX_REVOLUTIONS = 4.0
HELIX_START_ANGLE_DEG = 0.0
HELIX_CLOCKWISE = True
SW_HELIX_DEFINED_BY_PITCH_AND_REV = 0


def _resolve(obj: Any, attr: str) -> Any:
    v = getattr(obj, attr)
    return v() if callable(v) else v


def _feature_type_names(doc: Any) -> list[str]:
    """Return all feature type-names via GetFeatures(False) + callable-or-property guard."""
    names: list[str] = []
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return names
    if feats is None:
        return names
    for feat in feats:
        try:
            names.append(str(_resolve(feat, "GetTypeName")))
            continue
        except Exception:
            pass
        try:
            names.append(str(_resolve(feat, "GetTypeName2")))
        except Exception:
            names.append("<unknown>")
    return names


def _count_helices(doc: Any) -> int:
    return sum(1 for n in _feature_type_names(doc) if n == "Helix")


def _metrics(doc: Any) -> dict[str, Any]:
    """(face_count, volume_mm3) over solid bodies; matches hem._metrics shape."""
    faces = 0
    vol_mm3 = 0.0
    try:
        bodies = doc.GetBodies2(0, True)
        if bodies:
            for b in (list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]):
                try:
                    f = b.GetFaces()
                    faces += len(f) if f else 0
                except Exception:
                    pass
                try:
                    mp = b.GetMassProperties(1.0)
                    if mp and len(mp) > 3:
                        vol_mm3 += float(mp[3]) * 1e9
                except Exception:
                    pass
    except Exception:
        pass
    return {"faces": faces, "vol_mm3": vol_mm3}


def _write_and_report(out: dict[str, Any], code: int) -> int:
    res_dir = Path(__file__).resolve().parent / "_results"
    res_dir.mkdir(parents=True, exist_ok=True)
    out_path = res_dir / "helix_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    sys.stderr.write(f"[helix] wrote {out_path}\n")
    sys.stderr.write(f"[helix] VERDICT: {out.get('verdict')} (exit {code})\n")
    sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
    return code


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "spike": "helix",
        "purpose": (
            "Mode-B helix probe — Mode-A QUARANTINED (no swFeatureNameID for "
            "helix in swconst harvest); Mode-B: SelectByID2 sketch + "
            "InsertHelix(10 args)"
        ),
        "params": {
            "pitch_mm": HELIX_PITCH_MM,
            "revolutions": HELIX_REVOLUTIONS,
            "start_angle_deg": HELIX_START_ANGLE_DEG,
            "clockwise": HELIX_CLOCKWISE,
        },
        "mode_a": {"status": "QUARANTINED", "reason": "no swFeatureNameID for helix in SW2024 swconst"},
    }
    sw = None
    doc = None
    code = 1
    try:
        sw = fx.connect()
        rev = sw.RevisionNumber
        out["sw_revision"] = rev() if callable(rev) else rev

        doc = fx.build_block(sw)
        sketch_name = fx.seed_circle_sketch(doc)
        out["sketch"] = sketch_name

        before = _metrics(doc)
        out["faces_before"] = before["faces"]
        out["vol_mm3_before"] = before["vol_mm3"]
        helices_before = _count_helices(doc)
        out["helices_before"] = helices_before
        out["feature_tree_before"] = _feature_type_names(doc)

        pitch_m = HELIX_PITCH_MM / 1000.0
        height_m = pitch_m * HELIX_REVOLUTIONS
        start_angle_rad = math.radians(HELIX_START_ANGLE_DEG)

        # Select the sketch (Extension.SelectByID2 with VARIANT-null callout —
        # W60/W61 proven idiom for named features).
        mode_b_diag: dict[str, Any] = {}
        mode_b_ok = False
        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        null_callout = VARIANT(pythoncom.VT_DISPATCH, None)
        try:
            sel_ok = doc.Extension.SelectByID2(
                sketch_name, "SKETCH", 0.0, 0.0, 0.0, False, 0, null_callout, 0,
            )
            mode_b_diag["select_sketch"] = bool(sel_ok)
        except Exception as e:
            mode_b_diag["select_sketch_error"] = f"{type(e).__name__}: {e}"[:200]
            sel_ok = False

        if sel_ok:
            try:
                doc.InsertHelix(
                    True,                               # ConstantPitch
                    False,                              # Reverse
                    False,                              # Dimension
                    HELIX_CLOCKWISE,                    # Clockwise
                    SW_HELIX_DEFINED_BY_PITCH_AND_REV,  # DefinedBy
                    pitch_m,                            # Pitch (m)
                    HELIX_REVOLUTIONS,                  # Revolution
                    height_m,                           # Height (m)
                    start_angle_rad,                    # StartAngle (rad)
                    0.0,                                # Diameter (0 = use sketch)
                )
                mode_b_diag["insert_helix_called"] = True
            except Exception as e:
                mode_b_diag["insert_helix_error"] = f"{type(e).__name__}: {e}"[:200]

            try:
                doc.ForceRebuild3(False)
            except Exception:
                pass

            helices_after_b = _count_helices(doc)
            mode_b_diag["helices_after"] = helices_after_b
            if helices_after_b > helices_before:
                mode_b_ok = True
        out["mode_b"] = mode_b_diag
        out["mode_b_ok"] = mode_b_ok

        after = _metrics(doc)
        out["faces_after"] = after["faces"]
        out["vol_mm3_after"] = after["vol_mm3"]
        out["delta_faces"] = after["faces"] - before["faces"]
        out["delta_vol_mm3"] = round(after["vol_mm3"] - before["vol_mm3"], 3)
        helices_after = _count_helices(doc)
        out["helices_after"] = helices_after
        out["feature_tree_after"] = _feature_type_names(doc)
        out["mode_fired"] = "B" if mode_b_ok else "NONE"

        if mode_b_ok:
            out["verdict"] = "PASS"
            try:
                doc2 = fx.save_and_reopen(sw, doc)
                doc = None
                helices_reopen = _count_helices(doc2)
                out["persist_survived"] = helices_reopen > helices_before
                out["helices_after_reopen"] = helices_reopen
                code = 0 if out["persist_survived"] else 2
                if not out["persist_survived"]:
                    out["verdict"] = "PASS_BUT_NOT_PERSISTED"
            except Exception as e:
                out["persist_error"] = f"{type(e).__name__}: {e}"[:200]
                out["verdict"] = "PASS_BUT_NOT_PERSISTED"
                code = 2
        else:
            out["verdict"] = "NO_OP"
            code = 2

    except Exception as exc:
        out["fatal_error"] = f"{type(exc).__name__}: {exc}"[:300]
        out["traceback"] = traceback.format_exc()
        out["verdict"] = "ERROR"
        code = 1
    finally:
        if doc is not None and sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        pythoncom.CoUninitialize()

    return _write_and_report(out, code)


if __name__ == "__main__":
    raise SystemExit(main())
