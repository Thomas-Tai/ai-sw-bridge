"""
Spike v0.15 / S-EDGE-PERSIST -- does a persist token round-trip on an EDGE?
[RUN ON A LIVE SEAT]

Durable selection is proven on FACES (capture token -> rebuild/reopen -> resolve,
selectable). The fillet-on-durable-edge lane (OI-2, high-payoff option) needs the
same on EDGES, which are not captured today. Edges are entities, so the persist
mechanism *should* apply -- this confirms it before any interrogator/manifest
infra is built, and surveys what edge geometry is reachable (to inform a future
edge fingerprint; v1 will rely on the persist token only).

What it does (non-destructive -- own blank Part):
  1. NewDocument blank Part, build the proven box.
  2. Pull edges off the body; pick edge[0]; snapshot its geometry.
  3. token = com.earlybind.read_persist_reference(doc, edge)   # shipped helper
  4. ForceRebuild3, then selection.live.resolve_persist_id(doc, token).
  5. Check it resolves (status Ok) AND the resolved edge matches the snapshot.
  6. Survey reachable edge geometry (start/end vertex, curve params, length).

Verdict
-------
PASS    : edge token resolves (status Ok) after rebuild and the resolved edge
          matches the pre-rebuild geometry -> edge capture is viable; build E1.
PARTIAL : token resolves but geometry match is inconclusive -> persist works,
          identity check needs refining.
FAIL    : edge token does not resolve -> edges are not persist-durable the way
          faces are; rethink the edge lane.

Usage
-----
    python spikes/v0_15/spike_edge_persist.py --out report.json
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

from ai_sw_bridge.com import earlybind  # noqa: E402
from ai_sw_bridge.selection import live as sel_live  # noqa: E402

from spike_persist_reference import build_single_box, _first_body  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _xyz(v: Any) -> list[float] | None:
    """An IVertex.GetPoint result -> [x,y,z], tolerating tuple/list shapes."""
    try:
        pt = v.GetPoint
        pt = pt() if callable(pt) else pt
        if isinstance(pt, (tuple, list)) and len(pt) >= 3:
            return [float(pt[0]), float(pt[1]), float(pt[2])]
    except Exception:  # noqa: BLE001
        pass
    return None


def _edge_geometry(edge: Any) -> dict[str, Any]:
    """Survey reachable edge geometry for fingerprint design (best-effort)."""
    g: dict[str, Any] = {}
    for meth, key in (("GetStartVertex", "start"), ("GetEndVertex", "end")):
        try:
            m = getattr(edge, meth)
            vtx = m() if callable(m) else m
            g[key] = _xyz(vtx) if vtx is not None else None
        except Exception as e:  # noqa: BLE001
            g[f"{key}_err"] = f"{type(e).__name__}"
    try:
        cp = edge.GetCurveParams2
        cp = cp() if callable(cp) else cp
        g["curve_params2_type"] = _tag(cp)
        if isinstance(cp, (tuple, list)):
            g["curve_params2_len"] = len(cp)
            g["curve_params2_head"] = [float(x) for x in cp[:6]]
    except Exception as e:  # noqa: BLE001
        g["curve_params2_err"] = f"{type(e).__name__}"
    return g


def run() -> dict[str, Any]:
    from ai_sw_bridge.sw_com import get_sw_app  # late import: needs a live seat

    result: dict[str, Any] = {}
    sw = get_sw_app()
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    result["build"] = build
    if not build.get("built"):
        _close(sw, doc, result)
        return {**result, "overall": "FAIL", "reason": "box did not build"}

    body = _first_body(doc)
    edges = list(body.GetEdges() or []) if body is not None else []
    result["edge_count"] = len(edges)
    if not edges:
        _close(sw, doc, result)
        return {**result, "overall": "FAIL", "reason": "no edges on body"}
    edge0 = edges[0]

    # Snapshot geometry BEFORE rebuild (the proxy goes stale after).
    snap = _edge_geometry(edge0)
    result["edge_geometry_before"] = snap

    # 1. Capture the edge persist token via the shipped helper.
    token = earlybind.read_persist_reference(doc, edge0)
    result["capture"] = {
        "ok": token is not None,
        "byte_len": len(token) if token else None,
    }
    if token is None:
        _close(sw, doc, result)
        return {
            **result,
            "overall": "FAIL",
            "reason": "read_persist_reference(edge) returned None",
        }

    # 2. Rebuild, then resolve the token on the rebuilt doc.
    try:
        doc.ForceRebuild3(False)
        result["rebuilt"] = True
    except Exception as e:  # noqa: BLE001
        result["rebuilt"] = False
        result["rebuild_error"] = f"{type(e).__name__}: {e}"

    res = sel_live.resolve_persist_id(doc, token)
    result["resolve"] = {
        "status": res.status_name,
        "ok": res.ok,
        "entity_type": _tag(res.entity),
        "error": res.error,
    }
    if not res.ok or res.entity is None:
        _close(sw, doc, result)
        return {
            **result,
            "overall": "FAIL",
            "reason": f"edge token did not resolve (status {res.status_name})",
        }

    # 3. Identity check: resolved edge geometry should match the snapshot.
    # GetStartVertex/GetEndVertex throw com_error late-bound on this build; the
    # reliable, late-bind-friendly source is GetCurveParams2 (head = start xyz +
    # end xyz). That is also the chosen edge-fingerprint input for E1/E2.
    after = _edge_geometry(res.entity)
    result["edge_geometry_after"] = after
    head_before = snap.get("curve_params2_head")
    head_after = after.get("curve_params2_head")
    match = head_before is not None and head_before == head_after
    result["geometry_match"] = match
    result["edge_fingerprint_source"] = "GetCurveParams2 (start/end xyz in head)"

    # 4. Selectable via the proven early-bound IEntity.Select2 path?
    result["selectable"] = sel_live.select_entity(res.entity)

    _close(sw, doc, result)

    if match and result["selectable"]:
        overall, reason = "PASS", (
            "edge persist token resolves after rebuild, matches geometry, and is "
            "selectable -- edge capture (E1) is viable"
        )
    elif res.ok:
        overall, reason = "PARTIAL", (
            "edge token resolves but geometry-match / selectability is inconclusive"
        )
    else:
        overall, reason = "FAIL", "edge token did not resolve"
    result["overall"] = overall
    result["reason"] = reason
    return result


def _close(sw: Any, doc: Any, result: dict[str, Any]) -> None:
    try:
        sw.CloseDoc(_title(doc))
        result["cleanup"] = "closed own doc (no save)"
    except Exception as e:  # noqa: BLE001
        result["cleanup"] = f"close failed: {type(e).__name__}"


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run()
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
