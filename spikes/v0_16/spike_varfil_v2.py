"""
Spike v0.16 / S-VARFIL-V2 — multi-radius fillet via the data object that
actually supports it.
[authored seat-free; RUN ON A LIVE SEAT]

Supersedes ``spike_varfil_qi.py`` (MORPH-FALSE) and ``spike_varfil_direct.py``
(NO-MEMBERS), whose shared premise was FALSIFIED by the 2026-05-30 typelib
audit:

  * ``ISimpleFilletFeatureData2.Initialize(FilletType)`` takes
    ``swSimpleFilletType_e`` = {swConstRadiusFillet=0, swFaceFillet=2,
    swFullRoundFillet=3}. There is **no "variable" value** — the ``1`` the
    morph spike passed is not even a member. "Morph a simple fillet into a
    variable one via Initialize" was impossible by construction, so MORPH-FALSE
    was correct and meaningless.
  * The probed names (``SetVariableRadiusParameters`` / ``RadiiCount`` /
    ``FilletType`` …) exist on **no** interface in sldworks.tlb. NO-MEMBERS was
    a wrong-name artifact, not a makepy gap.

What the typelib actually exposes:
  * ``ISimpleFilletFeatureData2.IsMultipleRadius`` (put bool) +
    ``SetRadius(PFilletItem:dispatch, Radius:r8)`` + ``GetFilletItemAtIndex`` +
    ``FilletItemsCount`` — i.e. multiple *per-edge* radii live on the SIMPLE
    data object. This is the "variable across edges" fillet.
  * ``IVariableFilletFeatureData2`` (control-point API:
    ``SetControlPointRadiusAtIndex``, ``GetControlPointsCount``,
    ``FilletEdgeCount``) is the **read/edit** interface for an EXISTING
    variable fillet (``GetDefinition → typed_qi``), not a creation target — no
    CreateDefinition id yields it, and a fresh simple-fillet definition rejects
    its IID (E_NOINTERFACE, confirmed in qi_featuredata.json). Acquiring a
    fresh one for *creation* is a separate open question (likely the legacy
    ``IFeatureManager.InsertFeatureFillet`` array method).

This spike tests the reachable claim: does a multi-radius fillet materialize
via ``CreateDefinition(1) → typed_qi(ISimpleFilletFeatureData2) → Initialize(0)
→ IsMultipleRadius=True → per-edge SetRadius → CreateFeature``?

Flow
----
  1. NewDocument part; 20×20×10 box.
  2. ``CreateDefinition(1)`` → ``typed_qi(ISimpleFilletFeatureData2)``.
  3. ``Initialize(swConstRadiusFillet=0)``; ``DefaultRadius = 3 mm``;
     ``IsMultipleRadius = True``.
  4. Select two top edges; best-effort per-item ``SetRadius`` (2 mm / 4 mm).
  5. ``CreateFeature``; report materialization + IsMultipleRadius read-back.

Verdict
-------
PASS-MULTIRADIUS : feature materializes AND IsMultipleRadius reads True →
                   multi-radius fillet creatable on ISimpleFilletFeatureData2;
                   build the F2 variable(-across-edges) fillet handler here.
PASS-CONST       : feature materializes but IsMultipleRadius did not stick →
                   only constant-radius proven on this build; multi-radius
                   needs a different setup (record what SetRadius did).
PARTIAL          : props set but CreateFeature no-op → selection/marshaler wall.
FAIL             : Initialize/acquisition regressed (constant fillet baseline broke).

Prereq: SOLIDWORKS running. Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_varfil_v2.py --out report.json
    python spikes/v0_16/spike_varfil_v2.py --mode vba
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

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SW_FM_FILLET = 1
IFACE = "ISimpleFilletFeatureData2"

# swSimpleFilletType_e.swConstRadiusFillet (verified by _investigate_enums.py).
SW_CONST_RADIUS_FILLET = 0

# Box (metres). Front Plane is z=0; extrude +Z gives z∈[0, BOX_D_M].
BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010

DEFAULT_RADIUS_M = 0.003
PER_EDGE_RADII_M = (0.002, 0.004)

# Two top edges (midpoints), z = BOX_D_M:
#   edge along X at y=+H/2  -> midpoint (0, +H/2, D)
#   edge along Y at x=+W/2  -> midpoint (+W/2, 0, D)
TOP_EDGES = (
    (0.0, BOX_H_M / 2, BOX_D_M),
    (BOX_W_M / 2, 0.0, BOX_D_M),
)


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:  # noqa: BLE001
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:  # noqa: BLE001
        pass


def _capture(fn: Any) -> tuple[dict[str, Any], Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        return {
            "status": "OK",
            "type": _tag(val),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, val
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }, None


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
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
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base_args)
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _select_edges(doc: Any) -> dict[str, Any]:
    """SelectByID (5-arg) ADDS to the selection list, so successive calls
    accumulate edges."""
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    picks: list[dict[str, Any]] = []
    for (x, y, z) in TOP_EDGES:
        rec, ok = _capture(lambda x=x, y=y, z=z: doc.SelectByID("", "EDGE", x, y, z))
        rec["xyz"] = (x, y, z)
        rec["selected"] = bool(ok)
        picks.append(rec)
    return {"picks": picks, "n_selected": sum(1 for p in picks if p["selected"])}


def _probe_per_item_radii(fd: Any) -> dict[str, Any]:
    """Best-effort: enumerate fillet items and set distinct radii. The items
    may not be populated until edges are bound; record whatever happens."""
    out: dict[str, Any] = {}
    cnt_rec, count = _capture(lambda: fd.FilletItemsCount)
    out["FilletItemsCount"] = {**cnt_rec, "value": count if isinstance(count, int) else None}
    if not isinstance(count, int) or count <= 0:
        out["note"] = "no fillet items to set (expected if items bind after CreateFeature)"
        return out
    sets: list[dict[str, Any]] = []
    for i in range(min(count, len(PER_EDGE_RADII_M))):
        item_rec, item = _capture(lambda i=i: fd.GetFilletItemAtIndex(i))
        if item is None:
            sets.append({"index": i, "get_item": item_rec})
            continue
        r = PER_EDGE_RADII_M[i]
        set_rec, _ = _capture(lambda it=item, r=r: fd.SetRadius(it, r))
        sets.append({"index": i, "radius_m": r, "set_radius": set_rec})
    out["per_item_set"] = sets
    return out


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind.typed_qi)"}

    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module (LoadTypeLib fallback)"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    acquired = False
    init_ok = False
    multi_set_ok = False
    multi_readback: Any = None
    create_rec: dict[str, Any] = {}
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}

        fm = doc.FeatureManager
        def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_FILLET))
        result["create_definition_1"] = def_rec
        if data is None:
            return {**result, "overall": "FAIL", "reason": "CreateDefinition(1) returned None"}

        qi_rec, fd = _capture(lambda: typed_qi(data, IFACE, module=mod))
        result["typed_qi"] = qi_rec
        acquired = fd is not None

        if acquired:
            init_rec, init_ret = _capture(lambda: fd.Initialize(SW_CONST_RADIUS_FILLET))
            result["initialize"] = init_rec
            init_ok = init_rec["status"] == "OK"

            r_rec, _ = _capture(lambda: setattr(fd, "DefaultRadius", DEFAULT_RADIUS_M))
            result["set_default_radius"] = r_rec

            m_rec, _ = _capture(lambda: setattr(fd, "IsMultipleRadius", True))
            result["set_is_multiple_radius"] = m_rec
            multi_set_ok = m_rec["status"] == "OK"

            # Select edges, then best-effort per-item radii.
            result["select_edges"] = _select_edges(doc)
            result["per_item"] = _probe_per_item_radii(fd)

            # Read IsMultipleRadius back before creating.
            rb_rec, multi_readback = _capture(lambda: fd.IsMultipleRadius)
            result["is_multiple_radius_readback"] = {
                **rb_rec, "value": bool(multi_readback) if multi_readback is not None else None
            }

            feat_rec, feat = _capture(lambda: fm.CreateFeature(data))
            create_rec = feat_rec
            create_rec["materialized"] = _materialized(feat)
            if _materialized(feat):
                create_rec["feature_name"] = getattr(feat, "Name", None)
                create_rec["type_name"] = _type_name(feat)
            result["create_feature"] = create_rec
    finally:
        _try_close(sw, doc)
        result["cleanup"] = "closed own doc (no save)"

    # --- Verdict -------------------------------------------------------------
    materialized = create_rec.get("materialized", False)
    if not acquired or not init_ok:
        overall = "FAIL"
        interp = (
            "constant-fillet baseline regressed: typed_qi acquisition or "
            "Initialize(swConstRadiusFillet=0) failed. Fix the proven constant "
            "path before chasing multi-radius."
        )
    elif materialized and multi_set_ok and bool(multi_readback):
        overall = "PASS-MULTIRADIUS"
        interp = (
            "multi-radius fillet materializes via ISimpleFilletFeatureData2 with "
            "IsMultipleRadius=True → build the F2 variable(-across-edges) fillet "
            "handler on this object. (True variable-along-edge control points "
            "remain a separate question — that's IVariableFilletFeatureData2, a "
            "read/edit iface; creation likely needs InsertFeatureFillet.)"
        )
    elif materialized:
        overall = "PASS-CONST"
        interp = (
            "a fillet materializes, but IsMultipleRadius did not stick "
            f"(set={multi_set_ok}, readback={multi_readback}) → only constant "
            "radius is proven on this build; inspect set_is_multiple_radius / "
            "per_item to see how multi-radius wants its setup."
        )
    else:
        overall = "PARTIAL"
        interp = (
            "props set but CreateFeature did not materialize → selection or "
            "marshaler wall; check select_edges.n_selected and run --mode vba."
        )

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba() -> str:
    return r"""' Spike v0.16 S-VARFIL-V2 VBA oracle.
