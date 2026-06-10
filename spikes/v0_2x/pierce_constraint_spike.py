"""S1 DE-RISK — the PIERCE relation for generative sweeps (W50).

`sweep` is shipped (`_create_sweep`, swFmSweep=17) but assumes the caller hands it
a profile + path ALREADY aligned in 3D — impossible for an LLM without a
programmatic anchor. The missing primitive is a PIERCE relation: bind a 2D
profile-sketch point to the point where a 3D path curve pierces the profile
plane. W39 shipped 6 sketch relations via `SketchAddConstraints` but DEFERRED
coincident; pierce was never attempted.

The W21/W39 no-op trap is the hazard: `SketchAddConstraints(badToken)` returns
with NO error and NO effect (sgEQUAL no-op'd; the real token was sgSAMELENGTH).
So the token is NOT trusted — candidates are tried and the EFFECT is measured:
an offset circle center must SNAP onto the path's pierce point.

Fixture:
  * PATH sketch on Top Plane: a line along part-Z crossing z=0 (pierces Front).
  * PROFILE sketch on Front Plane: a circle DELIBERATELY OFFSET (center at
    x=20mm), so a working pierce moves the center to the pierce point (origin).

GREEN: a token snaps the center to ~(0,0) (|dx|<1mm) AND adds a relation
(RelationManager count delta) AND the subsequent sweep materializes a body.
A frozen center across all tokens = pierce not reachable out-of-process (a wall).

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/pierce_constraint_spike.py
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "pierce_constraint_spike.json"

_SW_FM_SWEEP = 17

# Candidate pierce tokens — sgATPIERCE is SW's documented name; the rest guard
# against a makepy/version surprise. The EFFECT (center snap) is the arbiter.
_PIERCE_TOKENS = ["sgATPIERCE", "sgPIERCE", "sgPIERCED", "sgATINTERSECT"]


def _last_sketch_name(doc: Any, mod: Any) -> str | None:
    """Name of the most recent sketch feature, via FeatureManager.GetFeatures
    (robust on the typed IModelDoc2 proxy where GetFeatureCount is finicky)."""
    try:
        feats = doc.FeatureManager.GetFeatures(True) or []
    except Exception:
        return None
    last = None
    for f in feats:
        try:
            tf = typed(f, "IFeature", module=mod)
            if tf.GetTypeName2() in ("ProfileFeature", "Sketch"):
                last = tf
        except Exception:
            continue
    if last is None:
        return None
    try:
        return last.Name
    except Exception:
        return None


def _count_relations(sk: Any) -> int:
    try:
        rm = sk.RelationManager
        rels = rm.GetRelations(0) if rm is not None else None
        if rels is None:
            return 0
        try:
            return len(list(rels))
        except TypeError:
            return 1
    except Exception:
        return 0


def _center_xy(circle: Any, mod: Any) -> tuple[float, float] | None:
    """Read a circle segment's center (sketch X/Y, metres)."""
    for getter in (circle,):
        try:
            cp = getter.GetCenterPoint2()
            if cp is not None:
                return (float(cp.X), float(cp.Y))
        except Exception:
            pass
    try:
        arc = typed_qi(circle, "ISketchArc", module=mod)
        cp = arc.GetCenterPoint2()
        return (float(cp.X), float(cp.Y))
    except Exception:
        return None


