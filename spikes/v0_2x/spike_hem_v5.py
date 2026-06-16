"""hem v5 — edge-precondition fix for the hem un-wall (Tactic 1 only).

v4 proved Tactic 1 (``VARIANT(VT_DISPATCH, None)``) BREACHES the PCBA
marshaling layer: the ``DISP_E_TYPEMISMATCH`` from fire3 is gone — the
call now returns cleanly. But the hem still NO_OP'd (dFace=0, dVol=0, no
node). Only 2 of v4's 4 tactics were valid tests (tactic-2 died on a
``winerror`` constant mislocation; tactic-3's ``VT_PTR``/26 is a type
*modifier*, not a standalone marshalable VARIANT type).

W0 adjudication (2026-06-16): the residual NO_OP is a TOPOLOGICAL-SOLVER
barrier, not a marshaling one. v4 selected ``GetEdges()[0]`` — an ARBITRARY
edge that is very plausibly a 2mm thickness edge or a 40mm short edge,
which SOLIDWORKS silently rejects for a hem. v5 GUARANTEES the
precondition: deterministically select the LONGEST linear boundary edge
(~60mm, a major-face perimeter edge) before firing Tactic 1.

Fixture: flat base flange 60(X) x 40(Y) x 2(Z thickness) — a 12-edge box.
Valid hem edges = the four 60mm perimeter edges of a major face; the four
40mm edges are the short perimeter, the four 2mm edges are thickness.

Verify-the-EFFECT (R3): a hem ADDS faces and folds a 10mm flange ->
  PASS  := dFace > 0 AND dVol != 0 AND the hem node SURVIVES save->reopen.
  NO_OP := clean return, zero geometric delta (still walled at the solver).
  ERROR := fixture/harness failure.

If v5 PASSES, the hem wall is broken and Tactic 1 is the universal trailing
-PCBA-null recipe. If it still NO_OPs on a GUARANTEED boundary edge, the
barrier is deeper and we loop back to the VT_ERROR / VT_EMPTY encodings.

Exit codes: 0 = PASS (folded + survived), 2 = NO_OP (solver wall), 1 = ERROR.
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

from ai_sw_bridge.com.earlybind import typed, typed_extension, typed_qi

# Reuse v4's proven helpers + constants (importing v4 runs only its
# module-level imports; its main() is __main__-guarded).
from spike_hem_v4 import (
    BEND_RADIUS_M,
    IFACE_BASEFLANGE,
    PROF_H_M,
    PROF_W_M,
    SW_BODY_SOLID,
    SW_DEFAULT_TEMPLATE_PART,
    SW_FM_BASEFLANGE,
    THICKNESS_M,
    _capture,
    _check_hem_materialized,
    _hem_scalars,  # noqa: F401  (kept for provenance / parity with tactic_1)
    _materialized,
    _metrics,
    _tactic_1_makepy_vt_dispatch,
    connect_running_sw,
    wrapper_module,
)


def _save_reopen_v5(sw: Any, mod: Any, doc: Any) -> dict[str, Any]:
    """Save, close, reopen, re-measure — using the repo's PROVEN reopen recipe.

    v4's ``_save_reopen`` reopened via the *dynamic* ``sw.OpenDoc6(tmp, 0, 0,
    ...)`` (Type=0) and hit ``DISP_E_TYPEMISMATCH`` — never seen before because
    v4 never reached PASS.  The proven recipe (assembly/handlers.py:175,
    config/dispatch.py:324, spike_sketch_3d.py:332) is the TYPED ``ISldWorks``
    proxy with ``Type=1`` (swDocPART), Options=1, ``[out]`` params as 0,
    returning a ``(doc, *out)`` tuple.  We then re-fetch the opened doc via the
    dynamic ``sw.ActiveDoc`` so the metric reads match the in-session flavor.
    """
    out: dict[str, Any] = {}
    tmp = tempfile.mktemp(suffix=".SLDPRT")
    try:
        doc.SaveAs3(tmp, 0, 2)
        out["saved_to"] = tmp
        sw.CloseAllDocuments(True)
        out["closed"] = True

        tsw = typed(sw, "ISldWorks", module=mod)
        try:
            ret = tsw.OpenDoc6(tmp, 1, 1, "", 0, 0)
            out["open_ret_tuple"] = isinstance(ret, tuple)
        except Exception as exc:
            out["reopen_error"] = f"{type(exc).__name__}: {exc}"[:200]
            return out

        doc2 = sw.ActiveDoc  # dynamic.Dispatch flavor — matches in-session reads
        if doc2 is None:
            out["reopen_error"] = "ActiveDoc None after OpenDoc6"
            return out
        out["reopened"] = True
        try:
            doc2.ForceRebuild3(False)
        except Exception:
            pass

        after = _metrics(doc2)
        out["faces_after_reopen"] = after["faces"]
        out["vol_mm3_after_reopen"] = after["vol_mm3"]
        out["hem_feature"] = _check_hem_materialized(doc2, mod)

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


def _edge_endpoints(edge: Any) -> tuple[tuple, tuple] | None:
    """Return (start_xyz, end_xyz) for a straight edge, or None.

    Seat-introspected (2026-06-16): on the ``dynamic.Dispatch`` edge object
    ``GetStartVertex``/``GetEndVertex``/``GetCurve`` raise
    ``DISP_E_MEMBERNOTFOUND``, while ``GetCurveParams2`` is exposed as a
    *property* (not a method) returning an 11-tuple
    ``[sx,sy,sz, ex,ey,ez, startParam, endParam, sense, ...]``.  Guard the
    property-vs-method ambiguity (the GetSaveFlag/RevisionNumber footgun
    class): read it bare, only call it if it is actually callable (e.g. a
    typed proxy).
    """
    try:
        cp = edge.GetCurveParams2
        if callable(cp):
            cp = cp()
        if cp and len(cp) >= 6:
            return tuple(cp[0:3]), tuple(cp[3:6])
    except Exception:
        pass
    return None


def _select_longest_boundary_edge(doc: Any, body: Any, mod: Any,
                                  diag: dict[str, Any]) -> Any:
    """Deterministically select the LONGEST linear edge of the body.

    On the flat 60x40x2 base flange the longest edges (~60mm) are the major
    -face perimeter edges — guaranteed open hem boundaries.  This removes the
    ``GetEdges()[0]`` topological lottery that NO_OP'd v4.
    """
    rec, edges_raw = _capture(lambda: body.GetEdges())
    edge_list = (list(edges_raw) if edges_raw and isinstance(edges_raw, (list, tuple))
                 else [edges_raw] if edges_raw else [])
    diag["edge_count"] = len(edge_list)
    if not edge_list:
        diag["error"] = "no edges"
        return None

    measured: list[dict[str, Any]] = []
    for i, e in enumerate(edge_list):
        pts = _edge_endpoints(e)
        if pts is None:
            continue
        (sx, sy, sz), (ex, ey, ez) = pts
        length = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2 + (ez - sz) ** 2)
        mid = ((sx + ex) / 2.0, (sy + ey) / 2.0, (sz + ez) / 2.0)
        measured.append({
            "idx": i,
            "len_mm": round(length * 1000.0, 4),
            "mid_mm": [round(c * 1000.0, 4) for c in mid],
            "edge": e,
        })

    if not measured:
        diag["error"] = "no measurable edges"
        return None

    measured.sort(key=lambda m: m["len_mm"], reverse=True)
    diag["edge_lengths_mm"] = [m["len_mm"] for m in measured]
    chosen = measured[0]
    diag["chosen_edge"] = {
        "idx": chosen["idx"],
        "len_mm": chosen["len_mm"],
        "mid_mm": chosen["mid_mm"],
    }
    # Sanity: the longest edge of a 60x40x2 plate must be ~60mm; if it is not,
    # the fixture is not the shape we think it is — fail loud rather than fire.
    if not (55.0 <= chosen["len_mm"] <= 65.0):
        diag["error"] = (f"longest edge {chosen['len_mm']}mm not the expected "
                         f"~60mm boundary — aborting before the fire")
        return None

    edge = chosen["edge"]
    # Resolve through a persist reference for a stable selectable entity
    # (the v4 pattern; a raw GetEdges dispatch can go stale across rebuild).
    try:
        ext = typed_extension(doc, module=mod)
        pid = ext.GetPersistReference3(edge)
        if pid:
            obj_result = ext.GetObjectByPersistReference3(pid)
            edge = obj_result[0] if isinstance(obj_result, tuple) else obj_result
    except Exception as e:
        diag["edge_resolve"] = f"{type(e).__name__}: {e}"[:120]

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    try:
        typed(edge, "IEntity", module=mod).Select2(False, 0)
        diag["select2"] = True
    except Exception as e:
        diag["select2_error"] = f"{type(e).__name__}: {e}"[:120]
        try:
            edge.Select2(False, 0)
            diag["select2"] = True
        except Exception as e2:
            diag["select2_fallback_error"] = f"{type(e2).__name__}: {e2}"[:120]
            return None
    return edge


def _build_fixture_v5(sw: Any, mod: Any) -> tuple[Any, Any, Any, dict[str, Any]]:
    """Base flange 60x40x2 + the deterministically chosen longest boundary edge."""
    diag: dict[str, Any] = {}
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        diag["error"] = "NewDocument None"
        return None, None, None, diag
    fm = doc.FeatureManager

    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        sk.CreateCornerRectangle(
            -PROF_W_M / 2, -PROF_H_M / 2, 0.0,
            PROF_W_M / 2, PROF_H_M / 2, 0.0)
        sk.InsertSketch(True)
    except Exception as e:
        diag["sketch_error"] = f"{type(e).__name__}: {e}"[:200]

    def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_BASEFLANGE))
    diag["create_definition"] = def_rec
    if data is None:
        diag["error"] = "CreateDefinition None"
        return doc, None, None, diag
    qi_rec, wrapped = _capture(lambda: typed_qi(data, IFACE_BASEFLANGE, module=mod))
    diag["typed_qi"] = qi_rec
    if wrapped is None:
        diag["error"] = "typed_qi None"
        return doc, None, None, diag
    for name, val in (("Thickness", THICKNESS_M), ("BendRadius", BEND_RADIUS_M)):
        try:
            setattr(wrapped, name, val)
        except Exception:
            pass
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
    diag["create_feature"] = feat_rec
    if not _materialized(feat):
        diag["error"] = "base flange not materialized"
        return doc, None, None, diag

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    rec, bodies = _capture(lambda: doc.GetBodies2(SW_BODY_SOLID, True))
    body_list = (list(bodies) if bodies and isinstance(bodies, (list, tuple))
                 else [bodies] if bodies else [])
    if not body_list:
        diag["error"] = "no bodies"
        return doc, fm, None, diag

    edge = _select_longest_boundary_edge(doc, body_list[0], mod, diag)
    if edge is None:
        diag.setdefault("error", "no valid boundary edge")
        return doc, fm, None, diag
    return doc, fm, edge, diag


def _write_and_report(out: dict[str, Any], code: int) -> int:
    res_dir = Path(__file__).resolve().parent / "_results"
    res_dir.mkdir(parents=True, exist_ok=True)
    out_path = res_dir / "hem_v5_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    sys.stderr.write(f"[hem-v5] wrote {out_path}\n")
    sys.stderr.write(f"[hem-v5] VERDICT: {out.get('verdict')} (exit {code})\n")
    sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
    return code


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "spike": "hem_v5",
        "purpose": "edge-precondition fix — longest boundary edge + Tactic 1 (VT_DISPATCH None) only",
        "funcdesc_anchor": "hem_funcdesc_dump.json (memid=91, arity=9, PCBA=PTR/26)",
        "adjudication": "W0 2026-06-16: v4 residual NO_OP = topological-solver barrier, not marshaling",
    }
    sw = None
    doc = None
    code = 1
    try:
        mod = wrapper_module()
        sw = connect_running_sw()
        rev = sw.RevisionNumber
        out["sw_revision"] = rev() if callable(rev) else rev

        doc, fm, edge, diag = _build_fixture_v5(sw, mod)
        out["fixture"] = diag
        if doc is None or fm is None or edge is None:
            out["error"] = diag.get("error", "fixture build failed")
            out["verdict"] = "ERROR"
            return _write_and_report(out, 1)

        before = _metrics(doc)
        out["faces_before"] = before["faces"]
        out["vol_mm3_before"] = before["vol_mm3"]

        rec, feat = _tactic_1_makepy_vt_dispatch(fm)
        out["call"] = rec
        out["materialized"] = _materialized(feat)

        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass

        after = _metrics(doc)
        out["faces_after"] = after["faces"]
        out["vol_mm3_after"] = after["vol_mm3"]
        out["delta_faces"] = after["faces"] - before["faces"]
        out["delta_vol_mm3"] = round(after["vol_mm3"] - before["vol_mm3"], 3)
        out["hem_feature"] = _check_hem_materialized(doc, mod)

        if out["delta_faces"] > 0 and out["delta_vol_mm3"] != 0:
            out["verdict"] = "PASS"
            out["persist"] = _save_reopen_v5(sw, mod, doc)
            doc = None  # _save_reopen_v5 closed all docs
            p = out["persist"]
            survived = bool(p.get("reopened")
                            and p.get("hem_feature", {}).get("found")
                            and p.get("faces_after_reopen", 0) > before["faces"])
            out["persist_survived"] = survived
            code = 0 if survived else 2
            if not survived:
                out["verdict"] = "PASS_BUT_NOT_PERSISTED"
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
