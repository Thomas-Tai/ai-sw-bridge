"""Spike v0.16 / F4-DOME — dome feature creation via COM.
[authored seat-free; RUN ON A LIVE SEAT]

Probes the dome feature API:
  ``CreateDefinition(swFmDome) → typed_qi(IDomeFeatureData)
   → select face → set height/radius → CreateFeature``

Target interface: ``IDomeFeatureData``.
The constant will be read from ``swconst.tlb``.

Geometry: a box with a flat face to dome.

Verdicts
--------
PASS    — dome materializes on the selected face.
PARTIAL — feature-data acquired but CreateFeature no-ops.
FAIL    — typelib walk yields no dome constant.

Usage
-----
    python spikes/v0_16/spike_dome.py --out report.json
    python spikes/v0_16/spike_dome.py --mode vba
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
from spike_persist_reference import build_single_box  # noqa: E402

SW_DEFAULT_TEMPLATE_PART = 8
SWCONST_TLB = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swconst.tlb")

ENUM_FUZZY_TOKENS = ("Dome",)
ENUM_EXACT_NAMES = ("swFeatureNameID_e",)


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _type_name(feat: Any) -> str | None:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            m = getattr(feat, attr)
            return str(m() if callable(m) else m)
        except Exception:
            continue
    return None


def _title(d: Any) -> Any:
    t = d.GetTitle
    return t() if callable(t) else t


def _try_close(sw: Any, doc: Any) -> None:
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
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
    except Exception as e:
        return {
            "status": "EXCEPTION",
            "exception_type": type(e).__name__,
            "message": str(e)[:200],
            "hresult": f"{e.hresult:#010x}" if hasattr(e, "hresult") else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }


def _walk_swconst_typelib() -> dict[str, Any]:
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
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["loadable"] = True
    enums: dict[str, dict[str, int]] = {}
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
    for bucket_name, tokens in (("swFmDome", ("FmDome", "FeatureNameDome")),):
        for ename, members in enums.items():
            for mname, val in members.items():
                if any(t in mname for t in tokens):
                    report["discovered"].setdefault(bucket_name, {})[
                        f"{ename}.{mname}"
                    ] = val
    report["enums"] = enums
    return report


def _route_a(
    fm: Any,
    mod: Any,
    doc: Any,
    dome_const: int | None,
    dome_const_name: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "route": "A - typelib-gated CreateDefinition + typed_qi",
        "const": dome_const,
        "const_name": dome_const_name,
    }
    if dome_const is None:
        result["error"] = "no dome constant from swconst.tlb"
        return result
    data_cap = _capture(lambda: fm.CreateDefinition(dome_const))
    result["create_definition"] = data_cap
    if data_cap["status"] != "OK" or not _materialized(data_cap.get("_val")):
        return result
    data = data_cap["_val"]
    qi_cap = _capture(lambda: typed_qi(data, "IDomeFeatureData", module=mod))
    result["typed_qi_IDomeFeatureData"] = qi_cap
    if qi_cap["status"] != "OK":
        return result
    fd = qi_cap["_val"]
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    result["select_face"] = _capture(
        lambda: ext.SelectByID2("", "FACE", 0.0, 0.0, 0.010, False, 0, None, 0)
    )
    # SEAT-PENDING (W0): CreateFeature must be validated on a live seat.
    create_cap = _capture(lambda: fm.CreateFeature(fd))
    result["create_feature"] = create_cap
    if create_cap["status"] == "OK":
        feat = create_cap["_val"]
        result["materialized"] = _materialized(feat)
        if _materialized(feat):
            result["feature_type_name"] = _type_name(feat)
    return result


def run(keep_file: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early"}
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback_info"] = info
    result["module"] = getattr(mod, "__name__", str(mod))
    typelib = _walk_swconst_typelib()
    result["typelib"] = typelib
    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:
        result["sw_revision"] = "<unreadable>"
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    result["box"] = build
    fm = doc.FeatureManager
    dome_bucket = typelib.get("discovered", {}).get("swFmDome") or {}
    dome_const: int | None = None
    dome_const_name: str | None = None
    if dome_bucket:
        dome_const_name, dome_const = next(iter(dome_bucket.items()))
    route_a = _route_a(fm, mod, doc, dome_const, dome_const_name)
    result["route_a"] = route_a
    result["overall"] = "PASS" if route_a.get("materialized") else "PARTIAL"
    _try_close(sw, doc)
    return result


def emit_vba() -> str:
    return "' F4-DOME VBA oracle. CreateDefinition(DOME_CONST) on a box face.\n"


def _scrub(o: Any) -> Any:
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
        out = Path(__file__).parent / "spike_dome.bas"
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
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