def main() -> int:
    out: dict[str, Any] = {"spike_id": "pierce_constraint_spike", "status": "UNKNOWN"}
    sw = None
    try:
        pythoncom.CoInitialize()
        mod = wrapper_module()
        sw = get_sw_app()
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

        template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
        raw_doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if raw_doc is None:
            out["error"] = "NewDocument(part) None"
            return _finish(out)
        doc = typed(raw_doc, "IModelDoc2", module=mod)
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)

        # --- PATH sketch on Top Plane: a line along part-Z crossing z=0 ---
        if not ext.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
            out["error"] = "could not select Top Plane"
            return _finish(out)
        sm = typed(doc.SketchManager, "ISketchManager", module=mod)
        sm.InsertSketch(True)
        # Top-Plane sketch (x->partX, y->partZ): (0,-5)->(0,60) = part Z -5..60,
        # piercing Front Plane (z=0) in its interior.
        path_seg = sm.CreateLine(0.0, -0.005, 0.0, 0.0, 0.060, 0.0)
        sm.InsertSketch(True)  # close
        doc.ClearSelection2(True)
        path_name = _last_sketch_name(doc, mod)
        out["path_sketch"] = path_name

        # --- PROFILE sketch on Front Plane: an OFFSET circle ---
        if not ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
            out["error"] = "could not select Front Plane"
            return _finish(out)
        sm.InsertSketch(True)
        circle = sm.CreateCircle(0.020, 0.0, 0.0, 0.025, 0.0, 0.0)  # center (20,0), r=5
        sk = doc.GetActiveSketch2
        before = _center_xy(circle, mod)
        out["center_before_mm"] = [round(before[0] * 1000, 4), round(before[1] * 1000, 4)] if before else None

        # --- Try pierce tokens; the EFFECT (center snap) is the arbiter ---
        attempts: list[dict[str, Any]] = []
        winner: str | None = None
        for token in _PIERCE_TOKENS:
            n0 = _count_relations(sk)
            pre = _center_xy(circle, mod)
            pre_offset = pre is not None and (abs(pre[0]) > 0.001 or abs(pre[1]) > 0.001)
            doc.ClearSelection2(True)
            # Select the circle CENTER by coordinate (ISketchPoint has no Select4
            # on the gen_py proxy). The center sits at part (0.020, 0, 0) on the
            # Front plane until a working pierce snaps it to the origin.
            cur = _center_xy(circle, mod) or (0.020, 0.0)
            try:
                sel_pt = bool(ext.SelectByID2(
                    "", "SKETCHPOINT", cur[0], cur[1], 0.0, False, 0, None, 0))
            except Exception as exc:  # noqa: BLE001
                sel_pt = f"pt_select_err:{exc!r}"[:80]
            try:
                sel_path = bool(path_seg.Select2(True, 0))
            except Exception as exc:  # noqa: BLE001
                sel_path = f"path_select_err:{exc!r}"[:80]
            try:
                doc.SketchAddConstraints(token)
                add_err = None
            except Exception as exc:  # noqa: BLE001
                add_err = f"{exc!r}"[:120]
            doc.EditRebuild3()
            n1 = _count_relations(sk)
            after = _center_xy(circle, mod)
            dx_mm = abs(after[0] * 1000) if after else None
            at_origin = bool(after is not None and abs(after[0]) < 0.001 and abs(after[1]) < 0.001)
            # The EFFECT is the arbiter (RelationManager.GetRelations(0) is a
            # TYPE filter, not a count of all relations — it returns 0 for
            # pierce). A token WINS only if THIS attempt moved the center from an
            # offset position to the pierce point (attribution, not coincidence).
            snapped = bool(pre_offset and at_origin)
            attempts.append({
                "token": token, "sel_point": sel_pt, "sel_path": sel_path,
                "add_error": add_err, "relation_delta": n1 - n0,
                "center_after_mm": [round(after[0] * 1000, 4), round(after[1] * 1000, 4)] if after else None,
                "snapped_this_attempt": snapped, "center_at_origin": at_origin,
            })
            print(f"[pierce] {token:<14} -> snapped={snapped} at_origin={at_origin} "
                  f"delta={n1-n0} center_x_mm={dx_mm}")
            if snapped:
                winner = token
                break
        out["attempts"] = attempts
        out["winning_token"] = winner

        sm.InsertSketch(True)  # close profile sketch
        doc.ClearSelection2(True)
        prof_name = _last_sketch_name(doc, mod)
        out["profile_sketch"] = prof_name

        if winner is None:
            out["status"] = "PIERCE_FROZEN"
            out["note"] = "no token snapped the center — pierce not reachable out-of-process"
            return _finish(out)

        # --- Secondary gate: the sweep now solves with the anchored profile ---
        try:
            fm = doc.FeatureManager
            data = fm.CreateDefinition(_SW_FM_SWEEP)
            sd = typed_qi(data, "ISweepFeatureData", module=mod)
            ext = typed(doc.Extension, "IModelDocExtension", module=mod)
            doc.ClearSelection2(True)
            ext.SelectByID2(prof_name, "SKETCH", 0, 0, 0, False, 1, None, 0)
            ext.SelectByID2(path_name, "SKETCH", 0, 0, 0, True, 4, None, 0)
            feats0 = fm.GetFeatures(True)
            n_before = len(feats0) if feats0 else 0
            fm.CreateFeature(sd)
            doc.ForceRebuild3(False)
            feats1 = fm.GetFeatures(True)
            n_after = len(feats1) if feats1 else 0
            pdoc = typed_qi(raw_doc, "IPartDoc", module=mod)
            bodies = pdoc.GetBodies2(0, True)
            nb = len(bodies) if bodies else 0
            vol = 0.0
            for b in bodies or ():
                try:
                    mp = b.GetMassProperties(1.0)
                    if mp and len(mp) > 3:
                        vol += float(mp[3]) * 1e9
                except Exception:
                    pass
            out["sweep"] = {"feature_delta": n_after - n_before, "bodies": nb,
                            "volume_mm3": round(vol, 1)}
            sweep_ok = (n_after > n_before) and nb >= 1 and vol > 0
        except Exception as exc:  # noqa: BLE001
            out["sweep"] = {"error": f"{exc!r}"[:160]}
            sweep_ok = False

        out["status"] = "GREEN" if sweep_ok else "PIERCE_OK_SWEEP_FAILED"
    except Exception as exc:  # noqa: BLE001
        out["status"] = "EXCEPTION"
        out["error"] = f"{exc!r}\n{traceback.format_exc()}"
    finally:
        if sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return _finish(out)


def _finish(out: dict) -> int:
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[pierce] verdict: {out.get('status')} (token={out.get('winning_token')}) -> {_OUT}")
    return 0 if out.get("status") == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
