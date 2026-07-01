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
  3. PARAMETRIC SURVIVAL      -- the SAME semantic spec builds at width 40 AND at
                                 width 80. The edges relocate; the selector still
                                 hits them. This is the property literal points
                                 lack.
  4. LITERAL CONTRAST         -- a literal {x,y,z} point tuned to the width-40
                                 edge FAILS ("matches no edge within 1um") when
                                 the box is rebuilt at width 80. This is the
                                 negative control that makes gate 3 meaningful.

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


def _box_spec(width, semantic_edges):
    """A box (width x 20 x 10 mm) plus a fillet + chamfer over ``semantic_edges``."""
    return {
        "schema_version": 1,
        "name": f"SemEdge_W{int(width)}",
        "features": [
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
            {
                "type": "fillet_constant_radius",
                "name": "F_top",
                "radius": 2.0,
                "edges": [{"of_feature": "Box", "face": "+z"}],
            },
            {
                "type": "chamfer_edge",
                "name": "Ch_corner",
                "mode": "equal_distance",
                "distance": 1.0,
                "edges": semantic_edges,
            },
        ],
    }


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


print("=" * 64)
print("PAE: semantic edge addressing (#9)")
print("=" * 64)

CHAMFER_SEM = [{"of_feature": "Box", "between_faces": ["+z", "+x"]}]

# --- Gate 1 + 2: both semantic forms resolve at the nominal width ----------
print("\n--- width 40: of_face fillet + between_faces chamfer ---")
res40, err40 = _build(_box_spec(40.0, CHAMFER_SEM), "w40")
if err40:
    gate("of_face_resolves", False, err40)
    gate("between_faces_resolves", False, err40)
else:
    built = set(res40.features_built)
    gate("of_face_resolves", res40.ok and "F_top" in built, f"features={sorted(built)}")
    gate(
        "between_faces_resolves",
        res40.ok and "Ch_corner" in built,
        f"ok={res40.ok}, error={res40.error}",
    )

# --- Gate 3: parametric survival -- same spec, different width -------------
print("\n--- width 80: SAME semantic spec, edges relocated ---")
res80, err80 = _build(_box_spec(80.0, CHAMFER_SEM), "w80")
if err80:
    gate("parametric_survival", False, err80)
else:
    built = set(res80.features_built)
    gate(
        "parametric_survival",
        res80.ok and {"F_top", "Ch_corner"} <= built,
        f"ok={res80.ok}, features={sorted(built)}, error={res80.error}",
    )

# --- Gate 4: literal contrast (negative control) --------------------------
# Tune a literal point to the width-40 top-right vertical edge (x = +20 mm),
# then rebuild at width 80 (edge now at x = +40). The literal must MISS.
print("\n--- literal point tuned to W40 must FAIL at W80 (negative control) ---")
lit_spec = _box_spec(80.0, [{"x": 20.0, "y": 0.0, "z": 5.0}])
res_lit, err_lit = _build(lit_spec, "w80_literal")
if err_lit is not None:
    # A build/validate exception carrying the literal-miss message counts.
    gate(
        "literal_contrast_fails",
        "matches no edge within 1um" in err_lit,
        err_lit,
    )
else:
    # If build() returned instead of raising, it must be a non-ok result.
    miss = (not res_lit.ok) and "1um" in (res_lit.error or "")
    gate(
        "literal_contrast_fails",
        miss,
        f"ok={res_lit.ok}, error={res_lit.error}",
    )

# --- Summary ---------------------------------------------------------------
print("\n" + "=" * 64)
all_pass = all(g["ok"] for g in results["gates"].values())
print(
    f"OVERALL: {'ALL GATES PASS -- flag may flip default-ON' if all_pass else 'SOME GATES FAILED'}"
)
print("=" * 64)

os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
with open(RESULTS_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print(f"\nResults written to {RESULTS_PATH}")

sys.exit(0 if all_pass else 1)
