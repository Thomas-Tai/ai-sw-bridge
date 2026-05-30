"""
Spike v0.15 / S-EARLYBIND-FEATURES -- do the four FAIL features fall to hybrid
early binding too?  [authored seat-free; RUN ON A LIVE SEAT]

S-EARLYBIND proved the *persist* OUT-param wall is the late-binding marshaler,
not the SW API: a typed-wrapped ``IModelDocExtension`` resolves
``GetObjectByPersistReference3`` out-of-process (PASS). This spike asks the
follow-up the roadmap demands before any feature is declared blocked: **does
the same hybrid early-binding trick clear the wave-2 FAIL features?**

The seat run (SW 2024 SP1, 2026-05-29) returned FAIL for:

  * **S-VARFIL** -- ``CreateDefinition(swFmFillet)`` returned an object whose
    ``VariableRadiusParameters`` were not exposed late-bound.
  * **S-WIZHOLE** -- ``CreateDefinition(swFmHoleWzd)`` ->
    ``IWizardHoleFeatureData2`` props / ``CreateFeature`` pipeline.
  * **S-SHELL / S-DRAFT** -- ``InsertFeatureShell`` / ``InsertDraft2``
    returned None in every arity.
  * **S-SHEETMETAL** -- ``InsertSheetMetalBaseFlange2`` returned no feature
    in any arity.

Two failure sub-classes, two hybrid hypotheses (both routed through the
shipped ``ai_sw_bridge.com.earlybind`` helper):

  A. *CreateDefinition -> feature-data interface* (varfil, wizhole). The
     returned data object's typed interface is not exposed late-bound.
     Hypothesis: ``typed(data, "IVariableRadiusFilletFeatureData")`` /
     ``typed(data, "IWizardHoleFeatureData2")`` exposes it -- the exact
     pattern that cleared the persist Extension.

  B. *direct FeatureManager.Insert\\* call* (shell, draft, sheetmetal). The
     late-bound ``IFeatureManager`` call returns None. Hypothesis:
     ``typed(fm, "IFeatureManager").Insert\\*(...)`` marshals the args
     through makepy's compiled dispids and materializes the feature.

Each probe opens its OWN fresh blank Part via ``NewDocument`` (non-destructive
-- it never touches the user's open documents), reuses the proven geometry
builders from the original spikes, and runs the decisive op **early-bound**.
The prior late-bound verdict (FAIL) is recorded alongside for the delta; we do
not re-run the late-bound op (it is already established and would mutate the
part).

Verdict (per feature, then aggregate)
-------------------------------------
PASS    : the feature materializes early-bound where it FAILed late-bound --
          hybrid binding generalizes; the lane is out-of-process viable.
PARTIAL : the typed interface / data object becomes reachable early-bound
          (props settable) but the final ``CreateFeature`` / ``Insert*`` still
          does not materialize -- the wall moved but did not fall; narrow the
          probe and retry.
FAIL    : early binding changes nothing -- the wall is the API for this
          feature, not the marshaler; it stays blocked (record in DEFERRED.md).

Aggregate: PASS if any feature newly materializes; else PARTIAL if any shows a
reachable-interface improvement; else FAIL.

Prereq: SOLIDWORKS 2024 SP1 running. First run may regenerate the makepy
cache (slow); later runs fast.

Usage
-----
    python spikes/v0_15/spike_earlybind_features.py --out report.json
    python spikes/v0_15/spike_earlybind_features.py --feature varfil
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import EarlyBindError, is_early_bound, typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

# Reuse the proven, binding-agnostic geometry + setup helpers from the original
# spikes (same script dir is on sys.path[0] when run directly), so only the
# binding differs from the established FAIL runs.
from spike_persist_reference import build_single_box, _first_body  # noqa: E402
from spike_earlybind_persist import ensure_sw_module  # noqa: E402
from spike_varfil import (  # noqa: E402
    SW_FM_FILLET,
    FILLET_TYPE_VARIABLE,
    VARRAD_START_M,
    VARRAD_END_M,
    _is_varfil_data,
    _select_bottom_edge,
)
from spike_wizhole import scan_swFmHoleWzd  # noqa: E402
from spike_shell_draft import SHELL_THICKNESS_M, DRAFT_ANGLE_RAD  # noqa: E402
from spike_sheetmetal import (  # noqa: E402
    _build_profile_sketch,
    SM_THICKNESS_M,
    SM_REVERSE,
    SM_BEND_RADIUS_M,
    SM_K_FACTOR,
    SM_RELIEF_TYPE,
    SM_RELIEF_W_M,
    SM_RELIEF_D_M,
    SM_RELIEF_RATIO,
    SM_AUTO_RELIEF,
    SM_FORM_FEATURE,
    SM_MERGE_RESULT,
)

SW_DEFAULT_TEMPLATE_PART = 8


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _materialized(feat: Any) -> bool:
    """A real feature came back (not None, not an int error sentinel)."""
    return feat is not None and not isinstance(feat, int)


def _capture(fn: Callable[[], Any]) -> dict[str, Any]:
    """Run *fn*, returning a uniform record of value / exception + timing."""
    t0 = time.perf_counter()
    try:
        val = fn()
        return {"status": "OK", "type": _tag(val), "_val": val,
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    except EarlyBindError as e:
        return {"status": "EARLYBIND_ERROR", "message": str(e),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    except Exception as e:  # noqa: BLE001 -- capture com_error + everything for the report
        return {"status": "EXCEPTION", "exception_type": type(e).__name__,
                "message": str(e)[:200],
                "hresult": (f"{e.hresult:#010x}" if hasattr(e, "hresult") else None),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}


def _new_blank_part(sw: Any) -> Any:
    """Open a fresh blank Part (non-destructive; own document)."""
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    return sw.NewDocument(template, 0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Class A -- CreateDefinition -> feature-data interface
# ---------------------------------------------------------------------------

def probe_varfil(sw: Any, mod: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "varfil", "class": "A",
                           "prior_late_bound_verdict": "FAIL", "iface": "IVariableRadiusFilletFeatureData"}
    doc = _new_blank_part(sw)
    if doc is None:
        return {**rec, "verdict": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    rec["build"] = build
    if not build.get("built"):
        return {**rec, "verdict": "FAIL", "reason": "box did not build"}
    fm = doc.FeatureManager

    data = fm.CreateDefinition(SW_FM_FILLET)
    if data is None:
        return {**rec, "verdict": "FAIL", "reason": "CreateDefinition(swFmFillet) returned None"}
    rec["late_bound_has_varrad"] = _is_varfil_data(data)  # expected False (the FAIL)

    wrap = _capture(lambda: typed(data, "IVariableRadiusFilletFeatureData", module=mod))
    rec["typed_wrap"] = {k: v for k, v in wrap.items() if k != "_val"}
    if wrap["status"] != "OK":
        return {**rec, "verdict": "FAIL", "reason": "could not typed-wrap the fillet data object"}
    tdata = wrap["_val"]
    rec["early_bound"] = is_early_bound(tdata)

    # Is the variable-radius surface now reachable?
    setup = _capture(lambda: (
        setattr(tdata, "FilletType", FILLET_TYPE_VARIABLE),
        setattr(tdata, "Radius", VARRAD_START_M),
        tdata.SetVariableRadiusParameters((VARRAD_START_M, VARRAD_END_M)),
    ))
    rec["varrad_setup"] = {k: v for k, v in setup.items() if k != "_val"}
    rec["interface_reachable"] = setup["status"] == "OK"

    sel = _select_bottom_edge(doc)
    rec["edge_selection"] = sel
    if not sel.get("ok"):
        return {**rec, "verdict": "PARTIAL" if rec["interface_reachable"] else "FAIL",
                "reason": "interface reachable but edge selection failed; cannot CreateFeature"}

    tfm = _capture(lambda: typed(fm, "IFeatureManager", module=mod))["_val"] if True else fm
    feat = _capture(lambda: (tfm or fm).CreateFeature(tdata))
    rec["create_feature"] = {k: v for k, v in feat.items() if k != "_val"}
    ok = feat["status"] == "OK" and _materialized(feat.get("_val"))
    if ok:
        return {**rec, "verdict": "PASS"}
    return {**rec, "verdict": "PARTIAL" if rec["interface_reachable"] else "FAIL",
            "reason": "interface reachable early-bound but CreateFeature did not materialize"}


def probe_wizhole(sw: Any, mod: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "wizhole", "class": "A",
                           "prior_late_bound_verdict": "FAIL", "iface": "IWizardHoleFeatureData2"}
    doc = _new_blank_part(sw)
    if doc is None:
        return {**rec, "verdict": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    rec["build"] = build
    if not build.get("built"):
        return {**rec, "verdict": "FAIL", "reason": "box did not build"}
    fm = doc.FeatureManager

    scan = scan_swFmHoleWzd(fm)
    rec["swFmHoleWzd_scan"] = {"found": scan.get("swFmHoleWzd_found"),
                              "int": scan.get("swFmHoleWzd_int")}
    if not scan.get("swFmHoleWzd_found"):
        return {**rec, "verdict": "FAIL", "reason": "swFmHoleWzd enum not found by scan"}
    data = fm.CreateDefinition(scan["swFmHoleWzd_int"])
    if data is None:
        return {**rec, "verdict": "FAIL", "reason": "CreateDefinition(swFmHoleWzd) returned None"}

    wrap = _capture(lambda: typed(data, "IWizardHoleFeatureData2", module=mod))
    rec["typed_wrap"] = {k: v for k, v in wrap.items() if k != "_val"}
    if wrap["status"] != "OK":
        return {**rec, "verdict": "FAIL", "reason": "could not typed-wrap the wizard-hole data object"}
    tdata = wrap["_val"]
    rec["early_bound"] = is_early_bound(tdata)

    setup = _capture(lambda: setattr(tdata, "HoleType", 2))  # swWzdHole -- simple drill probe
    rec["prop_setup"] = {k: v for k, v in setup.items() if k != "_val"}
    rec["interface_reachable"] = setup["status"] == "OK"

    # Place on the +z top face centre (best-effort; the hole-wizard needs a point).
    placed = _capture(lambda: doc.SelectByID("", "FACE", 0.0, 0.0, 0.010))
    rec["placement_select"] = {k: v for k, v in placed.items() if k != "_val"}

    tfm = _capture(lambda: typed(fm, "IFeatureManager", module=mod))["_val"]
    feat = _capture(lambda: (tfm or fm).CreateFeature(tdata))
    rec["create_feature"] = {k: v for k, v in feat.items() if k != "_val"}
    ok = feat["status"] == "OK" and _materialized(feat.get("_val"))
    if ok:
        return {**rec, "verdict": "PASS"}
    return {**rec, "verdict": "PARTIAL" if rec["interface_reachable"] else "FAIL",
            "reason": "interface reachable early-bound but CreateFeature did not materialize"}


# ---------------------------------------------------------------------------
# Class B -- direct FeatureManager.Insert* call (typed IFeatureManager)
# ---------------------------------------------------------------------------

def _typed_fm(fm: Any, mod: Any) -> dict[str, Any]:
    wrap = _capture(lambda: typed(fm, "IFeatureManager", module=mod))
    return wrap


def probe_shell(sw: Any, mod: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "shell", "class": "B",
                           "prior_late_bound_verdict": "FAIL", "iface": "IFeatureManager"}
    doc = _new_blank_part(sw)
    if doc is None:
        return {**rec, "verdict": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    rec["build"] = build
    if not build.get("built"):
        return {**rec, "verdict": "FAIL", "reason": "box did not build"}
    fm = doc.FeatureManager

    # Select the +z top face to remove (shell needs >=1 removed face for an open box).
    body = _first_body(doc)
    faces = list(body.GetFaces() or []) if body is not None else []
    rec["face_count"] = len(faces)
    sel = _capture(lambda: doc.SelectByID("", "FACE", 0.0, 0.0, 0.010))
    rec["face_select"] = {k: v for k, v in sel.items() if k != "_val"}

    wrap = _typed_fm(fm, mod)
    rec["typed_wrap"] = {k: v for k, v in wrap.items() if k != "_val"}
    if wrap["status"] != "OK":
        return {**rec, "verdict": "FAIL", "reason": "could not typed-wrap FeatureManager"}
    tfm = wrap["_val"]
    rec["early_bound"] = is_early_bound(tfm)

    feat = _capture(lambda: tfm.InsertFeatureShell(SHELL_THICKNESS_M, True))
    rec["insert_shell"] = {k: v for k, v in feat.items() if k != "_val"}
    ok = feat["status"] == "OK" and _materialized(feat.get("_val"))
    return {**rec, "verdict": "PASS" if ok else "FAIL",
            "reason": None if ok else "InsertFeatureShell still did not materialize early-bound"}


def probe_draft(sw: Any, mod: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "draft", "class": "B",
                           "prior_late_bound_verdict": "FAIL", "iface": "IFeatureManager"}
    doc = _new_blank_part(sw)
    if doc is None:
        return {**rec, "verdict": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    rec["build"] = build
    if not build.get("built"):
        return {**rec, "verdict": "FAIL", "reason": "box did not build"}
    fm = doc.FeatureManager

    # Draft needs a neutral plane + face(s) to taper. Select a side face to draft;
    # the original spike marks faces via GetFaces -- mirror that best-effort.
    sel = _capture(lambda: doc.SelectByID("", "FACE", 0.010, 0.0, 0.005))
    rec["face_select"] = {k: v for k, v in sel.items() if k != "_val"}

    wrap = _typed_fm(fm, mod)
    rec["typed_wrap"] = {k: v for k, v in wrap.items() if k != "_val"}
    if wrap["status"] != "OK":
        return {**rec, "verdict": "FAIL", "reason": "could not typed-wrap FeatureManager"}
    tfm = wrap["_val"]
    rec["early_bound"] = is_early_bound(tfm)

    args_7 = (DRAFT_ANGLE_RAD, False, False, False, 0.0, True, DRAFT_ANGLE_RAD)
    feat = _capture(lambda: tfm.InsertDraft2(*args_7))
    rec["insert_draft_7arg"] = {k: v for k, v in feat.items() if k != "_val"}
    if not (feat["status"] == "OK" and _materialized(feat.get("_val"))):
        feat6 = _capture(lambda: tfm.InsertDraft2(*args_7[:6]))
        rec["insert_draft_6arg"] = {k: v for k, v in feat6.items() if k != "_val"}
        feat = feat6 if (feat6["status"] == "OK" and _materialized(feat6.get("_val"))) else feat
    ok = feat["status"] == "OK" and _materialized(feat.get("_val"))
    return {**rec, "verdict": "PASS" if ok else "FAIL",
            "reason": None if ok else "InsertDraft2 still did not materialize early-bound"}


def probe_sheetmetal(sw: Any, mod: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {"feature": "sheetmetal", "class": "B",
                           "prior_late_bound_verdict": "FAIL", "iface": "IFeatureManager"}
    doc = _new_blank_part(sw)
    if doc is None:
        return {**rec, "verdict": "FAIL", "reason": "NewDocument returned None"}
    # Sheet metal needs an OPEN profile sketch (not a solid) -- reuse the original setup.
    prof = _build_profile_sketch(doc)
    rec["profile_sketch"] = prof
    if not prof.get("built", prof.get("ok", False)):
        # _build_profile_sketch may key its success differently; keep going if a
        # sketch exists, but record what came back.
        rec["profile_note"] = "profile sketch builder did not report success; attempting anyway"
    fm = doc.FeatureManager

    wrap = _typed_fm(fm, mod)
    rec["typed_wrap"] = {k: v for k, v in wrap.items() if k != "_val"}
    if wrap["status"] != "OK":
        return {**rec, "verdict": "FAIL", "reason": "could not typed-wrap FeatureManager"}
    tfm = wrap["_val"]
    rec["early_bound"] = is_early_bound(tfm)

    base_11 = (SM_THICKNESS_M, SM_REVERSE, SM_BEND_RADIUS_M, SM_K_FACTOR,
               SM_RELIEF_TYPE, SM_RELIEF_W_M, SM_RELIEF_D_M, SM_RELIEF_RATIO,
               SM_AUTO_RELIEF, SM_FORM_FEATURE, SM_MERGE_RESULT)
    feat = _capture(lambda: tfm.InsertSheetMetalBaseFlange2(*base_11))
    rec["insert_baseflange_11arg"] = {k: v for k, v in feat.items() if k != "_val"}
    if not (feat["status"] == "OK" and _materialized(feat.get("_val"))):
        feat10 = _capture(lambda: tfm.InsertSheetMetalBaseFlange2(*base_11[:10]))
        rec["insert_baseflange_10arg"] = {k: v for k, v in feat10.items() if k != "_val"}
        feat = feat10 if (feat10["status"] == "OK" and _materialized(feat10.get("_val"))) else feat
    ok = feat["status"] == "OK" and _materialized(feat.get("_val"))
    return {**rec, "verdict": "PASS" if ok else "FAIL",
            "reason": None if ok else "InsertSheetMetalBaseFlange2 still did not materialize early-bound"}


PROBES: dict[str, Callable[[Any, Any], dict[str, Any]]] = {
    "varfil": probe_varfil,
    "wizhole": probe_wizhole,
    "shell": probe_shell,
    "draft": probe_draft,
    "sheetmetal": probe_sheetmetal,
}


def run(features: list[str]) -> dict[str, Any]:
    from ai_sw_bridge.sw_com import get_sw_app  # late import: needs a live seat

    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind.typed)"}
    sw = get_sw_app()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception as e:  # noqa: BLE001
        result["sw_revision"] = f"<unreadable: {type(e).__name__}>"

    # Source the makepy module via the SHIPPED helper; fall back to the proven
    # LoadTypeLib path (S-EARLYBIND) if the wrapper isn't generated yet.
    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module (LoadTypeLib fallback)"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source
    result["module"] = getattr(mod, "__name__", str(mod))

    per_feature: list[dict[str, Any]] = []
    for name in features:
        probe = PROBES[name]
        try:
            per_feature.append(probe(sw, mod))
        except Exception as e:  # noqa: BLE001 -- a probe must never sink the harness
            per_feature.append({"feature": name, "verdict": "FAIL",
                                "harness_error": f"{type(e).__name__}: {e}"})
    result["features"] = per_feature

    verdicts = [f.get("verdict") for f in per_feature]
    if "PASS" in verdicts:
        result["overall"] = "PASS"
    elif "PARTIAL" in verdicts:
        result["overall"] = "PARTIAL"
    else:
        result["overall"] = "FAIL"
    result["interpretation"] = {
        "PASS": "at least one wave-2 FAIL feature materializes under hybrid early binding "
                "-> generalize the typed-wrap to that lane; re-classify in the roadmap.",
        "PARTIAL": "typed interface(s) became reachable early-bound but the feature did not "
                   "materialize -> the wall moved; narrow the probe (selection / arg form).",
        "FAIL": "early binding changed nothing for these features -> the wall is the API, "
                "not the marshaler; keep blocked, record in DEFERRED.md.",
    }[result["overall"]]
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--feature", choices=sorted(PROBES), action="append",
                   help="Probe only this feature (repeatable). Default: all.")
    p.add_argument("--out", type=Path, default=None,
                   help="Write JSON report to this path instead of stdout.")
    args = p.parse_args()
    features = args.feature or list(PROBES)

    pythoncom.CoInitialize()
    try:
        result = run(features)
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
