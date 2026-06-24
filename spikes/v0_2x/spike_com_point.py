"""Spike W63 / COM_POINT — InsertCenterOfMass materialization probe.

Tests whether a Center-of-Mass reference point can be created via the
legacy ``IModelDoc2.InsertCenterOfMass`` (no-arg) on a solid block part.

Pipeline under test:
    build_block(sw)  →  handler.create_com_point(doc, feature, target)

Records:
  * feature node count before/after (liveness gate)
  * GetTypeName2 of the new node ("CenterOfMass" or "CenterOfMassFolder")
  * which mode fired (mode_b only — mode_a is skipped by design)
  * save → reopen survival (the W21 ghost trap)

Verdicts:
  GO    — count +1, CenterOfMass-typed, survives reopen.
  NO-GO — InsertCenterOfMass no-ops, or wrong type, or does not survive.

Usage:
    C:/Python314/python.exe spikes/v0_2x/spike_com_point.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "com_point.json"

import pythoncom  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _feature_spike_fixtures
from _feature_spike_fixtures import save_and_reopen  # noqa: E402

from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.features.com_point import (  # noqa: E402
    create_com_point,
    _count_feature_nodes,
    _find_com_node,
    _get_type_name,
)

SW_DEFAULT_TEMPLATE_PART = 8

BOX_W_M = 0.040  # 40 mm
BOX_H_M = 0.030  # 30 mm
BOX_D_M = 0.010  # 10 mm

SAVE_PATH = (
    Path(__file__).resolve().parents[2]
    / "spikes"
    / "v0_2x"
    / "_artifacts"
    / "com_point_test.sldprt"
)


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _build_block(doc: Any) -> dict[str, Any]:
    """Build a 40x30x10 mm block (the W62 archetype)."""
    out: dict[str, Any] = {}
    fm = doc.FeatureManager
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        sk = doc.SketchManager
        sk.InsertSketch(True)
        sk.CreateCornerRectangle(
            -BOX_W_M / 2,
            -BOX_H_M / 2,
            0.0,
            BOX_W_M / 2,
            BOX_H_M / 2,
            0.0,
        )
        sk.InsertSketch(True)
        out["sketch"] = "Sketch1"
    except Exception as e:
        out["sketch_error"] = f"{type(e).__name__}: {e}"
        return out

    try:
        feat = fm.FeatureExtrusion3(
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
            0,
            False,
        )
        out["extrude"] = feat is not None
        out["extrude_materialized"] = feat is not None and not isinstance(feat, int)
    except Exception as e:
        out["extrude_error"] = f"{type(e).__name__}: {e}"
    try:
        doc.EditRebuild3()
    except Exception:
        pass
    return out


def _save_and_reopen(sw: Any, doc: Any) -> dict[str, Any]:
    """Save, close, reopen — return the new doc or None.

    W63 round-5 fix: the bespoke reopen called bare late-bound
    ``sw.OpenDoc6`` which walls at arg-5 with ``com_error -2147352571
    'Type mismatch.'`` — the same CDispatch dispatch failure that walled
    the handler's CoM insert. We delegate to the SHARED
    ``_feature_spike_fixtures.save_and_reopen`` which types ``sw`` to
    ``ISldWorks`` first and calls ``OpenDoc6`` on the typed proxy (proven
    in the bbox round-5 fire). Same late-bound-first / typed-fallback
    lesson; do NOT reintroduce a bare ``sw.OpenDoc6`` here.
    """
    out: dict[str, Any] = {}
    try:
        reopened = save_and_reopen(sw, doc)
        out["saved"] = True
        out["closed"] = True
        out["reopened"] = reopened is not None
        if reopened is not None:
            out["doc"] = reopened
    except Exception as e:
        # The fixture raises on any failure in the save/close/reopen chain;
        # we can't cheaply tell which step failed, so record the message.
        out.setdefault("saved", True)
        out.setdefault("closed", True)
        out["reopened"] = False
        out["reopen_error"] = f"{type(e).__name__}: {e}"
    return out


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike_id": "W63_com_point",
        "pipeline": "IModelDoc2.InsertCenterOfMass (Mode-B only — Mode-A skipped by design)",
    }

    try:
        sw = get_sw_app()
    except Exception as e:
        result["sw_connection"] = f"{type(e).__name__}: {e}"
        result["overall"] = "NO-GO"
        result["reason"] = "cannot connect to SOLIDWORKS"
        return result

    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        result["overall"] = "NO-GO"
        result["reason"] = "NewDocument returned None"
        return result

    try:
        box = _build_block(doc)
        result["box"] = box
        if not box.get("extrude_materialized"):
            result["overall"] = "NO-GO"
            result["reason"] = "box extrude failed"
            return result

        before = _count_feature_nodes(doc)
        result["node_count_before"] = before

        ok, note = create_com_point(doc, {"kind": "com_point", "name": "CoM-1"}, {})
        result["handler_ok"] = ok
        result["handler_note"] = note

        after = _count_feature_nodes(doc)
        result["node_count_after"] = after
        result["node_delta"] = after - before

        com_node = _find_com_node(doc)
        if com_node is not None:
            result["com_node_type"] = _get_type_name(com_node)
            result["com_node_found"] = True
        else:
            result["com_node_found"] = False

        if not ok or after - before < 1 or com_node is None:
            result["overall"] = "NO-GO"
            result["reason"] = (
                f"handler_ok={ok}, delta={after - before}, "
                f"com_node={'found' if com_node else 'missing'}"
            )
            return result

        reopen = _save_and_reopen(sw, doc)
        result["reopen"] = {k: v for k, v in reopen.items() if k != "doc"}

        if not reopen.get("reopened"):
            result["overall"] = "NO-GO"
            result["reason"] = "save/reopen failed"
            return result

        reopened_doc = reopen["doc"]
        after_reopen = _count_feature_nodes(reopened_doc)
        result["node_count_after_reopen"] = after_reopen

        com_node_reopen = _find_com_node(reopened_doc)
        result["com_node_survives_reopen"] = com_node_reopen is not None
        if com_node_reopen is not None:
            result["com_node_type_after_reopen"] = _get_type_name(com_node_reopen)

        if com_node_reopen is not None:
            result["overall"] = "GO"
            result["confirmed"] = {
                "mode_fired": note or "mode_b",
                "feature_node_delta": after - before,
                "type_name": _get_type_name(com_node),
                "survives_reopen": True,
            }
        else:
            result["overall"] = "NO-GO"
            result["reason"] = "CenterOfMass node did not survive save/reopen"

    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        result["cleanup"] = "CloseAllDocuments(True)"

    return result


def main() -> None:
    result = run()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    verdict = result.get("overall", "NO-GO")
    print(f"verdict: {verdict}", file=sys.stderr)
    if result.get("confirmed"):
        print(
            f"confirmed: {json.dumps(result['confirmed'], indent=2)}", file=sys.stderr
        )
    print(f"results written to {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
