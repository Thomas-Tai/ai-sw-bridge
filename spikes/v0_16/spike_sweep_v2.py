"""
Spike v0.16 / S-SWEEP v2 — typelib-gated sweep (+ mate probe) via COM.
[authored seat-free; RUN ON A LIVE SEAT]

Supersedes ``spike_sweep.py`` (v1, PARTIAL — blind 0..63 scan of
``CreateDefinition`` returned 12 CDispatch objects but no QI match because
the ``swFeatureNameID_e`` constant was never read from the typelib).

Strategy — three routes tried in order, first PASS wins
-------------------------------------------------------

Route A — TYPELIB-GATED (preferred)
    1. Walk ``swconst.tlb``; dump every enum fuzzy-matching
       ``Sweep | Loft | Mate`` (plus ``swFeatureNameID_e`` verbatim,
       plus ``swMateType_e`` for the mate probe).
    2. ``CreateDefinition(real_const)`` with the typelib-sourced value.
    3. ``typed_qi(data, "ISweepFeatureData")`` — QI-by-IID, proven sound
       on SW 2024 SP1 (see ``com.earlybind.typed_qi``).
    4. Select profile + path via typed ``IModelDocExtension.SelectByID2``
       (marks 1 / 4 — proven in D4 v1 + spike_drawview).
    5. ``CreateFeature(fd)`` — materialize.

Route B — LEGACY FALLBACK
    ``IFeatureManager.InsertProtrusionSwept*`` family. Bypasses the
    feature-data property mapping entirely; profile + path come from the
    selection set. Tries signatures from longest (11-arg) down; first one
    that materializes a body wins.

Route C — MATE REACHABILITY PROBE (informational, zero marginal seat cost)
    The typelib walk already extracts ``swFmMate`` (if present). A naked
    ``CreateDefinition(swFmMate) -> typed_qi(IMateFeatureData)`` — with
    no mate geometry built — proves the assembly-mate pipeline is
    reachable, de-risking the upcoming assembly epic. This is *not* a
    mate creation attempt; ``spike_mate.py`` owns that.

Verdicts
--------
PASS    — Route A or B materializes a sweep body.
PARTIAL — feature-data acquired but CreateFeature / Insert* did not
          materialize; narrow on seat (run ``--mode vba`` to isolate).
FAIL    — typelib walk yields no sweep constant, or CreateDefinition
          returns None for every candidate — sweep unreachable.

Prereq: SOLIDWORKS running. Creates its own part with profile+path
sketches (non-destructive; never touches the user's open documents).

Usage
-----
    python spikes/v0_16/spike_sweep_v2.py --out report.json
    python spikes/v0_16/spike_sweep_v2.py --mode vba
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402

from spike_earlybind_persist import connect_running_sw, ensure_sw_module  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8

SWCONST_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb")

ENUM_FUZZY_TOKENS = ("Sweep", "Loft", "Mate")
ENUM_EXACT_NAMES = ("swFeatureNameID_e", "swMateType_e")


# ---------------------------------------------------------------- helpers --


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


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


def _materialized(feat: Any) -> bool:
    return feat is not None and not isinstance(feat, int)


def _capture(fn: Any) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        val = fn()
        out = {
            "status": "OK",
            "type": _tag(val),
            "_val": val,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
        if isinstance(val, (bool, int, float, str)):
            out["value"] = val
        return out
    except Exception as e:  # noqa: BLE001
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


def _build_sweep_geometry(doc: Any) -> dict[str, Any]:
    """Circle profile on Front Plane + line path on Right Plane."""
    out: dict[str, Any] = {}
    try:
        doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateCircleByRadius(0.0, 0.0, 0.0, 0.005)
        doc.SketchManager.InsertSketch(True)
        out["profile_sketch"] = "Sketch1"
    except Exception as e:  # noqa: BLE001
        out["profile_error"] = f"{type(e).__name__}: {e}"
        return out
    try:
        doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
        doc.SketchManager.InsertSketch(True)
        doc.SketchManager.CreateLine(0.0, 0.0, 0.0, 0.05, 0.0, 0.0)
        doc.SketchManager.InsertSketch(True)
        out["path_sketch"] = "Sketch2"
    except Exception as e:  # noqa: BLE001
        out["path_error"] = f"{type(e).__name__}: {e}"
    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass
    return out


# ----------------------------------------------------------- typelib walk --


def _walk_swconst_typelib() -> dict[str, Any]:
    """Read sweep/loft/mate enum members straight out of swconst.tlb.

    Authoritative — no guessing, no hard-coded constants.
    """
    report: dict[str, Any] = {
        "path": str(SWCONST_TLB),
        "loadable": False,
        "enums": {},
        "discovered": {},
    }
    if not SWCONST_TLB.exists():
        report["error"] = f"swconst.tlb not found at {SWCONST_TLB}"
        return report

    try:
        tlb = pythoncom.LoadTypeLib(str(SWCONST_TLB))
    except Exception as e:  # noqa: BLE001
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["loadable"] = True

    la = tlb.GetLibAttr()
    libname, *_ = tlb.GetDocumentation(-1)
    report["libname"] = libname
    report["major"] = la[3]
    report["minor"] = la[4]

    enums: dict[str, dict[str, int]] = {}
    discovered: dict[str, dict[str, int]] = {}

    for i in range(tlb.GetTypeInfoCount()):
        name, *_ = tlb.GetDocumentation(i)
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        if ta.typekind != pythoncom.TKIND_ENUM:
            continue
        if not (name in ENUM_EXACT_NAMES or any(t in name for t in ENUM_FUZZY_TOKENS)):
            continue
        members: dict[str, int] = {}
        for v in range(ta.cVars):
            vd = info.GetVarDesc(v)
            mname = info.GetNames(vd.memid)[0]
            members[mname] = vd.value
        enums[name] = members

    for bucket_name, tokens in (
        ("swFmSweep", ("FmSweep", "FeatureNameSweep")),
        ("swFmLoft", ("FmLoft", "FeatureNameLoft")),
        ("swFmMate", ("FmMate", "AssemblyMate")),
    ):
        for ename, members in enums.items():
            for mname, val in members.items():
                if any(t in mname for t in tokens):
                    discovered.setdefault(bucket_name, {})[f"{ename}.{mname}"] = val
    report["enums"] = enums
    report["discovered"] = discovered
    return report


# ---------------------------------------------------------------- Route A --


def _route_a(
    fm: Any,
    mod: Any,
    doc: Any,
    geom: dict[str, Any],
    sweep_const: int | None,
    sweep_const_name: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "route": "A - typelib-gated CreateDefinition + typed_qi",
        "const": sweep_const,
        "const_name": sweep_const_name,
    }
    if sweep_const is None:
        result["error"] = "no sweep constant discovered from swconst.tlb"
        return result

    data_cap = _capture(lambda: fm.CreateDefinition(sweep_const))
    result["create_definition"] = data_cap
    if data_cap["status"] != "OK" or not _materialized(data_cap.get("_val")):
        return result

    data = data_cap["_val"]
    qi_cap = _capture(lambda: typed_qi(data, "ISweepFeatureData", module=mod))
    result["typed_qi_ISweepFeatureData"] = qi_cap
    if qi_cap["status"] != "OK":
        return result

    fd = qi_cap["_val"]
    profile = geom.get("profile_sketch", "Sketch1")
    path = geom.get("path_sketch", "Sketch2")
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    result["select_profile"] = _capture(
        lambda: ext.SelectByID2(profile, "SKETCH", 0, 0, 0, False, 1, None, 0)
    )
    result["select_path"] = _capture(
        lambda: ext.SelectByID2(path, "SKETCH", 0, 0, 0, True, 4, None, 0)
    )
    create_cap = _capture(lambda: fm.CreateFeature(fd))
    result["create_feature"] = create_cap
    if create_cap["status"] == "OK":
        feat = create_cap["_val"]
        result["materialized"] = _materialized(feat)
        if _materialized(feat):
            result["feature_type"] = _tag(feat)
            result["feature_type_name"] = _type_name(feat)
    return result


# ---------------------------------------------------------------- Route B --


_LEGACY_SWEEP_TRIES: tuple[tuple[str, tuple[Any, ...]], ...] = (
    (
        "InsertProtrusionSwept(11)",
        (False, False, 0, False, False, 0.0, 0.0, False, 0.0, 0.0, 0),
    ),
    (
        "InsertProtrusionSwept(10)",
        (False, False, 0, False, False, 0.0, 0.0, False, 0.0, 0.0),
    ),
    (
        "InsertProtrusionSwept(9)",
        (False, False, 0, False, False, 0.0, 0.0, False, 0.0),
    ),
    (
        "InsertProtrusionSwept(8)",
        (False, False, 0, False, False, 0.0, 0.0, False),
    ),
    ("InsertProtrusionSwept4", (False, False, 0, False, False)),
    ("InsertProtrusionSwept3", (False, False, 0)),
)


def _route_b(fm: Any, doc: Any, mod: Any, geom: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "route": "B - legacy InsertProtrusionSwept*",
    }
    profile = geom.get("profile_sketch", "Sketch1")
    path = geom.get("path_sketch", "Sketch2")
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    result["select_profile"] = _capture(
        lambda: ext.SelectByID2(profile, "SKETCH", 0, 0, 0, False, 1, None, 0)
    )
    result["select_path"] = _capture(
        lambda: ext.SelectByID2(path, "SKETCH", 0, 0, 0, True, 4, None, 0)
    )

    attempts: list[dict[str, Any]] = []
    for label, args in _LEGACY_SWEEP_TRIES:
        meth_name = label.split("(")[0]
        meth = getattr(fm, meth_name, None)
        if meth is None:
            attempts.append({"label": label, "status": "MISSING"})
            continue
        cap = _capture(lambda m=meth, a=args: m(*a))
        cap["label"] = label
        if cap["status"] == "OK" and _materialized(cap.get("_val")):
            cap["materialized"] = True
            cap["feature_type_name"] = _type_name(cap["_val"])
            attempts.append(cap)
            result["materialized"] = True
            result["winning_signature"] = label
            break
        attempts.append(cap)
    result["attempts"] = attempts
    return result


# -------------------------------------------------------------- Route C --


def _route_c_probe(
    fm: Any,
    mod: Any,
    mate_const: int | None,
    mate_const_name: str | None,
) -> dict[str, Any]:
    """Mate reachability probe - CreateDefinition + typed_qi only.

    No mate geometry built. A PASS here means the assembly epic starts
    with the pipeline proven; FAIL means spike_mate.py has a real wall.
    """
    result: dict[str, Any] = {
        "route": "C - [PROBE - MATE] reachability, no geometry",
        "const": mate_const,
        "const_name": mate_const_name,
    }
    if mate_const is None:
        result["error"] = "no mate constant discovered from swconst.tlb"
        return result
    data_cap = _capture(lambda: fm.CreateDefinition(mate_const))
    result["create_definition"] = data_cap
    if data_cap["status"] != "OK" or not _materialized(data_cap.get("_val")):
        return result
    data = data_cap["_val"]
    qi_cap = _capture(lambda: typed_qi(data, "IMateFeatureData", module=mod))
    result["typed_qi_IMateFeatureData"] = qi_cap
    if qi_cap["status"] == "OK":
        result["reachable"] = True
    return result


# ----------------------------------------------------------------- main --


def run(keep_file: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind pattern)"}

    mod = wrapper_module()
    mod_source = "com.sw_type_info.wrapper_module"
    if mod is None:
        mod, info = ensure_sw_module()
        mod_source = "spike_earlybind_persist.ensure_sw_module (LoadTypeLib fallback)"
        result["module_fallback_info"] = info
    result["module_source"] = mod_source
    result["module"] = getattr(mod, "__name__", str(mod))

    # --- 0. typelib walk (deterministic; fuels A + C) -----------------------
    typelib = _walk_swconst_typelib()
    result["typelib"] = typelib

    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    tmp_dir = Path(tempfile.gettempdir()) / "ai-sw-bridge"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    part_path = tmp_dir / "spike_sweep_v2.sldprt"
    if part_path.exists():
        try:
            part_path.unlink()
        except OSError:
            pass

    # --- 1. part + sweep geometry -------------------------------------------
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}

    geom = _build_sweep_geometry(doc)
    result["geometry"] = geom
    if "profile_error" in geom:
        _try_close(sw, doc)
        return {
            **result,
            "overall": "FAIL",
            "reason": f"profile sketch failed: {geom['profile_error']}",
        }
    if "path_error" in geom:
        _try_close(sw, doc)
        return {
            **result,
            "overall": "FAIL",
            "reason": f"path sketch failed: {geom['path_error']}",
        }

    fm = doc.FeatureManager

    sweep_bucket = typelib.get("discovered", {}).get("swFmSweep") or {}
    sweep_const: int | None = None
    sweep_const_name: str | None = None
    if sweep_bucket:
        sweep_const_name, sweep_const = next(iter(sweep_bucket.items()))

    mate_bucket = typelib.get("discovered", {}).get("swFmMate") or {}
    mate_const: int | None = None
    mate_const_name: str | None = None
    if mate_bucket:
        mate_const_name, mate_const = next(iter(mate_bucket.items()))

    # --- 2. Route A ---------------------------------------------------------
    route_a = _route_a(fm, mod, doc, geom, sweep_const, sweep_const_name)
    result["route_a"] = route_a

    # --- 3. Route B (only if A did not materialize) ------------------------
    if route_a.get("materialized"):
        overall = "PASS"
        interp = (
            "Route A materialized a sweep body via typelib-gated "
            "CreateDefinition + typed_qi(ISweepFeatureData) - build the handler."
        )
    else:
        route_b = _route_b(fm, doc, mod, geom)
        result["route_b"] = route_b
        if route_b.get("materialized"):
            overall = "PASS"
            interp = (
                "Route B materialized a sweep body via legacy "
                f"{route_b.get('winning_signature')} - build the handler on the "
                "legacy path; Route A's CreateDefinition still needs diagnosis."
            )
        else:
            overall = "PARTIAL"
            interp = (
                "Neither Route A (CreateDefinition + typed_qi) nor Route B "
                "(InsertProtrusionSwept*) materialized - narrow on seat with "
                "--mode vba. Check: did the typelib walk surface swFmSweep at "
                "all? If not, the SW edition may ship sweep under a different "
                "feature-name enum."
            )
    result["overall"] = overall
    result["interpretation"] = interp

    # --- 4. Route C - mate probe (informational, decoupled from verdict) ---
    result["route_c"] = _route_c_probe(fm, mod, mate_const, mate_const_name)

    # --- cleanup -----------------------------------------------------------
    _try_close(sw, doc)
    if not keep_file:
        try:
            part_path.unlink()
        except OSError:
            pass
        result["cleanup"] = "closed doc + removed temp file"
    else:
        result["cleanup"] = f"kept file at {part_path}"

    return result


def emit_vba() -> str:
    return r"""' Spike v0.16 S-SWEEP v2 - VBA oracle.
