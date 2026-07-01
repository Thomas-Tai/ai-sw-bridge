# Known Limitations

Read this before authoring your first spec. Each section names a sharp edge, shows how to recognize when you've hit it, and gives the workaround.

For codebase-extension gotchas (pywin32 marshalling, SW API quirks), see [known_gotchas.md](known_gotchas.md) instead.

---

## 1. Face-sketch origin = part-origin projection, NOT face centroid

The single biggest source of "the geometry came out at the wrong position" bugs. When you sketch on a face of an earlier extrusion via `sketch_rectangle_on_face`, `sketch_circle_on_face`, or `sketch_circles_on_face`, the **sketch local origin is at the projection of the part origin onto that face**, not the face's geometric center.

These coincide IF the parent extrusion is centered on the part origin (which is what MMP does — its base plate is a `CreateCenterRectangle` on the Front Plane through the origin). They diverge as soon as the parent is shifted off origin.

### How to recognize

- You expected a child feature centered on the face, but it ends up at the EDGE of the face (or fully outside the face, producing a half-cut hole or a slab that hangs off into space).
- `doc.GetPartBox(True)` shows a Y or X range that's 2x what you expected.
- Visually: a child block sticks out below the parent's footprint by exactly half the parent's relevant dimension.

### Worked example (TensionBracket §13.3)

Inboard cap is shifted in the spec to land at part-frame Y ∈ [0, 15]:
```json
{"type": "sketch_rectangle_on_plane", "name": "SK_InboardCap",
 "plane": "Front", "width": 20, "height": 15,
 "center": {"x": 0.0, "y": 7.5}}
```

Now the cap's centroid in part-frame X/Y is `(0, 7.5)`, but the part origin is at `(0, 0)`. The cap's `+z` face inherits this: face geometric center is at part `(0, 7.5, 3)`, but the face-sketch origin lands at part `(0, 0, 3)`.

The slot slab on top of the cap needs to be CENTERED on the cap's centroid (Y=7.5), so its spec must offset the sketch:
```json
{"type": "sketch_rectangle_on_face", "name": "SK_SlotSlab",
 "of_feature": "Extrude_InboardCap", "face": "+z",
 "width": 8.5, "height": 15,
 "center": {"u": 0.0, "v": 7.5}}
```

Without that `v: 7.5`, the slab would land at part Y ∈ [-7.5, 7.5] instead of [0, 15], and the bounding box would come out as 22.5mm in Y instead of 15mm.

### Workaround

1. Mentally track where your parent extrusion's geometric center sits in part coordinates.
2. If that's not `(0, 0)`, add a `center: {u: <dx>, v: <dy>}` field to every child face-sketch to compensate.
3. After the build, run `doc.GetPartBox(True)` (multiply by 1000 for mm) and compare against the dimensions you expected. The bounding box is the cheapest reality check.

### Runtime detection

The builder emits a warning to stderr when it detects a face-sketch on a non-origin-aligned parent and you haven't specified a `center` offset. The warning includes the parent's face center coords so you can see whether the default is what you wanted.

---

## 2. Side faces (`±x`/`±y`): supported on Front/Top/Right, but not flipped or non-rectangular parents

All six faces (`+z`, `-z`, `+x`, `-x`, `+y`, `-y`) of an extrusion resolve a part-frame transform via `_face_frame` in [`spec/_face_geometry.py`](../src/ai_sw_bridge/spec/_face_geometry.py). Face names are **sketch-local**: `+x`/`+y` are the `+u`/`+v` sides of the parent's own sketch, so on a Top- or Right-plane parent they point along different *part* axes than on a Front-plane parent.

