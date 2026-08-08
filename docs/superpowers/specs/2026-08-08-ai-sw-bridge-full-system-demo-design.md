# Full-System `--no-dim` Demo — Design

**Date:** 2026-08-08
**Status:** Design (awaiting review → implementation plan)
**Owner:** repo maintainer
**Target artifact:** a chaptered, recordable demo (`tools/demo_full_system.py`) that produces GIF(s) for the README, showing the bridge build a small product end-to-end — parts → assembly → observe/DFM → drawing → export — in `--no-dim` mode. **Second deliverable (same script + widget):** a runnable `--quickstart` mode and a synced `QUICKSTART.md` that get a fresh cloner from zero to a first part and "ready to develop" in ≤5 minutes.

---

## 1. Goal & framing

The existing `tools/demo_no_dim_showcase.py` prints the capability surface (a "tour") and live-builds **one part**. It does not exercise the rest of the v1.7 surface — assembly, mirror, exploded views, interference/DFM, drawings, exports. This project grows the showcase into a **full-system** demo.

This demo serves **two audiences with one codebase and one widget**:

1. **The evaluator (GIF showcase).** A first-time visitor who is an **experienced SOLIDWORKS user**. That framing drives the chaptered design (§4): such a viewer is not impressed by geometry appearing on screen — they judge a CAD tool by *design intent, feature-tree quality, real mate constraints, and engineering read-backs*, and they are quick to discount a demo that shows breadth without value or that quietly papers over a limitation. Every showcase choice is made against that skeptical eye.
2. **The fresh cloner (5-minute quickstart, §4B).** A developer who just cloned the repo and wants to *start building* — install, confirm the seat works, produce a first part, and know where to edit next — in ≤5 minutes. This audience wants a hands-on happy path and copy-pasteable commands, not a capability tour. The `--quickstart` mode and the synced `QUICKSTART.md` serve them.

### Non-goals
- Not an exhaustive live build of all ~37 feature kinds / all 13 mates / all 9 export formats. The **tour** enumerates the full surface; the **live build** shows a representative, legible spread.
- Not a new geometry kernel showcase — no walled features (loft/rib/wrap/sweep-if-risky/etc.; see `DEFERRED.md`).
- Not coupled to any external project. All parts are bundled in-repo with relative paths so any cloner can reproduce.

---

## 2. Locked decisions (from brainstorming)

| # | Decision | Rationale |
|---|---|---|
| D1 | **One master script with selectable chapters** (`--chapter part\|assembly\|observe\|drawing\|export\|all`). | Run `all` for a hero GIF; run one chapter for a short focused clip. One codebase, both outcomes; reuses the existing tool's mode pattern. |
| D2 | **Purpose-built demo widget** (new bundled specs), not reused example parts. | A clean, legible product reads better than an arbitrary cluster of existing example parts; we control interfaces so the assembly is coherent. |
| D3 | **Tour lists everything (auto-introspected); live build is representative.** | "Cover all functions" = the printed surface is complete and current; the on-screen build shows a curated, GIF-sized spread that hits every subsystem. |
| D4 | **Natural mates only** for the widget (not all 13 types). | Forcing gear/rack/cam/hinge/slot needs contrived geometry and multiplies risk. The tour lists all 13; the widget uses the ~4–5 it genuinely needs. |

---

## 3. Design principles

1. **Introspective — survives version bumps.** The tour reads the *live* surface at runtime: `ai-sw-build --list-kinds`, `pyproject.toml` `[project.scripts]`, and the `ai-sw-observe` subcommand list. A re-run after any release auto-reflects new kinds/verbs. Prefer runtime introspection over hardcoded feature tables; anything uncategorized degrades to an "Other supported" line (never dropped).
2. **`--no-dim --yes` throughout.** No Modify-Dimension popups (`known_limitations.md` §3), safe for unattended recording. See the headline beat (§6) for how the parametric story is told despite the stripped in-file equation link.
3. **Avoid the known part-spec traps** in the widget (see §5): origin-centered parents (§1 face-sketch-origin), axis-aligned extrudes only (§2 side faces), semantic edge selectors for fillet/chamfer (§4), `--save-as` on every part (§5 each build is a new untitled part).
4. **Honesty over polish.** Where the tool has a boundary the target viewer will find within minutes (`--no-dim` strips the in-file equation link; mates are unproven out-of-process; loft/rib/configs are walled), the demo *names* it rather than stepping around it. For this audience, candor builds trust faster than a seamless-looking GIF.
5. **Value, not just capability.** Each chapter carries a one-line "why this matters" caption, because the target viewer can hand-model the widget in minutes and will otherwise ask "why wouldn't I just do this myself?"

