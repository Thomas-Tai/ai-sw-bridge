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

## 2. Only `+/-z` faces of extrusions can host child sketches

`_select_extrude_face` in the builder currently has wiring for `+z` and `-z` only. If you write `"face": "+x"` or any `+/-y` value, the builder raises `NotImplementedError`.

### How to recognize

```
RuntimeError: v1 only supports +z/-z (out/in board) faces of extrusions; got +x
```

### Workaround

Reorient the parent extrusion so the face you want to sketch on becomes its `+z` or `-z` face. Since extrudes inherit their axis from the parent sketch's reference plane, this usually means picking a different reference plane for the base sketch:

- Need a sketch on the +X face of a box? Sketch the box on the **Right Plane** (YZ, normal +X) instead of Front Plane. Then the +X face becomes the box's `+z` face in the bridge's local frame.
- Need both side faces and the top face accessible? You'll need to split the part into two stacked extrudes, one whose `+z` is the original `+z` and one whose `+z` is the original `+x` — currently no clean way to do this.

### What's needed to lift the limit

Mechanical: extend `_select_extrude_face` to compute tangent-plane offsets when the extrude axis is `+/-Y` or `+/-X` (currently only `+/-Z` is wired), and extend the mirror-u logic in the face-sketch handlers. Estimate: 60-90 min including spec tests. Tracked in the [Roadmap](../README.md#roadmap) "near-term" tier.

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

Three failed suppression approaches documented in [spikes/phase0/MMP_DEBUG_SESSION.md](../spikes/phase0/MMP_DEBUG_SESSION.md) and the Spike M / Spike O sweep:

- `SetUserPreferenceToggle(swInputDimValOnCreate=8, False)` — toggle reads back as set, popup still fires
- `SetUserPreferenceToggle(78, False)` (swSketchEnableOnScreenNumericInput class) — same: no effect
- `SendKeys("{ENTER}")` to dismiss the dialog — doesn't route to modal child windows
- `keybd_event(VK_RETURN)` via Win32 — dismisses the floating popup but PM pane still blocks
- Bypassing AddDimension2 entirely with queryable internal SW dims (Spike O) — SW doesn't auto-create the linkable dim objects

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

**Rectangle support (fixed 2026-05-20, Spike ZF):** rectangle sketches (`sketch_rectangle_on_plane`, `sketch_rectangle_on_face`) previously had their second edge-dim demoted to driven on SW 2024 SP1, breaking the equation binding for that dim. Root cause: the API-side `CreateCenterRectangle` adds a spurious Midpoint relation absent from the UI-drawn equivalent, collapsing 2-DOF to 1-DOF. Fix is `_strip_centerrectangle_midpoint_relation()` in [`builder.py`](../src/ai_sw_bridge/spec/builder.py), called from both rectangle handlers immediately after `CreateCenterRectangle()`. Rectangle specs now ship clean equation links in all three modes (default-inline, `--deferred-dim`, `--no-dim`). Verified on `motor_mount_plate` end-to-end with both D1 and D2 driving their `S1B_MMP_H`/`S1B_MMP_W` bindings.

Spike trail Z1–ZF (2026-05-19 to 2026-05-20) explored 11 mitigation routes before ZF identified the root cause via user UI inspection. Routes that did NOT work and are documented for the historical record: per-sketch dim grouping, construction-diagonal deletion, `IDisplayDimension.DrivenState` override (via pywin32 AND via VBA injector — both unreachable), mid-edit `EditRebuild3`, manual `CornerRectangle` + Midpoint, `gencache.EnsureModule` by explicit GUID, `MakeSelectedDriving`, `LinkValue` property, `Add3` with `swAllConfiguration`, `SetEquationAndConfigurationOption`, inline-dim with deferred bindings.

---

## 4. Edge selection uses literal part coordinates

Fillet (`fillet_constant_radius`) and any future edge-targeting primitives select edges via 3D point-on-edge:

```json
{"type": "fillet_constant_radius", "name": "F", "radius": 2.0,
 "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}]}
```

This is mechanical and predictable, but it means **changing an upstream dim (e.g. the box width) can put the edge somewhere else, and the literal edge-point will no longer hit it.**

### How to recognize

`RuntimeError: could not select edge #0 at part (X, Y, Z) mm -- point not on any edge of current geometry`

### Workaround

When you change a dim that affects edge positions, update the literal edge coordinates in the spec to match. There is no "edge of feature X by index" addressing yet.

A future `edges_by_face: "+z"` sugar (filllet all edges of a face) would handle the common case without per-edge coords; on the roadmap but not implemented.

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

## Reporting new sharp edges

If you hit something that's reproducible and not in this list, please open an issue with: the spec JSON, the full CLI output (including the traceback), the SW build (Help → About → revision string), and the `doc.GetPartBox(True)` output after the (partial) build.