For the **side** faces (`±x`, `±y`), both fillet/chamfer edge selection (`of_feature`/`between_faces`, #9) and sketch-on-face child features (`sketch_*_on_face`, `simple_hole`) work on the three standard-plane parents:

| Parent | Base sketch plane | Extrude axis | Side-face support |
|---|---|---|---|
| Front | Front | `+z` | ✅ edges + sketch-on-face |
| Top | Top | `+y` | ✅ edges + sketch-on-face (since v1.7+) |
| Right | Right | `+x` | ✅ edges + sketch-on-face (since v1.7+) |
| flipped / other axis | — | `-y`, `-x`, non-axis-aligned | edges ✅ where the axis is axis-aligned; **sketch-on-face ❌** (frame `uv_calibrated=False`) |

Two constraints remain:

1. **Sketch-on-face needs a measured orientation.** The in-face `u`/`v` frame is SW's own calibrated sketch frame for `+z`/`+y`/`+x`-axis parents. A flipped (`-y`/`-x`) or otherwise unmeasured axis leaves the frame `uv_calibrated=False` — edge selection still works, but placing a child sketch is refused.
2. **Rectangular profile only** (the half-extents define where the side faces sit); a circle/arbitrary-curve profile has a curved side surface that isn't addressable.

> **Sign convention (side faces):** on Top/Right parents, `+u`/`+v` point from the part-origin projection *into* the face (SW's native frame). The Front-plane table predates this and uses a flipped sign on the extrude-parallel axis, so the same nominal `+u` can point the opposite way on a Front side face — provide the `center` offset with the correct sign for the parent's plane.

### How to recognize

```
RuntimeError: sketch-on-face on a side face (+/-x, +/-y) of a Top/Right-plane
(±x/±y-axis) parent is not yet supported: only the face center and normal are
calibrated ...
```
(This now fires only for flipped/unmeasured orientations.) Or, for a non-rectangular profile at any orientation:
```
RuntimeError: side face '+x' of 'Extrude_Box': parent has no sketch_extent_uv
stashed. Side faces are only addressable on extrusions whose profile is a
rectangle ...
```

### Workaround

- **Sketch on a side face of a flipped/unmeasured parent:** sketch the base so the extrude axis is `+z`/`+y`/`+x` (Front/Top/Right, non-flipped), or address the face via `±z` of a child extrude.
- **Non-rectangular profile:** there is no side-face sketch path; add the feature on a `±z` face instead.

### What's needed to lift the remaining limit

Measure and add the calibrated sketch frame for the flipped (`-y`/`-x`) axis orientations (same `ISketch.ModelToSketchTransform` read used for `+y`/`+x`), and handle non-rectangular profile extents. Tracked in [`ROADMAP.md`](ROADMAP.md) (v0.13+ backlog).

---

## 3. Parametric mode triggers blocking AddDimension2 popups

When you run `ai-sw-build` WITHOUT `--no-dim`, every dimensioned sketch entity triggers a "Modify Dimension" popup that requires manual mouse-tick before the build can proceed. On SW 2024 SP1, an MMP-sized part is ~16 popups. The relevant `swInputDimValOnCreate` user preference (toggle ID 8) reads back the expected `False` but does NOT suppress the popup empirically.

### How to recognize

`ai-sw-build` appears to hang. SOLIDWORKS shows a small floating "Modify" dialog with a numeric field and green/red ticks. The CLI is waiting for you to tick through every one.

### Workaround

**Use `--no-dim` mode** unless you specifically need a live equation link to `locals.txt` in the resulting SLDPRT:

```powershell
ai-sw-build my_spec.json --no-dim
```

In `--no-dim` mode the builder resolves every `{"rhs": "..."}` reference against `spec['locals']` in Python upfront, substitutes the literal mm value, and skips every `AddDimension2` call. Geometry comes out correct; the SLDPRT just has no equations linking back to locals.

### Why this isn't fixed

Three failed suppression approaches documented in [spikes/phase0/MMP_DEBUG_SESSION.md](../spikes/phase0/MMP_DEBUG_SESSION.md) and experiments M and O:

- `SetUserPreferenceToggle(swInputDimValOnCreate=8, False)` — toggle reads back as set, popup still fires
- `SetUserPreferenceToggle(78, False)` (swSketchEnableOnScreenNumericInput class) — same: no effect
- `SendKeys("{ENTER}")` to dismiss the dialog — doesn't route to modal child windows
- `keybd_event(VK_RETURN)` via Win32 — dismisses the floating popup but PM pane still blocks
- Bypassing AddDimension2 entirely with queryable internal SW dims (experiment O) — SW doesn't auto-create the linkable dim objects

The forum-canonical advice (set toggle 8) is reported to work inside SW's own VBA editor but does not propagate to external pywin32 COM clients on this build. A VBA-macro fallback (emit `.bas`, run via `RunMacro2`) is the only remaining avenue and carries its own risks; see [Roadmap "Not on the roadmap"](../README.md#roadmap).

### Second workaround: `--deferred-dim`

`--deferred-dim` gives you a live equation link with the popup ticks **time-localized per-sketch** (all popups for a single sketch arrive consecutively with no COM-call delay between them) instead of interleaved through the multi-minute geometry phase:

```powershell
ai-sw-build my_spec.json --deferred-dim
```

In this mode, geometry builds at placeholder sizes with no `AddDimension2` calls; immediately after each sketch handler returns, the bridge re-enters the sketch via `EditSketch`, replays all of its `AddDimension2` calls in one session, then applies the feature's `EquationMgr.Add2` bindings and rebuilds.

**Per-dim popup tick still required.** Each individual `AddDimension2` call still blocks for one manual "Modify Dimension" popup tick. The total popup count is the **same as default-inline mode** — one tick per dimensioned entity. The user-visible improvement is *timing*, not *count*:

- Inline mode: popup → multi-second COM call → popup → multi-second COM call → ... (popups spread over the whole build)
- `--deferred-dim`: COM-only geometry build (no popups) → consecutive cluster of N popups for sketch A → COM-only build for sketch B → consecutive cluster of M popups for sketch B → ...

You still tick the same number of popups. They just arrive in predictable clusters separated by COM-only build phases.

If you need zero popups, use `--no-dim` (no equation link). There is no fourth mode that gives both live-link AND no-popups — empirically falsified after 12 candidate suppression paths tested (see [deferred_dim_investigation.md](deferred_dim_investigation.md)).

**Rectangle support (fixed 2026-05-20, experiment ZF):** rectangle sketches (`sketch_rectangle_on_plane`, `sketch_rectangle_on_face`) previously had their second edge-dim demoted to driven on SW 2024 SP1, breaking the equation binding for that dim. Root cause: the API-side `CreateCenterRectangle` adds a spurious Midpoint relation absent from the UI-drawn equivalent, collapsing 2-DOF to 1-DOF. Fix is `_strip_centerrectangle_midpoint_relation()` in [`builder.py`](../src/ai_sw_bridge/spec/builder.py), called from both rectangle handlers immediately after `CreateCenterRectangle()`. Rectangle specs now ship clean equation links in all three modes (default-inline, `--deferred-dim`, `--no-dim`). Verified on `motor_mount_plate` end-to-end with both D1 and D2 driving their `S1B_MMP_H`/`S1B_MMP_W` bindings.

Experiment trail Z1–ZF (2026-05-19 to 2026-05-20) explored 11 mitigation routes before ZF identified the root cause via user UI inspection. Routes that did NOT work and are documented for the historical record: per-sketch dim grouping, construction-diagonal deletion, `IDisplayDimension.DrivenState` override (via pywin32 AND via VBA injector — both unreachable), mid-edit `EditRebuild3`, manual `CornerRectangle` + Midpoint, `gencache.EnsureModule` by explicit GUID, `MakeSelectedDriving`, `LinkValue` property, `Add3` with `swAllConfiguration`, `SetEquationAndConfigurationOption`, inline-dim with deferred bindings.

---

## 4. Edge selection: literal coordinates (default) or semantic topology (opt-in)

Fillet (`fillet_constant_radius`) and chamfer (`chamfer_edge`) select edges via 3D point-on-edge by default:

```json
{"type": "fillet_constant_radius", "name": "F", "radius": 2.0,
 "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}]}
```

This is mechanical and predictable, but it means **changing an upstream dim (e.g. the box width) can put the edge somewhere else, and the literal edge-point will no longer hit it.**

### How to recognize

`RuntimeError: edge #0 at part (X, Y, Z) mm matches no edge within 1um (best squared distance <d> m^2)`

### Semantic edge addressing (`--enable-flag semantic_edges`)

Semantic selectors name *topology* instead of coordinates, so they re-resolve
against the current geometry on every build and survive upstream dim edits. Two
forms, both keyed off a named parent feature's semantic face (`+x`/`-x`/`+y`/`-y`/`+z`/`-z`):

```json
{"type": "fillet_constant_radius", "name": "F1", "radius": 2.0,
 "edges": [
   {"of_feature": "Box", "face": "+z"},                // ALL edges bounding the top face
   {"of_feature": "Box", "between_faces": ["+z", "+x"]} // the ONE shared top-right edge
 ]}
```

The three forms may be mixed in one `edges[]` array; edges reached more than one
way are de-duplicated. `of_feature` must name an earlier **fixed-extent boss
extrude** (blind / midplane / two-direction) — the extents whose faces the
builder can resolve. `between_faces` naming two anti-parallel faces (e.g.
`["+z", "-z"]`, which share no edge) is rejected at validation.

The flag defaults **ON** since v1.7 — the live-seat PAE of `IFace2.GetEdges` is
green (of_face resolves, between_faces resolves, both survive a 40→80 mm width
change, and a literal point tuned to the old width correctly misses; see
[`pending_gates.md`](pending_gates.md) and `spikes/spike_semantic_edges_pae.py`).
To fall back to literal-only edges, `--disable-flag semantic_edges`; with the
flag off a semantic selector is rejected at validation and literal specs are
unaffected.

**Authoring gotcha:** filleting or chamfering a face's edges *consumes* those
sharp edges (the fillet replaces the edge with a rounded face). A later
`between_faces` selector naming two faces whose shared edge was already filleted
resolves to 0 shared edges — correctly, the edge no longer exists. Order edge
operations so a later selector doesn't target geometry an earlier one removed.

---

## 5. Each `ai-sw-build` creates a new untitled Part

The builder always calls `NewDocument`. It does NOT modify the currently-active SOLIDWORKS document. After a build:

- A new "PartN" window appears (where N auto-increments).
- The previously-active window remains untouched.
- The new window may not be the visible window on top (focus depends on whatever the user clicks).
- If you want the SLDPRT on disk, pass `--save-as <absolute_path>`. Otherwise the part lives in memory only and is discarded when you close SW (or its window).

This is intentional — builds are reproducible and don't risk overwriting hand-edited work. But it does mean an ai-sw-observe `screenshot` call right after a build may not show the freshly-built part if a different window currently has focus. Use `doc.GetTitle` to confirm which doc you're inspecting; or walk `sw.GetFirstDocument` to enumerate all open docs.

---

## 6. Schema validation does not catch geometry impossibilities

The validator checks: schema shape, topological references between features, locals-file variable existence. It does NOT check:

- Whether a circle on a face will actually land on material (it might sit entirely in a void from a previous cut).
- Whether a fillet radius is larger than the smallest adjacent edge.
- Whether the resulting geometry is closed, valid, or sane.

These failures surface as runtime exceptions during the build (`FeatureCut4 returned None`, or worse, a silently-succeeded build with broken geometry). The bbox sanity check after building is the cheapest way to catch the latter.

---

## 7. Checkpoint retention is bounded by three AND-combined tunables

Every build with `flags.checkpoint = true` writes one SQLite row per
feature into `.checkpoints/<part_name>.sqlite`. Without a retention
policy the store grows unbounded; on long-running projects it can
reach hundreds of megabytes.

`ai_sw_bridge.checkpoint.gc.run` prunes rows according to
three dimensions, all AND-combined — a row survives only if it
satisfies every configured dimension:

| Tunable                    | Default | Effect                                                        |
| -------------------------- | ------- | ------------------------------------------------------------- |
| `max_count_per_part`       | 100     | Keep the N most recent checkpoints per part.                  |
| `max_age_days`             | 30      | Drop rows older than M days.                                  |
| `max_db_size_mb`           | 50.0    | Drop oldest rows until the SQLite file is under the cap.      |

Passing `None` disables a dimension. Example TOML:

```toml
[checkpoint]
max_count_per_part = 25
max_age_days = 14
max_db_size_mb = 20.0
```

### How to recognize

- `.checkpoints/` directory is growing past your comfort level.
- `ai-sw-history part <name>` returns more rows than you care to read.

### Workaround

- Run `python -c "from ai_sw_bridge.checkpoint import gc_run; print(gc_run())"`
  periodically, or wire it into a CI teardown step.
- Tighten the tunables in `.ai-sw-bridge.toml` for long-lived parts.
- Note: GC is pure SQLite — it never touches the running SOLIDWORKS
  session, so it's safe to run mid-build on a different part.

---

## 8. In-context references, assembly mates, and sub-assemblies are out of scope

The bridge authors **single parts**. Assembly-level workflows are deliberately not supported at this stage:

- **In-context references** — a feature in one component that references another component's geometry (e.g. an extrude up-to a mating part's face). These are fragile across edits and a classic source of circular / under-defined references even in hand-built assemblies; driving them blind and out-of-process multiplies that risk.
- **Mates** — `AddMate5` / `CreateMate` pass entity arrays across the assembly COM boundary, which is exactly the IDispatch-variant-array marshalling class that fails under late binding without a verified workaround.
- **Sub-assembly orchestration** and **large-assembly performance** — not targeted.

### How to recognize

You opened an assembly (`.SLDASM`) and expected the bridge to insert components or add mates. `ai-sw-build` only creates/edits parts; assembly docs are read-only to the observe surface (`sw_get_mate_errors` reports *existing* mate state but cannot author mates).

### Workaround

Author the individual parts with the bridge, then assemble + mate them by hand in SOLIDWORKS. Assembly + mate primitives are tracked as v0.13+ backlog in [ROADMAP.md](ROADMAP.md) and [DEFERRED.md](DEFERRED.md). A deeper blocker: mates reference specific faces/edges, and the bridge has no durable topological reference for those yet (cf. §4 — edge selection is by literal coordinate), so robust mate authoring depends on solving that first.

---

## SOLIDWORKS / seat death during a batch

Since v1.6.0, `client.mutate.batch()` and `ai-sw-batch` run inside a crash-recovery
envelope **by default**: if SOLIDWORKS dies mid-batch, the bridge respawns the seat
and replays your proposal list to an identical result (Tier-1 replays onto the
pristine file; Tier-2 restores a pre-save snapshot if the death struck during the
atomic save). The returned manifest carries a `recovery` block, and a headless-orphan
reaper prevents leaked windowless `SLDWORKS.exe` processes from pinning a license seat.

Caveats:

- The MCP in-process reconnect path (`sw_reconnect`) does **not** auto-replay — after a
  reconnect there, verify your document. Only the supervised batch path auto-restores.
- Respawn timing is calibrated against SOLIDWORKS 2024 SP1 (~8–9 s, ~3.5× headroom).
  On much slower hardware a respawn may exceed the budget and return a clean
  `SeatRespawnTimeout` instead of recovering — fail-actionable, never a hang.
- Pass `supervised=False` to opt out (e.g. CI, or an environment with no recoverable
  seat); the envelope also degrades to the bare best-effort engine automatically if it
  cannot be constructed.

---

## Features not available out-of-process (the OOP boundary)

A class of SOLIDWORKS features cannot be created via the COM API out-of-process: the
call returns `None` / no-ops because the kernel must **traverse or solve geometry
mid-invocation** to derive the result (arc-length curve marches, boolean shells,
deform frames, external/symbolic tables). The bridge **fails these closed** —
`propose_feature_add` rejects an unsupported feature `type` with an explicit error
naming the supported kinds, so you never silently get a no-op part.

Walled (deferred) feature types include: `loft`, `rib`, `wrap`, `indent`, `flex`,
`chain` fillet/chamfer, `curve_driven_pattern`, `table_driven_pattern`, `combine`,
`split`, `edge_flange`, `miter_flange`, `jog`, `thicken`, `equation_curve`,
`dimension_pattern` / `derived_pattern`.

The forensic record of each wall (experiment, HRESULT, falsification) is in
[DEFERRED.md](DEFERRED.md). If you need a walled feature, author it interactively in
SOLIDWORKS, then continue with the bridge.

---

## Reporting new sharp edges

If you hit something that's reproducible and not in this list, please open an issue with: the spec JSON, the full CLI output (including the traceback), the SW build (Help → About → revision string), and the `doc.GetPartBox(True)` output after the (partial) build.
