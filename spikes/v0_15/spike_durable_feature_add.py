"""
Spike v0.15 / S-DURABLE-FEATURE-ADD -- the full edit-time loop end-to-end.
[RUN ON A LIVE SEAT]

Proves the OI-2 payoff: add a feature to a *previously built, saved, reopened*
part, anchored to a DurableEdgeRef from its manifest -- the edit-robust path the
durable-selection keystone exists for. Ties together every shipped piece:

  build box
  -> interrogate(persist_capture) -> manifest edges (E1)
  -> DurableEdgeRef.from_manifest_edge(edge) (E2)
  -> SaveAs3 temp .sldprt -> CloseDoc
  -> reopen (typed ISldWorks.OpenDoc6, byref ints) -> ForceRebuild3
  -> resolve_edge_ref(doc, edge_ref) -> live edge (tier-1 persist)
  -> typed_qi fillet pipeline (CreateDefinition -> Initialize -> CreateFeature)
  -> Fillet materializes on the durable edge
  -> SaveAs3 (the "commit") -> verify -> cleanup temp file

The decisive new fact vs. prior spikes: a captured EDGE token survives a real
save->close->reopen (not just an in-session rebuild) and still resolves to the
right edge for a feature add.

Non-destructive: own temp file under %TEMP%; own documents; deletes the temp
file at the end (unless --keep-file).

Verdict
-------
PASS    : the fillet materializes on the durable edge after reopen -> the
          edit-time durable feature-add loop works end-to-end; productize into
          mutate.py (F1).
PARTIAL : the edge resolves after reopen but CreateFeature does not materialize
          -> resolve/reopen is sound; the feature step needs work.
FAIL    : the edge token does not resolve after reopen -> edge durability does
          not survive a file round-trip; revisit E1/E2.

Usage
-----
    python spikes/v0_15/spike_durable_feature_add.py --out report.json
    python spikes/v0_15/spike_durable_feature_add.py --keep-file
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ["AI_SW_BRIDGE_FLAG_BREP_INTERROGATION"] = "1"
os.environ["AI_SW_BRIDGE_FLAG_PERSIST_CAPTURE"] = "1"

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.brep.interrogator import interrogate  # noqa: E402
from ai_sw_bridge.selection import DurableEdgeRef, live as sel_live  # noqa: E402

from spike_persist_reference import build_single_box  # noqa: E402
from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_DOC_PART = 1
SW_OPEN_SILENT = 1
SW_CONST_RADIUS_FILLET = 0
SW_FM_FILLET = 1
FILLET_RADIUS_M = 0.002


class _Ctx:
    def __init__(self, doc: Any) -> None:
        self.doc = doc


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(f: Any) -> bool:
    return f is not None and not isinstance(f, int)


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:  # noqa: BLE001
            continue
    return None


def run(keep_file: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    mod = wrapper_module() or ensure_sw_module()[0]
    sw = connect_running_sw()

    # --- 1. Build + capture edge manifest -----------------------------------
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    result["build"] = build
    feat = doc.FeatureByName(build.get("feature_name")) if build.get("built") else None
    if feat is None:
        return {**result, "overall": "FAIL", "reason": "could not get extrude feature"}

    payload = interrogate(feat, _Ctx(doc))
    edges = (payload or {}).get("edges", [])
    captured = [e for e in edges if e.get("persist_id")]
    result["capture"] = {"n_edges": len(edges), "n_with_token": len(captured)}
    if not captured:
        _try_close(sw, doc)
        return {
            **result,
            "overall": "FAIL",
            "reason": "no edge captured a persist token",
        }
    edge_ref = DurableEdgeRef.from_manifest_edge(captured[0])
    result["edge_ref"] = {
        "start": list(edge_ref.start),
        "end": list(edge_ref.end),
        "has_token": edge_ref.persist_id is not None,
    }

    # --- 2. Save -> close ----------------------------------------------------
    tmp = (
        Path(tempfile.gettempdir())
        / "ai-sw-bridge"
        / "spike_durable_feature_add.sldprt"
    )
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
    try:
        doc.SaveAs3(str(tmp), 0, 0)
    except Exception as e:  # noqa: BLE001
        _try_close(sw, doc)
        return {**result, "overall": "FAIL", "reason": f"SaveAs3 raised: {e}"}
    if not tmp.exists():
        _try_close(sw, doc)
        return {**result, "overall": "FAIL", "reason": "SaveAs3 produced no file"}
    title = _title(doc)
    try:
        sw.CloseDoc(title)
    except Exception:  # noqa: BLE001
        pass
    result["saved"] = str(tmp)

    # --- 3. Reopen (typed OpenDoc6 byref ints) + rebuild --------------------
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(str(tmp), SW_DOC_PART, SW_OPEN_SILENT, "", 0, 0)
    doc2 = ret[0] if isinstance(ret, tuple) else ret
    if doc2 is None:
        try:
            doc2 = sw.ActiveDoc
        except Exception:  # noqa: BLE001
            doc2 = None
    if doc2 is None:
        return {**result, "overall": "FAIL", "reason": "reopen produced no document"}
    try:
        doc2.ForceRebuild3(False)
    except Exception as e:  # noqa: BLE001
        result["reopen_rebuild_error"] = f"{type(e).__name__}: {e}"

    # --- 4. Resolve the durable edge on the reopened doc --------------------
    res = sel_live.resolve_edge_ref(doc2, edge_ref)
    result["resolve"] = {
        "method": res.method,
        "ok": res.entity is not None,
        "entity_type": _tag(res.entity),
    }
    if res.entity is None:
        _cleanup(sw, doc2, tmp, keep_file, result)
        return {
            **result,
            "overall": "FAIL",
            "reason": f"edge ref did not resolve after reopen (method={res.method})",
        }

    # --- 5. Fillet pipeline on the durable edge -----------------------------
    fm = doc2.FeatureManager
    pipe: dict[str, Any] = {}
    feat2 = None
    try:
        data = fm.CreateDefinition(SW_FM_FILLET)
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=mod)
        fd.Initialize(SW_CONST_RADIUS_FILLET)  # the builder's way (not Type=)
        fd.DefaultRadius = FILLET_RADIUS_M
        # Re-select the resolved edge right before CreateFeature.
        pipe["selected"] = sel_live.select_entity(res.entity)
        feat2 = fm.CreateFeature(fd)
        pipe["createfeature_type"] = _tag(feat2)
        pipe["feature_type_name"] = _type_name(feat2) if _materialized(feat2) else None
        try:
            fd.ReleaseSelectionAccess()
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        pipe["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    result["pipeline"] = pipe

    materialized = _materialized(feat2)
    if materialized:
        # commit: persist the edited doc (still non-destructive -- temp file).
        try:
            doc2.SaveAs3(str(tmp), 0, 0)
            result["commit_saved"] = True
        except Exception as e:  # noqa: BLE001
            result["commit_save_error"] = f"{type(e).__name__}: {e}"

    _cleanup(sw, doc2, tmp, keep_file, result)

    type_name = pipe.get("feature_type_name") or ""
    if materialized:
        overall, reason = "PASS", (
            f"fillet ({type_name!r}) materialized on the durable edge after "
            "save->close->reopen -- edit-time durable feature-add works end-to-end"
        )
    elif res.entity is not None:
        overall, reason = "PARTIAL", (
            "durable edge resolved after reopen but CreateFeature did not materialize"
        )
    else:
        overall, reason = "FAIL", "edge did not resolve after reopen"
    result["overall"] = overall
    result["reason"] = reason
    return result


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass


def _cleanup(sw: Any, doc: Any, tmp: Path, keep: bool, result: dict[str, Any]) -> None:
    if keep:
        result["cleanup"] = f"kept doc + temp file at {tmp}"
        return
    _try_close(sw, doc)
    try:
        tmp.unlink()
        result["cleanup"] = "closed doc + removed temp file"
    except OSError as e:
        result["cleanup"] = f"closed doc; temp remove failed: {e}"


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--keep-file", action="store_true")
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