' Paste into a Part with a circle profile (Sketch1) and line path (Sketch2).
' Replace SWEEP_CONST with the typelib-sourced swFmSweep value from the
' Python harness's Route A report before running.
Option Explicit
Sub ProbeSweepV2()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As Object
    Dim Feat  As SldWorks.Feature
    Const SWEEP_CONST = 0  ' <-- paste typelib-discovered value here
    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager

    Set fd = fm.CreateDefinition(SWEEP_CONST)
    If fd Is Nothing Then
        MsgBox "CreateDefinition returned Nothing for " & SWEEP_CONST
        Exit Sub
    End If

    ' SelectByID2 marks: 1 = profile, 4 = path
    Part.Extension.SelectByID2 "Sketch1", "SKETCH", 0, 0, 0, False, 1, Nothing, 0
    Part.Extension.SelectByID2 "Sketch2", "SKETCH", 0, 0, 0, True,  4, Nothing, 0

    Set Feat = fm.CreateFeature(fd)
    If Feat Is Nothing Then
        ' Route A failed - try legacy
        Set Feat = fm.InsertProtrusionSwept(False, False, 0, False, False, _
                                            0#, 0#, False, 0#, 0#, 0)
        If Feat Is Nothing Then
            MsgBox "Neither Route A nor Route B produced a sweep."
        Else
            MsgBox "Route B sweep created: " & Feat.Name
        End If
    Else
        MsgBox "Route A sweep created: " & Feat.Name
    End If
End Sub
"""


def _scrub(o: Any) -> Any:
    """Drop internal ``_val`` live-COM handles + neutralize any stray object.

    ``_capture`` stashes the raw COM return under ``_val`` so routes can chain;
    those proxies are dead by serialization time (doc closed) and stringifying
    a dynamic CDispatch re-invokes it -> "Object is not connected to server".
    """
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if k != "_val"}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--keep-file", action="store_true")
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_sweep_v2.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
