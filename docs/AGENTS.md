# AGENTS.md

Briefing for an AI assistant (Claude, ChatGPT, Codex, etc.) that will use ai-sw-bridge to drive SOLIDWORKS. Read this whole file before your first action. It is short on purpose.

## What you are

You are pair-programming with a human engineer who has SOLIDWORKS open and this repo installed. They will give you a goal like *"build a 30 mm flange with 4 bolt holes"* or *"add a fillet to the top edge of the existing part"*. Your job is to translate that goal into either:

- a **JSON spec** that [`ai-sw-build`](../src/ai_sw_bridge/cli/build.py) consumes (when building a new part), OR
- a **mutate proposal** that [`ai-sw-mutate`](../src/ai_sw_bridge/cli/mutate.py) consumes (when changing a parametric variable on an existing part), OR
- an [`ai-sw-observe`](../src/ai_sw_bridge/cli/observe.py) command (when you just need to read the model first).

You never call the SOLIDWORKS COM API directly. You write JSON specs or invoke CLIs. The bridge handles COM.

## The rules

1. **Propose first, execute second.** Show the human the spec/proposal before running it. Mutations go dry-run → review → commit. Builds default to `--no-dim` so you can re-run cheaply.
2. **The spec is the source of truth.** When in doubt, write or edit `spec.json` and rebuild. Do not hand-edit the SLDPRT in SW UI between runs unless the human asked.
3. **Default to `--no-dim`.** It builds in seconds with zero manual clicks. Use parametric mode (no flag) only if the human explicitly needs a live equation link to `locals.txt`.
4. **One feature at a time when debugging.** If a build fails at feature 7 of 10, trim the spec to features 1–7, fix, re-run, then add the rest back.
5. **Read the example most like your target.** Don't write specs from scratch. The [`examples/`](../examples/) folder has 12 working specs covering every shipped feature type. Find the closest match, copy it, modify.

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

14 feature types ship today. The right starting example by goal:

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
- **`revolve_boss` needs the axis inside the profile sketch** as a `centerline` field. Don't try to declare the axis as a separate feature.
- **One centerline per sketch.** Multiple would be ambiguous.
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

14 feature primitives ship as of v0.5. **Not yet supported**: sweep, loft, sheet metal, custom reference planes/axes, assemblies, mates, drawings, HoleWizard countersink/counterbore, variable-radius fillet. If the human asks for one of these, say so — don't fake it with a worse primitive.

The full not-yet-shipped list and the v0.6+ plan: [`README.md`](../README.md) bottom section.

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
