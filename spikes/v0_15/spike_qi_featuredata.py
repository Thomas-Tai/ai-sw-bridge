"""
Spike v0.15 / S-QI-FEATUREDATA -- can a raw QueryInterface soundly acquire a
typed SOLIDWORKS feature-data interface out-of-process?  [RUN ON A LIVE SEAT]

This attacks OI-1 (keystone_status.md sec.4.1): the direct typed-wrap
``cls(obj._oleobj_)`` invokes by *compiled dispid* and does NOT QueryInterface,
so wrapping a ``CreateDefinition`` result as a guessed feature-data interface
calls whatever member sits at that dispid (dispid collision) -- "it worked" is
meaningless. ``CastTo`` also fails because SW refuses ``IDispatch::GetTypeInfo``.

The untried mechanism: a *raw* ``_oleobj_.QueryInterface(iid)``. QI does NOT use
``GetTypeInfo`` -- it asks the C++ ``IUnknown`` directly whether it implements
the interface, returning ``E_NOINTERFACE`` (0x80004002) if not. If SW exposes
each feature-data interface as a genuinely QI-able (dual/vtable) interface, QI
is a side-effect-free, sound way to both *acquire* and *identify* the object.

THIS IS A HYPOTHESIS TEST, NOT A CONFIRMED FIX. Three possible outcomes, and
the spike is built to tell them apart per object:

  * DISCRIMINATING : the object answers QI for its own interface (and related
                     ones in its inheritance chain) and REJECTS unrelated
                     feature-data IIDs with E_NOINTERFACE. -> QI is sound;
                     OI-1's acquisition question is answered. Adopt
                     QueryInterface-by-IID in com.earlybind.
  * NON_DISCRIMINATING : the object answers S_OK to unrelated IIDs too (a shared
                     IDispatch / aggregated object). -> QI does not discriminate;
                     same disease, new symptom. Pivot (comtypes / behaviour-
                     validation).
  * NOT_QI_ABLE   : the object rejects even its OWN interface IID (these are
                     dispinterfaces, not QI-able). -> QI is dead for feature
                     data; pivot.

Corrections vs. the naive approach this replaces:
  1. IID construction uses ``pywintypes.IID`` (``pythoncom.IID`` does NOT exist).
  2. IIDs are read from the makepy class ``.CLSID`` -- no hand-copied GUIDs.
  3. Two acquisition paths are tested: ``IFeature.GetDefinition`` on an EXISTING
     feature (control) AND ``IFeatureManager.CreateDefinition`` on a fresh one
     (the actual OI-1 feature-addition path) -- they can behave differently.
  4. Full QI support MATRIX per object (every candidate IID at once) with the
     hresult + COM-identity of each hit, so NON_DISCRIMINATING is caught
     explicitly rather than mistaken for a pass.

Non-destructive: own fresh blank Parts via NewDocument; never touches the user's
open docs; closes its own docs at the end (no save).

Usage
-----
    python spikes/v0_15/spike_qi_featuredata.py
    python spikes/v0_15/spike_qi_featuredata.py --out report.json --keep-docs
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
import pywintypes  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

# Reuse proven, binding-agnostic setup from the established spikes.
from spike_persist_reference import build_single_box  # noqa: E402
from spike_earlybind_persist import ensure_sw_module  # noqa: E402
from spike_varfil import SW_FM_FILLET  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
E_NOINTERFACE = 0x80004002

# Candidate feature-data interfaces. The matrix QIs each test object against
# ALL of these; IIDs are resolved from makepy ``.CLSID`` at runtime (missing
# names are skipped, not fatal -- the module surface differs across SW builds).
CANDIDATE_IFACES = [
    "IExtrudeFeatureData2",
    "IShellFeatureData",
    "IDraftFeatureData2",
    "ISimpleFilletFeatureData2",
    "IVariableFilletFeatureData2",
    "IWizardHoleFeatureData2",
    "IBaseFlangeFeatureData",
]


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _new_blank_part(sw: Any) -> Any:
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    return sw.NewDocument(template, 0, 0.0, 0.0)


def _resolve_iids(mod: Any) -> dict[str, Any]:
    """Map each candidate interface name -> its IID, read from makepy .CLSID.

    makepy generates ``class IShellFeatureData(DispatchBaseClass): CLSID = IID(...)``
    where CLSID is the *interface* IID. Reading it here removes the hand-copied-
    GUID failure mode entirely.
    """
    out: dict[str, Any] = {}
    for name in CANDIDATE_IFACES:
        cls = getattr(mod, name, None)
        iid = getattr(cls, "CLSID", None) if cls is not None else None
        if iid is not None:
            out[name] = iid
    return out


def _qi_one(src_ole: Any, src_unk: Any, name: str, iid: Any) -> dict[str, Any]:
    """QI *src_ole* for one interface IID; record support / hresult / identity.

    Uses ``QueryInterface(iid, IID_IDispatch)`` -- the second arg tells pywin32
    to wrap the returned pointer as ``IDispatch`` (valid: SW feature-data
    interfaces are dual). Without it, a *bare* ``QueryInterface(iid)`` raises
    ``TypeError("no interface object registered ...")`` on S_OK for any SW
    custom interface (no compiled pywin32 gateway), which is easily mistaken for
    a failure. With the hint, S_OK -> a usable dispatch, E_NOINTERFACE -> a clean
    rejection.
    """
    row: dict[str, Any] = {"iface": name, "iid": str(iid)}
    try:
        disp = src_ole.QueryInterface(iid, pythoncom.IID_IDispatch)
        row["supported"] = True
        row["hresult"] = None
        row["wrapped_as"] = _tag(disp)
        # Identity: does the QI'd pointer denote the SAME COM object as the
        # source? (True is expected -- QI returns an interface on the same
        # object; it is informational, not a failure signal.)
        try:
            row["same_object_as_source"] = bool(disp == src_unk)
        except Exception as e:  # noqa: BLE001
            row["same_object_as_source"] = None
            row["identity_note"] = f"{type(e).__name__}: {str(e)[:60]}"
    except pythoncom.com_error as e:
        hr = getattr(e, "hresult", None)
        if hr is None and e.args:
            hr = e.args[0]
        hr_u = (hr & 0xFFFFFFFF) if isinstance(hr, int) else None
        row["supported"] = False
        row["hresult"] = f"{hr_u:#010x}" if hr_u is not None else str(hr)
        row["is_e_nointerface"] = hr_u == E_NOINTERFACE
    except Exception as e:  # noqa: BLE001 -- non-COM failure (e.g. no _oleobj_)
        row["supported"] = None
        row["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return row


def _matrix(obj: Any, iids: dict[str, Any], expected: set[str]) -> dict[str, Any]:
    """QI *obj* against every candidate IID; classify discrimination.

    ``expected`` = the interface names this object SHOULD support (its own type
    and related chain). Everything else is the unrelated set used to prove QI
    actually filters.
    """
    raw = getattr(obj, "_oleobj_", None)
    if raw is None:
        return {"verdict": "ERROR", "reason": "object has no _oleobj_ (not a dispatch)"}
    try:
        src_unk = raw.QueryInterface(pythoncom.IID_IUnknown)
    except Exception as e:  # noqa: BLE001
        return {
            "verdict": "ERROR",
            "reason": f"QI to IUnknown failed: {type(e).__name__}: {e}",
        }

    rows = [_qi_one(raw, src_unk, name, iid) for name, iid in iids.items()]

    supported = {r["iface"] for r in rows if r.get("supported") is True}
    rejected_noiface = {
        r["iface"]
        for r in rows
        if r.get("supported") is False and r.get("is_e_nointerface")
    }
    unrelated = set(iids) - expected
    expected_present = expected & set(iids)

    # "at least one expected interface answers" -- an object legitimately
    # supports a *subset* of its family (e.g. a default fillet is simple, not
    # variable), so requiring ALL would mis-fail a sound result.
    expected_hit = bool(supported & expected_present)
    unrelated_rejected = bool(unrelated) and unrelated.issubset(rejected_noiface)
    unrelated_leaked = supported & unrelated

    if not supported:
        verdict = "NOT_QI_ABLE"  # rejects every IID including its own family
    elif unrelated_leaked:
        verdict = "NON_DISCRIMINATING"  # answers S_OK to unrelated IIDs
    elif expected_hit and unrelated_rejected:
        verdict = "DISCRIMINATING"  # the sound result
    else:
        verdict = (
            "INCONCLUSIVE"  # e.g. no unrelated IIDs present, or only-unexpected hits
        )

    return {
        "verdict": verdict,
        "expected": sorted(expected_present),
        "supported": sorted(supported),
        "rejected_E_NOINTERFACE": sorted(rejected_noiface),
        "unrelated_leaked": sorted(unrelated_leaked),
        "matrix": rows,
    }


def run(keep_docs: bool) -> dict[str, Any]:
    from ai_sw_bridge.sw_com import get_sw_app  # late import: needs a live seat

    result: dict[str, Any] = {"mechanism": "raw _oleobj_.QueryInterface(iid)"}
    sw = get_sw_app()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception as e:  # noqa: BLE001
        result["sw_revision"] = f"<unreadable: {type(e).__name__}>"

    mod = wrapper_module()
    result["module_source"] = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_source"] = "ensure_sw_module (LoadTypeLib fallback)"
        result["module_fallback_info"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    iids = _resolve_iids(mod)
    result["resolved_iids"] = {k: str(v) for k, v in iids.items()}
    missing = [n for n in CANDIDATE_IFACES if n not in iids]
    if missing:
        result["iface_names_not_in_module"] = missing
    if not iids:
        return {
            **result,
            "overall": "ERROR",
            "reason": "no candidate feature-data interfaces resolved from makepy",
        }

    objects: list[dict[str, Any]] = []
    open_docs: list[Any] = []

    # --- Object 1: GetDefinition on an EXISTING extrude (acquisition control) ---
    doc1 = _new_blank_part(sw)
    rec1: dict[str, Any] = {
        "object": "extrude_GetDefinition",
        "path": "IFeature.GetDefinition (existing feature)",
    }
    if doc1 is None:
        rec1["result"] = {"verdict": "ERROR", "reason": "NewDocument returned None"}
    else:
        open_docs.append(doc1)
        build = build_single_box(doc1)
        rec1["build"] = build
        feat = (
            doc1.FeatureByName(build.get("feature_name"))
            if build.get("built")
            else None
        )
        getdef = None
        if feat is not None:
            try:
                gd = feat.GetDefinition
                getdef = gd() if callable(gd) else gd
            except Exception as e:  # noqa: BLE001
                rec1["getdefinition_late_error"] = f"{type(e).__name__}: {str(e)[:120]}"
                # Late-bound GetDefinition hit "Member not found"; retry via an
                # early-bound typed IFeature (feat genuinely IS IFeature, so this
                # dispid call is sound -- it is the *identification* of arbitrary
                # data objects that dispid can't do, which is what QI is for).
                try:
                    getdef = typed(feat, "IFeature", module=mod).GetDefinition()
                    rec1["getdefinition_via"] = "typed IFeature (early-bound)"
                except Exception as e2:  # noqa: BLE001
                    rec1["getdefinition_typed_error"] = (
                        f"{type(e2).__name__}: {str(e2)[:120]}"
                    )
        rec1["getdefinition_type"] = _tag(getdef)
        if getdef is None:
            rec1["result"] = {
                "verdict": "ERROR",
                "reason": "GetDefinition returned None",
            }
        else:
            rec1["result"] = _matrix(getdef, iids, expected={"IExtrudeFeatureData2"})
    objects.append(rec1)

    # --- Object 2: CreateDefinition(swFmFillet) (the real OI-1 path) ---
    doc2 = _new_blank_part(sw)
    rec2: dict[str, Any] = {
        "object": "fillet_CreateDefinition",
        "path": "IFeatureManager.CreateDefinition(swFmFillet)",
    }
    if doc2 is None:
        rec2["result"] = {"verdict": "ERROR", "reason": "NewDocument returned None"}
    else:
        open_docs.append(doc2)
        build2 = build_single_box(doc2)
        rec2["build"] = build2
        data = None
        if build2.get("built"):
            try:
                data = doc2.FeatureManager.CreateDefinition(SW_FM_FILLET)
            except Exception as e:  # noqa: BLE001
                rec2["createdefinition_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        rec2["createdefinition_type"] = _tag(data)
        if data is None:
            rec2["result"] = {
                "verdict": "ERROR",
                "reason": "CreateDefinition(swFmFillet) returned None",
            }
        else:
            # Fillet family is "expected"; shell/draft/wizhole/baseflange/extrude
            # are the unrelated discriminators.
            rec2["result"] = _matrix(
                data,
                iids,
                expected={"ISimpleFilletFeatureData2", "IVariableFilletFeatureData2"},
            )
    objects.append(rec2)

    result["objects"] = objects

    # Cleanup (best-effort, no save).
    if not keep_docs:
        closed = []
        for d in open_docs:
            try:
                sw.CloseDoc(_title(d))
                closed.append(True)
            except Exception:  # noqa: BLE001
                closed.append(False)
        result["cleanup"] = f"closed {sum(closed)}/{len(open_docs)} own docs (no save)"
    else:
        result["cleanup"] = f"kept {len(open_docs)} docs open"

    # Aggregate OI-1 verdict. Setup-ERROR objects (acquisition failed before the
    # matrix ran) don't bear on whether QI discriminates -- judge on matrixed ones.
    verdicts = [
        o.get("result", {}).get("verdict")
        for o in objects
        if o.get("result", {}).get("verdict") != "ERROR"
    ]
    if "NON_DISCRIMINATING" in verdicts:
        overall, interp = "NON_DISCRIMINATING", (
            "QI returns S_OK for unrelated feature-data IIDs -- it does not "
            "discriminate. Same disease as the dispid collision; QueryInterface-"
            "by-IID is NOT a sound acquisition path as-is. Pivot to comtypes or "
            "behaviour-validation."
        )
    elif "NOT_QI_ABLE" in verdicts:
        overall, interp = "NOT_QI_ABLE", (
            "An object rejected even its OWN interface IID -- SW feature-data "
            "interfaces are not QI-able (dispinterface / shared IDispatch). "
            "QueryInterface is dead for OI-1; pivot to comtypes / behaviour-validation."
        )
    elif "DISCRIMINATING" in verdicts:
        overall, interp = "DISCRIMINATING", (
            "QI soundly acquires AND identifies feature-data objects: each answers "
            "its own interface and rejects unrelated IIDs with E_NOINTERFACE. OI-1's "
            "acquisition question is ANSWERED -- adopt QueryInterface-by-IID (IIDs "
            "from makepy .CLSID) in com.earlybind, then build the rich feature pipeline."
        )
    else:
        overall, interp = "INCONCLUSIVE", (
            "Mixed/inconclusive (e.g. an object errored before the matrix, or no "
            "unrelated IIDs were available to test discrimination). Inspect per-object "
            "results before drawing an OI-1 conclusion."
        )
    result["overall"] = overall
    result["interpretation"] = interp
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    p.add_argument(
        "--keep-docs",
        action="store_true",
        help="Do not close the spike's own documents at the end.",
    )
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
    return {"DISCRIMINATING": 0, "INCONCLUSIVE": 2}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
