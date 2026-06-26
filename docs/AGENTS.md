# AGENTS.md

Briefing for an AI assistant (Claude, ChatGPT, Codex, etc.) that will use ai-sw-bridge to drive SOLIDWORKS. Read this whole file before your first action. It is short on purpose.

## What you are

You are pair-programming with a human engineer who has SOLIDWORKS open and this repo installed. They will give you a goal like *"build a 30 mm flange with 4 bolt holes"* or *"add a fillet to the top edge of the existing part"*. Your job is to translate that goal into either:

- a **JSON spec** that [`ai-sw-build`](../src/ai_sw_bridge/cli/build.py) consumes (when building a new part), OR
- a **mutate proposal** that [`ai-sw-mutate`](../src/ai_sw_bridge/cli/mutate.py) consumes (when changing a parametric variable on an existing part), OR
- an [`ai-sw-observe`](../src/ai_sw_bridge/cli/observe.py) command (when you just need to read the model first).

You never call the SOLIDWORKS COM API directly. You write JSON specs or invoke CLIs. The bridge handles COM.

## Quickstart (2 minutes)

1. **Install**: `pip install -e ".[dev]"` from the repo root. Requires Windows + SOLIDWORKS running.
2. **Validate a spec**: `ai-sw-build examples/filleted_box/spec.json --validate-only`
3. **Dry-run (no SW needed)**: `ai-sw-build examples/filleted_box/spec.json --dry-run`
4. **Lint check**: `ai-sw-build examples/filleted_box/spec.json --lint`
5. **Build a part**: `ai-sw-build examples/filleted_box/spec.json --no-dim` (creates a fresh part in SW)
6. **Observe the result**: `ai-sw-observe features` / `ai-sw-observe bbox` / `ai-sw-observe volume`

The feature types available (16 shipped primitives + 2 cut end-condition variants + 8 sketch primitives):

| Category | Types |
|---|---|
| Sketch | `sketch_rectangle_on_plane`, `sketch_rectangle_on_face`, `sketch_circle_on_plane`, `sketch_circle_on_face`, `sketch_circles_on_face` |
| Sketch primitives | `sketch_line`, `sketch_arc`, `sketch_spline`, `sketch_slot`, `sketch_polygon`, `sketch_ellipse`, `sketch_text`, `sketch_3d_sketch` |
| Extrude | `boss_extrude_blind`, `boss_extrude_midplane`, `boss_extrude_through_all`, `boss_extrude_two_direction`, `boss_extrude_up_to_surface`, `cut_extrude_through_all`, `cut_extrude_blind`, `cut_extrude_midplane`, `cut_extrude_two_direction`, `revolve_boss`, `revolve_cut` |
| Modify | `fillet_constant_radius`, `chamfer_edge`, `simple_hole` |
| Pattern | `linear_pattern`, `circular_pattern`, `mirror_feature` |

## The rules

1. **Propose first, execute second.** Show the human the spec/proposal before running it. Mutations go dry-run → review → commit. Builds default to `--no-dim` so you can re-run cheaply.
2. **The spec is the source of truth.** When in doubt, write or edit `spec.json` and rebuild. Do not hand-edit the SLDPRT in SW UI between runs unless the human asked.
3. **Default to `--no-dim`.** It builds in seconds with zero manual clicks. Use parametric mode (no flag) only if the human explicitly needs a live equation link to `locals.txt`.
4. **One feature at a time when debugging.** If a build fails at feature 7 of 10, trim the spec to features 1–7, fix, re-run, then add the rest back.
5. **Read the example most like your target.** Don't write specs from scratch. The [`examples/`](../examples/) folder has 15 working specs covering every shipped feature type. Find the closest match, copy it, modify.

## What the spec looks like

A spec is a JSON file declaring features in build order. Lengths are either literal millimetres (`20.0`) or expressions that bind to variables in a `*_locals.txt` equation file (`{"rhs": "\"PART_DIAMETER\""}`).

Minimum viable spec — a 20 × 20 × 10 mm box:

```json
{
  "schema_version": 1,
  "name": "Box",
  "features": [
    {"type": "sketch_rectangle_on_plane", "name": "SK_Box",
     "plane": "Front", "width": 20.0, "height": 20.0},
    {"type": "boss_extrude_blind", "name": "EX_Box",
     "sketch": "SK_Box", "depth": 10.0}
  ]
}
```

