# Landing-Page Breadth Enhancement (`site/index.html`) — Design

**Date:** 2026-08-14
**Status:** Design — **enhanced (v2)**, approved by user (awaiting spec review → writing-plans)
**Owner:** repo maintainer
**Parent:** the landing page `site/index.html` exists and is live on the `gh-pages`
branch at `https://thomas-tai.github.io/ai-sw-bridge/`, built by
`tools/build_pages.py` (see `site/README.md`). It is the **"Spine"** every
Project B launch asset links back to. This spec is an **enhancement pass** over
that page, brainstormed through a 20-year-SOLIDWORKS-veteran lens.
**Target artifact:** a fresh visitor — especially a skeptical CAD veteran who
assumes "AI CAD" is another throwaway-kernel LLM wrapper — absorbs, in their
first ~15 seconds, that the bridge's output is **a real parametric model**
(named feature tree + driving equations that **survive an edit**, not a frozen
`Imported1` solid *and not a dumb one-shot tree*) **and** that it **goes all the
way to manufacturing** (part → assembly → DFM → drawing → export).

> **v2 note.** v1 of this spec (commit `c6da48d`) assumed the "alive tree" still
> could be frame-extracted from `demo_part.gif` and that only one asset was
> seat-gated. Frame inspection during the enhancement pass **disproved both**
> (see §13). v2 corrects the seat scoping and deepens Block ① from a two-state
> "alive vs dead" contrast to a three-state **"dead solid → real parametric
> model → survives the edit"** proof.

---

## 1. Goal & framing

