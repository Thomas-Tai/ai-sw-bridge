"""
Spike E4 - get a typed wrapper for FeatureManager via gencache to bypass
late-binding marshalling failures on FeatureCut4.

Background: late-binding pywin32 has rejected EVERY FeatureCut4 variant
with PARAMNOTOPTIONAL, despite identical-shape FeatureExtrusion2 args
working. Hypothesis: FeatureCut4's typelib signature is mis-parsed by
pywin32 without a generated stub. Try win32com.client.gencache.EnsureDispatch
on the FeatureManager object specifically -- bypasses the failure mode
of trying to gencache the whole SldWorks.Application.

If we can get a typed FeatureManager, we can call FeatureCut4 against
the stub which knows the correct VARIANT types per arg.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


def _build_box(doc):
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("select Front Plane")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0.0, 0.010, 0.010, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Box"
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box", "SKETCH", 0.0, 0.0, 0.0)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        0,
        0,
        0.005,
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
    if feat is None:
        raise RuntimeError("FeatureExtrusion2 None")
    feat.Name = "Box"


def _hole_sketch(doc) -> str:
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.0, 0.0, 0.005):
        raise RuntimeError("select top face")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.0015, 0.0, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Hole"
    return "SK_Hole"


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"ok": False, "error": "no doc"}))
        return 1
    if doc.GetFeatureCount > 17:
        print(json.dumps({"ok": False, "error": f"not blank ({doc.GetFeatureCount})"}))
        return 1

    try:
        _build_box(doc)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"box: {e!r}"}))
        return 1

    fm_late = doc.FeatureManager

    # Try gencache on the FeatureManager object
    try:
        from win32com.client import gencache, CDispatch

        # gencache.EnsureDispatch on a Dispatch-like proxy doesn't work
        # directly; we use Dispatch with a CLSID + create a typed proxy.
        # The simpler approach: gencache.EnsureModule with FeatureManager's
        # typeinfo. Try the type info route.
        import win32com.client

        # Get the typelib info from the late-bound object
        try:
            tinfo = fm_late._oleobj_.GetTypeInfo()
            typelib = tinfo.GetContainingTypeLib()[0]
            tla = typelib.GetLibAttr()
            print("typelib_iid:", tla[0], "ver:", tla[3], tla[4])
            mod = gencache.EnsureModule(tla[0], tla[1], tla[3], tla[4])
            print("EnsureModule mod:", mod)
        except Exception as e:
            print("typelib probe failed:", repr(e))

        # Try creating a typed FeatureManager directly
        try:
            fm_typed = win32com.client.Dispatch(fm_late._oleobj_)
            typed_class = type(fm_typed).__name__
        except Exception as e:
            fm_typed = None
            typed_class = f"FAIL: {e!r}"
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"gencache outer: {e!r}"}))
        return 1

    # Now select sketch and try FeatureCut4 via typed wrapper
    sk_name = _hole_sketch(doc)
    doc.ClearSelection2(True)
    doc.SelectByID(sk_name, "SKETCH", 0.0, 0.0, 0.0)

    args24 = [
        True,
        False,
        False,
        0,
        0,
        0.005,
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
        False,
        True,
        True,
        True,
        0,
        0.0,
        False,
    ]

    # Try via the typed wrapper if we got one
    typed_result = None
    if fm_typed is not None:
        try:
            f = fm_typed.FeatureCut4(*args24)
            typed_result = {"ok": True, "feature_returned": f is not None}
        except Exception as e:
            typed_result = {"ok": False, "error": repr(e)}

    # Probe: list methods available on FeatureManager
    try:
        # Late-bind object can introspect via _oleobj_
        methods = []
        for n in dir(fm_late):
            if not n.startswith("_"):
                methods.append(n)
    except Exception:
        methods = []

    print(
        json.dumps(
            {
                "typed_class": typed_class,
                "typed_cut4_result": typed_result,
                "method_count_on_late_fm": len(methods),
                "first_methods": methods[:20],
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
