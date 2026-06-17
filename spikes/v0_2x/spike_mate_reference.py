"""Spike v0.2x / W63-lane1 — mate_reference creation via parametric COM.

[authored seat-free; RUN ON A LIVE SEAT — W0 fires]

Probes the mate-reference API via the SHIPPING handler:
  Mode-A (quarantined): no swFmMateReference in swconst.tlb — skipped.
  Mode-B (primary path): ``IFeatureManager.InsertMateReference2`` — a 12-arg
  PARAMETRIC call (entities passed directly, NO selection marks). DLL
  reflection (SolidWorks.Interop.sldworks.dll 32.1.0.123, 2026-06-17) gives
  the authoritative signature; the recollection 13-arg form is a
  hallucination (no TertiaryReferenceAlignAxes).

Geometry: a 40x30x10 mm block on the Front Plane. Entity:
  - primary: the +X face, captured durably via persist_id and fed to the
    handler through a persist-only ref (resolve_ref tier-1, the proven path).

If the handler fails, a DIRECT-API probe fires to disambiguate a resolution
failure from a genuine InsertMateReference2 failure.

A7 probe: logs the kernel's actual ``GetTypeName2`` for the new node — the
guessed name is NOT trusted (bbox returned 'BoundingBoxProfileFeat',
com_point 'CenterOfMassRefPoint'). The verifier matches substring 'materef'.

Verdicts
--------
PASS    — mate-reference node materializes via the handler, survives save->reopen.
PARTIAL — handler ok + node found but save/reopen failed.
FAIL    — handler fails (direct probe result recorded for diagnosis).

Usage
-----
    C:/Python314/python.exe spikes/v0_2x/spike_mate_reference.py --out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _feature_spike_fixtures

import pythoncom  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.features.mate_reference import create_mate_reference  # noqa: E402
from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402
from _feature_spike_fixtures import save_and_reopen  # noqa: E402

BOX_W_M = 0.040
BOX_H_M = 0.030
BOX_D_M = 0.010

SW_DEFAULT_TEMPLATE_PART = 8


class _PersistOnlyRef:
    """Minimal ref carrying just a persist_id — resolve_ref resolves it via
    tier-1 (the proven-reliable path), no fingerprint needed. Mirrors what a
    production DurableRef/DurableEdgeRef does for the persist-GREEN case."""

    def __init__(self, persist_id: bytes | None) -> None:
        self.persist_id = persist_id


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _build_block(doc: Any) -> dict[str, Any]:
    """Build a 40x30x10 mm box on the Front Plane (W62 archetype)."""
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}

    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0,
        BOX_W_M / 2, BOX_H_M / 2, 0.0,
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)

    fm = doc.FeatureManager
    base_args = (
        True, False, False, 0, 0, BOX_D_M, 0.0,
        False, False, False, False,
        0.0, 0.0, False, False, False, False,
        True, True, True, 0, 0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)
    except Exception:
        feat = fm.FeatureExtrusion2(*base_args)
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _count_feature_nodes(doc: Any) -> int:
    feats = doc.FeatureManager.GetFeatures(False)
    return len(feats) if feats else 0


def _type_name_of(node: Any) -> str:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            _v = getattr(node, attr)
            return str(_v() if callable(_v) else _v)
        except Exception:
            continue
    return ""


def _is_materef(tn: str) -> bool:
    return "materef" in tn.lower()


def _find_plus_x_face(doc: Any) -> Any:
    """Select + return the live +X IFace2 via the proven coordinate-pick
    pattern (Extension.SelectByID2 + GetSelectedObject6 — the
    _feature_spike_fixtures.top_face recipe). The +X face of the block sits at
    x = +BOX_W_M/2, centred at (BOX_W_M/2, 0, BOX_D_M/2). Walking GetFaces +
    PlaneParams is brittle (PlaneParams is a flat 6-array, not (origin,normal));
    the coordinate pick sidesteps it entirely."""
    try:
        null = VARIANT(pythoncom.VT_DISPATCH, None)
        doc.Extension.SelectByID2(
            "", "FACE", BOX_W_M / 2, 0.0, BOX_D_M / 2, False, 0, null, 0
        )
        face = doc.SelectionManager.GetSelectedObject6(1, -1)
        doc.ClearSelection2(True)
        return face
    except Exception:
        return None


def _new_node_types(doc: Any, before: int) -> list[str]:
    """A7 probe — the kernel's actual type-name strings for the new tail nodes."""
    feats = doc.FeatureManager.GetFeatures(False) or []
    return [_type_name_of(f) for f in feats[before:]]


