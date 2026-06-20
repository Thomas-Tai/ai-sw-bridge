"""W67 P3b — CURVE geometric-witness head-hop probe (DO NOT RUN OFFLINE).

The CURVE lanes (composite/helix/project_curve) gate on a feature-node COUNT
delta alone — the W42 ghost trap.  The geometric anti-ghost witness is total
arc length.  The length TAIL is proven OOP (brep/interrogator.py:
``typed_qi(ICurve).GetEndParams()`` → ``GetLength(tmin,tmax)``), reused verbatim
inside ``verify.icurve_length_mm``.  The unproven piece is the HEAD hop —
``IFeature`` node → ``ICurve`` — for a STANDALONE reference curve (the
interrogator only proves EDGE → ICurve, i.e. solid-body topology; a reference
curve is not a B-rep boundary).

This spike fires the PRODUCTION-CANDIDATE function ``verify.curve_length_mm``
against real curve nodes and reports, per lane:

  * the runtime type of ``GetSpecificFeature2()`` (O1 introspection — we never
    guess the QI target; we discover what SW actually hands back);
  * which candidate head landed (GetCurves / GetSketchSegments / GetEdges);
  * the measured arc length (mm) vs the expected geometry.

VERDICT semantics (per node type):
  PASS    — verify.curve_length_mm returned a positive length matching geometry
  NO_OP   — node created but curve_length_mm returned None (head hop WALLED OOP)
  ERROR   — fixture / COM fault

If a head lands, W0 wires ``gate_curve`` into that lane's handler (a follow-up
commit).  If ALL heads NO_OP, the CURVE witness is Route-C-walled OOP and the
lanes keep their node-count gate (documented in DEFERRED.md).

Co-located with the sibling W62 curve spikes (spike_helix/composite/
project_curve) so ``_feature_spike_fixtures`` resolves with no path hacks.

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

from ai_sw_bridge.features import verify  # noqa: E402

# -- Helix parameters (mirror spike_helix so geometry is predictable) ---------
HELIX_PITCH_MM = 5.0
HELIX_REVOLUTIONS = 4.0
SW_HELIX_DEFINED_BY_PITCH_AND_REV = 0


def _resolve(obj: Any, attr: str) -> Any:
    v = getattr(obj, attr)
    return v() if callable(v) else v


def _type_name(node: Any) -> str:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            return str(_resolve(node, attr))
        except Exception:
            continue
    return "<unknown>"


def _feature_nodes(doc: Any) -> list[Any]:
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return []
    return list(feats) if feats else []


def _nodes_matching(doc: Any, tokens: tuple[str, ...]) -> list[Any]:
    """Curve nodes whose type-name contains any token (lowercased substring)."""
    out = []
    for n in _feature_nodes(doc):
        low = _type_name(n).lower()
        if any(t in low for t in tokens):
            out.append(n)
    return out


def _introspect_head(node: Any) -> dict[str, Any]:
    """O1 introspection of the IFeature → ICurve head ladder on a real node.

    Discovers (never guesses) what GetSpecificFeature2() returns and which
    candidate tail the spec object exposes, so a NO_OP verdict is diagnosable.
    """
    diag: dict[str, Any] = {"type_name": _type_name(node)}
    try:
        spec = _resolve(node, "GetSpecificFeature2")
        diag["specific_feature_repr"] = repr(spec)[:160]
        diag["specific_feature_type"] = type(spec).__name__
        for probe in ("GetCurves", "GetSketchSegments", "GetEdges"):
            try:
                val = _resolve(spec, probe) if spec is not None else None
                diag[f"spec.{probe}"] = (
                    f"len={len(val)}" if isinstance(val, (list, tuple))
                    else repr(val)[:80]
                )
            except Exception as e:
                diag[f"spec.{probe}_error"] = f"{type(e).__name__}: {e}"[:120]
    except Exception as e:
        diag["specific_feature_error"] = f"{type(e).__name__}: {e}"[:160]
    # node-level GetEdges (low-confidence head 3)
    try:
        edges = _resolve(node, "GetEdges")
        diag["node.GetEdges"] = (
            f"len={len(edges)}" if isinstance(edges, (list, tuple))
            else repr(edges)[:80]
        )
    except Exception as e:
        diag["node.GetEdges_error"] = f"{type(e).__name__}: {e}"[:120]
    return diag


def _probe_lane(
    doc: Any, label: str, tokens: tuple[str, ...], expected_min_mm: float,
) -> dict[str, Any]:
    """Locate the new curve node, introspect its head, fire the production
    candidate verify.curve_length_mm, and judge."""
    nodes = _nodes_matching(doc, tokens)
    if not nodes:
        return {"lane": label, "verdict": "NO_NODE", "tokens": list(tokens)}
    node = nodes[-1]  # the most-recently-created matching node
    res: dict[str, Any] = {
        "lane": label,
        "introspection": _introspect_head(node),
        "expected_min_mm": expected_min_mm,
    }
    try:
        length_mm = verify.curve_length_mm(node)
        res["curve_length_mm"] = length_mm
        if length_mm is None:
            res["verdict"] = "NO_OP"  # head hop WALLED — gate would fail-closed
        elif length_mm >= expected_min_mm:
            res["verdict"] = "PASS"
        else:
            res["verdict"] = "SHORT"  # length read but implausibly small
    except Exception as e:
        res["verdict"] = "ERROR"
        res["error"] = f"{type(e).__name__}: {e}"[:200]
    return res


def _make_helix(doc: Any) -> bool:
    sketch = fx.seed_circle_sketch(doc)
    pitch_m = HELIX_PITCH_MM / 1000.0
    height_m = pitch_m * HELIX_REVOLUTIONS
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    null_callout = VARIANT(pythoncom.VT_DISPATCH, None)
    try:
        if not doc.Extension.SelectByID2(
            sketch, "SKETCH", 0.0, 0.0, 0.0, False, 0, null_callout, 0,
        ):
            return False
        doc.InsertHelix(
            True, False, False, True, SW_HELIX_DEFINED_BY_PITCH_AND_REV,
            pitch_m, HELIX_REVOLUTIONS, height_m, 0.0, 0.0,
        )
        doc.ForceRebuild3(False)
    except Exception:
        return False
    return True


def _make_composite(doc: Any) -> bool:
    try:
        edges = fx.top_face_edges(doc, n=2)
        doc.ClearSelection2(True)
        for e in edges:
            if hasattr(e, "Select2"):
                e.Select2(True, 1)  # append, mark=1 (Edges-to-join list box)
        ic = doc.InsertCompositeCurve
        _ = ic() if callable(ic) else ic
        doc.ForceRebuild3(False)
    except Exception:
        return False
    return True


def _write_and_report(out: dict[str, Any], code: int) -> int:
    res_dir = Path(__file__).resolve().parent / "_results"
    res_dir.mkdir(parents=True, exist_ok=True)
    out_path = res_dir / "curve_length_witness.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    sys.stderr.write(f"[curve-witness] wrote {out_path}\n")
    sys.stderr.write(f"[curve-witness] VERDICT: {out.get('verdict')} (exit {code})\n")
    sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
    return code


def main() -> int:
    pythoncom.CoInitialize()
    out: dict[str, Any] = {
        "spike": "curve_length_witness",
        "purpose": (
            "Prove (or wall) the IFeature -> ICurve head hop for standalone "
            "reference curves; fire production-candidate verify.curve_length_mm "
            "on real helix/composite nodes; report which head lands."
        ),
        "lanes": [],
    }
    sw = None
    doc = None
    code = 1
    try:
        sw = fx.connect()
        rev = sw.RevisionNumber
        out["sw_revision"] = rev() if callable(rev) else rev

        # --- Helix lane: pitch 5mm * 4 rev on a 20mm-dia sketch circle.
        # Expected length ~ sqrt((pi*D)^2 + pitch^2) per turn * revs; lower-bound
        # generously at the total height (4*5=20mm) so SHORT only flags a near-
        # zero ghost, not a geometry-model mismatch.
        doc = fx.build_block(sw)
        if _make_helix(doc):
            out["lanes"].append(
                _probe_lane(doc, "helix", ("helix",), expected_min_mm=20.0)
            )
        else:
            out["lanes"].append({"lane": "helix", "verdict": "MAKE_FAILED"})

        # --- Composite lane: join >=2 top-face edges (40x30 block -> perimeter
        # edges each >=30mm); lower-bound at 20mm.
        if _make_composite(doc):
            out["lanes"].append(
                _probe_lane(
                    doc, "composite",
                    ("compositecurve", "refcurve", "ref_curve"),
                    expected_min_mm=20.0,
                )
            )
        else:
            out["lanes"].append({"lane": "composite", "verdict": "MAKE_FAILED"})

        verdicts = [latest.get("verdict") for latest in out["lanes"]]
        if any(v == "PASS" for v in verdicts):
            out["verdict"] = "HEAD_PROVEN"
            out["wire_recommendation"] = (
                "Wire verify.gate_curve into the lane(s) whose verdict is PASS; "
                "leave NO_OP lanes on node-count and document in DEFERRED.md."
            )
            code = 0
        elif all(v in ("NO_OP", "SHORT") for v in verdicts):
            out["verdict"] = "HEAD_WALLED"
            out["wire_recommendation"] = (
                "IFeature -> ICurve head hop WALLED OOP for all probed lanes; "
                "CURVE witness is Route-C. Keep node-count gate; DEFERRED.md."
            )
            code = 2
        else:
            out["verdict"] = "PARTIAL"
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
