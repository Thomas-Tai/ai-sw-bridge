"""PAE (Task #14): side-face semantic edges on Top/Right-plane parents.

_face_frame now resolves the ±x/±y SIDE faces of extrudes built on the Top
(axis +y) and Right (axis +x) planes -- not just Front (axis +z). This proves
it on a live seat by filleting a side face (of_face) and chamfering the edge
shared by two side faces (between_faces) on each orientation, plus a Front
regression check.

    set AI_SW_BRIDGE_FLAG_SEMANTIC_EDGES=1
    python spikes/spike_face_frame_axes_pae.py

GATES (per orientation, each on its own fresh box so features don't interact):
  *_offace_side   -- fillet of_face("+x") builds (side-face edges via IFace2.GetEdges)
  *_between_sides -- chamfer between_faces(["+x","+y"]) builds (shared side-side edge)
front_regression  -- Front-plane of_face("+x") still builds (byte-compatible path)
"""

import json
import os
import sys
import time

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
os.environ.setdefault("AI_SW_BRIDGE_FLAG_SEMANTIC_EDGES", "1")

from ai_sw_bridge.spec import validator  # noqa: E402
from ai_sw_bridge.spec.builder import build  # noqa: E402

RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_results", "face_frame_axes_pae.json"
)
results = {
    "pae": "face_frame_axes_#14",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
}


def gate(name, ok, detail=""):
    results["gates"][name] = {"ok": bool(ok), "detail": detail}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _spec(name, plane, extra):
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": plane,
                "width": 40.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "Box",
                "sketch": "SK",
                "depth": 10.0,
            },
            extra,
        ],
    }


def _fillet_side(name, plane):
    return _spec(
        name,
        plane,
        {
            "type": "fillet_constant_radius",
            "name": "Fx",
            "radius": 1.0,
            "edges": [{"of_feature": "Box", "face": "+x"}],
        },
    )


def _chamfer_between_sides(name, plane):
    return _spec(
        name,
        plane,
        {
            "type": "chamfer_edge",
            "name": "Cxy",
            "mode": "equal_distance",
            "distance": 1.0,
            "edges": [{"of_feature": "Box", "between_faces": ["+x", "+y"]}],
        },
    )


def _run(spec, feature, tag):
    try:
        validator.validate(spec)
        res = build(spec, no_dim=True)
    except Exception as e:
        return False, f"{tag}: raised {e!r}"
    ok = res.ok and feature in set(res.features_built)
    return (
        ok,
        f"ok={res.ok}, built={sorted(set(res.features_built))}, error={res.error}",
    )


print("=" * 64)
print("PAE (#14): side-face semantic edges on Top/Right parents")
print("=" * 64)

for plane, prefix in (("Top", "top"), ("Right", "right")):
    print(f"\n--- {plane}-plane parent ---")
    ok, d = _run(_fillet_side(f"{prefix}_off", plane), "Fx", f"{prefix}_offace")
    gate(f"{prefix}_offace_side", ok, d)
    ok, d = _run(
        _chamfer_between_sides(f"{prefix}_btw", plane), "Cxy", f"{prefix}_between"
    )
    gate(f"{prefix}_between_sides", ok, d)

print("\n--- Front-plane regression ---")
ok, d = _run(_fillet_side("front_off", "Front"), "Fx", "front_regression")
gate("front_regression", ok, d)

print("\n" + "=" * 64)
all_pass = all(g["ok"] for g in results["gates"].values())
print("OVERALL: " + ("ALL GATES PASS" if all_pass else "SOME GATES FAILED"))
print("=" * 64)

os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
with open(RESULTS_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print(f"\nResults written to {RESULTS_PATH}")
sys.exit(0 if all_pass else 1)