def _find_materef_node(doc: Any) -> str | None:
    feats = doc.FeatureManager.GetFeatures(False)
    if not feats:
        return None
    for node in feats:
        tn = _type_name_of(node)
        if _is_materef(tn):
            return tn
    return None


def _direct_api_probe(doc: Any) -> dict[str, Any]:
    """Bypass the handler: call InsertMateReference2 directly with the live
    +X face. Isolates the API/signature question from entity resolution."""
    out: dict[str, Any] = {"ran": True}
    face = _find_plus_x_face(doc)
    out["face_found"] = face is not None
    if face is None:
        return out
    try:
        ent = typed(face, "IEntity")
    except Exception as exc:
        out["typed_entity_error"] = f"{type(exc).__name__}: {exc}"
        ent = face
    fm = doc.FeatureManager
    try:
        fm_t = typed_qi(fm, "IFeatureManager", module=wrapper_module())
    except Exception as exc:
        out["typed_qi_error"] = f"{type(exc).__name__}: {exc}"
        fm_t = fm
    # Null entity args on the typed proxy must be plain None, NOT a VARIANT
    # (the typed wrapper can't convert a VARIANT to a COM object — W63 lesson).
    before = _count_feature_nodes(doc)
    try:
        feat = fm_t.InsertMateReference2(
            "DirectProbe", ent, 0, 0, False, None, 0, 0, False, None, 0, 0,
        )
        out["call_ok"] = True
        out["returned"] = repr(feat)
    except Exception as exc:
        out["call_ok"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    after = _count_feature_nodes(doc)
    out["delta"] = after - before
    out["new_node_types"] = _new_node_types(doc, before)
    out["materef_node"] = _find_materef_node(doc)
    return out


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "late (dynamic dispatch)"}
    mod, info = ensure_sw_module()
    result["module_info"] = info

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    try:
        build = _build_block(doc)
        result["block"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "block build failed"}

        before = _count_feature_nodes(doc)
        result["nodes_before"] = before

        # Capture the +X face durably (persist_id tier-1) and feed the
        # SHIPPING handler a persist-only ref.
        face = _find_plus_x_face(doc)
        result["plus_x_face_found"] = face is not None
        if face is None:
            return {**result, "overall": "FAIL", "reason": "no +X face found"}

        from ai_sw_bridge.selection.live import capture_persist_id
        persist_id = capture_persist_id(doc, face)
        result["persist_id_captured"] = persist_id is not None
        if persist_id is None:
            # Resolution can't proceed without a token; go straight to the
            # direct probe so we still learn whether the API works.
            result["direct_api_probe"] = _direct_api_probe(doc)
            return {**result, "overall": "FAIL", "reason": "persist_id capture failed"}

        feature = {
            "type": "mate_reference",
            "name": "MateRef-1",
            "entities": [{"ref": _PersistOnlyRef(persist_id), "role": "primary"}],
        }

        t0 = time.perf_counter()
        ok, note = create_mate_reference(doc, feature, {})
        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
        result["handler_ok"] = ok
        result["handler_note"] = note

        after = _count_feature_nodes(doc)
        result["nodes_after"] = after
        result["node_delta"] = after - before
        result["new_node_types"] = _new_node_types(doc, before)  # A7 probe
        materef_type = _find_materef_node(doc)
        result["mate_reference_type"] = materef_type
        result["mate_reference_in_tree"] = materef_type is not None

        # Diagnostic: if the handler did not materialize a node, run the
        # direct API probe to split resolution-failure from API-failure.
        if not (ok and materef_type is not None):
            result["direct_api_probe"] = _direct_api_probe(doc)

        # Save -> reopen via the SHARED typed-OpenDoc6 fixture (bare
        # sw.OpenDoc walls arg-marshaling — com_point round-5 lesson).
        reopen: dict[str, Any] = {}
        try:
            doc2 = save_and_reopen(sw, doc)
            reopen["saved"] = True
            reopen["reopened"] = doc2 is not None
            if doc2 is not None:
                reopen["node_count_after"] = _count_feature_nodes(doc2)
                survived = _find_materef_node(doc2)
                reopen["mate_reference_type_after"] = survived
                reopen["mate_reference_survived"] = survived is not None
        except Exception as exc:
            reopen["reopened"] = False
            reopen["error"] = f"{type(exc).__name__}: {exc}"
        result["save_reopen"] = reopen

        if ok and materef_type is not None and reopen.get("mate_reference_survived"):
            result["overall"] = "PASS"
        elif ok and materef_type is not None:
            result["overall"] = "PARTIAL"
            result["partial_reason"] = "node found but save/reopen failed"
        else:
            result["overall"] = "FAIL"
            result["fail_reason"] = note or "handler returned False"
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

    return result


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if k != "_val"}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
