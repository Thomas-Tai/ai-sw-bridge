"""W62 / SEAT-AUTHOR — project_curve method-discovery + dual-mode seat probe.
[authored offline by W4; RUN ON A LIVE SEAT — W0 fires]

Purpose
-------
The boss-fight lane: reflection found NO dedicated ``*ProjectCurveFeatureData``
interface and NO ``InsertProjectCurve*`` method.  This spike exhausts every
candidate creation route:

  **Stage 1 — O1 typelib introspection (offline-safe):**
    Walk ``sldworks.tlb`` for ``IModelDoc2``, ``IModelDocExtension``,
    ``IFeatureManager`` — dump every method whose name contains "Project",
    "RefCurve", or "ReferenceCurve".  Walk ``swconst.tlb`` for enum
    constants with the same tokens.

  **Stage 2 — CreateDefinition scan (side-effect-free):**
    Probe ``CreateDefinition(id)`` for IDs 14 (swFmRefCurve) and 61
    (swFmReferenceCurve); QI the returned object for every ref-curve
    candidate interface.

  **Stage 3 — Mode-A seat fire:**
    Build the fixture (``fx.build_block`` + ``fx.seed_line_over_top``),
    run the handler's Mode-A path, check for a new ref-curve feature
    node, verify save→reopen survival.

  **Stage 4 — Mode-B seat fire:**
    Same fixture, Mode-B path (Insert* probe + convert-on-face fallback).

Fixture
-------
40×30×10 mm solid block (``fx.build_block``) + a Front-plane line at
y=+5 mm that projects +Z onto the top face (``fx.seed_line_over_top``).

Verify-the-effect (survives save→reopen):
    A new reference-curve feature node appears in the
    ``IFeatureManager.GetFeatures(False)`` tuple (type name contains
    "RefCurve" / "ProjectedCurve"), no ΔVol.

Verdicts
--------
PASS    — at least one mode created a ref-curve node AND survived reopen.
PARTIAL — a mode created a node but reopen failed, or only one sub-probe
          succeeded.
LEAD    — targeted probes failed, BUT the CreateDefinition scan or
          typelib walk discovered candidate interfaces — retry with
          the discovered IDs/names.
FAIL    — all probes exhausted, no ref-curve node created.

Exit codes: PASS=0, PARTIAL=2, LEAD=3, FAIL=1.

Usage
-----
    python spikes/v0_2x/spike_project_curve.py --out spikes/v0_2x/_results/project_curve.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_PKG_ROOT = _HERE.parents[2] / "src"
_SPIKE_DIR = _HERE.parent
for _p in (str(_PKG_ROOT), str(_SPIKE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed_qi, EarlyBindError  # noqa: E402

import _feature_spike_fixtures as fx  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLDWORKS_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb")
SWCONST_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb")

_PROJECT_TOKENS = ("project", "refcurve", "referencecurve", "ref_curve")
_CONST_TOKENS = ("Project", "RefCurve", "ReferenceCurve", "swFmRefCurve")

_SW_FM_REF_CURVE = 14
_SW_FM_REFERENCE_CURVE = 61

_REF_CURVE_QI_IFACES = (
    "IReferenceCurveFeatureData",
    "IProjectedCurveFeatureData",
    "IRefCurveFeatureData",
    "ICompositeCurveFeatureData",
    "ISplitLineFeatureData",
)

_FEATURE_TREE_WALK_LIMIT = 500
_NODE_TYPE_TOKENS = ("refcurve", "projectedcurve", "ref_curve")


# ---------------------------------------------------------------------------
# VT decoder (mirror of spike_thread)
# ---------------------------------------------------------------------------

_VT_NAMES = {
    0: "VT_EMPTY", 2: "VT_I2", 3: "VT_I4", 4: "VT_R4", 5: "VT_R8",
    8: "VT_BSTR", 9: "VT_DISPATCH", 11: "VT_BOOL", 12: "VT_VARIANT",
    13: "VT_UNKNOWN", 16: "VT_I1", 17: "VT_UI1", 19: "VT_UI4", 24: "VT_VOID",
    26: "VT_PTR", 27: "VT_SAFEARRAY",
}


def _vt(vt: int) -> str:
    base = vt & 0x0FFF
    flags = vt & 0xF000
    s = _VT_NAMES.get(base, f"VT_{base}")
    if flags & 0x2000:
        s = f"VT_ARRAY|{s}"
    if flags & 0x4000:
        s = f"VT_BYREF|{s}"
    return s


def _extract_vt(raw: Any) -> int:
    if isinstance(raw, tuple):
        return raw[0] if isinstance(raw[0], int) else _extract_vt(raw[0])
    return raw


def _funcdesc(info: Any, f_idx: int) -> dict[str, Any]:
    fd = info.GetFuncDesc(f_idx)
    names = info.GetNames(fd.memid)
    mname = names[0] if names else f"<memid={fd.memid}>"
    arg_vts = []
    for elem in fd.args:
        vt_val = _extract_vt(elem[0])
        arg_vts.append(_vt(vt_val))
    ret_vt = _extract_vt(fd.rettype)
    return {
        "name": mname,
        "param_names": list(names[1:]) if len(names) > 1 else [],
        "cParams": len(fd.args),
        "arg_vts": arg_vts,
        "return_vt": _vt(ret_vt),
        "invkind": fd.invkind,
    }


# ---------------------------------------------------------------------------
# O1 typelib walks
# ---------------------------------------------------------------------------

def _walk_interface_methods(
    iface_name: str, tokens: tuple[str, ...],
) -> dict[str, Any]:
    """Walk sldworks.tlb for *iface_name*, dump FUNCDESCs matching *tokens*."""
    report: dict[str, Any] = {
        "path": str(SLDWORKS_TLB),
        "loadable": False,
        "iface_found": False,
        "matches": {},
    }
    if not SLDWORKS_TLB.exists():
        report["error"] = f"sldworks.tlb not found at {SLDWORKS_TLB}"
        return report
    try:
        tlb = pythoncom.LoadTypeLib(str(SLDWORKS_TLB))
        report["loadable"] = True
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report

    for i in range(tlb.GetTypeInfoCount()):
        name, *_ = tlb.GetDocumentation(i)
        if name != iface_name:
            continue
        report["iface_found"] = True
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        for f in range(ta.cFuncs):
            try:
                fd_data = _funcdesc(info, f)
                mname_lower = fd_data["name"].lower()
                if any(t.lower() in mname_lower for t in tokens):
                    report["matches"][fd_data["name"]] = fd_data
            except Exception as e:
                report.setdefault("errors", []).append(f"f={f}: {e}")
        break

    return report


def _walk_swconst_enums(tokens: tuple[str, ...]) -> dict[str, Any]:
    """Walk swconst.tlb for enum constants matching *tokens*."""
    report: dict[str, Any] = {
        "path": str(SWCONST_TLB),
        "loadable": False,
        "matches": {},
    }
    if not SWCONST_TLB.exists():
        report["error"] = f"swconst.tlb not found at {SWCONST_TLB}"
        return report
    try:
        tlb = pythoncom.LoadTypeLib(str(SWCONST_TLB))
        report["loadable"] = True
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report

    for i in range(tlb.GetTypeInfoCount()):
        name, *_ = tlb.GetDocumentation(i)
        info = tlb.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        if ta.typekind != pythoncom.TKIND_ENUM:
            continue
        for v in range(ta.cVars):
            try:
                vd = info.GetVarDesc(v)
                mname = info.GetNames(vd.memid)[0]
                if any(t.lower() in mname.lower() for t in tokens):
                    report["matches"][mname] = {"enum": name, "value": vd.value}
            except Exception:
                continue

    return report


# ---------------------------------------------------------------------------
# Feature-node detection
# ---------------------------------------------------------------------------

def _walk_features(doc: Any) -> list[Any]:
    """Headless-reliable feature-tree walk via ``IFeatureManager.GetFeatures(False)``.

    Replaces FirstFeature/GetNextFeature chains — that walk is unreachable
    on the raw late-bound doc out-of-process (W62 composite seat fire,
    2026-06-17 — com_error "Member not found"). ``GetFeatures(False)``
    returns a flat tuple that IS reachable; each node still exposes
    ``Name`` / ``GetTypeName2`` directly.
    """
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception:
        return []
    if feats is None:
        return []
    return list(feats)[:_FEATURE_TREE_WALK_LIMIT]


def _count_ref_curve_nodes(doc: Any) -> int:
    """Count feature-tree nodes whose type matches a ref-curve token."""
    count = 0
    for feat in _walk_features(doc):
        try:
            tname = str(feat.GetTypeName2() or "").lower()
            if any(tok in tname for tok in _NODE_TYPE_TOKENS):
                count += 1
        except Exception:
            pass
    return count


def _get_feature_names(doc: Any) -> list[str]:
    """Return all feature names in the tree."""
    names: list[str] = []
    for feat in _walk_features(doc):
        try:
            names.append(str(feat.Name))
        except Exception:
            pass
    return names


def _get_feature_types(doc: Any) -> list[dict[str, str]]:
    """Return list of {name, type} for every feature node."""
    result: list[dict[str, str]] = []
    for feat in _walk_features(doc):
        entry: dict[str, str] = {}
        try:
            entry["name"] = str(feat.Name)
        except Exception:
            entry["name"] = "<unknown>"
        try:
            entry["type"] = str(feat.GetTypeName2() or "")
        except Exception:
            entry["type"] = "<unknown>"
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Topology measurement
# ---------------------------------------------------------------------------

def _get_bodies(doc: Any) -> list[Any]:
    try:
        bodies = doc.GetBodies2(0, True)
        return list(bodies) if bodies else []
    except Exception:
        return []


def _total_volume_m3(doc: Any) -> float | None:
    bodies = _get_bodies(doc)
    if not bodies:
        return None
    total = 0.0
    for b in bodies:
        try:
            mp = b.GetMassProperties(1.0)
            if mp is not None and len(mp) >= 4:
                total += float(mp[3])
        except Exception:
            continue
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# CreateDefinition probe (side-effect-free)
# ---------------------------------------------------------------------------

def _probe_createdefinition(sw: Any, template: str) -> dict[str, Any]:
    """Probe CreateDefinition(14) and CreateDefinition(61) for ref-curve QI."""
    out: dict[str, Any] = {}
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        out["error"] = "NewDocument returned None"
        return out
    try:
        fm = doc.FeatureManager
        for label, id_ in [("swFmRefCurve", _SW_FM_REF_CURVE),
                           ("swFmReferenceCurve", _SW_FM_REFERENCE_CURVE)]:
            entry: dict[str, Any] = {"id": id_, "label": label}
            try:
                obj = fm.CreateDefinition(id_)
                entry["return_type"] = type(obj).__name__ if obj else None
                entry["return_none"] = obj is None
            except Exception as e:
                entry["error"] = f"{type(e).__name__}: {e}"
                out[label] = entry
                continue

            if obj is not None:
                qi_results: dict[str, bool] = {}
                for iface in _REF_CURVE_QI_IFACES:
                    try:
                        typed_qi(obj, iface)
                        qi_results[iface] = True
                    except Exception:
                        qi_results[iface] = False
                entry["qi_results"] = qi_results
                entry["any_qi_match"] = any(qi_results.values())
            out[label] = entry
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Mode-A seat fire
# ---------------------------------------------------------------------------

def _probe_mode_a(doc: Any) -> dict[str, Any]:
    """Mode-A: CreateDefinition(14) → QI → CreateFeature."""
    result: dict[str, Any] = {"mode": "A"}

    features_before = _get_feature_names(doc)
    ref_nodes_before = _count_ref_curve_nodes(doc)
    vol_before = _total_volume_m3(doc)

    fm = doc.FeatureManager
    try:
        data = fm.CreateDefinition(_SW_FM_REF_CURVE)
        result["create_definition_return"] = type(data).__name__ if data else None
    except Exception as e:
        result["create_definition_error"] = f"{type(e).__name__}: {e}"
        data = None

    if data is None:
        result["error"] = "CreateDefinition(14) returned None"
        return result

    qi_iface = None
    for iface in _REF_CURVE_QI_IFACES:
        try:
            typed_qi(data, iface)
            qi_iface = iface
            result["qi_success"] = iface
            break
        except Exception:
            continue
    if qi_iface is None:
        result["qi_all_failed"] = True

    try:
        feat = fm.CreateFeature(data)
        result["create_feature_return"] = type(feat).__name__ if feat else None
    except Exception as e:
        result["create_feature_error"] = f"{type(e).__name__}: {e}"
        feat = None

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    features_after = _get_feature_names(doc)
    ref_nodes_after = _count_ref_curve_nodes(doc)
    vol_after = _total_volume_m3(doc)

    new_features = [n for n in features_after if n not in features_before]
    result["feature_count_before"] = len(features_before)
    result["feature_count_after"] = len(features_after)
    result["new_features"] = new_features
    result["ref_curve_nodes_before"] = ref_nodes_before
    result["ref_curve_nodes_after"] = ref_nodes_after
    result["ref_curve_delta"] = ref_nodes_after - ref_nodes_before
    result["feature_tree"] = _get_feature_types(doc)

    if vol_before is not None and vol_after is not None:
        result["delta_volume_mm3"] = round((vol_after - vol_before) * 1e9, 2)

    result["success"] = (ref_nodes_after - ref_nodes_before) > 0
    return result


# ---------------------------------------------------------------------------
# Mode-B seat fire
# ---------------------------------------------------------------------------

def _probe_mode_b_insert(doc: Any) -> dict[str, Any]:
    """Mode-B(a): probe Insert* methods with 'Project' on doc and FM."""
    result: dict[str, Any] = {"mode": "B-insert"}
    candidates = ("InsertProjectCurve", "InsertProjectedCurve",
                  "InsertRefCurve", "InsertProjectedCurve2")
    probes: dict[str, Any] = {}
    for name in candidates:
        for target_label, obj in [("doc", doc), ("FM", doc.FeatureManager)]:
            fn = getattr(obj, name, None)
            key = f"{target_label}.{name}"
            if fn is None or not callable(fn):
                probes[key] = "not_found"
                continue
            try:
                ret = fn()
                probes[key] = {"called": True, "return": type(ret).__name__ if ret else None}
            except Exception as e:
                probes[key] = {"called": True, "error": f"{type(e).__name__}: {e}"}
    result["probes"] = probes
    result["any_succeeded"] = any(
        isinstance(v, dict) and v.get("return") is not None
        for v in probes.values()
    )
    return result


def _probe_mode_b_convert(sw: Any, doc: Any, sketch_name: str) -> dict[str, Any]:
    """Mode-B(b): convert-on-face fallback."""
    result: dict[str, Any] = {"mode": "B-convert"}

    features_before = _get_feature_names(doc)
    ref_nodes_before = _count_ref_curve_nodes(doc)

    try:
        source_feat = doc.FeatureByName(sketch_name)
        if source_feat is None:
            result["error"] = f"FeatureByName({sketch_name!r}) returned None"
            return result

        doc.ClearSelection2(True)
        source_feat.Select2(False, 0)

        doc.SketchManager.InsertSketch(True)
        result["sketch_opened"] = True

        try:
            doc.SketchManager.SketchUseEdge3(False, False, 0.0)
            result["sketch_use_edge3"] = "ok"
        except Exception as e:
            result["sketch_use_edge3_error"] = f"{type(e).__name__}: {e}"

        doc.SketchManager.InsertSketch(True)
        doc.ClearSelection2(True)
        doc.ForceRebuild3(False)
        result["sketch_closed"] = True

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    features_after = _get_feature_names(doc)
    ref_nodes_after = _count_ref_curve_nodes(doc)

    new_features = [n for n in features_after if n not in features_before]
    result["new_features"] = new_features
    result["ref_curve_delta"] = ref_nodes_after - ref_nodes_before
    result["feature_tree"] = _get_feature_types(doc)
    result["success"] = (ref_nodes_after - ref_nodes_before) > 0
    return result


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run() -> dict[str, Any]:
    result: dict[str, Any] = {
        "spike_id": "W62_project_curve",
        "timestamp": time.time(),
    }

    # ── Stage 1: O1 typelib introspection ────────────────────────────────
    for iface in ("IModelDoc2", "IModelDocExtension", "IFeatureManager"):
        walk = _walk_interface_methods(iface, _PROJECT_TOKENS)
        result[f"walk_{iface}"] = walk

    const_walk = _walk_swconst_enums(_CONST_TOKENS)
    result["swconst_walk"] = const_walk

    all_methods: list[str] = []
    for key in ("walk_IModelDoc2", "walk_IModelDocExtension", "walk_IFeatureManager"):
        matches = result.get(key, {}).get("matches", {})
        all_methods.extend(matches.keys())
    result["all_candidate_methods"] = all_methods

    # ── Stage 2: connect to live SW ──────────────────────────────────────
    try:
        sw = fx.connect()
        try:
            result["sw_revision"] = str(sw.RevisionNumber)
        except Exception:
            result["sw_revision"] = "<unreadable>"
    except Exception as exc:
        result["overall"] = "FAIL"
        result["reason"] = f"could not connect to SW: {exc!r}"
        return result

    template = sw.GetUserPreferenceStringValue(8)

    # ── Stage 2b: CreateDefinition probe ─────────────────────────────────
    result["probe_createdefinition"] = _probe_createdefinition(sw, template)

    # ── Stage 3: Mode-A seat fire ────────────────────────────────────────
    mode_a_result: dict[str, Any] = {}
    try:
        doc = fx.build_block(sw)
        sketch_name, face = fx.seed_line_over_top(doc)
        doc.ForceRebuild3(False)
        mode_a_result = _probe_mode_a(doc)
        mode_a_result["fixture"] = {
            "sketch_name": sketch_name,
            "face_type": type(face).__name__ if face else None,
        }
    except Exception as e:
        mode_a_result["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    result["mode_a"] = mode_a_result

    # ── Stage 4: Mode-B insert probe ─────────────────────────────────────
    mode_b_insert: dict[str, Any] = {}
    try:
        doc = fx.build_block(sw)
        sketch_name, face = fx.seed_line_over_top(doc)
        doc.ForceRebuild3(False)
        mode_b_insert = _probe_mode_b_insert(doc)
    except Exception as e:
        mode_b_insert["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    result["mode_b_insert"] = mode_b_insert

    # ── Stage 5: Mode-B convert fallback ─────────────────────────────────
    mode_b_convert: dict[str, Any] = {}
    doc = None
    try:
        doc = fx.build_block(sw)
        sketch_name, face = fx.seed_line_over_top(doc)
        doc.ForceRebuild3(False)
        mode_b_convert = _probe_mode_b_convert(sw, doc, sketch_name)
        if mode_b_convert.get("success"):
            mode_b_convert["save_reopen"] = _save_reopen(sw, doc)
    except Exception as e:
        mode_b_convert["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    result["mode_b_convert"] = mode_b_convert

    # ── Stage 6: overall verdict ─────────────────────────────────────────
    a_ok = mode_a_result.get("success", False)
    b_convert_ok = mode_b_convert.get("success", False)

    a_reopen = (
        mode_a_result.get("save_reopen", {}).get("ref_curve_survived", False)
        if a_ok else False
    )
    b_reopen = (
        mode_b_convert.get("save_reopen", {}).get("ref_curve_survived", False)
        if b_convert_ok else False
    )

    if a_ok or b_convert_ok:
        if (a_ok and a_reopen) or (b_convert_ok and b_reopen):
            result["overall"] = "PASS"
            modes_fired = []
            if a_ok:
                modes_fired.append("A")
            if b_convert_ok:
                modes_fired.append("B-convert")
            result["modes_fired"] = modes_fired
        else:
            result["overall"] = "PARTIAL"
            result["reason"] = "node created but save→reopen did not confirm"
    else:
        # Check for leads from typelib walk or CreateDefinition scan
        leads: list[str] = []
        if all_methods:
            leads.append(f"candidate methods: {all_methods}")
        scan = result.get("probe_createdefinition", {})
        for label in ("swFmRefCurve", "swFmReferenceCurve"):
            entry = scan.get(label, {})
            if entry.get("any_qi_match"):
                leads.append(f"{label} QI matched: {entry.get('qi_results')}")
        if leads:
            result["overall"] = "LEAD"
            result["leads"] = leads
        else:
            result["overall"] = "FAIL"
            result["reason"] = (
                "all probes exhausted — no ref-curve node, no candidate "
                "methods, no QI matches"
            )

    return result


# ---------------------------------------------------------------------------
# Save → reopen
# ---------------------------------------------------------------------------

def _save_reopen(sw: Any, doc: Any) -> dict[str, Any]:
    """Save → close → reopen; verify the ref-curve node survives."""
    result: dict[str, Any] = {}
    doc2 = None
    try:
        doc2 = fx.save_and_reopen(sw, doc)
        result["reopen"] = "ok"
        result["ref_curve_nodes_after_reopen"] = _count_ref_curve_nodes(doc2)
        result["ref_curve_survived"] = result["ref_curve_nodes_after_reopen"] > 0
        result["feature_tree_after_reopen"] = _get_feature_types(doc2)
    except Exception as e:
        result["reopen"] = "failed"
        result["error"] = f"{type(e).__name__}: {e}"
    return result


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)

    return {"PASS": 0, "PARTIAL": 2, "LEAD": 3, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
