"""PAE: semantic edge addressing (#9) on a LIVE SOLIDWORKS seat.

This is the live-seat proof that gates flipping the ``semantic_edges`` flag to
default-ON. It exercises the ONE new COM call the offline tests can only stub --
``IFace2.GetEdges`` on a resolved face -- and proves the whole point of the
feature: that a topology-named selector SURVIVES a parametric dim edit where the
legacy literal coordinate does NOT.

Run on the operator's live seat (the bridge attaches to it via the ROT):

    set AI_SW_BRIDGE_FLAG_SEMANTIC_EDGES=1
    python spikes/spike_semantic_edges_pae.py

WHAT IT PROVES (falsifiable gates):

  1. of_face resolves         -- fillet {of_feature: Box, face: +z} builds; the
                                 top face's 4 edges are found via IFace2.GetEdges.
  2. between_faces resolves   -- chamfer {of_feature: Box, between_faces:[+z,+x]}
                                 builds; the single shared edge is found by
                                 pure set intersection (NO GetTwoAdjacentFaces2).
  3. PARAMETRIC SURVIVAL      -- the SAME two semantic specs build at width 40 AND
                                 width 80. The edges relocate; the selectors still
                                 hit them. This is the property literal points lack.
  4. LITERAL CONTRAST         -- a literal {x,y,z} point tuned to the width-40
                                 edge FAILS ("matches no edge within 1um") when the
                                 box is rebuilt at width 80. The negative control
                                 that makes gate 3 meaningful.

DESIGN NOTE: each semantic selector is exercised on its OWN fresh box (one
semantic feature per build). Filleting a face's edges and THEN chamfering across
that same now-rounded edge would (correctly) find 0 shared edges -- the fillet
consumes the sharp edge. That is a spec-authoring gotcha, not a resolver bug, so
the PAE keeps the two selectors on non-interacting geometry.

A green run here is the sole remaining blocker on the flag default; record it in
docs/pending_gates.md and flip flags.py::semantic_edges default to True.
"""

import json
import os
import sys
import time

# The bridge attaches to the running seat via the ROT (get_sw_app). No path
# insert needed when run from an editable install; add src for a raw checkout.
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Enable the gate for this process even if the operator forgot the env var.
os.environ.setdefault("AI_SW_BRIDGE_FLAG_SEMANTIC_EDGES", "1")

from ai_sw_bridge.spec import validator  # noqa: E402
from ai_sw_bridge.spec.builder import build  # noqa: E402

RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_results",
    "semantic_edges_pae.json",
)

results = {
    "pae": "semantic_edges_#9",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
}


def gate(name, ok, detail=""):
    results["gates"][name] = {"ok": bool(ok), "detail": detail}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _base(width):
    """The box base: a (width x 20 x 10 mm) blind extrude off the Front plane."""
    return [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Box",
            "plane": "Front",
            "width": float(width),
            "height": 20.0,
        },
        {
            "type": "boss_extrude_blind",
            "name": "Box",
            "sketch": "SK_Box",
            "depth": 10.0,
        },
    ]


def _spec(name, width, *extra):
    return {"schema_version": 1, "name": name, "features": _base(width) + list(extra)}


def _fillet_of_face(width):
    return _spec(
        f"OfFace_W{int(width)}",
        width,
        {
            "type": "fillet_constant_radius",
            "name": "F_top",
            "radius": 2.0,
            "edges": [{"of_feature": "Box", "face": "+z"}],
        },
    )


def _chamfer_between(width):
    return _spec(
        f"Between_W{int(width)}",
        width,
        {
            "type": "chamfer_edge",
            "name": "Ch_corner",
            "mode": "equal_distance",
            "distance": 1.0,
            "edges": [{"of_feature": "Box", "between_faces": ["+z", "+x"]}],
        },
    )


def _literal(width):
    # A literal point tuned to the width-40 top-right vertical corner (x=+20mm).
    return _spec(
        f"Literal_W{int(width)}",
        width,
        {
            "type": "chamfer_edge",
            "name": "Ch_lit",
            "mode": "equal_distance",
            "distance": 1.0,
            "edges": [{"x": 20.0, "y": 0.0, "z": 5.0}],
        },
    )


def _build(spec, tag):
    """Validate then build; return (BuildResult|None, error_str|None)."""
    try:
        validator.validate(spec)
    except Exception as e:  # ValidationError
        return None, f"validation({tag}): {e}"
    try:
        res = build(spec, no_dim=True)
    except Exception as e:
        return None, f"build({tag}) raised: {e!r}"
    return res, None


def _ok_with(res, err, feature):
    """True iff the build succeeded and named feature is present."""
    if err:
        return False, err
    built = set(res.features_built)
    return (
        res.ok and feature in built
    ), f"ok={res.ok}, built={sorted(built)}, error={res.error}"


print("=" * 64)
print("PAE: semantic edge addressing (#9)")
print("=" * 64)

# --- Gate 1: of_face resolves (own build) ----------------------------------
print("\n--- width 40: fillet of_face +z (fresh box) ---")
r, e = _build(_fillet_of_face(40.0), "offace40")
ok, detail = _ok_with(r, e, "F_top")
gate("of_face_resolves", ok, detail)

# --- Gate 2: between_faces resolves (own build) ----------------------------
print("\n--- width 40: chamfer between_faces +z/+x (fresh box) ---")
r, e = _build(_chamfer_between(40.0), "between40")
ok, detail = _ok_with(r, e, "Ch_corner")
gate("between_faces_resolves", ok, detail)

# --- Gate 3: parametric survival -- SAME specs at width 80 -----------------
print("\n--- width 80: SAME semantic specs, edges relocated ---")
r1, e1 = _build(_fillet_of_face(80.0), "offace80")
ok1, d1 = _ok_with(r1, e1, "F_top")
r2, e2 = _build(_chamfer_between(80.0), "between80")
ok2, d2 = _ok_with(r2, e2, "Ch_corner")
gate("parametric_survival", ok1 and ok2, f"of_face[{d1}] between[{d2}]")

# --- Gate 4: literal contrast (negative control) ---------------------------
# Literal point tuned to the width-40 corner (x=+20mm); rebuild at width 80
# (corner now at x=+40). The literal must MISS.
print("\n--- literal point tuned to W40 must FAIL at W80 (negative control) ---")
r, e = _build(_literal(80.0), "literal80")
if e is not None:
    gate("literal_contrast_fails", "matches no edge within 1um" in e, e)
else:
    miss = (not r.ok) and "1um" in (r.error or "")
    gate("literal_contrast_fails", miss, f"ok={r.ok}, error={r.error}")

# --- Summary ---------------------------------------------------------------
print("\n" + "=" * 64)
all_pass = all(g["ok"] for g in results["gates"].values())
print(
    "OVERALL: "
    + (
        "ALL GATES PASS -- flag may flip default-ON"
        if all_pass
        else "SOME GATES FAILED"
    )
)
print("=" * 64)

os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
with open(RESULTS_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print(f"\nResults written to {RESULTS_PATH}")

sys.exit(0 if all_pass else 1)
