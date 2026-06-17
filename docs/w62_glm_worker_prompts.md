# W62 — Curves group — GLM/Sonnet worker briefs (DRAFT for review)

Four lanes extending the **`feature_add` HANDLER_REGISTRY** (the hem sibling —
MCP + CLI feature creation, NOT the CLI-only sketch_editing surface). Targets:
**helix · split_line · composite · project_curve**. All are topology-generative
features driven by pre-selected entities + parameters — **no headless UI/ray-cast
traps**. The risk is the `CreateDefinition` (Mode-A) vs legacy `Insert*` (Mode-B)
COM-marshaling duality, so every lane MUST probe BOTH modes.

DLL-verified surface (SW2024 v32):

| Lane | Mode-A (FeatureData) | Mode-B (legacy, `IModelDoc2`) | Prereq selection | Verify |
|---|---|---|---|---|
| helix | `IHelixFeatureData` (Pitch/Revolution/Height/StartingAngle/Clockwise/DefinedBy) | `InsertHelix(b,b,b,b,int,d,d,d,d,d)` | a sketch with ONE circle | new feature node (no ΔVol) |
| split_line | `ISplitLineFeatureData` (Sketch/Faces/SplitType/ISetFaces) | `InsertSplitLineProject(bool Reverse, bool SingleDir)` | solid body + sketch over a face | **ΔFace > 0, ΔVol == 0** |
| composite | `ICompositeCurveFeatureData` (SetEntitiesToJoin) | `InsertCompositeCurve()` | solid body, a chain of edges | new feature node (no ΔVol) |
| project_curve | **none found** | **none found** — DISCOVER on seat | solid body + face + sketch | new feature node (no ΔVol) |

---

## §0 SHARED CONTEXT (every lane reads this)

**Project:** `ai-sw-bridge` — declarative JSON→SOLIDWORKS COM bridge. You author
Python + offline tests + a spike you do NOT run (no seat). Follow LITERALLY; do
not explore beyond named files; do not redesign.

**Architecture you extend (already shipped — do NOT modify):**
`src/ai_sw_bridge/features/` — the `feature_add` registry seam (W56; hem is the
first customer, W59). Each lane = one module defining a handler with the uniform
contract:
```
def create_<kind>(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]
```
- Shared by dry-run AND commit. **Return `(False, "<reason>")` on any failure —
  NEVER raise.** Return `(True, "<note>")` only after verify-the-EFFECT passes.
- Registered in `features/__init__.py` by W0 (one line:
  `HANDLER_REGISTRY["<kind>"] = create_<kind>`) — you do NOT touch `__init__.py`.
- `feature` = the spec's feature dict (your params). `target` = the resolved
  target dict (durable refs / selection context).
- Verify-the-EFFECT INSIDE the handler — a measurable B-rep / feature-tree delta
  (the W21/W42 ghost trap: `call_ok` + name + "no error" is NOT proof).

**THE DUAL-MODE DOCTRINE (mandatory — the heart of this wave):**
OOP feature creation has two opposite failure modes
([[reference_createdefinition_qi_wall]]):
- **Mode-A** — `doc.FeatureManager.CreateDefinition(<swFeatureNameID>)` →
  `typed_qi(data, "I<X>FeatureData")` → set params (+ `AccessSelections`/setters
  where the iface requires it) → `doc.FeatureManager.CreateFeature(data)`.
  Fails by **`E_NOINTERFACE` on the QI** or by `CreateDefinition` returning None.
- **Mode-B** — the legacy `IModelDoc2.Insert*` method on pre-selected entities.
  Fails by **silent no-op** (returns, but no feature node materializes).

Your handler MUST **try Mode-A first** (a `FeatureData` iface exists for 3 of 4
lanes), and **on `E_NOINTERFACE` / None / silent-drop, fall back to Mode-B in the
same handler call**. Structure it as:
```python
feat, mode = _try_mode_a(doc, feature), "A"
if feat is None:
    feat, mode = _try_mode_b(doc, feature), "B"
if feat is None:
    return (False, "both Mode-A (CreateDefinition/QI) and Mode-B (Insert*) failed")
# ... then verify-the-effect ...
```
**No feature is declared WALLED until BOTH modes are exhausted on the live seat.**
(W0 fires the spike and adjudicates; your job is to author both paths + the
verify so W0 can see which fires.)

**typed_qi import:** `from ..com.typed_qi import typed_qi` (the same helper hem
uses; check `features/hem.py` for the exact import path + usage). Import only
stdlib + project modules at module scope (must import with NO live seat).

