"""W50 PRODUCTION PAE — auto-pierce sweep (offset profile self-anchors).

Exercises the production _create_sweep with auto_pierce wired in: two
INDEPENDENTLY-authored sketches (a circle profile OFFSET 20mm from the path, a
path on a different plane that pierces the profile plane) → the handler
auto-anchors the profile to the path (sgATPIERCE) and the sweep solves. This is
the cure for the 'dummy wrapper' problem: the LLM no longer has to pre-align the
sketches in 3D.

  LEG 1 (happy path): circular profile offset from path → auto_pierce anchors it
    → a real swept body materializes (feature delta + body + volume>0).
  LEG 2 (guardrail): rectangle profile (no arc center) → fail-closed with the
    'circular/arc profiles' message (the v1 scope guardrail), NO body.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/sweep_autopierce_pae.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.mutate import _create_sweep  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "sweep_autopierce_pae.json"


def _name_last_sketch(doc: Any, mod: Any, newname: str) -> str | None:
    last = None
    for f in doc.FeatureManager.GetFeatures(True) or []:
        try:
            tf = typed(f, "IFeature", module=mod)
            if tf.GetTypeName2() in ("ProfileFeature", "Sketch"):
                last = tf
        except Exception:
            continue
    if last is None:
        return None
    try:
        last.Name = newname
        return newname
    except Exception:
        try:
            return last.Name
        except Exception:
            return None


def _build_path(doc: Any, ext: Any, sm: Any, mod: Any) -> str | None:
    """Path line on Top Plane along part-Z, piercing Front (z=0) at the origin."""
    if not ext.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    sm.CreateLine(0.0, -0.005, 0.0, 0.0, 0.060, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _name_last_sketch(doc, mod, "PathSk")


def _build_circle_profile(doc: Any, ext: Any, sm: Any, mod: Any) -> str | None:
    """Circle on Front Plane OFFSET to (20,0) — NOT on the path."""
    if not ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    sm.CreateCircle(0.020, 0.0, 0.0, 0.025, 0.0, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _name_last_sketch(doc, mod, "ProfSk")


def _build_rect_profile(doc: Any, ext: Any, sm: Any, mod: Any) -> str | None:
    """Center rectangle on Front Plane — no arc center (guardrail trigger)."""
    if not ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0):
        return None
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, 0.010, 0.010, 0.0)
    sm.InsertSketch(True)
    doc.ClearSelection2(True)
    return _name_last_sketch(doc, mod, "RectProfSk")


def _body_stats(raw_doc: Any, mod: Any) -> tuple[int, float]:
    try:
        pdoc = typed_qi(raw_doc, "IPartDoc", module=mod)
        bodies = pdoc.GetBodies2(0, True)
    except Exception:
        return 0, 0.0
    nb = len(bodies) if bodies else 0
    vol = 0.0
    for b in bodies or ():
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                vol += float(mp[3]) * 1e9
        except Exception:
            pass
    return nb, round(vol, 1)


def _new_part(sw: Any, mod: Any) -> tuple[Any, Any, Any, Any]:
    template = sw.GetUserPreferenceStringValue(8)
    raw = sw.NewDocument(template, 0, 0.0, 0.0)
    doc = typed(raw, "IModelDoc2", module=mod)
    ext = typed(doc.Extension, "IModelDocExtension", module=mod)
    sm = typed(doc.SketchManager, "ISketchManager", module=mod)
    return raw, doc, ext, sm


def _leg_happy(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "happy_circular_offset", "ok": False}
    raw, doc, ext, sm = _new_part(sw, mod)
    path = _build_path(doc, ext, sm, mod)
    prof = _build_circle_profile(doc, ext, sm, mod)
    r["path"], r["profile"] = path, prof
    if not path or not prof:
        r["error"] = "fixture sketch naming failed"
        return r
    ok, err = _create_sweep(doc, {"type": "sweep"}, {"profile": prof, "path": path})
    r["sweep_ok"], r["sweep_err"] = ok, err
    nb, vol = _body_stats(raw, mod)
    r["bodies"], r["volume_mm3"] = nb, vol
    r["ok"] = bool(ok and nb >= 1 and vol > 0)
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def _leg_guardrail(sw: Any, mod: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"leg": "guardrail_rectangle", "ok": False}
    raw, doc, ext, sm = _new_part(sw, mod)
    path = _build_path(doc, ext, sm, mod)
    prof = _build_rect_profile(doc, ext, sm, mod)
    r["path"], r["profile"] = path, prof
    if not path or not prof:
        r["error"] = "fixture sketch naming failed"
        return r
    ok, err = _create_sweep(doc, {"type": "sweep"}, {"profile": prof, "path": path})
    r["sweep_ok"], r["sweep_err"] = ok, err
    nb, vol = _body_stats(raw, mod)
    r["bodies"] = nb
    # GREEN = fail-closed: NOT ok, an arc/circle message, and NO body.
    r["ok"] = bool((not ok) and err and "circ" in err.lower() and nb == 0)
    r["verdict"] = "GREEN" if r["ok"] else "NO-GO"
    return r


def main() -> int:
    result: dict[str, Any] = {"spike_id": "sweep_autopierce_pae", "legs": {}}
    try:
        pythoncom.CoInitialize()
        mod = wrapper_module()
        sw = get_sw_app()
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        result["legs"]["happy"] = _leg_happy(sw, mod)
        print(
            f"[swp] happy -> {result['legs']['happy'].get('verdict')} "
            f"vol={result['legs']['happy'].get('volume_mm3')}"
        )
        result["legs"]["guardrail"] = _leg_guardrail(sw, mod)
        print(
            f"[swp] guardrail -> {result['legs']['guardrail'].get('verdict')} "
            f"err={result['legs']['guardrail'].get('sweep_err')}"
        )
        result["overall"] = (
            "PASS"
            if all(result["legs"][k].get("ok") for k in result["legs"])
            else "FAIL"
        )
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        result["fatal"] = f"{exc!r}\n{traceback.format_exc()}"
        result["overall"] = "FAIL"
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    _OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