Run with:

```powershell
ai-sw-build path\to\spec.json --no-dim
```

Full spec reference: [`docs/spec_reference.md`](spec_reference.md).

## Which feature type to pick

16 feature types ship today. The right starting example by goal:

| Goal | Best example to copy | Primitives it uses |
|---|---|---|
| Just a box | [`filleted_box/`](../examples/filleted_box/) | `sketch_rectangle_on_plane`, `boss_extrude_blind`, `fillet_constant_radius` |
| A cylinder, parametric | [`minimal_cylinder_v2/`](../examples/minimal_cylinder_v2/) | `sketch_circle_on_plane`, `boss_extrude_blind` with `{rhs}` |
| A plate with bolt holes | [`motor_mount_plate/`](../examples/motor_mount_plate/) | face-sketch + multi-circle holes |
| A simple drilled hole | [`drilled_plate/`](../examples/drilled_plate/) | `simple_hole` (blind + through_all) |
| A pattern of holes | [`patterned_plate/`](../examples/patterned_plate/) | `linear_pattern` |
| A radial pattern | [`patterned_disc/`](../examples/patterned_disc/) | `circular_pattern` |
| A mirrored feature | [`mirrored_holes/`](../examples/mirrored_holes/) | `mirror_feature` |
| A chamfered edge | [`chamfered_box/`](../examples/chamfered_box/) | `chamfer_edge` |
| A turned/lathed part (ring, shaft) | [`revolved_ring/`](../examples/revolved_ring/) | `revolve_boss` + `centerline` |
| A revolved groove or channel | [`drive_roller/`](../examples/drive_roller/) | `revolve_cut` + Top Plane `center.z` + `centerline` |
| Bosses on side faces | [`side_face_bosses/`](../examples/side_face_bosses/) | side-face support on existing types |

Every example has its own README explaining the gotchas specific to that primitive.

## Working with parametric variables

If the human's part has a `*_locals.txt` equation file (Equation Manager linked to a text file), you can:

- **Build a new part** that binds dims to those variables — use `{"rhs": "\"VAR_NAME\""}` in length fields and set `locals` to the file path.
- **Change a variable** on the existing part — use `ai-sw-mutate`. Workflow: `propose` → `dry_run` (rebuilds + screenshots + rolls back) → human reviews → `commit`. Never skip `dry_run`.

**Memory rule (from past incidents):** never edit values inside SW's Equation Manager UI. The `*_locals.txt` file is the source of truth — edit there, reload in SW.

## What's safe vs. what to ask first