' Paste into a Part with a 20x20x10 box. Tests multi-radius via the SIMPLE
' fillet data object (IsMultipleRadius), the path the typelib actually exposes.
Option Explicit
Sub ProbeMultiRadiusFillet()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As SldWorks.SimpleFilletFeatureData2
    Dim feat  As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set fm = Part.FeatureManager

    Set fd = fm.CreateDefinition(swFmFillet)        ' 1
    If fd Is Nothing Then MsgBox "CreateDefinition(1) Nothing": Exit Sub
    fd.Initialize swConstRadiusFillet                ' 0
    fd.DefaultRadius = 0.003
    fd.IsMultipleRadius = True

    Part.ClearSelection2 True
    Part.SelectByID2 "", "EDGE", 0, 0.01, 0.01, True, 0, Nothing, 0
    Part.SelectByID2 "", "EDGE", 0.01, 0, 0.01, True, 0, Nothing, 0

    Set feat = fm.CreateFeature(fd)
    If feat Is Nothing Then
        MsgBox "CreateFeature: NOTHING"
    Else
        MsgBox "Fillet: " & feat.Name & " / " & feat.GetTypeName2 & _
               "  IsMultipleRadius=" & fd.IsMultipleRadius
    End If
End Sub
"""


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_varfil_v2.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

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

    return {"PASS-MULTIRADIUS": 0, "PASS-CONST": 0, "PARTIAL": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
