"""W65 sketched_bend — boss-fight derisk spike (LIVE seat only).

Probes the method-name ambiguity for "Sketched Bend" on a real SOLIDWORKS
seat.  Two candidates carry the semantics:

  Candidate A (preferred):
    IFeatureManager.InsertSheetMetal3dBend(
        Angle, BUseDefaultRadius, Radius, FlipDir, BendPos, PCBA,
    ) -> Feature      [6-arg, per-bend params, PCBA null]

  Candidate B (fallback):
    IFeatureManager.InsertBends2(
        Radius, UseBendTable, UseKfactor, UseBendAllowance,
        UseAutoRelief, OffsetRatio, DoFlatten,
    ) -> Boolean      [7-arg, global auto-bend pass]

Fixture: ``_build_fixture_v5`` (base flange 60×40×2 mm) + a line sketch on
the major planar face.

PASS iff ΔFaces > 0 AND |ΔVol| > 1e-6 mm³ surviving save→reopen.
Seat telemetry records which candidate fired, both returns, ΔFaces/ΔVol,
and GetTypeName2 — so the doctrine memory captures the resolved method name.

Exit codes: 0 = PASS, 2 = NO_OP (solver wall / method ambiguity), 1 = ERROR.
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
from win32com.client import VARIANT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# spike_earlybind_persist lives under spikes/v0_15/
_v0_15 = str(Path(__file__).resolve().parents[1] / "v0_15")
if _v0_15 not in sys.path:
    sys.path.insert(0, _v0_15)

import _feature_spike_fixtures as fx  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.features.sketched_bend import create_sketched_bend  # noqa: E402
from ai_sw_bridge.features.sketched_bend import _metrics  # noqa: E402

# Reuse the hem v5 fixture builder (base flange + longest boundary edge).
# spike_hem_v5 is a sibling in the same directory — on sys.path[0].
from spike_hem_v4 import (  # noqa: E402
    BEND_RADIUS_M,
    IFACE_BASEFLANGE,
    PROF_H_M,
    PROF_W_M,
    SW_BODY_SOLID,
    SW_DEFAULT_TEMPLATE_PART,
    SW_FM_BASEFLANGE,
    THICKNESS_M,
    _capture,
    _materialized,
    connect_running_sw,
    wrapper_module as _v4_wrapper_module,
)

# ── constants ──────────────────────────────────────────────────────────────

BEND_ANGLE_RAD = math.radians(90.0)
USE_DEFAULT_RADIUS = True
BEND_RADIUS_M_ARG = 0.001  # 1 mm, ignored when use_default_radius=True
FLIP_DIR = False
BEND_POS = 1  # swFlangePositionTypeMaterialInside


def _pcba_null() -> Any:
    return VARIANT(pythoncom.VT_DISPATCH, None)


# ── fixture extension: sketch on the major face ───────────────────────────

def _build_fixture_v5(sw: Any, mod: Any):
    """Import the proven fixture builder from spike_hem_v5."""
    from spike_hem_v5 import _build_fixture_v5 as _v5_build
    return _v5_build(sw, mod)


def _sketch_line_on_major_face(doc: Any, mod: Any,
                               diag: dict[str, Any]) -> str | None:
    """Add a single line sketch on the major planar face of the base flange.

    The base flange is 60(X) × 40(Y) × 2(Z).  The major face is the top
    surface at Z = +1mm = 0.001 m.  We select it via coordinate pick, open
    a sketch, draw a line across the face, and close.  Returns the sketch
    feature name (typically "Sketch2").
    """
    try:
        null_disp = VARIANT(pythoncom.VT_DISPATCH, None)
        doc.Extension.SelectByID2(
            "", "FACE", 0.0, 0.0, THICKNESS_M, False, 0, null_disp, 0,
        )
        face = doc.SelectionManager.GetSelectedObject6(1, -1)
        doc.ClearSelection2(True)
        if face is None:
            diag["face_select"] = "None — coordinate pick missed"
            return None
        diag["face_selected"] = True
    except Exception as e:
        diag["face_select_error"] = f"{type(e).__name__}: {e}"[:200]
        return None

    try:
        face.Select2(False, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        # Line across the face in X, offset from center in Y so it does not
        # coincide with the sketch origin axes.
        sk.CreateLine(-0.020, 0.005, 0.0, 0.020, 0.005, 0.0)
        sk.InsertSketch(True)  # close (non-empty → persists)
        doc.ClearSelection2(True)
        sketch_name = _last_sketch_name(doc)
        diag["sketch_name"] = sketch_name
        diag["sketch_line"] = {
            "start_mm": [-20.0, 5.0, 0.0],
            "end_mm": [20.0, 5.0, 0.0],
        }
        return sketch_name
    except Exception as e:
        diag["sketch_error"] = f"{type(e).__name__}: {e}"[:200]
        return None


def _last_sketch_name(doc: Any) -> str:
    """Return the most-recent Sketch feature name, or 'Sketch2' as fallback."""
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return "Sketch2"
    if not feats:
        return "Sketch2"
    last = "Sketch2"
    for feat in feats:
        try:
            tname = feat.GetTypeName if not callable(feat.GetTypeName) else feat.GetTypeName()
        except Exception:
            continue
        if tname in ("ProfileFeature", "Sketch"):
            try:
                nm = feat.Name if not callable(feat.Name) else feat.Name()
                if isinstance(nm, str) and nm.startswith("Sketch"):
                    last = nm
            except Exception:
                pass
    return last


# ── candidate probes ──────────────────────────────────────────────────────

def _probe_candidate_a(fm: Any, diag: dict[str, Any]) -> Any:
    """Candidate A: IFeatureManager.InsertSheetMetal3dBend (6-arg → Feature)."""
    try:
        pcba = _pcba_null()
        result = fm.InsertSheetMetal3dBend(
            BEND_ANGLE_RAD, USE_DEFAULT_RADIUS, BEND_RADIUS_M_ARG,
            FLIP_DIR, BEND_POS, pcba,
        )
        diag["A_return"] = str(type(result))
        diag["A_is_none"] = result is None
        # GetTypeName2 probe (the A7 doctrine)
        if result is not None:
            try:
                tname = result.GetTypeName2
                if callable(tname):
                    tname = tname()
                diag["A_GetTypeName2"] = tname
            except Exception as e:
                diag["A_GetTypeName2_error"] = f"{type(e).__name__}: {e}"[:120]
        return result
    except Exception as e:
        diag["A_error"] = f"{type(e).__name__}: {e}"[:200]
        return None


def _probe_candidate_b(fm: Any, diag: dict[str, Any]) -> Any:
    """Candidate B: IFeatureManager.InsertBends2 (7-arg → Boolean)."""
    try:
        result = fm.InsertBends2(
            BEND_RADIUS_M_ARG,  # Radius
            "",                 # UseBendTable (empty = none)
            0.5,                # UseKfactor
            0.0,                # UseBendAllowance
            False,              # UseAutoRelief
            0.5,                # OffsetRatio
            False,              # DoFlatten
        )
        diag["B_return"] = str(type(result))
        diag["B_value"] = result
        return result
    except Exception as e:
        diag["B_error"] = f"{type(e).__name__}: {e}"[:200]
        return None


# ── save→reopen ───────────────────────────────────────────────────────────

def _save_reopen(sw: Any, doc: Any) -> dict[str, Any]:
    """Save → close-all → reopen via the proven typed-OpenDoc6 recipe."""
    out: dict[str, Any] = {}
    tmp = tempfile.mktemp(suffix=".SLDPRT")
    try:
        doc.SaveAs3(tmp, 0, 2)
        out["saved_to"] = tmp
        sw.CloseAllDocuments(True)
        out["closed"] = True

        mod = wrapper_module()
        tsw = typed(sw, "ISldWorks", module=mod)
        try:
            ret = tsw.OpenDoc6(tmp, 1, 1, "", 0, 0)
            out["open_ret_tuple"] = isinstance(ret, tuple)
        except Exception as exc:
            out["reopen_error"] = f"{type(exc).__name__}: {exc}"[:200]
            return out

        doc2 = sw.ActiveDoc
        if doc2 is None:
            out["reopen_error"] = "ActiveDoc None after OpenDoc6"
            return out
        out["reopened"] = True
        try:
            doc2.ForceRebuild3(False)
        except Exception:
            pass

        after = _metrics(doc2)
        out["faces_after_reopen"] = after[0]
        out["vol_mm3_after_reopen"] = after[1]
        sw.CloseAllDocuments(True)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass
    return out


# ── main ──────────────────────────────────────────────────────────────────

def _write_and_report(out: dict[str, Any], code: int) -> int:
    res_dir = Path(__file__).resolve().parent / "_results"
    res_dir.mkdir(parents=True, exist_ok=True)
    out_path = res_dir / "sketched_bend_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    sys.stderr.write(f"[sketched_bend] wrote {out_path}\n")
    sys.stderr.write(f"[sketched_bend] VERDICT: {out.get('verdict')} (exit {code})\n")
    sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
    return code


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "spike": "sketched_bend",
        "purpose": (
            "boss-fight — method disambiguation between "
            "InsertSheetMetal3dBend (Candidate A) and InsertBends2 (Candidate B)"
        ),
        "candidate_a": "IFeatureManager.InsertSheetMetal3dBend(6-arg) -> Feature",
        "candidate_b": "IFeatureManager.InsertBends2(7-arg) -> Boolean",
    }
    sw = None
    doc = None
    code = 1
    try:
        mod = wrapper_module()
        sw = connect_running_sw()
        rev = sw.RevisionNumber
        out["sw_revision"] = rev() if callable(rev) else rev

        # ── 1. Build the base flange + select longest boundary edge ────
        doc, fm, edge, diag = _build_fixture_v5(sw, mod)
        out["fixture"] = diag
        if doc is None or fm is None:
            out["error"] = diag.get("error", "fixture build failed")
            out["verdict"] = "ERROR"
            return _write_and_report(out, 1)

        # ── 2. Add a line sketch on the major face ─────────────────────
        sketch_diag: dict[str, Any] = {}
        sketch_name = _sketch_line_on_major_face(doc, mod, sketch_diag)
        out["sketch"] = sketch_diag
        if sketch_name is None:
            out["error"] = sketch_diag.get("sketch_error", "sketch authoring failed")
            out["verdict"] = "ERROR"
            return _write_and_report(out, 1)

        # ── 3. Pre-select the sketch + measure before ──────────────────
        faces_before, vol_before = _metrics(doc)
        out["faces_before"] = faces_before
        out["vol_mm3_before"] = vol_before

        try:
            doc.ClearSelection2(True)
        except Exception:
            pass
        try:
            feat_obj = doc.FeatureByName(sketch_name)
            if feat_obj is not None:
                feat_obj.Select2(False, 0)
                out["sketch_selected"] = True
            else:
                out["sketch_selected"] = False
                out["error"] = f"FeatureByName({sketch_name!r}) returned None"
                out["verdict"] = "ERROR"
                return _write_and_report(out, 1)
        except Exception as e:
            out["error"] = f"sketch select error: {type(e).__name__}: {e}"[:200]
            out["verdict"] = "ERROR"
            return _write_and_report(out, 1)

        # ── 4. Fire Candidate A ────────────────────────────────────────
        a_diag: dict[str, Any] = {}
        a_result = _probe_candidate_a(fm, a_diag)
        out["candidate_A"] = a_diag

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        faces_after_a, vol_after_a = _metrics(doc)
        out["faces_after_A"] = faces_after_a
        out["vol_mm3_after_A"] = vol_after_a
        out["delta_faces_A"] = faces_after_a - faces_before
        out["delta_vol_mm3_A"] = round(vol_after_a - vol_before, 3)

        a_passed = (
            out["delta_faces_A"] > 0 and abs(out["delta_vol_mm3_A"]) > 1e-6
        )

        if a_passed:
            # Candidate A materialized — save→reopen survival check.
            out["verdict"] = "PASS_A"
            out["persist"] = _save_reopen(sw, doc)
            doc = None
            p = out["persist"]
            survived = bool(
                p.get("reopened")
                and p.get("faces_after_reopen", 0) > faces_before
            )
            out["persist_survived"] = survived
            code = 0 if survived else 2
            if not survived:
                out["verdict"] = "PASS_A_BUT_NOT_PERSISTED"
        else:
            # Candidate A no-op'd — try Candidate B.
            # First, re-select the sketch (A may have consumed or cleared selection).
            try:
                doc.ClearSelection2(True)
            except Exception:
                pass
            try:
                feat_obj = doc.FeatureByName(sketch_name)
                if feat_obj is not None:
                    feat_obj.Select2(False, 0)
            except Exception:
                pass

            faces_before_b, vol_before_b = _metrics(doc)
            b_diag: dict[str, Any] = {}
            b_result = _probe_candidate_b(fm, b_diag)
            out["candidate_B"] = b_diag

            try:
                doc.ForceRebuild3(False)
            except Exception:
                pass

            faces_after_b, vol_after_b = _metrics(doc)
            out["faces_after_B"] = faces_after_b
            out["vol_mm3_after_B"] = vol_after_b
            out["delta_faces_B"] = faces_after_b - faces_before_b
            out["delta_vol_mm3_B"] = round(vol_after_b - vol_before_b, 3)

            b_passed = (
                out["delta_faces_B"] > 0 and abs(out["delta_vol_mm3_B"]) > 1e-6
            )

            if b_passed:
                out["verdict"] = "PASS_B"
                out["persist"] = _save_reopen(sw, doc)
                doc = None
                p = out["persist"]
                survived = bool(
                    p.get("reopened")
                    and p.get("faces_after_reopen", 0) > faces_before_b
                )
                out["persist_survived"] = survived
                code = 0 if survived else 2
                if not survived:
                    out["verdict"] = "PASS_B_BUT_NOT_PERSISTED"
            else:
                out["verdict"] = "NO_OP"
                out["note"] = (
                    "Both candidates no-op'd.  The sketch-line-on-face selection "
                    "or the sheet-metal solver state may be the barrier.  "
                    "Characterize for DEFERRED.md."
                )
                code = 2

        # ── 5. Handler PAE (if candidate A passed) ─────────────────────
        if a_passed and doc is None:
            # Re-open for the handler PAE
            try:
                mod2 = wrapper_module()
                sw2 = connect_running_sw()
                doc2, fm2, edge2, diag2 = _build_fixture_v5(sw2, mod2)
                if doc2 and fm2:
                    sk_name = _sketch_line_on_major_face(doc2, mod2, {})
                    if sk_name:
                        handler_ok, handler_err = create_sketched_bend(
                            doc2,
                            {"angle_deg": 90, "position": "material_inside"},
                            {"sketch": sk_name},
                        )
                        out["handler_pae"] = {
                            "ok": handler_ok,
                            "err": handler_err,
                        }
                sw2.CloseAllDocuments(True)
            except Exception as e:
                out["handler_pae_error"] = f"{type(e).__name__}: {e}"[:200]

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