---

## 4. Chapters

Order in `all`: **tour → part → assembly → observe → drawing → export.**

| Chapter | Live actions | CLIs | Value caption (shown on screen) |
|---|---|---|---|
| `tour` (always first) | Print the full introspected surface: ~37 feature kinds, 22 CLIs, 13 mate types, 9 export formats — **each list ends by pointing at `DEFERRED.md`** for the honest boundary. | reads sources | "The whole surface, and its honest edges." |
| `part` | Build the 3 widget parts (rich feature trees — §5) via the COM build, `--save-as` each to `demo_out/`; bbox reality-check each; **climax: parametric edit → rebuild via `ai-sw-mutate` — the headline beat (§6).** | `ai-sw-build`, `ai-sw-mutate`, `ai-sw-observe` | "Change one number; the model rebuilds. That's the whole point." |
| `assembly` | Place parts into `.SLDASM`; **mirror** the 2nd bearing block; **exploded view**; **mates per Spike 0** (§7). | `ai-sw-assembly` | "Real constraints, not fixed coordinates." (fallback caption if Spike 0 fails, see §7) |
| `observe` | Interference (expect 0) · **min-wall DFM** · mass properties · bounding box · screenshot. | `ai-sw-observe` | "DFM is a build gate, not a manual afterthought." |
| `drawing` | 3 orthographic + isometric views · model dimensions · **BOM** → PDF into `demo_out/`. | `ai-sw-drawing` | "Drawing + BOM fall out of the same model." |
| `export` | STEP + STL + 3MF (all seat-confirmed) into `demo_out/`. | export (engine `export/formats.py`; exact CLI/flag confirmed in impl — §12) | "One model, every downstream format." |

A caption near the start states: **`--yes` is a recording/CI convenience; the interactive default is propose → approve → execute, human-gated.** This closes the "wait, it runs unattended?" gap before the viewer raises it.

The `observe` chapter is deliberately weighted: the read-backs (interference numbers, min-wall, mass) are the most credible, differentiated content for this audience and should get real screen time — not a rushed tail.

---

## 4B. Quickstart mode — the 5-minute onboarding path (second deliverable)

A fresh cloner's question is not "what can it do?" but "how do *I* get running and make my first part?" `--quickstart` answers exactly that, and `QUICKSTART.md` is its written twin. **The doc's commands are generated from / mirror the `--quickstart` step list**, so the guide can never drift from what actually runs.

**Design rules.**
- **One happy path, no branches, no capability tour.** Just the shortest line from clone → first part → "you're developing."
- **No-SW-first, tiered**, so *anyone* completes it in 5 minutes and a seat-less user still gets real value:

| Tier | Needs a seat? | Steps | Payoff |
|---|---|---|---|
| **A — get ready** (~3 min) | No | install → `ai-sw-doctor` (COM/seat health) → `ai-sw-build --list-kinds` → `ai-sw-build examples/demo_widget/demo_baseplate/spec.json --dry-run --lint` | "You can author and validate part specs right now." |
| **B — first real part** (~2 min) | Yes | `ai-sw-build --demo --no-dim --yes` → `ai-sw-observe bounding_box` | "That's your first SOLIDWORKS part from a JSON spec." |
| **Next** (pointer) | — | Signposts: edit a `spec.json`, run the full `--chapter all` demo, read `docs/demo_full_system.md` | "Here's where to go deeper." |

