# Pending live-seat gates

Features that are **code-complete and green offline** but carry a deliberate
`default OFF` (or otherwise inert) state until a proof on a live SOLIDWORKS seat
retires the risk. This machine has no live seat (COM is mocked in the offline
suite), so these gates are recorded here rather than faked. Each entry names the
exact spike to run and the one-line change that flips the feature on once it is
green.

---

## `semantic_edges` — semantic edge addressing (#9)

**State:** implemented behind the `semantic_edges` feature flag (default OFF);
literal `{x, y, z}` edge selection is unchanged and always on.

**Why gated:** the of_face / between_faces resolution adds exactly ONE new COM
call — `IFace2.GetEdges` on a face resolved by `_resolve_face_object`. It is the
proven-class return-array analog of `IBody2.GetEdges` (already shipped), but it
has not been exercised against a real face on this machine. Everything else in
the lane is pure set algebra (`spec/_edge_selectors.py`) and is fully covered by
the offline suite. `between_faces` deliberately uses a frozenset intersection of
the two faces' edge sets — NOT `IEdge.GetTwoAdjacentFaces2` — so the riskiest
marshalling call in the design space is avoided entirely.

**Spike:** [`spikes/spike_semantic_edges_pae.py`](../spikes/spike_semantic_edges_pae.py)

```
set AI_SW_BRIDGE_FLAG_SEMANTIC_EDGES=1
python spikes/spike_semantic_edges_pae.py
```

**Gates it must pass:**

1. `of_face_resolves` — a fillet over `{of_feature: Box, face: +z}` builds (the
   top face's edges come back from `IFace2.GetEdges`).
2. `between_faces_resolves` — a chamfer over `{of_feature: Box, between_faces:
   ["+z", "+x"]}` builds (single shared edge found by set intersection).
3. `parametric_survival` — the SAME semantic spec builds at width 40 AND width
   80. This is the whole point: the edges relocate, the selector still hits them.
4. `literal_contrast_fails` — a literal `{x, y, z}` tuned to the width-40 edge
   FAILS ("matches no edge within 1um") when the box is rebuilt at width 80. The
   negative control that makes gate 3 meaningful.

**On green:** flip `flags.py::FLAG_REGISTRY["semantic_edges"].default` to `True`,
update this entry to "SHIPPED", drop the "default OFF pending…" language from
`known_limitations.md` §4 and `spec_reference.md`, and record the run's
`_results/semantic_edges_pae.json` in the changelog for that release.