The page today opens strong on the *thesis* ("drive your real SOLIDWORKS seat
from a JSON spec") but proves it almost entirely in **prose**. A veteran skims
prose in five seconds and bounces, pattern-matching to "just another LLM
wrapper," before the essay's real arguments land. The scarcest currency on a
launch landing page is the newcomer's first fifteen seconds; today those seconds
carry a headline and a hero GIF but no *breadth* proof and no *parametric-reality*
proof at a glance.

**The veteran's real skepticism has three tiers, not two.** A 20-year seat-holder
distinguishes:

1. **Dead solid** — an `Imported1` STEP body, no history. (Obviously not a design.)
2. **Dumb tree** — a linear pile of `Sketch1 / Boss-Extrude1 / Boss-Extrude2…`,
   hard-coded dims, under-defined sketches. **An LLM can emit this.** It *looks*
   alive in a screenshot and **shatters on the first edit.**
3. **Real parametric model** — named features, dims driven by *named equations /
   globals*, driving (not driven) constraints, and it **survives a dimension
   change with a clean rebuild.**

A static "here's a tree" screenshot doesn't separate tier 2 from tier 3 — and a
skeptic *assumes* tier 2, because that's what every other "AI CAD" wrapper
produces. So the enhancement spends the fifteen seconds on **three** things (the
trust coin, now three-sided):

- **Output is a real parametric model** — a Dead-STEP-vs-Named-Tree side-by-side
  with the **Equation Manager** visible, so the first thing the eye lands on is
  the one thing a code-CAD generator *and* a naive LLM cannot fake: authored
  feature names driven by named globals.
- **It survives the edit** — a short looping clip of `BORE_DIA 16 → 20` via
  `ai-sw-mutate`, the bore growing and the tree **rebuilding with 0 errors**.
  This is the single most disarming proof for a veteran: a robust tree, not a
  fragile one.
- **It goes all the way** — a five-stage workflow pipeline, so "it makes a part"
  reads instead as "it runs the whole job."

**Primary anchor (locked, user-reasserted): breadth.** Native-tree /
parametric-reality is the *philosophy lead*; breadth is the *absolute primary
anchor* — the thing that proves the tool is not a toy. Safety (propose → approve
→ execute) and honesty (labeled kernel walls) are **secondary constraints woven
into the copy**, not their own billboards.

### Non-goals

- **Not a redesign.** The hero, wedge headline, "Who are you?" doorways, the
  five-beat essay, the A4 explainer, the CTA, and the footer are all
  **untouched**. This is two inserted `<section>` blocks and one generalization
  of the build script — nothing else.
- **Not a general relaxation of the no-motion rule.** Exactly **one** motion
  asset ships (the live-edit GIF, L9); every other interactive/animated idea
  stays deferred (see §7).
- **Not new geometry or new capability.** Every asset depicts a capability the
  repo already ships. The breadth stills reuse existing verified clips; the
  Block ① assets are new *captures of existing capability*, not new features.
- **Not a launch task.** Firing the external sends (Show HN / X / Reddit /
  LinkedIn / registry PRs) is Project B Task 10 and is **user-driven**. This
  enhancement ships *before* those sends so the Spine is at its best when they
  fire; it does not itself send anything.

---

## 2. Locked decisions

| # | Decision | Rationale |
|---|---|---|
| L1 | **Breadth is the absolute primary anchor; parametric-reality is the philosophy lead.** Safety + skimmability are secondary constraints woven into copy, not separate billboards. | A veteran's "is this a toy?" is answered by breadth; their "is the output real, or a dumb tree?" by the named tree + equations + surviving-edit proof. |
| L2 | **Incremental — ships WITH the launch.** Two new `<section>` blocks inserted after the hero, before the doorways. Everything else on the page is untouched. | First impressions are brutal; the Spine must be at its best before any external send links to it. Minimal structural change keeps risk low. |
| L3 | **Real captured SOLIDWORKS imagery, never schematic illustration.** | A veteran discounts illustrations instantly. Real FeatureManager / Equation-Manager pixels are the proof; a drawn diagram is not. |
| L4 | **Two seat-dependency tiers.** *Tier A (seat-free):* the 5 **Block ②** breadth stills = single-frame ffmpeg extracts from the shipped, verified `docs/img/demo_*.gif`. *Tier B (one seat session):* the 3 **Block ①** assets (dead-STEP still · alive-tree+Equation still · live-edit GIF) — none exist in any GIF (§13), so all need a live seat. | Frame inspection (§13) proved the existing GIFs are graphics-area renders that never show tree/equation/dim chrome. The breadth payload is cheap; the veteran-depth payload is the seat cost. |
| L5 | **One focused seat session, before launch; Block ① + ② ship together.** | User decision. The parametric-reality hook is the whole point of the enhancement, so it must be present at the moment first impressions form — worth gating launch on one seat session. |
| L6 | **Honesty (defensibility) over polish.** Every caption defensible against `docs/CAPABILITIES.md` + the CLI registry; no phantom CLI; no implication of live in-browser SOLIDWORKS; the live-edit GIF is a recording of a real seat, labeled as such. | Carried standing constraint. Candor is the edge over a confident-but-thin competitor — a single overclaim spotted by a veteran forfeits the whole page. |
| L7 | **Source keeps `../`-relative paths; the build script does the publish rewrite.** `tools/build_pages.py` generalizes from one hero copy to a **list** of assets (stills + the GIF + hero). | Preserves the on-disk lint convention (`check_launch_kit.py` verifies `../` paths); the existing "fail loudly if `../` survives" guard then covers every new asset for free. |
| L8 | **Block ① proves tier-3, not tier-2.** It must show **named features** (`SK_Block`, `Cut_Bore`, …, not `Sketch1`) **and** the **Equation Manager** with named globals (`"BORE_DIA" = 16`) **and** a surviving edit. A bare tree screenshot is insufficient. | This is the enhancement's core thesis (§1). The repo genuinely produces all three (`builder.py:12` renames features; `_apply_bindings` at `builder.py:675` writes `"D1@…"="GLOBAL"` equations; deferred-dim machinery keeps dims *driving*). |
| L9 | **Exactly one motion asset: the live-edit GIF.** All other interactivity/animation deferred (§7). | User relaxed the "static only" cut for the single highest-value proof, and only that one. Discipline on weight + verification. |

---

## 3. Structure

Two new blocks are inserted between the existing `<header class="hero">` and the
existing "Who are you? → start here" `<section>`. Final page order:

```
hero  →  ① Dead → Real → Survives-edit anchor  →  ② Workflow pipeline  →  doorways  →  essay  →  A4  →  CTA  →  footer
         └──────────────────── NEW ────────────────────┘                 └──────────── all UNTOUCHED ───────────┘
```

Both new blocks live inside the existing `<main>` and reuse the page's existing
tokens and utility classes verbatim — `--accent:#1e4fd8`, `--bg:#fbfbfc`, the
`.container` (max-width 760px), `.card`, `.grid-2up`, the system font stack, and
the three-state theme structure (bare `:root` light / `@media
(prefers-color-scheme: dark)`; the page has no `[data-theme]` toggle and this
enhancement does not add one). No new tokens, no new fonts, no CDN. New styles
are additive class rules appended to the existing `<style>` block.

---

## 4. Block ① — Dead → Real parametric model → Survives the edit

The first thing below the hero, and the enhancement's centerpiece. **All three
zones are real captures of the same widget on a live seat (Tier B, L4/L8).**
"Same widget" is a hard constraint: the alive tree, the dead-STEP `Imported1`,
and the live-edit clip are all the **same part** (the pillow-block the pipeline
uses), so the panes are provably one shape — one dead, one alive, one surviving
an edit. The spec does not hard-name the part, to stay consistent with whatever
the pipeline widget is.

**Zone 1 + 2 — the pair** (`.grid-2up`, two-up desktop / stacked mobile with the
dead tile on top):

| | Left — the foil | Right — the bridge |
|---|---|---|
| **Eyebrow** | "what most 'AI CAD' gives you" | "what the bridge builds" |
| **Image** | STEP import: a single frozen `Imported1` body, no history | the **named** editable tree (`SK_Block → EX_Block → SK_Bore → Cut_Bore → FIL_Block → Hole_MountA/B → CHA_BoreLeadIn`) **with the Equation Manager panel visible** — `"BORE_DIA" = 16`, globals linked from `locals.txt` |
| **Treatment** | muted / desaturated, plain border | full color, **accent border** (`--accent`) |

**Hinge line** below the pair: *"Same shape. Opposite futures."*

**Zone 3 — the surviving-edit proof (the one motion asset, L9):** directly below
the pair, a short looping GIF — `ai-sw-mutate` changes `BORE_DIA 16 → 20`, the
bore visibly grows, and the tree **rebuilds with 0 errors**. Caption line:
*"…and it survives the edit."* A one-line honesty tag confirms it is a recording
of a real seat, not a live browser kernel.

- **Alt text:** left = "STEP import collapsed to a single Imported1 solid, no
  feature history"; right = "the same part as a native SOLIDWORKS feature tree
  with named features and an Equation Manager driving the dimensions"; GIF = "the
  bore diameter changed from 16 to 20 mm; the feature tree rebuilds with no
  errors."
- **Copy carries the tier-3 point** explicitly but plainly: the right tile's
  supporting line names *"named features, driven by equations"*; the GIF line
  names *"rebuilds, 0 errors."* Together they say **real parametric model**, not
  *dumb tree* — without lecturing the newcomer on what a dumb tree is.
- **Weight (L9):** the GIF is short, looped, palette-optimized, target ≤ ~1 MB
  (same budget as the demo-suite clips); if a clean loop can't fit the budget,
  fall back to a 2-up before/after still (no motion) rather than ship a heavy
  asset.
- **Honesty (L6):** all three are real captures of a real seat; nothing implies
  the browser runs SOLIDWORKS; no caption claims anything not visible in the
  pixels.

---

## 5. Block ② — Workflow pipeline filmstrip

Chosen by the user over a grid and a fused single-image layout: an
arrow-connected filmstrip, because the arrows are **honest** — they depict the
real sequence produced from **one model**, not five disconnected features. All
five stills are **Tier A seat-free** frame extracts (§6).

**Intro line:** *"It doesn't stop at the part. The same model runs the whole
job:"*

Five arrow-connected tiles. Each = a real still + a proof line + the real tool:

| # | Tile | Proof line | Tool (verbatim) | Still source |
|---|---|---|---|---|
| 1 | **Part** | "A real, authored `.SLDPRT` — the seed of everything below." | `ai-sw-build` | `demo_part.gif` (build-complete frame) |
| 2 | **Assembly** | "Real mates, not fixed coordinates — the shaft seats through both bores." | `ai-sw-assembly` | `demo_assembly.gif` |
| 3 | **Observe / DFM** | "Interference, mass, bounding box — measured on SW's own kernel." | `ai-sw-observe` | `demo_observe.gif` (keeps the honest `[experimental]` section card) |
| 4 | **Drawing** | "Section A–A, auto-BOM, balloons — all from the one model." | `ai-sw-drawing` | `demo_drawing.gif` (real sheet: views + BOM + section) |
| 5 | **Export** | "STEP / STL / 3MF — and STEP round-trips back, Δbbox = 0." | **spec export block** (NOT a CLI) | `demo_export.gif` (**crop the burned-in `ai-sw-export` label**, §13-F2) |

**De-duplication (v2).** The parametric-rebuild story now lives **entirely in
Block ①**. So the Part tile is re-pointed away from `ai-sw-mutate` to
`ai-sw-build`: it is the **seed** of the breadth story ("here's the authored
part; watch it flow through the next four stages"), not a second rebuild claim.

**Same-widget continuity (v2).** All five stills — plus Block ①'s three assets —
are visibly the **same** pillow-block widget. An explicit line ties it together:
*"That's the same part in every frame — one model, all the way."* This turns the
"one model" arrows from an assertion into a proof.

**Phantom-CLI guard (L6).** Tile 5 must **never** cite an `ai-sw-export` command
— the CLI registry has no such entry point (only `ai-sw-export-dxf-flat` and
`ai-sw-import`; verified in `pyproject.toml [project.scripts]`). Export runs via
a spec `schema-v2` export block. The **extracted still must have the burned-in
`ai-sw-export` lower-third cropped/masked** before use (§13-F2).

**Assembly honesty (v2).** The GIFs never show a MateGroup tree, so the "real
mates" claim rests on the assembled render + the observe `interference = 0`, not
a mate-tree screenshot. The copy will not imply a mate-tree capture exists.

**No Tour tile.** Tour is meta (it reads the tool's own surface); it is not a
workflow stage, so including it would blur the "one model, all the way" story.

**Micro-line under the filmstrip** folds in the two secondary constraints
without a billboard: *"Every stage is propose → approve → execute — and the walls
are labeled, not hidden →"* linking to `../docs/known_limitations.md`.

- **Desktop:** horizontal row of tiles with `→` connectors; wraps gracefully;
  never forces a horizontal scrollbar on the page body.
- **Mobile:** vertical stack with **down-arrow** (`↓`) connectors — no sideways
  scroll.
- **Observe honesty (L6):** `min_wall` and `section_props` are **experimental**
  in the repo (parent demo-suite audit §13 F2/F3), and a one-line tile caption
  can't carry an "(experimental)" tag cleanly — so tile 3 lists only the
  **standard** reads (interference, mass, bounding box). The section/min-wall
  depth stays in the observe clip with its experimental label, not on the tile.

---

## 6. Proof medium & asset production

**Tier A — seat-free (5 assets):** single-frame ffmpeg extracts from the shipped,
verified clips, e.g.:

```
ffmpeg -i docs/img/demo_part.gif -vf "select=eq(n\,<frame>)" -vframes 1 docs/img/still_part.png
```

Frame chosen by eye for the clearest state (build complete, assembled, sectioned,
sheet+BOM, re-import card). PNGs land in `docs/img/`. The **export still**
additionally gets its burned-in `ai-sw-export` lower-third cropped/masked.

**Tier B — one seat session (3 assets):** none of these exist in any GIF (§13);
all are new non-destructive captures (open → observe → close without saving):

| Asset | How produced | Block |
|---|---|---|
| **dead-STEP `Imported1`** | export the widget → STEP, `ai-sw-import` back into a fresh doc, screenshot the collapsed `Imported1` tree | ① left |
| **alive tree + Equation Manager** | open the built widget, expand the FeatureManager (named features visible), open the Equation Manager (named globals visible), screenshot | ① right |
| **live-edit GIF** | record `ai-sw-mutate` changing `BORE_DIA 16 → 20`, capturing the bore growth + tree rebuild (0 errors); encode a short palette-optimized loop (≤ ~1 MB) | ① zone 3 |

The alive-tree and dead-STEP screenshots may be composed in one seat sitting; the
live-edit GIF is recorded in the same sitting. Non-destructive throughout.

---

## 7. YAGNI — deferred post-launch

Exactly **one** motion asset ships (the live-edit GIF, L9). Everything else
interactive/animated is cut from v1 and gated on the 14-day post-launch
measurement window:

- The `Spec → Feature Tree` interactive stepper mockup (throwaway artifact
  `https://claude.ai/code/artifact/4fdf83d4-3e30-4196-8423-c5f065a45573`) —
  measurement-gated, **not** shipped now.
- Any Dead ⇄ Alive toggle / hover-to-reveal on Block ①.
- Any animated or auto-playing filmstrip, or motion on the Block ② tiles.

Everything except the single Block ① GIF is a static real still. This keeps the
ship-with-launch change small, low-risk, and fast to verify across themes and
viewports.

---

## 8. Build, deploy & verification

**Tier A + authoring** (working tree; committed):
1. Extract the 5 seat-free breadth stills (§6); crop the export still's phantom
   label.
2. Author Block ① and Block ② as two `<section>`s in `site/index.html`, inserted
   after the hero, before the doorways; append their CSS to the existing
   `<style>` block. Source keeps `../docs/img/…` relative paths (L7). Block ①'s
   image slots reference the Tier-B assets (produced in step 5).
3. **Generalize `tools/build_pages.py`:** replace the single `HERO_SRC_REL` /
   `HERO_OUT_REL` copy with a **list** of assets (hero + 5 stills + the dead-STEP
   still + the alive-tree still + the live-edit GIF), each copied into `assets/`
   and its `src` repointed. The existing "fail loudly if any `../` survives"
   guard then covers them all. Add a test asserting each asset is copied +
   repointed.
4. Re-run `python tools/check_launch_kit.py` — the `../` on-disk paths lint green.

**Tier B — one seat session** (no final commit until produced):
5. Capture the 3 Block ① assets (§6): dead-STEP still, alive-tree+Equation still,
   live-edit GIF. Drop in `docs/img/`; wire into Block ①; re-verify.

**Verification:**
- **Defensibility (L6):** every caption / proof line checked line-by-line vs
  `docs/CAPABILITIES.md` + the CLI registry; phantom-CLI guard on tile 5 (and the
  cropped still) confirmed; the live-edit GIF labeled as a real-seat recording;
  no claim implies in-browser SOLIDWORKS.
- **Tier-3 check:** Block ① right actually shows **named** features (not
  `Sketch1`) and the **Equation Manager** with named globals; the GIF shows **0
  rebuild errors**. If any is not legibly visible, re-capture — a bare tree
  fails L8.
- **Local preview:** open `site/index.html` on disk — both blocks render, all
  eight assets resolve, the essay/doorways/CTA are visually unchanged.
- **Theme:** eyeball light + dark (system-pref) — the muted left tile and the
  accent-bordered right tile read in both; no color defined only in the dark
  media block.
- **Mobile:** narrow viewport — Block ① stacks (dead on top, GIF below), Block ②
  stacks with down-arrows, no horizontal page scroll.
- **Weight:** the live-edit GIF ≤ ~1 MB; total added page weight sane on a cold
  load.
- **Deploy:** `python tools/build_pages.py . _site`, confirm it copies every
  asset and exits clean; publish `_site/` to `gh-pages` via the existing orphan
  flow; verify every asset returns 200 on the live URL and both blocks render
  live.

---

## 9. Sequence

1. Extract the 5 seat-free breadth stills; crop the export still's phantom label.
2. Author the two `<section>` blocks + CSS in `site/index.html` (Block ① image
   slots point at the not-yet-captured Tier-B assets).
3. Generalize `tools/build_pages.py` (asset list) + add its test; re-lint with
   `check_launch_kit.py`.
4. **[seat session]** capture the 3 Block ① assets (dead-STEP still, alive-tree+
   Equation still, live-edit GIF); wire into Block ①.
5. Local preview + tier-3 check + defensibility pass + light/dark + mobile + weight.
6. Rebuild + redeploy `gh-pages`; verify every asset 200 on the live URL.
7. *(Then, separately and user-driven:)* Project B external sends fire against
   the improved Spine.

---

## 10. Deliverables

- `site/index.html`: two new `<section>` blocks (Block ① three-zone anchor +
  Block ② pipeline filmstrip) + additive CSS. Hero / doorways / essay / A4 / CTA /
  footer unchanged.
- `docs/img/`: 5 seat-free breadth stills (export still cropped) + 3 seat-gated
  Block ① assets (dead-STEP still, alive-tree+Equation still, live-edit GIF).
- `tools/build_pages.py`: generalized to copy a **list** of assets; new test
  covering asset copy + repoint.
- Redeployed `gh-pages` artifact with every asset resolving on the live URL.

---

## 11. Risks

| Risk | Handling |
|---|---|
| A caption overclaims (e.g. min-wall / export CLI) and a veteran spots it → whole page loses trust | Line-by-line defensibility pass vs `docs/CAPABILITIES.md` + CLI registry; phantom-CLI guard + cropped export still (§13-F2); min-wall kept off tile 3 (§5). |
| Block ① right reads as a *dumb tree* (tier 2) — auto-named or no equations visible | L8 tier-3 check: re-capture until named features **and** the Equation Manager with named globals are legibly visible; a bare tree fails verification. |
| Live-edit GIF too heavy / janky | ≤ ~1 MB palette-optimized short loop; if it can't be made clean + light, fall back to a static 2-up before/after (still proves the edit, no motion) — L9. |
| Seat session unavailable → Block ① blocked | Block ① is all Tier-B; per L5 the launch waits on the one seat session (no schematic substitute — L3). Tier-A breadth is done and committed meanwhile, so only the anchor is gated. |
| Extracted still illegible at tile size | Frame chosen by eye; eyeball gate; re-extract a different frame if weak. |
| A still invisible in one theme | Stills are theme-neutral PNGs on `--card-bg`; the left-tile desaturation is a CSS filter over a real image, checked in both themes. |
| `build_pages.py` drops an asset on publish | The "fail loudly if `../` survives" guard + the new per-asset copy test + the live-URL 200 check catch a missed asset. |
| Filmstrip forces horizontal page scroll on mobile | Vertical stack with down-arrows on narrow viewports; page body never scrolls sideways (§5). |
| **Cross-ref:** shipped `demo_export.gif` itself carries the phantom `ai-sw-export` label | Out of scope for this spec (landing page crops it), but recorded as a **demo-suite** defect to fix at the source (§13-F2). |
| Scope creep back into motion/interactivity | L9 caps motion at one asset; §7 defers the rest to the measurement gate. |

---

## 12. Traceability

- Brainstorm checklist: v1 tasks #58–65 (design → spec → committed `c6da48d`);
  v2 enhancement tasks #66–68 (verify veteran-tells → gap-analysis + 2 decisions
  → this revision).
- **v2 user decisions:** (1) add one live-edit GIF for the parametric proof;
  (2) one seat session, ship Block ① + ② together before launch.
- Approved-design checkpoint: memory `project_index_enhancement_design`.
- Relates to Project B Task 10 (task #57) — this ships **before** the external
  sends, which remain user-driven.

---

## 13. Enhancement audit (2026-08-14, v2)

Frame-by-frame inspection of the shipped `docs/img/demo_*.gif` during the
enhancement pass, plus a CLI-registry check. Findings that shaped v2:

- **F1 — the existing GIFs are graphics-area renders, not UI-chrome clips
  (blocker for v1's asset plan).** Every clip is a 3D-model render + a
  lower-third caption + a small info-card. **None** shows the FeatureManager tree,
  the Equation Manager, a dimension value, or a MateGroup. v1's assumption that
  the "alive tree" still (and 6-of-7 seat-free) could be extracted from
  `demo_part.gif` is false. **Resolution:** the seat scoping was rebuilt into the
  Tier A / Tier B split (L4); Block ①'s three assets are all new seat captures.
- **F2 — phantom CLI burned into `demo_export.gif` (honesty, L6).** Its
  lower-third reads `ai-sw-export`, which is **not** a console script (registry
  has only `ai-sw-export-dxf-flat` + `ai-sw-import`; `pyproject.toml
  [project.scripts]`). **Resolution (this spec):** the export *still* crops/masks
  that label and captions "spec export block." **Cross-ref (out of scope):** the
  GIF itself should be corrected in demo-suite scope.
- **F3 — the existing clips are already honest + well-captioned (positive).**
  `demo_observe` carries an `[experimental]` tag on the section; `demo_export`
  shows real round-trip numbers (bbox 40×28×30 mm, vol 26.58 cm³); `demo_drawing`
  shows a real BOM (3 line items) + section view. These make strong, defensible
  Tier-A stills as-is (modulo F2's crop).
- **F4 — the repo genuinely produces tier-3 output (positive; underpins L8).**
  `builder.py:12` renames features to the spec `name` (so the tree shows
  `SK_Block`, `Cut_Bore`, … not `Sketch1`); `_apply_bindings` (`builder.py:675`)
  writes `"D1@…" = "GLOBAL"` into the Equation Manager with globals linked from
  `locals.txt`; the deferred-dim machinery keeps dims **driving**, not driven.
  So the Block ① tier-3 proof is real, not aspirational.
