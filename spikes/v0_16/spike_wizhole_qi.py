"""
Spike v0.16 / S-WIZHOLE-QI — wizard hole via CreateDefinition → typed_qi,
as a DIAGNOSTIC of why the v0.15 attempt failed (O1 / F2).
[authored seat-free; RUN ON A LIVE SEAT]

The v0.15 probe (spikes/v0_15/_results/earlybind_features.json, "wizhole")
got *further* than the others: ``CreateDefinition(swFmHoleWzd=25)`` returned a
real object and the typed wrap succeeded — but then
``data.HoleType`` raised ``AttributeError`` and ``CreateFeature`` returned
``None`` (ran 439 ms, no materialization).

Why typed_qi alone may NOT fix this
-----------------------------------
``typed`` and ``typed_qi`` wrap the underlying pointer with the **same**
makepy class. typed_qi's only advantage is *sound acquisition* (QI instead of
a dispid guess) — it does **not** add members the makepy class lacks. The
wizhole object was already correctly acquired in v0.15 (CreateDefinition(25)
genuinely makes a wizard-hole data object, so there is no dispid-collision to
fix). So the ``HoleType`` ``AttributeError`` is almost certainly a **makepy
coverage gap** in ``IWizardHoleFeatureData2``, not an acquisition problem.

This spike is therefore a DIAGNOSTIC, not an unlock: it probes the member
surface of the typed_qi'd ``IWizardHoleFeatureData2`` and reports which setup
members are reachable, so the verdict cleanly separates:

  * **MEMBER-GAP** — required wizard members (``HoleType`` / ``Standard`` /
    setup ``Initialize*``) are MISSING from the makepy class → regenerate
    makepy for the SW typelib; typed_qi cannot conjure them. This confirms the
    v0.15 finding's root cause.
  * **PARTIAL** — the members ARE present (e.g. a fuller makepy on this seat)
    and set, but ``CreateFeature`` still no-ops → the wall is placement/setup
    (wizard holes need sketch points on a face) or marshaling; run ``--mode vba``.
  * **PASS** — members present, minimal setup + placement, and CreateFeature
    materializes a wizard hole.

Flow
----
  1. NewDocument part; 20×20×10 box; grab the top face.
  2. ``CreateDefinition(25)`` → ``typed_qi(IWizardHoleFeatureData2)``.
  3. Probe the member surface (HoleType, Standard, FastenerType, Diameter,
     Depth, EndCondition, Initialize/Initialize2, hole-element accessors).
  4. Best-effort minimal setup + select top face + CreateFeature.

NOTE: full wizard-hole placement (sketch points / standards / fastener tables)
is deliberately minimal here — the spike's primary value is the member-surface
diagnosis; a PARTIAL with members-present is an expected and informative result.

Verdict
-------
PASS       : wizard hole materializes → build the F2 hole handler on
             CreateDefinition+typed_qi.
PARTIAL    : members present + set, CreateFeature no-op → placement/marshaler
             wall; run --mode vba and add sketch-point placement.
MEMBER-GAP : typed_qi acquires the object but wizard setup members are MISSING
             from the makepy class → regenerate makepy, then retry. (Confirms
             the v0.15 HoleType AttributeError as a wrapper-coverage gap.)
FAIL       : CreateDefinition(25) returns no usable object on this build.

Prereq: SOLIDWORKS running. Non-destructive (own doc, closed without save).

Usage
-----
    python spikes/v0_16/spike_wizhole_qi.py --out report.json
    python spikes/v0_16/spike_wizhole_qi.py --mode vba
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

# swFmHoleWzd confirmed = 25 (earlybind_features.json swFmHoleWzd_scan).
SW_FM_HOLE_WZD = 25

IFACE = "IWizardHoleFeatureData2"

# Box (metres). Top face center is (0, 0, +BOX_D_M) on this build.
BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010

# Candidate wizard-hole setup members (probed for presence). HoleType is the
# one that raised AttributeError in v0.15 — the canary for the makepy gap.
CANDIDATE_MEMBERS = (
    "HoleType",
    "Standard",
    "FastenerType",
    "Size",
    "Diameter",
    "Depth",
    "EndCondition",
    "ThreadClass",
    "Initialize",
    "Initialize2",
    "GetHoleElementCount",
    "SetHoleElementValue",
)

# A plausible minimal hole type (swWzdHoleTypes_e: swWzdSimpleHole = 0).
SIMPLE_HOLE_TYPE = 0


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


def _probe_members(obj: Any, names: tuple[str, ...]) -> dict[str, str]:
    """Which candidate members are reachable on the typed wrapper. A MISSING
    member is a makepy-coverage gap (same class for typed and typed_qi)."""
    out: dict[str, str] = {}
    for name in names:
        try:
            getattr(obj, name)
            out[name] = "present"
        except AttributeError:
            out[name] = "MISSING"
        except Exception as e:  # noqa: BLE001
            out[name] = f"reachable({type(e).__name__})"
    return out


def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0, 0, 0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2,
        -BOX_H_M / 2,
        0.0,
        BOX_W_M / 2,
        BOX_H_M / 2,
        0.0,
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base_args = (
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
        0.0,
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
    members: dict[str, str] = {}
    create_rec: dict[str, Any] = {}
    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}

        fm = doc.FeatureManager
        def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_HOLE_WZD))
        result["create_definition_25"] = def_rec
        if data is None:
            return {
                **result,
                "overall": "FAIL",
                "reason": "CreateDefinition(25) returned None",
            }

        qi_rec, typed_obj = _capture(lambda: typed_qi(data, IFACE, module=mod))
        result["typed_qi"] = qi_rec
        acquired = typed_obj is not None

        if acquired:
            members = _probe_members(typed_obj, CANDIDATE_MEMBERS)
            result["members"] = members

            # Best-effort minimal setup: set HoleType if present.
            if members.get("HoleType") == "present":
                set_rec, _ = _capture(
                    lambda: setattr(typed_obj, "HoleType", SIMPLE_HOLE_TYPE)
                )
                result["set_hole_type"] = set_rec

            # Select the top face, then attempt CreateFeature. Wizard holes
            # really want sketch points; without them a no-op is expected and
            # is itself an informative PARTIAL.
            try:
                doc.ClearSelection2(True)
            except Exception:  # noqa: BLE001
                pass
            sel_rec, _ = _capture(lambda: doc.SelectByID("", "FACE", 0, 0, BOX_D_M))
            result["select_top_face"] = sel_rec

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
    hole_type_present = members.get("HoleType") == "present"
    if not acquired:
        overall = "FAIL"
        interp = "typed_qi(IWizardHoleFeatureData2) failed to acquire the object."
    elif not hole_type_present:
        overall = "MEMBER-GAP"
        interp = (
            "typed_qi ACQUIRED the wizard-hole object but HoleType (and likely "
            f"other wizard setup members) is MISSING from the makepy class ({members}) "
            "→ regenerate makepy for the SW typelib; typed_qi cannot add members. "
            "This confirms the v0.15 HoleType AttributeError as a wrapper-coverage gap."
        )
    elif create_rec.get("materialized"):
        overall = "PASS"
        interp = (
            "wizard hole materializes via CreateDefinition+typed_qi → build the "
            "F2 hole handler on this pipeline."
        )
    else:
        overall = "PARTIAL"
        interp = (
            "wizard setup members ARE present and set, but CreateFeature did not "
            "materialize → the wall is placement/setup (wizard holes need sketch "
            "points on the face) or marshaling; run --mode vba and add placement."
        )

    result["overall"] = overall
    result["interpretation"] = interp
    return result


def emit_vba() -> str:
    return r"""' Spike v0.16 S-WIZHOLE-QI VBA oracle.
' Paste into a Part with a 20x20x10 box. Tests whether the wizard-hole data
' object exposes HoleType + materializes in EARLY binding (where Python's
' makepy may be missing members).
Option Explicit
Sub ProbeWizHole()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As SldWorks.WizardHoleFeatureData2
    Dim feat  As SldWorks.Feature
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set fm = Part.FeatureManager

    Set fd = fm.CreateDefinition(swFmHoleWzd)   ' 25
    If fd Is Nothing Then MsgBox "CreateDefinition(25) Nothing": Exit Sub
    MsgBox "HoleType reads as: " & fd.HoleType   ' AttributeError canary in Python

    Part.ClearSelection2 True
    Part.SelectByID2 "", "FACE", 0, 0, 0.01, False, 0, Nothing, 0
    Set feat = fm.CreateFeature(fd)
    If feat Is Nothing Then
        MsgBox "CreateFeature: NOTHING (placement likely needs sketch points)"
    Else
        MsgBox "Wizard hole: " & feat.Name & " / " & feat.GetTypeName2
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
        out = Path(__file__).parent / "spike_wizhole_qi.bas"
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

    return {"PASS": 0, "PARTIAL": 2, "MEMBER-GAP": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
