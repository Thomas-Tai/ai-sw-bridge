"""Seat-check: drive the variable_radius_fillet feature_add through the real
PAE lifecycle (propose -> dry_run -> commit) against mutate.py, anchored on two
DURABLE edge refs with DISTINCT radii.

Non-destructive: own box in a temp .sldprt; proposals to a temp dir.

Usage:  .venv-py310\Scripts\python spikes\v0_16\_seatcheck_varfil_pae.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ["AI_SW_BRIDGE_FLAG_BREP_INTERROGATION"] = "1"
os.environ["AI_SW_BRIDGE_FLAG_PERSIST_CAPTURE"] = "1"

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="aiswb_varfil_"))
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_TMP / "proposals")

from ai_sw_bridge.brep.interrogator import interrogate  # noqa: E402
from ai_sw_bridge.com.earlybind import typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.selection import DurableEdgeRef  # noqa: E402
from ai_sw_bridge import mutate  # noqa: E402

from spike_persist_reference import build_single_box  # noqa: E402
from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

R0_MM = 2.0
R1_MM = 4.0


class _Ctx:
    def __init__(self, doc: Any) -> None:
        self.doc = doc


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _mid(e: dict) -> tuple[float, float, float]:
    s, en = e["start"], e["end"]
    return ((s[0] + en[0]) / 2, (s[1] + en[1]) / 2, (s[2] + en[2]) / 2)


def _pick_two_far(captured: list[dict]) -> list[dict]:
    best = (-1.0, None, None)
    for i in range(len(captured)):
        for j in range(i + 1, len(captured)):
            a, b = _mid(captured[i]), _mid(captured[j])
            d = sum((a[k] - b[k]) ** 2 for k in range(3))
            if d > best[0]:
                best = (d, captured[i], captured[j])
    return [best[1], best[2]]


def _verify(sw: Any, path: str) -> dict[str, Any]:
    """Reopen, read Fillet1's per-item radii."""
    out: dict[str, Any] = {}
    doc = mutate._open_doc_typed(path)
    if doc is None:
        return {"reopened": False}
    out["reopened"] = True
    mod = wrapper_module()
    try:
        # Name-select the fillet, then pull it from the selection list (the
        # typed doc has no FeatureByName).
        out["has_fillet1"] = bool(doc.SelectByID("Fillet1", "BODYFEATURE", 0, 0, 0))
        feat = None
        try:
            sm = doc.SelectionManager
            feat = sm.GetSelectedObject6(1, -1)
        except Exception as e:  # noqa: BLE001
            out["selmgr_error"] = f"{type(e).__name__}: {str(e)[:80]}"
        if feat is not None:
            # Late-bind GetDefinition raises 'Member not found'; the handler's
            # helper falls back to early-bound IFeature.
            defn_raw = mutate._get_definition(feat, mod)
            defn = typed_qi(defn_raw, "ISimpleFilletFeatureData2", module=mod)
            try:
                defn.AccessSelections(doc, None)
            except Exception:  # noqa: BLE001
                pass
            count = int(defn.FilletItemsCount)
            radii = []
            for i in range(count):
                item = defn.GetFilletItemAtIndex(i)
                radii.append(defn.GetRadius(item))
            out["fillet_items_count"] = count
            out["radii_m"] = radii
    except Exception as e:  # noqa: BLE001
        out["verify_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    finally:
        try:
            sw.CloseDoc(_title(doc))
        except Exception:  # noqa: BLE001
            pass
    return out


def main() -> int:
    pythoncom.CoInitialize()
    report: dict[str, Any] = {"tmp": str(_TMP)}
    try:
        mod = wrapper_module() or ensure_sw_module()[0]
        sw = connect_running_sw()
        template = sw.GetUserPreferenceStringValue(8)
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            report["overall"] = "FAIL-NEWDOC"
            return _emit(report, 1)

        build = build_single_box(doc)
        report["build"] = build
        feat = doc.FeatureByName(build.get("feature_name")) if build.get("built") else None
        if feat is None:
            report["overall"] = "FAIL-BUILD"
            return _emit(report, 1)

        payload = interrogate(feat, _Ctx(doc))
        edges = (payload or {}).get("edges", [])
        captured = [e for e in edges if e.get("persist_id")]
        report["capture"] = {"n_edges": len(edges), "n_token": len(captured)}
        if len(captured) < 2:
            report["overall"] = "FAIL-CAPTURE"
            return _emit(report, 1)

        two = _pick_two_far(captured)
        refs = [DurableEdgeRef.from_manifest_edge(e).to_dict() for e in two]
        report["chosen_midpoints"] = [_mid(e) for e in two]

        path = str(_TMP / "varfil_test.sldprt")
        doc.SaveAs3(path, 0, 0)
        sw.CloseDoc(_title(doc))
        report["profile_part"] = path

        feature = {"type": "variable_radius_fillet"}
        target = {"edges": [
            {"ref": refs[0], "radius_mm": R0_MM},
            {"ref": refs[1], "radius_mm": R1_MM},
        ]}

        prop = mutate.sw_propose_feature_add(path, feature, target)
        report["propose"] = {"ok": prop.get("ok"), "error": prop.get("error")}
        pid = prop.get("proposal_id")
        if not prop.get("ok"):
            report["overall"] = "FAIL-PROPOSE"
            return _emit(report, 1)

        dry = mutate.sw_dry_run_feature_add(pid)
        report["dry_run"] = {"ok": dry.get("ok"), "state": dry.get("state"),
                             "result": dry.get("dry_run_result"), "error": dry.get("error")}
        if not dry.get("ok"):
            report["overall"] = "FAIL-DRYRUN"
            return _emit(report, 1)

        commit = mutate.sw_commit_feature_add(pid)
        report["commit"] = {"ok": commit.get("ok"), "doc_saved": commit.get("doc_saved"),
                            "error": commit.get("error")}
        if not commit.get("ok"):
            report["overall"] = "FAIL-COMMIT"
            return _emit(report, 1)

        verify = _verify(sw, path)
        report["verify"] = verify
        radii = sorted(round(float(r), 6) for r in verify.get("radii_m", [])
                       if isinstance(r, (int, float)))
        expected = sorted({round(R0_MM / 1000, 6), round(R1_MM / 1000, 6)})
        ok = (verify.get("has_fillet1") and verify.get("fillet_items_count") == 2
              and radii == expected)
        report["overall"] = "PASS" if ok else "PARTIAL"
        return _emit(report, 0 if ok else 2)
    finally:
        pythoncom.CoUninitialize()


def _emit(report: dict[str, Any], code: int) -> int:
    out = _TMP / "varfil_pae.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
