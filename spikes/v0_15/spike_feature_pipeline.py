"""
Spike v0.15 / S-FEATURE-PIPELINE -- materialize a feature through the
QI-acquired feature-data pipeline.  [RUN ON A LIVE SEAT]

S-QI-FEATUREDATA proved QueryInterface-by-IID soundly *acquires and identifies*
feature-data objects (OI-1 acquisition). This spike closes the remaining
question -- does a feature actually **materialize** through that pipeline? -- by
building a constant-radius fillet end-to-end out-of-process:

    fm.CreateDefinition(swFmFillet=1)             # untyped IDispatch
    fd = com.earlybind.typed_qi(data,             # <-- the shipped helper, on-seat
                                "ISimpleFilletFeatureData2")
    fd.Type = swConstRadiusFillet (0); fd.DefaultRadius = 2 mm
    Extension.SelectByID2(<bottom-front edge>)    # the edge to round
    feat = fm.CreateFeature(fd)                   # materialize

Why fillet, not shell: a CreateDefinition-id scan (typed_qi as the identity
oracle) showed CreateDefinition yields ISimpleFilletFeatureData2 (id 1),
IWizardHoleFeatureData2 (id 25) and IBaseFlangeFeatureData (id 34) -- but NO id
yields IShellFeatureData. Shell is *not* a CreateDefinition feature (its data
object is only reachable via GetDefinition on an existing shell); the earlier
"shell via CreateDefinition" note was wrong. Fillet is the simplest genuine
CreateDefinition feature, so it is the honest first materialization proof.

Non-destructive: own fresh blank Part via NewDocument; never touches the user's
open docs; closes its own doc at the end (no save).

Verdict
-------
PASS    : CreateFeature returns a materialized feature (type ~ "Fillet") -- the
          QI feature-data pipeline works end-to-end; OI-1 is closed through
          materialization and per-feature handlers can follow.
PARTIAL : ISimpleFilletFeatureData2 is acquired + props set, but CreateFeature
          does not materialize -- acquisition is sound; the remaining issue is
          selection / CreateFeature args, NOT binding or QI.
FAIL    : typed_qi cannot acquire ISimpleFilletFeatureData2 (contradicts
          S-QI-FEATUREDATA) -- investigate.

Usage
-----
    python spikes/v0_15/spike_feature_pipeline.py --out report.json
    python spikes/v0_15/spike_feature_pipeline.py --keep-docs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import (  # noqa: E402
    EarlyBindError,
    is_early_bound,
    typed,
    typed_qi,
)
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_persist_reference import build_single_box, _first_body  # noqa: E402
from spike_earlybind_persist import ensure_sw_module  # noqa: E402
from spike_varfil import SW_FM_FILLET  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_CONST_RADIUS_FILLET = 0  # swSimpleFilletType_e.swConstRadiusFillet
FILLET_RADIUS_M = 0.002  # 2 mm


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


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


def _new_blank_part(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def run(keep_docs: bool) -> dict[str, Any]:
    from ai_sw_bridge.sw_com import get_sw_app  # late import: needs a live seat

    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind.typed_qi)",
                              "feature": "constant-radius fillet"}
    sw = get_sw_app()
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback_info"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    doc = _new_blank_part(sw)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    result["build"] = build
    if not build.get("built"):
        _close(sw, doc, result)
        return {**result, "overall": "FAIL", "reason": "box did not build"}
    fm = doc.FeatureManager

    pipe: dict[str, Any] = {"swFmFillet": SW_FM_FILLET}

    # 1. Untyped feature-data object from CreateDefinition.
    data = fm.CreateDefinition(SW_FM_FILLET)
    pipe["createdefinition_type"] = _tag(data)
    if data is None:
        result["pipeline"] = pipe
        _close(sw, doc, result)
        return {**result, "overall": "FAIL", "reason": "CreateDefinition(swFmFillet) returned None"}

    # 2. QI-acquire the typed interface via the shipped helper.
    try:
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=mod)
        pipe["typed_qi"] = "OK"
        pipe["early_bound"] = is_early_bound(fd)
    except EarlyBindError as e:
        pipe["typed_qi"] = f"FAIL: {e}"
        result["pipeline"] = pipe
        _close(sw, doc, result)
        return {**result, "overall": "FAIL",
                "reason": "typed_qi could not acquire ISimpleFilletFeatureData2"}

    # 3. Set the fillet parameters on the typed object.
    for prop, val in (("Type", SW_CONST_RADIUS_FILLET),
                      ("DefaultRadius", FILLET_RADIUS_M),
                      ("PropagateToTangentFaces", True)):
        try:
            setattr(fd, prop, val)
            pipe[f"set_{prop}"] = "OK"
        except Exception as e:  # noqa: BLE001
            pipe[f"set_{prop}_error"] = f"{type(e).__name__}: {str(e)[:100]}"

    # 4. Select an edge to round -- robustly: pull the first edge off the body
    # and select it via the proven early-bound IEntity.Select2 (no fragile
    # coordinate picking; same mechanism as selection/live.select_entity).
    edge0 = None
    sel: dict[str, Any] = {}
    try:
        body = _first_body(doc)
        edges = list(body.GetEdges() or []) if body is not None else []
        sel["edge_count"] = len(edges)
        if edges:
            edge0 = edges[0]
            doc.ClearSelection2(True)
            ent = typed(edge0, "IEntity", module=mod)
            sel["selected"] = bool(ent.Select2(False, 0))
    except Exception as e:  # noqa: BLE001
        sel["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    pipe["edge_selection"] = sel

    # 5. Materialize (implicit selection path).
    feat = None
    try:
        feat = fm.CreateFeature(fd)
        pipe["createfeature_type"] = _tag(feat)
        pipe["feature_type_name"] = _type_name(feat) if _materialized(feat) else None
    except Exception as e:  # noqa: BLE001
        pipe["createfeature_error"] = f"{type(e).__name__}: {str(e)[:160]}"

    # 5b. Fallback: explicit AccessSelections + Edges with the edge object.
    if not _materialized(feat) and edge0 is not None:
        try:
            fd.AccessSelections(doc, None)
            fd.Edges = (edge0,)
            feat = fm.CreateFeature(fd)
            pipe["fallback_createfeature_type"] = _tag(feat)
            pipe["fallback_feature_type_name"] = _type_name(feat) if _materialized(feat) else None
            fd.ReleaseSelectionAccess()
        except Exception as e:  # noqa: BLE001
            pipe["fallback_error"] = f"{type(e).__name__}: {str(e)[:160]}"

    result["pipeline"] = pipe

    materialized = _materialized(feat)
    type_name = (pipe.get("feature_type_name") or pipe.get("fallback_feature_type_name") or "")
    if materialized:
        overall, reason = "PASS", (
            f"feature materialized (type {type_name!r}) via the QI feature-data pipeline")
    else:
        overall, reason = "PARTIAL", (
            "ISimpleFilletFeatureData2 acquired + props set, but CreateFeature did "
            "not materialize -- remaining issue is selection / CreateFeature, not QI")
    result["overall"] = overall
    result["reason"] = reason

    _close(sw, doc, result, keep_docs)
    return result


def _close(sw: Any, doc: Any, result: dict[str, Any], keep: bool = False) -> None:
    if keep:
        result["cleanup"] = "kept doc open"
        return
    try:
        sw.CloseDoc(_title(doc))
        result["cleanup"] = "closed own doc (no save)"
    except Exception as e:  # noqa: BLE001
        result["cleanup"] = f"close failed: {type(e).__name__}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=None,
                   help="Write JSON report to this path instead of stdout.")
    p.add_argument("--keep-docs", action="store_true",
                   help="Do not close the spike's own document at the end.")
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run(args.keep_docs)
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
