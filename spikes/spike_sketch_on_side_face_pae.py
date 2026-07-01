"""PAE (Task #15): sketch-on-face (simple_hole) on side faces of Top/Right parents.

_face_frame now carries SW's OWN calibrated sketch frame for the ±x/±y side
faces of Top(+y)/Right(+x)-plane parents (uv_calibrated=True), so simple_hole /
sketch-on-face place a child feature at the intended (u, v) on those faces.

Verify-by-EFFECT: each hole is offset along the face's ASYMMETRIC (depth) axis,
so if that axis pointed the wrong way the pick point would land OFF the face and
SelectByID would fail the build. A green build therefore proves the sign, not
just that "a hole got made somewhere".

    set AI_SW_BRIDGE_FLAG_SEMANTIC_EDGES=1
    python spikes/spike_sketch_on_side_face_pae.py
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
    os.path.dirname(os.path.abspath(__file__)),
    "_results",
    "sketch_on_side_face_pae.json",
)
results = {
    "pae": "sketch_on_side_face_#15",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
}


def gate(name, ok, detail=""):
    results["gates"][name] = {"ok": bool(ok), "detail": detail}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _spec(name, plane, width, height, face, u, v):
    return {
        "schema_version": 1,
        "name": name,
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": plane,
                "width": width,
                "height": height,
            },
            {
                "type": "boss_extrude_blind",
                "name": "Box",
                "sketch": "SK",
                "depth": 10.0,
            },
            {
                "type": "simple_hole",
                "name": "Hole",
                "of_feature": "Box",
                "face": face,
                "center": {"u": u, "v": v},
                "diameter": 3.0,
                "end_condition": "blind",
                "depth": 4.0,
            },
        ],
    }


def _run(spec, tag):
    try:
        validator.validate(spec)
        res = build(spec, no_dim=True)
    except Exception as e:
        return False, f"{tag}: raised {e!r}"
    ok = res.ok and "Hole" in set(res.features_built)
    return (
        ok,
        f"ok={res.ok}, built={sorted(set(res.features_built))}, error={res.error}",
    )


print("=" * 64)
print("PAE (#15): sketch-on-face on side faces of Top/Right parents")
print("=" * 64)

# Each case offsets along the face's asymmetric depth axis (the one that spans
# 0..depth, not ±half), so a wrong sign lands off the face and fails the build.
CASES = [
    # (gate, plane, width, height, face, u, v)  -- depth axis: Top side v, Right side u
    ("top_plus_x", "Top", 40.0, 40.0, "+x", 5.0, 3.0),
    ("top_minus_x", "Top", 40.0, 40.0, "-x", 5.0, 3.0),
    ("right_plus_y", "Right", 40.0, 20.0, "+y", 3.0, 5.0),
    ("right_minus_y", "Right", 40.0, 20.0, "-y", 3.0, 5.0),
    # Front regression (existing calibrated table). Front uses a FLIPPED sign
    # convention: its +x face origin sits on the z=0 edge and +u points toward
    # -z (off the face), so the on-face offset is u=-5 (byte-identical, pre-#15).
    ("front_plus_x", "Front", 40.0, 40.0, "+x", -5.0, 3.0),
]

for name, plane, w, h, face, u, v in CASES:
    ok, detail = _run(_spec(f"H_{name}", plane, w, h, face, u, v), name)
    gate(name, ok, detail)

print("\n" + "=" * 64)
all_pass = all(g["ok"] for g in results["gates"].values())
print("OVERALL: " + ("ALL GATES PASS" if all_pass else "SOME GATES FAILED"))
print("=" * 64)

os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
with open(RESULTS_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print(f"\nResults written to {RESULTS_PATH}")
sys.exit(0 if all_pass else 1)