**Safe to do without asking** (read-only / Propose stage):
- Any `ai-sw-observe` call.
- Drafting a `spec.json` for review.
- `ai-sw-mutate propose` (creates a proposal file, doesn't touch SW).
- Running `ai-sw-build … --no-dim` on a fresh part (creates new doc; doesn't modify open one).

**Always confirm with the human first:**
- `ai-sw-mutate dry_run` and `commit` (touches the active doc).
- `ai-sw-build` against an already-open part (the builder creates a new doc anyway, but if the human has unsaved work, warn).
- Anything that calls `SaveAs3` or overwrites files.

## Things that will bite you

- **`AddDimension2` opens a blocking popup** in parametric mode that cannot be suppressed via API on SW 2024 SP1. **Always start with `--no-dim`.** Only switch to parametric mode if the human explicitly needs the live equation link.
- **SW selects faces by 3D coordinate**, not by name. The builder computes coords from feature geometry. For face-bound primitives (`sketch_*_on_face`, `simple_hole`), `(u, v)` is measured from the **face SKETCH ORIGIN** — the projection of the part origin onto the face plane — *not* the face's geometric centroid. They coincide for `±z` faces of centered rectangles but diverge for everything else. See `examples/side_face_bosses/README.md` and `examples/tension_bracket/README.md` for the exact rule.
- **`revolve_boss` and `revolve_cut` need the axis inside the profile sketch** as a `centerline` field. Don't try to declare the axis as a separate feature.
- **Top Plane sketches with `centerline` need `center.z`.** On Top Plane, `center.y` is sketch-local (maps to part-Z with a sign flip). The `center.z` field positions the sketch at the correct part-Z. Without it, the centerline defaults to part Z=0. Run `--lint` to catch this.
- **One centerline per sketch.** Multiple would be ambiguous.
- **`sketch_slot` is always rounded-ended.** The SOLIDWORKS slot kernel produces inherently rounded (arc) ends — there is no flat-ended slot creation type. For a flat-ended rectangular slot, use `sketch_rectangle_on_plane`. `slot_type` only accepts `"arc"`.
- **The 7 `sketch_*` primitives build literal-size geometry only** (like `--no-dim`): no parametric `{rhs}` dimensioning, and the `construction` flag, spline `closed`, and text `height`/`font`/`angle_deg` are not yet applied.
- **The profile of a revolve must not cross its centerline.** SW rejects it with a cryptic error.
- **Pattern/mirror seeds are referenced by name**, and the seed must already exist earlier in the `features` array. The validator catches forward references.
- **Pre-existing complete API gotcha list:** [`docs/known_gotchas.md`](known_gotchas.md), [`docs/known_limitations.md`](known_limitations.md).

## When something fails

1. **Read the error message verbatim** — the bridge surfaces precise messages including which feature and which field. Don't paraphrase before showing the human.
2. **Validation errors** (before any SW call): the spec is wrong. Fix the spec.
3. **`PARAMNOTOPTIONAL` / `Invalid number of parameters`** at runtime: usually means an API arg count drifted. Check [`docs/api_reference.md`](api_reference.md) for the CHM-authoritative signature. If you genuinely need a new API surface, add it to [`tools/_api_extract_input.json`](../tools/_api_extract_input.json) and regenerate.
4. **`SelectByID returned False`**: face-select failed. Most common cause: an earlier feature changed the geometry and the seed coord is now on a curved/missing face. Reduce the spec until you find which feature breaks the select; adjust `center` offsets accordingly.
5. **The build returns a feature but the geometry looks wrong**: probably a `center` offset from the wrong origin (see the face-sketch-origin gotcha above). The runtime stderr warning fires with the exact offset to add.

## Roadmap awareness

16 feature primitives ship as of v0.10. **Not yet supported**: sweep, loft, sheet metal, custom reference planes/axes, assemblies, mates, drawings, HoleWizard countersink/counterbore, variable-radius fillet. If the human asks for one of these, say so — don't fake it with a worse primitive.

The full not-yet-shipped list and the v0.6+ plan: [`README.md`](../README.md) bottom section.

## Why late binding (and the type stubs)

The bridge uses `win32com.client.Dispatch("SldWorks.Application")` — late binding only. Early binding (`gencache.EnsureDispatch`) fails with *"this COM object can not automate the makepy process"* on most installs.

Consequences:
- Zero-arg COM methods auto-invoke as properties on `getattr` — you never "call" them with parens.
- Some args (Callout, OUT params) can't be marshalled — we use legacy 5-arg `SelectByID` instead of 9-arg `SelectByID2`.
- No compile-time type checking — mypy sees `Any` everywhere.

Type stubs in [`src/ai_sw_bridge/_sw_stubs/sw_stubs.pyi`](../src/ai_sw_bridge/_sw_stubs/sw_stubs.pyi) describe the API surface we actually use. They're not loaded at runtime (the real objects are `CDispatch`), but they serve as documentation and can be used for manual mypy validation. Do NOT attempt to switch to early binding — the typelib limitation is an SW install constraint, not a code issue.

## Session handoff

When ending a session, summarize the current build state and paste it into the next session's opening message. This preserves context across a multi-session workflow.

**Memory enforcement**: Before ending any session, write at least one memory file (project, feedback, or reference type) covering what you learned. The memory index at `~/.claude/projects/.../memory/MEMORY.md` must stay current.

## Where the source of truth lives

| Concern | File |
|---|---|
| Spec JSON format | [`docs/spec_reference.md`](spec_reference.md) |
| CLI flags + return shapes | [`docs/tools_reference.md`](tools_reference.md) |
| API gotchas (pywin32 limits) | [`docs/known_gotchas.md`](known_gotchas.md) |
| User-facing limitations | [`docs/known_limitations.md`](known_limitations.md) |
| CHM-verified SW API ref | [`docs/api_reference.md`](api_reference.md) |
| Schema (the actual code) | [`src/ai_sw_bridge/spec/schema.py`](../src/ai_sw_bridge/spec/schema.py) |
| Working example specs | [`examples/`](../examples/) |
