"""
Spike v0.16 / S-VARFIL-QI — does typed_qi + Initialize() reach the
variable-radius fillet interface? (O1, P1.5)
[authored seat-free; RUN ON A LIVE SEAT]

THE retry of S-VARFIL through the *proven* acquisition mechanism. The
v0.15 spike (spikes/v0_15/spike_varfil.py) tried to switch a fillet data
object to variable mode by setting ``FilletType`` on the **late-bound**
``CDispatch`` returned by ``CreateDefinition`` — and died with
``AttributeError: Property '<unknown>.FilletType' can not be set``
(spikes/v0_15/_results/varfil.json). That is the late-bind ``[unknown]``
wall, not an API gap.

Since then two things were learned and shipped:

  1. ``com.earlybind.typed_qi`` — QueryInterface-by-IID — *soundly acquires
     and identifies* feature-data objects (S-QI-FEATUREDATA = DISCRIMINATING,
     spikes/v0_15/_results/qi_featuredata.json).
  2. The production constant-radius fillet (``mutate._create_fillet``) sets
     the fillet **type via a METHOD on the typed interface** —
     ``fd.Initialize(swConstRadiusFillet=0)`` — *not* a ``FilletType=``
     property. That is what makes the constant path work.

The discriminating datum from qi_featuredata.json: a freshly
``CreateDefinition(swFmFillet)``-d object QI-supports
``ISimpleFilletFeatureData2`` but **rejects** ``IVariableFilletFeatureData2``
with ``E_NOINTERFACE`` *before any Initialize*.

THE HYPOTHESIS THIS SPIKE FALSIFIES
-----------------------------------
Calling ``Initialize(<variable-radius type>)`` on the typed_qi'd
``ISimpleFilletFeatureData2`` *morphs* the underlying COM object so that a
subsequent ``QueryInterface(IVariableFilletFeatureData2)`` now SUCCEEDS —
i.e. the variable interface is reachable via the same
``CreateDefinition → typed_qi → Initialize`` pipeline that already ships for
constant fillets, with only the type argument changed.

If true (PASS), the Phase-1 variable-radius fillet handler (P1.5) is a
small extension of the proven constant handler, no new acquisition
machinery. If the morph happens but the per-edge radius SAFEARRAY or
``CreateFeature`` fails (PARTIAL), the wall is marshaling — run ``--mode
vba`` to confirm and signal Route-C. If ``Initialize(var)`` runs but the QI
still returns ``E_NOINTERFACE`` (MORPH-FALSE), the hypothesis is wrong and
variable fillets need a different acquisition path (documented below).

swFilletType_e
--------------
Constant radius = 0 is proven in production (``_SW_CONST_RADIUS_FILLET``).
The variable-radius sibling value is expected to be 1; this spike probes a
small candidate set {1, 2, 3} via Initialize and keeps the first value that
makes ``IVariableFilletFeatureData2`` QI-succeed, so the exact enum is
discovered empirically rather than guessed.

Verdict
-------
PASS         : Initialize(var) morphs the object so QI(IVariableFilletFeatureData2)
               succeeds AND per-edge radii set AND CreateFeature materializes a
               variable-radius fillet → build the P1.5 handler as a thin
               extension of _create_fillet.
PARTIAL-MARSHAL : morph succeeds (QI reaches the variable interface) but the
               radius SAFEARRAY write or CreateFeature fails → marshaler wall;
               run --mode vba. If VBA PASSes → Route-C signal; if VBA also
               fails → API genuinely refuses the array form.
MORPH-FALSE  : Initialize(var) runs cleanly but QI(IVariableFilletFeatureData2)
               still E_NOINTERFACE for every candidate type → the morph
               hypothesis is wrong; variable fillet is not reachable by
               re-typing a swFmFillet definition. Next probe: a distinct
               CreateDefinition constant, or the legacy
               IFeatureManager.InsertFeatureFillet path. (Constant fillet is
               unaffected — it already ships.)
FAIL         : typed_qi(ISimpleFilletFeatureData2) itself fails or the box
               does not build → a regression in the proven pipeline, not a
               variable-fillet finding.

Prereq: SOLIDWORKS running. Creates its OWN part (NewDocument) with a
20×20×10 mm box; never touches the user's open documents; closes its own
doc WITHOUT saving.

Usage
-----
    python spikes/v0_16/spike_varfil_qi.py --out report.json
    python spikes/v0_16/spike_varfil_qi.py --mode vba
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
SW_DOC_PART = 1

# Proven in production (mutate.py) and prior spikes.
SW_FM_FILLET = 1
SW_CONST_RADIUS_FILLET = 0  # swFilletType_e constant radius (control)

# swFilletType_e variable-radius candidates — probed in order; the first
# that makes IVariableFilletFeatureData2 QI-succeed wins. 1 is the expected
# value (constant is 0); 2/3 are fallbacks in case the enum differs.
VAR_RADIUS_TYPE_CANDIDATES = (1, 2, 3)

SIMPLE_IFACE = "ISimpleFilletFeatureData2"
VAR_IFACE = "IVariableFilletFeatureData2"

# Box geometry (metres). 20×20×10 mm; the fillet target is the front-bottom
# edge whose mid-point is (0, -0.010, 0).
BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010
EDGE_X_M, EDGE_Y_M, EDGE_Z_M = 0.0, -BOX_H_M / 2, 0.0

# Per-vertex radii for the variable fillet (start 2 mm, end 4 mm).
VARRAD_START_M = 0.002
VARRAD_END_M = 0.004


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
    """Run *fn*, return (json-safe record, raw value).

    The raw value is kept out of the record so COM objects never reach
    ``json.dumps``.
    """
    t0 = time.perf_counter()
    try:
        val = fn()
        rec = {
            "status": "OK",
            "type": _tag(val),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
        return rec, val
    except Exception as e:  # noqa: BLE001
        rec = {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
        return rec, None


def _is_e_nointerface(rec: dict[str, Any]) -> bool:
    """typed_qi raises EarlyBindError carrying the 'E_NOINTERFACE' text on a
    clean QI rejection — the 'object is not this interface' signal."""
    return "E_NOINTERFACE" in (rec.get("message") or "")


# ---------------------------------------------------------------------------
# Box fixture (own document; mirrors spike_varfil._build_box)
# ---------------------------------------------------------------------------

def _build_box(doc: Any) -> dict[str, Any]:
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
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
        feat = fm.FeatureExtrusion2(*base_args, False)  # 23-arg
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base_args)  # 22-arg fallback
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    try:
        doc.EditRebuild3
    except Exception:  # noqa: BLE001
        pass
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _select_target_edge(doc: Any) -> dict[str, Any]:
    try:
        doc.ClearSelection2(True)
    except Exception:  # noqa: BLE001
        pass
    rec, _ = _capture(
        lambda: doc.SelectByID("", "EDGE", EDGE_X_M, EDGE_Y_M, EDGE_Z_M)
    )
    return rec


# ---------------------------------------------------------------------------
# The morph probe — the heart of the spike
# ---------------------------------------------------------------------------

def _probe_morph(fm: Any, mod: Any, fillet_type: int) -> dict[str, Any]:
    """For one candidate swFilletType_e value: CreateDefinition → typed_qi
    ISimpleFilletFeatureData2 → Initialize(type) → re-QI IVariableFilletFeatureData2.

    Returns a record including ``var_iface_reachable`` (the discriminating
    bit) and, on reach, keeps the morphed data object under ``_data`` for the
    caller to drive CreateFeature.
    """
    out: dict[str, Any] = {"fillet_type": fillet_type}

    def_rec, data = _capture(lambda: fm.CreateDefinition(SW_FM_FILLET))
    out["create_definition"] = def_rec
    if data is None:
        out["var_iface_reachable"] = False
        return out

    simple_rec, simple = _capture(lambda: typed_qi(data, SIMPLE_IFACE, module=mod))
    out["typed_qi_simple"] = simple_rec
    if simple is None:
        out["var_iface_reachable"] = False
        return out

    init_rec, _ = _capture(lambda: simple.Initialize(fillet_type))
    out["initialize"] = init_rec

    # The discriminating QI: did Initialize(type) morph the object so it now
    # answers the variable interface?
    var_rec, var = _capture(lambda: typed_qi(data, VAR_IFACE, module=mod))
    out["typed_qi_variable"] = var_rec
    reachable = var is not None
    out["var_iface_reachable"] = reachable
    if reachable:
        out["_data"] = data  # popped before serialization
        out["_var"] = var
    elif _is_e_nointerface(var_rec):
        out["note"] = "Initialize ran but object still rejects the variable IID (E_NOINTERFACE)"
    return out


def _probe_set_radii(var: Any) -> dict[str, Any]:
    """Best-effort: set per-vertex radii on the early-bound variable interface.

    Probes the same forms the v0.15 spike used, but now on the QI'd typed
    object rather than the late-bound CDispatch. Also sets a default radius
    (mirrors the constant path's ``DefaultRadius``).
    """
    out: dict[str, Any] = {}

    dr_rec, _ = _capture(lambda: setattr(var, "DefaultRadius", VARRAD_START_M))
    out["default_radius_set"] = dr_rec

    array = (VARRAD_START_M, VARRAD_END_M)
    forms = (
        ("method_SetVariableRadiusParameters", lambda: var.SetVariableRadiusParameters(array)),
        ("prop_VariableRadiusParameters", lambda: setattr(var, "VariableRadiusParameters", array)),
    )
    attempts = []
    any_ok = False
    for name, fn in forms:
        rec, _ = _capture(fn)
        rec["form"] = name
        attempts.append(rec)
        if rec["status"] == "OK":
            any_ok = True
            break  # first working write wins; don't double-set
    out["write_attempts"] = attempts
    out["any_write_ok"] = any_ok
    return out


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

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

    try:
        build = _build_box(doc)
        result["build"] = build
        if not build.get("built"):
            return {**result, "overall": "FAIL", "reason": "box did not build"}

        fm = doc.FeatureManager

        # --- Control: prove the constant pipeline is intact on this seat. ----
        ctrl_def_rec, ctrl_data = _capture(lambda: fm.CreateDefinition(SW_FM_FILLET))
        ctrl_simple_rec, ctrl_simple = (
            _capture(lambda: typed_qi(ctrl_data, SIMPLE_IFACE, module=mod))
            if ctrl_data is not None
            else ({"status": "SKIPPED"}, None)
        )
        result["control"] = {
            "create_definition": ctrl_def_rec,
            "typed_qi_simple": ctrl_simple_rec,
        }
        if ctrl_simple is None:
            # The proven acquisition itself is broken here — not a varfil finding.
            return {
                **result,
                "overall": "FAIL",
                "reason": (
                    f"typed_qi({SIMPLE_IFACE}) failed on this seat — the proven "
                    "constant-fillet acquisition is broken; fix that before "
                    "interpreting the variable-fillet probe"
                ),
            }

        # --- Morph probe across candidate variable-radius type values. -------
        morph_probes: list[dict[str, Any]] = []
        winner: dict[str, Any] | None = None
        for ft in VAR_RADIUS_TYPE_CANDIDATES:
            probe = _probe_morph(fm, mod, ft)
            morph_probes.append(probe)
            if probe.get("var_iface_reachable"):
                winner = probe
                break
        # strip COM objects before serialization
        var_obj = winner.pop("_var", None) if winner else None
        win_data = winner.pop("_data", None) if winner else None
        result["morph_probes"] = morph_probes
        result["morph_succeeded"] = winner is not None
        result["winning_fillet_type"] = winner["fillet_type"] if winner else None

        create_rec: dict[str, Any] = {}
        set_radii_rec: dict[str, Any] = {}
        if winner is not None and var_obj is not None:
            result["edge_selection"] = _select_target_edge(doc)
            set_radii_rec = _probe_set_radii(var_obj)
            result["set_radii"] = set_radii_rec
            feat_rec, feat = _capture(lambda: fm.CreateFeature(win_data))
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
    if winner is None:
        # Initialize ran for every candidate but QI never reached the variable
        # interface → the morph hypothesis is false.
        overall = "MORPH-FALSE"
        interp = (
            "Initialize(<candidate>) ran but QI(IVariableFilletFeatureData2) "
            "stayed E_NOINTERFACE for every probed type → re-typing a swFmFillet "
            "definition does NOT expose the variable interface. Next: probe a "
            "distinct CreateDefinition constant or the legacy "
            "IFeatureManager.InsertFeatureFillet path. Constant fillet is "
            "unaffected (already ships)."
        )
    elif create_rec.get("materialized"):
        overall = "PASS"
        interp = (
            f"Initialize({result['winning_fillet_type']}) morphs the object so "
            "QI(IVariableFilletFeatureData2) succeeds, radii set, and CreateFeature "
            "materializes a variable-radius fillet → build the P1.5 handler as a "
            "thin extension of mutate._create_fillet (swap Initialize arg + set radii)."
        )
    else:
        overall = "PARTIAL-MARSHAL"
        interp = (
            "MORPH PROVEN — typed_qi + Initialize reaches IVariableFilletFeatureData2 "
            "(the v0.15 late-bind wall is cleared) — but the radius SAFEARRAY write "
            "or CreateFeature did not materialize. Run --mode vba: if VBA PASSes the "
            "round-trip, the pywin32 marshaler is the wall → Route-C signal; if VBA "
            "also fails, the API refuses the array form out-of-process."
        )

    result["overall"] = overall
    result["interpretation"] = interp
    return result


# ---------------------------------------------------------------------------
# VBA oracle (early binding)
# ---------------------------------------------------------------------------

def emit_vba() -> str:
    return r"""' Spike v0.16 S-VARFIL-QI VBA oracle.
' Paste into a Part module with a 20x20x10 mm box on the Front Plane, press F5.
' Tests whether Initialize(swFilletTypeVariable) yields a working variable-
' radius fillet in EARLY binding. If this PASSes but the Python spike is
' PARTIAL-MARSHAL, the pywin32 marshaler (not the SW API) is the wall.
Option Explicit
Sub ProbeVarFilletQI()
    Dim swApp As SldWorks.SldWorks
    Dim Part  As SldWorks.ModelDoc2
    Dim fm    As SldWorks.FeatureManager
    Dim fd    As SldWorks.SimpleFilletFeatureData2
    Dim feat  As SldWorks.Feature
    Dim radii(1) As Double
    Dim msg   As String

    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set fm = Part.FeatureManager

    Set fd = fm.CreateDefinition(swFmFillet)            ' swFmFillet = 1
    If fd Is Nothing Then MsgBox "CreateDefinition returned Nothing": Exit Sub

    fd.Initialize swFilletTypeVariable                   ' the morph under test
    fd.DefaultRadius = 0.002

    ' Select the front-bottom edge, then set per-vertex radii.
    Part.ClearSelection2 True
    Part.SelectByID2 "", "EDGE", 0, -0.01, 0, False, 0, Nothing, 0
    radii(0) = 0.002
    radii(1) = 0.004
    fd.SetVariableRadiusParameters radii

    Set feat = fm.CreateFeature(fd)
    If feat Is Nothing Then
        msg = "CreateFeature: NOTHING"
    Else
        msg = "CreateFeature OK -> " & feat.Name & " / " & feat.GetTypeName2
    End If
    MsgBox "S-VARFIL-QI VBA oracle:" & Chr(10) & msg
End Sub
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["com", "vba"], default="com")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_varfil_qi.bas"
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

    # PASS=0, marshaler/morph-false signals=2, hard fail=1.
    return {"PASS": 0, "PARTIAL-MARSHAL": 2, "MORPH-FALSE": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
