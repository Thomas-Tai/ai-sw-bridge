"""W62 helix derisk spike — dual-mode probe on the live seat (DO NOT RUN offline).

Probes both helix creation modes on a 40×30×10 mm solid block with a
Ø10 mm circle sketch (``fx.build_block`` + ``fx.seed_circle_sketch``):

  Mode-A: ``CreateDefinition(swFeatureNameID=36)`` →
    ``typed_qi(data, "IHelixFeatureData")`` → set Pitch / Revolution /
    Height / StartingAngle / Clockwise / DefinedBy →
    ``CreateFeature(data)``.  The swFeatureNameID 36 is a PROBE
    (``swFmHelix``); W0 resolves the exact ID on the seat.

  Mode-B: ``doc.InsertHelix(ConstantPitch:bool, Reverse:bool,
    Dimension:bool, Clockwise:bool, DefinedBy:int, Pitch:double,
    Revolution:double, Height:double, StartAngle:double,
    Diameter:double)`` — 10 args, returns void.

Verify: a new Helix feature node via FirstFeature walk (no ΔVol — a
helix is a reference curve).  If PASS, runs save→reopen to confirm
persistence.

Exit codes: 0 = PASS (materialized + persisted), 2 = NO_OP or
PASS_BUT_NOT_PERSISTED, 1 = ERROR.

** DO NOT RUN OFFLINE — requires a live SOLIDWORKS seat. **
"""

from __future__ import annotations

import json
import math
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import pythoncom

# Ensure repo src is on sys.path for ai_sw_bridge imports.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from ai_sw_bridge.com.earlybind import EarlyBindError, typed, typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module

import _feature_spike_fixtures as fx  # noqa: E402  (needs sys.path patch above)

# -- Helix parameters (W0-tunable on the seat) --------------------------------

HELIX_PITCH_MM = 5.0
HELIX_REVOLUTIONS = 4.0
HELIX_START_ANGLE_DEG = 0.0
HELIX_CLOCKWISE = True

# Probe value — W0 resolves the exact swFeatureNameID for helix on the seat.
SW_FM_HELIX_PROBE = 36
SW_HELIX_DEFINED_BY_PITCH_AND_REV = 0


def _feature_type_names(doc: Any, mod: Any) -> list[str]:
    """Walk FirstFeature → GetNextFeature, re-typing each node to IFeature."""
    names: list[str] = []
    try:
        feat = doc.FirstFeature()
        while feat is not None:
            try:
                typed_feat = typed(feat, "IFeature", module=mod)
                names.append(typed_feat.GetTypeName())
            except Exception:
                try:
                    names.append(feat.GetTypeName())
                except Exception:
                    names.append("<unknown>")
            feat = feat.GetNextFeature()
    except Exception:
        pass
    return names


def _count_helices(doc: Any, mod: Any) -> int:
    return sum(1 for n in _feature_type_names(doc, mod) if n == "Helix")


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
            "dual-mode helix probe — Mode-A: CreateDefinition(36) → "
            "IHelixFeatureData → CreateFeature; Mode-B: InsertHelix(10 args)"
        ),
        "params": {
            "pitch_mm": HELIX_PITCH_MM,
            "revolutions": HELIX_REVOLUTIONS,
            "start_angle_deg": HELIX_START_ANGLE_DEG,
            "clockwise": HELIX_CLOCKWISE,
        },
    }
    sw = None
    doc = None
    code = 1
    try:
        mod = wrapper_module()
        sw = fx.connect()
        rev = sw.RevisionNumber
        out["sw_revision"] = rev() if callable(rev) else rev

        doc = fx.build_block(sw)
        sketch_name = fx.seed_circle_sketch(doc)
        out["sketch"] = sketch_name

        before = _metrics(doc)
        out["faces_before"] = before["faces"]
        out["vol_mm3_before"] = before["vol_mm3"]
        helices_before = _count_helices(doc, mod)
        out["helices_before"] = helices_before

        pitch_m = HELIX_PITCH_MM / 1000.0
        height_m = pitch_m * HELIX_REVOLUTIONS
        start_angle_rad = math.radians(HELIX_START_ANGLE_DEG)

        # -- Mode-A: CreateDefinition → typed_qi(IHelixFeatureData) → CreateFeature
        mode_a_diag: dict[str, Any] = {}
        mode_a_ok = False
        try:
            fm = doc.FeatureManager
            data = fm.CreateDefinition(SW_FM_HELIX_PROBE)
            mode_a_diag["create_definition"] = data is not None
            if data is not None:
                fd = typed_qi(data, "IHelixFeatureData", module=mod)
                mode_a_diag["typed_qi"] = True
                fd.DefinedBy = SW_HELIX_DEFINED_BY_PITCH_AND_REV
                fd.Pitch = pitch_m
                fd.Revolution = HELIX_REVOLUTIONS
                fd.Height = height_m
                fd.StartingAngle = start_angle_rad
                fd.Clockwise = HELIX_CLOCKWISE
                doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
                feat = fm.CreateFeature(data)
                mode_a_diag["create_feature"] = feat is not None
                helices_after_a = _count_helices(doc, mod)
                if helices_after_a > helices_before:
                    mode_a_ok = True
        except EarlyBindError as e:
            mode_a_diag["early_bind_error"] = str(e)[:200]
        except Exception as e:
            mode_a_diag["error"] = f"{type(e).__name__}: {e}"[:200]
        out["mode_a"] = mode_a_diag
        out["mode_a_ok"] = mode_a_ok

        # -- Mode-B: doc.InsertHelix(10 args)
        mode_b_diag: dict[str, Any] = {}
        mode_b_ok = False
        if not mode_a_ok:
            try:
                doc.ClearSelection2(True)
            except Exception:
                pass
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
                    0.0,                                # Diameter (use sketch)
                )
                mode_b_diag["called"] = True
                helices_after_b = _count_helices(doc, mod)
                if helices_after_b > helices_before:
                    mode_b_ok = True
            except Exception as e:
                mode_b_diag["error"] = f"{type(e).__name__}: {e}"[:200]
        out["mode_b"] = mode_b_diag
        out["mode_b_ok"] = mode_b_ok

        # -- Verify
        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        after = _metrics(doc)
        out["faces_after"] = after["faces"]
        out["vol_mm3_after"] = after["vol_mm3"]
        out["delta_faces"] = after["faces"] - before["faces"]
        out["delta_vol_mm3"] = round(after["vol_mm3"] - before["vol_mm3"], 3)
        helices_after = _count_helices(doc, mod)
        out["helices_after"] = helices_after
        out["feature_tree"] = _feature_type_names(doc, mod)

        any_mode_ok = mode_a_ok or mode_b_ok
        out["mode_fired"] = (
            "A" if mode_a_ok else ("B" if mode_b_ok else "NONE")
        )

        if any_mode_ok:
            out["verdict"] = "PASS"
            # Save → reopen → verify persistence
            try:
                doc2 = fx.save_and_reopen(sw, doc)
                doc = None  # save_and_reopen closed all docs
                helices_reopen = _count_helices(doc2, mod)
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