- **`ai-sw-doctor` gets its home here** (not in the showcase): it is the natural "is my install/seat wired?" gate for a newcomer, and it degrades gracefully with no seat (reports what's missing).
- **Honest 5-min claim.** Tier A alone satisfies "start developing" (author + dry-run specs) and needs no license; Tier B is the live payoff for anyone with a seat. The doc states this split so the "5 minutes" is truthful for both.
- Reuses the same `_demo_lib` runner, `--no-pause`/`--sleep` ergonomics, and the committed `examples/demo_widget/` specs — no new subject to maintain.

---

## 5. The demo widget

A small **pillow-block shaft assembly** — recognizable, assembles cleanly, and spans feature families without looking like a feature dumping-ground. Bundled in `examples/demo_widget/`.

| Part (new spec) | Feature families exercised (live, COM build) |
|---|---|
| `demo_baseplate` | rectangle sketch · blind extrude (with **draft**) · `simple_hole` · **linear_pattern** + **circular_pattern** (bolt circle) · **mirror_feature** · **fillet** (semantic edge) · **chamfer** |
| `demo_shaft` | **revolve boss** (turned profile with shoulders) · **revolve_cut** (retaining groove) · end chamfers · optional **cosmetic thread** (only if `--list-kinds` confirms) |
| `demo_bearing_block` | rectangle sketch · extrude · through bore + **counterbore** + **countersink** cuts · **shell** (lighten the housing) · reference **offset plane** for an off-origin sketch · **fillet** · 2 mounting holes (mirror-ready) |

Aggregate ≈ **16–18 feature families** across 3 parts — a rich, legible tree, **not** a feature dumping-ground: every feature reads as intentional design on a real pillow-block (draft = cast intent, shell = lightened housing, revolve = turned shaft, circular_pattern = rotary bolt mount, offset plane = real reference geometry). **Walled kinds are deliberately excluded** (loft/rib/wrap/sweep/flex/combine/thicken — see `DEFERRED.md`). The final kind list is confirmed against live `ai-sw-build --list-kinds` at implementation; any kind not present degrades gracefully — drop that one feature, keep the part legible.

### Spec-authoring rules (trap avoidance, from `known_limitations.md`)
- **Origin-centered parents.** Base extrudes centered on the part origin so face-sketch children land where expected (§1). Any off-origin child sketch carries an explicit `center: {u,v}` offset.
- **Axis-aligned, non-flipped extrudes** (Front/Top/Right, `+z`/`+y`/`+x`) so side-face sketches and edges resolve (§2).
- **Semantic edge selectors** (`of_feature` / `between_faces`) for fillet/chamfer so they survive dimension edits (§4). Order edge ops so a later `between_faces` doesn't target an already-consumed edge.
- **`--save-as <abs path>`** for every part — each build is a new untitled part; the assembly chapter needs the parts on disk (§5). After a build, confirm the doc by title before observing (focus is not guaranteed).
- Named features (`SK_Box`, `Extrude_Base`, …) so the **feature tree is legible on screen** — the tree is the money shot for this audience; the GIF must frame the FeatureManager tree, not only the body. `feature_statistics` counts are a weak substitute and are shown only as a secondary read-back.

---

## 6. The headline beat — parametric edit → rebuild (`ai-sw-mutate`)

This is the demo's **hero moment** and the single best answer to "why wouldn't I just model this myself?" A programmatic CAD tool earns its keep when **you change one number and the model rebuilds correctly** — design intent, not fixed geometry. The beat is framed as strength, not apology.

**The beat** (climax of the `part` chapter; also recordable as its own short clip):
1. Build the widget parts (§5) via the COM build.
2. Run `ai-sw-mutate` to change one driving value in the widget's `locals` — e.g. the bearing bore Ø or the baseplate length — and rebuild.
3. Show the feature tree and bbox/geometry update on screen. **If Spike 0 (§7) passed,** re-open the assembly and show the concentric mate *follow* the resized bore — design intent propagating across the whole assembly. That single shot is the most persuasive frame in the demo.

On-screen message: **"The JSON spec is the parametric source of truth; `mutate` drives the change and the model rebuilds."**

**Footnote (candor, one line — not the theme):** `--no-dim` records popup-free but writes **no in-file equation link back to `locals`** (`known_limitations.md` §3), so the *recorded* tree carries literal dims. The parametric power lives in the spec + `mutate` — which is exactly what this beat shows. If a live *in-file* equation link is wanted on camera, one part can be built `--deferred-dim` as a cameo (per-sketch popup ticked off-camera). The caveat gets one sentence; it is no longer the reason the beat exists.

---

## 7. Spike 0 — the mates gate (do/fail, decides the assembly chapter's identity)

**Problem.** `CAPABILITIES.md` (v1.7.1) advertises `ai-sw-assembly` with 13 mate types; `known_limitations.md` §8 still says *assembly mates are out of scope / fail under late-binding marshalling.* These conflict, and every assembly this project has built to date (e.g. the conveyor sub-assembly) used **`mate_count: 0`** — pure transform placement. So mate authoring out-of-process is, on current evidence, **unverified**.

**Spike 0 (first verification step).** Build a throwaway 2-part assembly and add a single **concentric** mate via `ai-sw-assembly`. Does it commit out-of-process and hold?

- **Pass →** the assembly chapter applies the widget's natural mates — concentric (bore↔shaft), coincident (block↔plate), distance (block X), width (shaft centered) — and is titled/captioned **"assembly with mates."** This is the credible version.
- **Fail →** the assembly chapter uses **transform-only placement** (proven today) and is honestly titled **"component placement / layout,"** *not* "assembly with mates." Mirror + exploded + interference still run and still make a compelling clip. The demo does not show a relationship that isn't really a mate.

**Doc-debt side effect.** Whichever way Spike 0 lands, reconcile the stale claim: if mates work, correct `known_limitations.md` §8; if they don't, correct `CAPABILITIES.md`'s mate advertisement. The demo must not ship against a self-contradictory capability doc.

**Optional stretch — `--chapter motion` (off by default).** Only if Spike 0 passes *and* the maintainer opts in: a tiny slider-in-slot or hinge vignette driven through `ai-sw-motion` travel audit, to show kinematic mates + motion. Excluded from `all` in v1 to keep scope and risk bounded.

---

## 8. Script architecture

- **New entry point:** `tools/demo_full_system.py`.
- **Shared library extraction:** move the proven helpers out of `demo_no_dim_showcase.py` into `tools/_demo_lib.py` — the introspection parsers (`parse_project_scripts`, `parse_observe_tools`, `build_capability_sections`), the step runner (`DemoStep`, `run_step`, `_command_env`, header/pause/sleep utilities). Refactor the existing single-part showcase to import from `_demo_lib`; **smoke-test it for output parity** so the existing tool is unchanged in behavior. The new full-system script is built on the same library. (Alternative considered: new script imports directly from the existing module — lighter but leaves two homes for the runner; rejected in favor of the extraction.)
- **Chapters as data.** Each chapter is a named list of `DemoStep`s; `all` concatenates them. A `--chapter` argument (default `all`) selects one. `--list-chapters` prints them.
- **`--quickstart` mode (§4B).** A separate top-level mode (not a chapter) that runs the tiered onboarding step list. `QUICKSTART.md` is generated from — or asserted equal to, via a test — that same step list so the doc and the runnable path stay in lock-step. `--quickstart --no-sw` (or the seat-less default) runs Tier A only.
- **Outputs:** `demo_out/` at repo root, **gitignored**, wiped at the start of each run so retakes are clean and idempotent. Committed specs live in `examples/demo_widget/`; only build products (`.SLDPRT`/`.SLDASM`/drawing/exports) go to `demo_out/`.
- **Recording ergonomics** (inherited + extended): `--no-pause`, `--sleep <s>`, per-chapter header + optional pause for framing, `--compact` capability summary, `--preflight-only` (no-SW rehearsal), `--tour-only`.

---

## 9. Verification plan (what the maintainer verifies first)

Staged so each cheap gate precedes an expensive one:

0. **Spike 0 — mates** (§7). Decides assembly-chapter identity; reconcile the capability doc.
1. **Preflight, no SW:** `--preflight-only --no-pause --sleep 0` — all widget specs dry-run + lint clean; tour renders.
2. **Full live rehearsal:** one `--chapter all --no-pause --sleep 0` on a **clean single SOLIDWORKS seat** (same single-instance discipline used elsewhere in this workspace) — every chapter completes, all enriched feature kinds build (no silent fallbacks), the `ai-sw-mutate` rebuild lands cleanly and (if Spike 0 passed) the mate follows the edit, interference = 0, drawing + exports land in `demo_out/`.
3. **Per-chapter rehearsal:** run each chapter alone to confirm it stands as an independent clip.
4. **Record:** re-run with pauses/sleep for framing → capture GIF(s); caption with the current version/tag.

---

## 10. Deliverables

- `tools/demo_full_system.py` — the chaptered demo.
- `tools/_demo_lib.py` — shared helpers; `demo_no_dim_showcase.py` refactored onto it (parity-tested).
- `examples/demo_widget/{demo_baseplate,demo_shaft,demo_bearing_block}/spec.json` + a `README.md` walking the feature list and the trap-avoidance notes.
- `.gitignore` += `demo_out/`.
- `docs/demo_full_system.md` (or an expanded `docs/demo_no_dim_showcase.md`) — how to run/record each chapter.
- **`--quickstart` mode** on `tools/demo_full_system.py` (tiered, no-SW-first) **+ `QUICKSTART.md`** at repo root, kept in lock-step by a test (§4B).
- A README **GIF section** embedding the chaptered clips **and a Quickstart link** pointing at `QUICKSTART.md`.
- Capability-doc reconciliation from Spike 0 (§7).

---

## 11. Risks & open items

| Risk / open item | Handling |
|---|---|
| Mates unproven out-of-process | Spike 0 gates it; honest fallback to placement. |
| Richer widget tree becomes a feature dumping-ground | §5 discipline: every feature must read as intentional on a pillow-block; walled kinds excluded; kinds confirmed vs `--list-kinds`. |
| A widget feature kind isn't actually supported live | `--list-kinds` gate at build; unsupported kind is dropped (feature omitted), part stays legible — never a hard failure mid-recording. |
| `ai-sw-mutate` rebuild fails on a widget spec | Rehearse the specific edit in verification step 2; pick a driving value with a clean, single-solve rebuild path. |
| `--no-dim` strips equation link → looks like dead geometry | Headline `mutate` beat (§6) makes parametric edit → rebuild the point; stripped-link caveat is a one-line footnote. |
| Full-system GIF too long/heavy | Chaptered short clips are the primary deliverable; `all` is a secondary hero clip. |
| Off-script viewer hits a walled feature | Tour signposts `DEFERRED.md`. |
| Existing showcase behavior drift during refactor | Parity smoke-test on `demo_no_dim_showcase.py`. |
| Drawing/export in `--no-dim` on this seat | Proven in rehearsal step 2 before recording. |
| Motion vignette scope creep | `--chapter motion` off by default, excluded from `all` in v1. |

---

## 12. Final choices deferred to implementation
- §6 headline beat: which driving value `ai-sw-mutate` changes on camera (bearing bore Ø vs baseplate length), and whether to include the `--deferred-dim` in-file-equation cameo.
- Final widget feature-kind list, pinned against live `ai-sw-build --list-kinds` (§5 lists the intended ~16–18; `cosmetic thread` and any kind not present degrade gracefully).
- Exact widget dimensions and hole counts (kept legible; final numbers in the specs).
- Whether the export chapter also emits the drawing PDF or keeps PDF in the drawing chapter only.
- **Export invocation:** confirm which CLI/flag drives `export/formats.py` for STEP/STL/3MF (no `ai-sw-export` entry point exists; likely a flag on an existing verb). If no CLI path exists, either add a thin one or scope the export chapter to the flat-pattern DXF verb + drawing PDF. Resolve early — it gates the export chapter's feasibility.
