"""W71 THROWAWAY probe — the Zero-Code Linked-Property hypothesis (LIVE seat).

Hypothesis: linked custom properties are just text values with link syntax;
the shipped Add3/Get4 path may resolve them natively with no new COM code.

``ICustomPropertyManager.Get4(name, useCached)`` returns a 3-tuple
``(resolvedFlag, rawValue, resolvedValue)``. The 3rd element is where an
EVALUATED link surfaces. If we Add3 a value of ``"D1@Boss-Extrude1"`` (a
dimension link) and on reopen Get4's resolvedValue comes back as the numeric
dimension (≠ the raw link text), the kernel resolved it zero-code.

We probe several candidate syntaxes and report, per syntax:
  raw   = Get4 element[1] (what SW stored)
  resolved = Get4 element[2] (what SW evaluated)
  ZERO_CODE_RESOLVES = resolved is non-empty AND != raw

Fixture: a 10 mm cube. The blind extrude guarantees a dimension named
``D1@Boss-Extrude1`` (= 10 mm = 0.01 m); the part also has mass under the
default material, so SW-Mass link variants are probed too.

Usage::

    C:/Python314/python.exe spikes/v0_2x/spike_linked_property_probe.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pythoncom

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from _feature_spike_fixtures import _new_part, _select_feature, connect  # noqa: E402

RESULTS_PATH = _REPO_ROOT / "spikes" / "v0_2x" / "_results" / "linked_property_probe.json"

_BLIND = 0
_TEXT = 30       # swCustomInfoText
_REPLACE = 1     # swCustomPropertyReplaceValue

_FILENAME = "W71_Link.SLDPRT"


def build_cube(sw: Any, path: str) -> bool:
    doc = _new_part(sw)
    _select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(-0.005, -0.005, 0.0, 0.005, 0.005, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    _select_feature(doc, "Sketch1")
    doc.FeatureManager.FeatureExtrusion2(
        True, False, False, _BLIND, 0,
        0.010, 0.0, False, False, False, False,
        0.0, 0.0, False, False, False, False,
        True, True, True, 0, 0.0, False,
    )
    doc.ClearSelection2(True)
    err = doc.SaveAs3(path, 0, 0)
    sw.CloseAllDocuments(True)
    return err == 0 and os.path.isfile(path)


def run() -> dict[str, Any]:
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module()
    result: dict[str, Any] = {
        "spike": "w71_linked_property_probe",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "probes": [],
    }

    sw = connect()
    tmp = tempfile.mkdtemp(prefix="w71_link_")
    path = os.path.join(tmp, _FILENAME)
    if not build_cube(sw, path):
        result["overall"] = "ERROR"
        result["finding"] = "cube fixture build failed"
        return result

    # Candidate link syntaxes (name -> raw value to Add3).
    candidates = {
        "LinkDimBare": "D1@Boss-Extrude1",
        "LinkDimQuoted": '"D1@Boss-Extrude1"',
        "LinkMassAt": f'"SW-Mass@{_FILENAME}"',
        "LinkMassPrp": '$PRP:"SW-Mass"',
        "PlainControl": "literal-no-link",
    }

    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(path, 1, 1, "", 0, 0)
    model_doc = ret[0] if isinstance(ret, tuple) else ret
    if model_doc is None:
        result["overall"] = "ERROR"
        result["finding"] = "OpenDoc6 for write failed"
        return result

    cpm = typed_qi(
        model_doc.Extension.CustomPropertyManager(""), "ICustomPropertyManager", module=mod
    )
    add_codes = {}
    for name, raw in candidates.items():
        try:
            add_codes[name] = cpm.Add3(name, _TEXT, raw, _REPLACE)
        except Exception as exc:
            add_codes[name] = f"RAISED {exc!r}"
    mdoc2 = typed(model_doc, "IModelDoc2", module=mod)
    mdoc2.SaveAs3(path, 0, 0)
    title = mdoc2.GetTitle
    title = title() if callable(title) else title
    sw.CloseDoc(title)

    # Reopen and read back (resolvedFlag, rawValue, resolvedValue).
    time.sleep(0.3)
    ret = tsw.OpenDoc6(path, 1, 1, "", 0, 0)
    model_doc2 = ret[0] if isinstance(ret, tuple) else ret
    cpm2 = typed_qi(
        model_doc2.Extension.CustomPropertyManager(""), "ICustomPropertyManager", module=mod
    )

    any_resolved = False
    for name, raw in candidates.items():
        entry: dict[str, Any] = {"name": name, "input": raw, "add_code": add_codes.get(name)}
        try:
            tup = cpm2.Get4(name, False)
            # pywin32 returns (resolvedFlag, ValOut, ResolvedValOut)
            entry["get4_raw_tuple"] = [str(x) for x in tup] if isinstance(tup, tuple) else str(tup)
            if isinstance(tup, tuple) and len(tup) >= 3:
                flag, val_out, resolved_out = tup[0], tup[1], tup[2]
                entry["stored_value"] = val_out
                entry["resolved_value"] = resolved_out
                zero_code = (
                    bool(resolved_out)
                    and str(resolved_out) != str(val_out)
                    and name != "PlainControl"
                )
                entry["ZERO_CODE_RESOLVES"] = zero_code
                if zero_code:
                    any_resolved = True
        except Exception as exc:
            entry["get4_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        result["probes"].append(entry)

    mdoc2b = typed(model_doc2, "IModelDoc2", module=mod)
    title2 = mdoc2b.GetTitle
    title2 = title2() if callable(title2) else title2
    sw.CloseDoc(title2)

    result["any_zero_code_resolution"] = any_resolved
    result["overall"] = "RESOLVES" if any_resolved else "NO_RESOLVE"
    resolved_names = [p["name"] for p in result["probes"] if p.get("ZERO_CODE_RESOLVES")]
    result["finding"] = (
        f"zero-code link resolution: {'YES' if any_resolved else 'NO'}; "
        f"resolved={resolved_names}"
    )
    return result


def _scrub(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [_scrub(v) for v in o]
    return o


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        try:
            connect().CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    payload = json.dumps(_scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>")
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}", file=sys.stderr)
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", ""), file=sys.stderr)
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
