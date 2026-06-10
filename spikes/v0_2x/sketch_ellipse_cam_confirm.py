"""W48 cleanup lane — confirm the DECLARATIVE sketch_ellipse cam, retire the hand-roll.

The Tier-2 cam-follower PAE used a hand-rolled ellipse cam (_build_cam_handrolled)
because the declarative sketch_ellipse->extrude path was broken (parent_plane_normal
not stashed). That builder defect was patched (b4e74ce / 5c3f77d). This confirms the
fix end-to-end: build the cam via the PRODUCTION builder from a declarative
sketch_ellipse spec, then run the production create_mate cam-follower leg.

GREEN ⇔ the declarative ellipse cam materializes a body with a non-planar lateral
face AND the cam-follower mate (MateCamTangent) solves + persists through save/reopen
— officially retiring _build_cam_handrolled.

Run:  PYTHONPATH=<repo>/src python spikes/v0_2x/sketch_ellipse_cam_confirm.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_HERE.parent))

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402
from ai_sw_bridge.assembly.handlers import create_mate  # noqa: E402

import mech_mate_tier1_gear_screw as t1  # noqa: E402
import mech_mate_tier2_rack_cam as t2  # noqa: E402
import mech_mate_tier2_pae as t2pae  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_RESULTS.mkdir(exist_ok=True)
_OUT = _RESULTS / "sketch_ellipse_cam_confirm.json"


def main() -> int:
    out: dict[str, Any] = {"spike_id": "sketch_ellipse_cam_confirm", "ok": False,
                           "verdict": "FAIL"}
    sw = None
    try:
        sw = get_sw_app()
        mod = wrapper_module()
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass

        # --- Build the cam from a DECLARATIVE sketch_ellipse spec (the fix) ---
        cam = t2._build("declcam", t2._cam_spec("declcam"))
        out["cam_build"] = cam
        if "error" in cam:
            out["error"] = f"declarative cam build failed: {cam['error']}"
            return _finish(out)

        follower = t2._build("follower", t2._follower_spec("follower"))
        if "error" in follower:
            out["error"] = follower["error"]
            return _finish(out)

        ctx = t2pae._place(sw, mod, [("cam", cam["path"], [0, 0, 0]),
                                     ("follower", follower["path"], [60, 0, 0])])
        if "error" in ctx:
            out["error"] = ctx["error"]
            return _finish(out)

        # GATE: the declarative cam must expose a non-planar lateral face.
        cam_face = t2._first_nonplanar_face(ctx["placed"]["cam"], mod)
        out["declarative_cam_has_nonplanar_face"] = cam_face is not None
        if cam_face is None:
            out["error"] = "declarative cam exposed NO non-planar face (build defect not fixed?)"
            out["verdict"] = "NO-GO"
            return _finish(out)

        # --- Production cam-follower mate on the DECLARATIVE cam ---
        spec = {
            "type": "camfollower",
            "a": {"component": "cam", "face_ref": {"non_planar": True}},
            "b": {"component": "follower", "face_ref": {"is_cylinder": True}},
        }
        mate, err = create_mate(ctx["asm"], ctx["placed"], spec, mod=mod)
        out["create_mate_error"] = err
        if mate is None:
            out["error"] = f"create_mate None: {err}"
            return _finish(out)
        out["feature_type"] = typed(mate, "IFeature", module=mod).GetTypeName2()

        asm_path = str(Path(t1._results_tmp(), f"declcam_{os.getpid()}.SLDASM"))
        if int(typed(ctx["asm"], "IModelDoc2", module=mod).SaveAs3(asm_path, 0, 0)) != 0:
            out["error"] = "SAVE_FAILED"
            return _finish(out)
        rb = t2._read_back(sw, mod, asm_path, "ICamFollowerMateFeatureData",
                           ("MateAlignment",))
        out["persist"] = rb

        green = (
            "Cam" in out.get("feature_type", "")
            and "read_back" in rb
        )
        out["ok"] = bool(green)
        out["verdict"] = "GREEN" if green else "NO-GO"
        print(f"[ellipse-cam] {out['verdict']}: feature={out.get('feature_type')} "
              f"nonplanar={out['declarative_cam_has_nonplanar_face']}")
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()
    finally:
        if sw is not None:
            try:
                sw.CloseAllDocuments(True)
            except Exception:
                pass
    return _finish(out)


def _finish(out: dict) -> int:
    _OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[ellipse-cam] verdict: {out.get('verdict')} -> {_OUT}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
