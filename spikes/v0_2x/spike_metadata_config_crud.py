"""W71 spike — config-level + delete metadata CRUD isolation witness (LIVE seat).

Proves the v3 metadata upgrade end-to-end through the PRODUCTION
``commit_properties`` path (not a hand-rolled COM probe):

  1. Build a part with TWO configurations (Default + Config_B), save, close.
  2. commit_properties #1 — file-level (configuration absent): PropA = "Global".
  3. commit_properties #2 — config Config_B: PropA = "Local_B", TempProp = "temp".
  4. commit_properties #3 — config Config_B: delete TempProp.
  5. INDEPENDENT reopen + isolation witness:
       * CustomPropertyManager("").Get4("PropA")        == "Global"
       * CustomPropertyManager("Config_B").Get4("PropA") == "Local_B"
       * "TempProp" ABSENT from CustomPropertyManager("Config_B").GetNames()

The crux is ISOLATION: the same property name resolves to DIFFERENT values in
the file-level vs config-level stores simultaneously, and the deletion leaves a
clean absence (not a stale ghost).

Usage::

    C:/Python314/python.exe spikes/v0_2x/spike_metadata_config_crud.py
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

RESULTS_PATH = (
    _REPO_ROOT / "spikes" / "v0_2x" / "_results" / "metadata_config_crud.json"
)

_BLIND = 0


def build_two_config_part(sw: Any, path: str) -> bool:
    """10 mm cube + a second configuration 'Config_B'; saved to *path*, closed."""
    doc = _new_part(sw)
    _select_feature(doc, "Front Plane")
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(-0.005, -0.005, 0.0, 0.005, 0.005, 0.0)
    doc.SketchManager.InsertSketch(True)
    doc.ClearSelection2(True)
    _select_feature(doc, "Sketch1")
    doc.FeatureManager.FeatureExtrusion2(
        True,
        False,
        False,
        _BLIND,
        0,
        0.010,
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
        False,
    )
    doc.ClearSelection2(True)
    # AddConfiguration3(Name, Comment, AlternateName, Options) -> Object
    cfg = doc.AddConfiguration3("Config_B", "", "", 0)
    if cfg is None:
        print("[fixture] AddConfiguration3 returned None", file=sys.stderr)
        return False
    err = doc.SaveAs3(path, 0, 0)
    sw.CloseAllDocuments(True)
    return err == 0 and os.path.isfile(path)


def _read_prop(ext_obj: Any, config_name: str, name: str, mod: Any):
    """(value | None, names_set) for *name* in the *config_name* manager."""
    from ai_sw_bridge.com.earlybind import typed_qi

    cpm = typed_qi(
        ext_obj.CustomPropertyManager(config_name), "ICustomPropertyManager", module=mod
    )
    names = set(cpm.GetNames() or ())
    if name not in names:
        return None, names
    _r, val, _r2 = cpm.Get4(name, False)
    return val, names


def run() -> dict[str, Any]:
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.metadata.lifecycle import commit_properties

    mod = wrapper_module()
    result: dict[str, Any] = {
        "spike": "w71_metadata_config_crud",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "commits": [],
    }

    sw = connect()
    tmp = tempfile.mkdtemp(prefix="w71_meta_")
    path = os.path.join(tmp, "W71_CRUD.SLDPRT")

    if not build_two_config_part(sw, path):
        result["overall"] = "ERROR"
        result["finding"] = "two-config fixture build failed"
        return result
    result["fixture"] = path

    specs = [
        (
            "file_level_write",
            {"kind": "properties", "model": path, "properties": {"PropA": "Global"}},
        ),
        (
            "config_write",
            {
                "kind": "properties",
                "model": path,
                "configuration": "Config_B",
                "properties": {"PropA": "Local_B", "TempProp": "temp"},
            },
        ),
        (
            "config_delete",
            {
                "kind": "properties",
                "model": path,
                "configuration": "Config_B",
                "delete": ["TempProp"],
            },
        ),
    ]
    for label, spec in specs:
        cr = commit_properties(sw, spec, mod=mod)
        result["commits"].append(
            {
                "label": label,
                "ok": cr.get("ok"),
                "summary": cr.get("summary"),
                "errors": cr.get("errors"),
                "props_deleted": cr.get("props_deleted"),
            }
        )
        if not cr.get("ok"):
            result["overall"] = "FAIL"
            result["finding"] = f"commit '{label}' failed: {cr.get('errors')}"
            return result

    # Independent isolation witness — fresh reopen, read both managers.
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(path, 1, 1, "", 0, 0)
    model_doc = ret[0] if isinstance(ret, tuple) else ret
    if model_doc is None:
        result["overall"] = "ERROR"
        result["finding"] = "isolation reopen failed"
        return result
    ext_obj = model_doc.Extension
    file_val, file_names = _read_prop(ext_obj, "", "PropA", mod)
    cfg_val, cfg_names = _read_prop(ext_obj, "Config_B", "PropA", mod)
    temp_val, _ = _read_prop(ext_obj, "Config_B", "TempProp", mod)
    mdoc2 = typed(model_doc, "IModelDoc2", module=mod)
    title = mdoc2.GetTitle
    title = title() if callable(title) else title
    sw.CloseDoc(title)

    result["witness"] = {
        "file_level_PropA": file_val,
        "config_B_PropA": cfg_val,
        "config_B_TempProp": temp_val,
    }

    isolation_ok = file_val == "Global"
    config_ok = cfg_val == "Local_B"
    delete_ok = temp_val is None
    result["checks"] = {
        "file_level_is_Global": isolation_ok,
        "config_is_Local_B": config_ok,
        "temp_deleted_clean": delete_ok,
    }

    if isolation_ok and config_ok and delete_ok:
        result["overall"] = "PASS"
        result["finding"] = (
            f"CRUD isolation proven: file PropA={file_val!r}, "
            f"Config_B PropA={cfg_val!r}, TempProp deleted (got {temp_val!r})"
        )
    else:
        result["overall"] = "FAIL"
        result["finding"] = (
            f"isolation/delete mismatch: file={file_val!r} (want 'Global'), "
            f"config={cfg_val!r} (want 'Local_B'), temp={temp_val!r} (want None)"
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
    payload = json.dumps(
        _scrub(result), indent=2, default=lambda o: f"<{type(o).__name__}>"
    )
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {RESULTS_PATH}", file=sys.stderr)
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", ""), file=sys.stderr)
    print(payload)
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
