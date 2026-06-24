"""W64 disposition probe — does the SHIPPED mutate._create_ref_axis wall OOP?

Ground-truth test of the bare-``None`` SelectByID2 callout (arg 8) in the
production Wave-5 handler ``mutate._create_ref_axis``, fired ENTIRELY
out-of-process on the live seat (no monkeypatched win32com seams — the
offline tests mock the COM boundary and can never see this).

The suspect line (mutate.py ~998):
    ext.SelectByID2(planes[1], "PLANE", 0, 0, 0, True, 0, None, 0)
                                                          ^^^^ bare None

The W64 ref_axis spike walled here with com_error(-2147352571,
'Type mismatch.', None, 8) on the late-bound doc.Extension proxy; a typed
VARIANT(VT_DISPATCH, None) was the load-bearing fix.

Two probes:
  A. Call the SHIPPED handler mutate._create_ref_axis(doc, feature, target)
     with target.planes=['Front Plane','Right Plane'] and inspect (ok, note).
  B. A minimal direct reproduction: doc.Extension.SelectByID2(..., None, 0)
     vs (..., VARIANT(VT_DISPATCH,None), 0) — isolate the callout from the
     handler's surrounding logic and capture the raw com_error.

Verdict:
  WALLS  — handler returns False with a Type-mismatch note OR direct probe
           A-None raises while A-VARIANT succeeds → existing handler is
           latently broken OOP; W64 ref_axis logic is a genuine fix.
  CLEAN  — handler materializes a RefAxis node → existing handler is fine
           OOP; W64 ref_axis is pure duplication, prune it.

Usage:
    C:/Python314/python.exe spikes/v0_2x/probe_existing_ref_axis_oop.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # _feature_spike_fixtures

RESULTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "_results"
    / "probe_existing_ref_axis_oop.json"
)

import pythoncom  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from _feature_spike_fixtures import build_block, save_and_reopen  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402


def _count_nodes(doc: Any) -> int:
    try:
        feats = doc.FeatureManager.GetFeatures(False)
        return len(feats) if feats else 0
    except Exception:
        return 0


def _type_name(node: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(node, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _find_axis_type(doc: Any) -> str | None:
    try:
        feats = doc.FeatureManager.GetFeatures(False) or []
    except Exception:
        return None
    for node in feats:
        t = _type_name(node)
        if t and ("refaxis" in t.lower() or t.lower() == "axis"):
            return t
    return None


def _probe_direct_callout(doc: Any) -> dict[str, Any]:
    """B: isolate the bare-None vs VARIANT callout on the append-select."""
    out: dict[str, Any] = {}
    # Bare None (the shipped handler's exact arg shape).
    try:
        doc.ClearSelection2(True)
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        r = doc.Extension.SelectByID2("Right Plane", "PLANE", 0, 0, 0, True, 0, None, 0)
        out["bare_none_ok"] = bool(r)
        out["bare_none_return"] = repr(r)
    except Exception as exc:
        out["bare_none_ok"] = False
        out["bare_none_error"] = f"{type(exc).__name__}: {exc}"
    # Typed VARIANT(VT_DISPATCH, None) (the W64 fix).
    try:
        doc.ClearSelection2(True)
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        null = VARIANT(pythoncom.VT_DISPATCH, None)
        r = doc.Extension.SelectByID2("Right Plane", "PLANE", 0, 0, 0, True, 0, null, 0)
        out["variant_ok"] = bool(r)
        out["variant_return"] = repr(r)
    except Exception as exc:
        out["variant_ok"] = False
        out["variant_error"] = f"{type(exc).__name__}: {exc}"
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    return out


def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "probe_id": "W64_disposition_existing_ref_axis_oop",
        "target": "mutate._create_ref_axis (shipped Wave-5 built-in)",
    }
    try:
        sw = get_sw_app()
    except Exception as exc:
        return {**result, "overall": "ERROR", "reason": f"cannot connect: {exc!r}"}
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"

    try:
        doc = build_block(sw)
    except Exception as exc:
        return {**result, "overall": "ERROR", "reason": f"build_block: {exc!r}"}

    try:
        # --- Probe A: the shipped handler, untouched ---
        before = _count_nodes(doc)
        result["nodes_before"] = before

        feature = {"kind": "ref_axis", "name": "Axis1"}
        target = {"planes": ["Front Plane", "Right Plane"]}
        ok, note = mutate._create_ref_axis(doc, feature, target)
        result["handler_ok"] = ok
        result["handler_note"] = note

        after = _count_nodes(doc)
        result["nodes_after"] = after
        result["node_delta"] = after - before
        result["axis_type_in_tree"] = _find_axis_type(doc)

        note_l = (note or "").lower()
        result["note_mentions_type_mismatch"] = (
            "type mismatch" in note_l or "arg 8" in note_l or "-2147352571" in note_l
        )

        # Save/reopen survival (only meaningful if it materialized).
        if ok and result["axis_type_in_tree"]:
            try:
                doc2 = save_and_reopen(sw, doc)
                result["survives_reopen"] = (
                    doc2 is not None and _find_axis_type(doc2) is not None
                )
            except Exception as exc:
                result["survives_reopen"] = False
                result["reopen_error"] = f"{type(exc).__name__}: {exc}"

        # --- Probe B: direct callout isolation (fresh block) ---
        doc_b = build_block(sw)
        result["direct_callout_probe"] = _probe_direct_callout(doc_b)

        # --- Verdict ---
        handler_walled = (not ok) and result["note_mentions_type_mismatch"]
        dc = result["direct_callout_probe"]
        callout_asymmetry = (dc.get("bare_none_ok") is False) and (
            dc.get("variant_ok") is True
        )

        if handler_walled or callout_asymmetry:
            result["overall"] = "WALLS"
            result["finding"] = (
                "Shipped mutate._create_ref_axis is latently broken OOP: the bare-None "
                "SelectByID2 callout walls 'Type mismatch arg 8' on the late-bound proxy. "
                "W64 ref_axis (VARIANT callout) is a genuine fix."
            )
        elif ok and result.get("axis_type_in_tree"):
            result["overall"] = "CLEAN"
            result["finding"] = (
                "Shipped mutate._create_ref_axis materializes a RefAxis node OOP. "
                "W64 ref_axis is pure duplication — prune it."
            )
        else:
            result["overall"] = "INCONCLUSIVE"
            result["finding"] = (
                f"Handler ok={ok}, note={note!r}, delta={result['node_delta']}, "
                f"direct={dc}. Neither a clean Type-mismatch wall nor a clean materialize."
            )
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    return result


def main() -> None:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(result, indent=2, default=lambda o: f"<{type(o).__name__}>"),
        encoding="utf-8",
    )
    print(f"verdict: {result.get('overall')}", file=sys.stderr)
    print(f"finding: {result.get('finding')}", file=sys.stderr)
    print(f"results written to {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