**Verify metrics (use the EXACT one named per lane):**
- `_metrics(doc) -> (face_count, volume)` — copy hem's `_metrics` (face count via
  body face iteration; volume via mass-props). Split-line: assert `ΔFace > 0` and
  `ΔVol == 0`.
- Feature-node materialization — walk `doc.FirstFeature()` → `.GetNextFeature()`,
  **re-typing each node to `IFeature` per step** (the thread W59 lesson — the walk
  returns loosely-typed nodes), count nodes (or match the new feature's type
  name) before vs after. Helix/composite/project: a new node of the expected type
  must appear.

**HARD RULES:**
- Create/modify ONLY your 3 files (named per lane). NEVER touch
  `features/__init__.py`, `mutate.py`, `com/*`, or any other lane's files.
- Return `(False, reason)`, never raise. Verify the EFFECT, never trust a return.
- No "Co-Authored-By" lines. Python `C:/Python314/python.exe`, `PYTHONPATH=src`.

**Fixture (W0-owned — provided before dispatch in `spikes/v0_2x/_feature_spike_fixtures.py`):**
`build_block(sw) -> doc` (a 40×30×10 mm solid via boss-extrude, the hem archetype);
plus per-lane seeds — `seed_circle_on_face(doc)` (helix), `seed_sketch_over_face(doc)`
(split/project). Your spike imports these; do NOT hand-roll a body. **A
solid-body B-rep target is mandatory** — projection/intersection/split need real
topology, never an abstract plane. DO NOT run the spike.

**Tests:** fake-COM in the style of `tests/features/test_hem.py` (or the nearest
hem test) — fake `doc` with fake `FeatureManager.CreateDefinition`/`CreateFeature`
and the fake `IModelDoc2.Insert*`; assert BOTH the Mode-A and Mode-B branches and
the verify-gate (effect delta → True; no delta → False ghost).

---

## LANE 1 — composite  (worktree `C:/D/wt_w62composite`, branch `feat/w62-composite`) — START HERE (cleanest)

Files: `features/composite.py`, `tests/features/test_composite.py`, `spikes/v0_2x/spike_composite.py`

`kind:"composite"`. Joins a chain of pre-selected edges into one reference curve.
- **Mode-A:** `CreateDefinition` → `typed_qi(data, "ICompositeCurveFeatureData")` →
  `data.AccessSelections(doc, None)` → `data.SetEntitiesToJoin(<edges>)` →
  `data.ReleaseSelectionAccess()` → `CreateFeature(data)`. (The swFeatureNameID is
  unknown — try `swFmRefCurve=14` first; W0 resolves the exact ID on the seat.)
- **Mode-B:** select the edges (`select_entity` per durable ref / by index), then
  `doc.InsertCompositeCurve()` (no args, returns Boolean).
- **Prereq:** the block's edges — `target` carries the edge refs (W0 fixture
  supplies a connected edge chain on the block).
- **Verify:** a new feature node materialized (FirstFeature walk; no ΔVol).
- Spike: `doc = fx.build_block(sw)`; select 2–3 connected edges; run handler; PASS
  iff a new node appears AND survives save→reopen. Report which mode fired.

Commit: `feat(W62): composite lane — composite curve (CreateDefinition+InsertCompositeCurve dual-mode) + tests + spike`

---

## LANE 2 — helix  (worktree `C:/D/wt_w62helix`, branch `feat/w62-helix`)

Files: `features/helix.py`, `tests/features/test_helix.py`, `spikes/v0_2x/spike_helix.py`

`kind:"helix"`. Builds a helix on a pre-selected sketch circle.
- **Mode-A:** `CreateDefinition` → `typed_qi(data, "IHelixFeatureData")` → set
  `DefinedBy` (swHelixDefinedBy_e — pitch+revolution vs height+revolution etc.),
  `Pitch`, `Revolution`, `Height`, `StartingAngle` (deg→rad), `Clockwise`,
  `ReverseDirection` → `CreateFeature(data)`. swFeatureNameID unknown → probe;
  if QI is `E_NOINTERFACE`, go Mode-B.
- **Mode-B:** `doc.InsertHelix(ConstantPitch:bool, Reverse:bool, Dimension:bool,
  Clockwise:bool, DefinedBy:int, Pitch:double, Revolution:double, Height:double,
  StartAngle:double, Diameter:double)` — 10 args, returns void. (Exact bool
  semantics are fuzzy; author the documented order, W0 nails them on the seat.)
- **Prereq:** a sketch with exactly ONE circle, pre-selected
  (`fx.seed_circle_on_face(doc)`).
