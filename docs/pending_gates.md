# Pending live-seat gates

Features that are **code-complete and green offline** but carry a deliberate
`default OFF` (or otherwise inert) state until a proof on a live SOLIDWORKS seat
retires the risk. When no live seat is available (COM is mocked in the offline
suite), the gate is recorded here rather than faked. Each entry names the exact
spike to run and the one-line change that flips the feature on once it is green;
entries stay as proof-of-record after they ship.

---

## `semantic_edges` — semantic edge addressing (#9) — ✅ SHIPPED

**State:** **PAE GREEN (4/4), flag promoted to default ON in v1.7.** Live-seat run
recorded in `spikes/_results/semantic_edges_pae.json`. Retained here as the
proof-of-record. Literal `{x, y, z}` edge selection is unchanged and always on;
`--disable-flag semantic_edges` reverts to literal-only.

**PAE result (live seat, box 40mm then 80mm):**
- `of_face_resolves` — PASS (fillet built; `IFace2.GetEdges` returns the face's 4 edges)
- `between_faces_resolves` — PASS (chamfer built; shared edge found by set intersection)
- `parametric_survival` — PASS (both selectors rebuild at width 80; edges relocated, still hit)
- `literal_contrast_fails` — PASS (literal point tuned to width-40 misses at width 80, as designed)

The original run also surfaced an authoring gotcha (not a bug): a fillet over a
face's edges consumes the sharp edge, so a *later* `between_faces` across that
now-rounded edge correctly finds 0 shared edges. The spike keeps the two
selectors on non-interacting geometry; the gotcha is documented in
`known_limitations.md` §4.

---

### Original gate record (for reference)

**Why it was gated:** the of_face / between_faces resolution adds exactly ONE new COM
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

**Done on green (v1.7):** flipped `flags.py::FLAG_REGISTRY["semantic_edges"].default`
to `True`, updated this entry to SHIPPED, dropped the "default OFF pending…"
language from `known_limitations.md` §4 and `spec_reference.md`, and recorded the
run in the changelog.