- **Verify:** a new Helix feature node (FirstFeature walk; no ΔVol — a helix is a
  reference curve).
- Params: `{"pitch_mm": 5, "revolutions": 4, "start_angle_deg": 0, "clockwise": true}`.

Commit: `feat(W62): helix lane — helix curve (CreateDefinition+InsertHelix dual-mode) + tests + spike`

---

## LANE 3 — split_line  (worktree `C:/D/wt_w62splitline`, branch `feat/w62-splitline`)

Files: `features/split_line.py`, `tests/features/test_split_line.py`, `spikes/v0_2x/spike_split_line.py`

`kind:"split_line"`. Projects a sketch onto a face, splitting it.
- **Mode-A:** `CreateDefinition` → `typed_qi(data, "ISplitLineFeatureData")` →
  `data.AccessSelections(doc, None)` → set `data.SplitType` (swSplitLineType_e:
  projection), `data.Sketch`, and the target faces via `data.ISetFaces` /
  `data.GetFacesCount`/`ISetFaces` → `ReleaseSelectionAccess()` →
  `CreateFeature(data)`.
- **Mode-B:** select the sketch + target face, then
  `doc.InsertSplitLineProject(Reverse:bool, SingleDirection:bool)` (returns void).
  (Silhouette variant `InsertSplitLineSil()` and intersect
  `FeatureManager.InsertSplitLineIntersect(int)` exist — projection is the lead.)
- **Prereq:** a solid block + a sketch (a line/curve) positioned OVER a target
  face (`fx.seed_sketch_over_face(doc)` → returns the sketch + the target face ref).
- **Verify (DIFFERENT from the others):** `_metrics` before/after — assert
  **`ΔFace > 0`** (the projected curve splits the face) **AND `ΔVol == 0`** (no
  material change). This is the definitive topological proof; the feature-node
  walk is secondary.

Commit: `feat(W62): split_line lane — split line (CreateDefinition+InsertSplitLineProject dual-mode) + tests + spike`

---

## LANE 4 — project_curve  (worktree `C:/D/wt_w62project`, branch `feat/w62-project`) — BOSS FIGHT

Files: `features/project_curve.py`, `tests/features/test_project_curve.py`, `spikes/v0_2x/spike_project_curve.py`

`kind:"project_curve"`. Projects a sketch onto a face (sketch-on-face) or
intersects two sketches → a 3D reference curve.

**Why boss fight:** reflection found **NO dedicated `*ProjectCurveFeatureData`
iface and NO `InsertProjectCurve*` method** on `IModelDoc2`/`IFeatureManager`. The
creation entry point is UNKNOWN — this lane includes a **method-discovery step**.
- **Mode-A candidate:** `CreateDefinition(swFmRefCurve=14)` → QI the returned data
  for `IReferenceCurveFeatureData` / a projection-typed ref-curve data; set the
  sketch + face; `CreateFeature`. (If `swFmRefCurve` yields composite/projection
  data, set the projection sub-type.)
- **Mode-B candidates (probe in order):** (a) any `Insert*` with "Project" the
  worker can find by reflecting `IModelDoc2`/`IModelDocExtension`/`IFeatureManager`
  at author time and listing them in a docstring; (b) the sketch-on-face implicit
  projection (open a sketch on the face, `SketchUseEdge3`-style convert of the
  source curve — reuse the W60 convert recipe as a fallback projection).
- **Author both candidate paths + a clear `(False, "...")` when neither fires.**
  Per the doctrine, **do NOT mark WALLED** — that adjudication is W0's after the
  seat exhausts every probe.
- **Prereq:** a solid block + a face + a source sketch
  (`fx.seed_sketch_over_face(doc)`).
- **Verify:** a new reference-curve feature node (FirstFeature walk; no ΔVol).

Commit: `feat(W62): project_curve lane — projected curve (dual-mode + method discovery) + tests + spike`

---

## W0 return protocol (W0 runs this — not the workers)

Per lane: pull branch → fire spike on the live seat → **let the spike exhaust
Mode-A then Mode-B** → adjudicate the named verify metric (ΔFace for split_line;
feature-node materialization for helix/composite/project) surviving save→reopen →
if GREEN wire `HANDLER_REGISTRY["<kind>"]` + merge; if BOTH modes fail, halt +
diagnose (only then is WALLED on the table, with DLL+seat provenance). Fixture/
harness bugs are W0's (the W60 lesson: suspect the W0 fixture before the lane).
W0 resolves the open unknowns: the exact `swFeatureNameID` per feature, the
`InsertHelix` bool semantics, and the project_curve creation entry point.
