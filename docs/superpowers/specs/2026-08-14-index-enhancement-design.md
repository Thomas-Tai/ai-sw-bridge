# Landing-Page Breadth Enhancement (`site/index.html`) — Design

**Date:** 2026-08-14
**Status:** Design — approved by user (awaiting spec review → writing-plans)
**Owner:** repo maintainer
**Parent:** the landing page `site/index.html` exists and is live on the `gh-pages`
branch at `https://thomas-tai.github.io/ai-sw-bridge/`, built by
`tools/build_pages.py` (see `site/README.md`). It is the **"Spine"** every
Project B launch asset links back to. This spec is an **enhancement pass** over
that page, brainstormed through a 20-year-SOLIDWORKS-veteran lens.
**Target artifact:** a fresh visitor — especially a skeptical CAD veteran who
assumes "AI CAD" is another throwaway-kernel LLM wrapper — absorbs, in their
first ~15 seconds, that the bridge's output is **alive** (a native editable
tree, not a dead `Imported1` solid) **and** that it **goes all the way to
manufacturing** (part → assembly → DFM → drawing → export).

---

## 1. Goal & framing

The page today opens strong on the *thesis* ("drive your real SOLIDWORKS seat
from a JSON spec") but proves it almost entirely in **prose**. A veteran skims
prose in five seconds and bounces, pattern-matching to "just another LLM
wrapper," before the essay's real arguments land. The single scarcest currency
on a launch landing page is the newcomer's first fifteen seconds; right now
those seconds carry a headline and a hero GIF but no *breadth* proof and no
*aliveness* proof at a glance.

This enhancement spends those fifteen seconds on the two halves of the **trust
coin**:

- **Output is alive** — a Dead-STEP-vs-Native-Tree side-by-side, so the one
  thing a code-CAD generator structurally cannot produce (an editable feature
  tree) is the first thing the eye lands on.
- **Goes all the way** — a five-stage workflow pipeline, so "it makes a part"
  reads instead as "it runs the whole job."

**Primary anchor (locked, user-reasserted): breadth.** Native-tree is the
*philosophy lead*; breadth is the *absolute primary anchor* — the thing that
proves the tool is not a toy. Safety (propose → approve → execute) and honesty
(labeled kernel walls) are **secondary constraints woven into the copy**, not
their own billboards.

### Non-goals

- **Not a redesign.** The hero, wedge headline, "Who are you?" doorways, the
  five-beat essay, the A4 explainer, the CTA, and the footer are all
  **untouched**. This is two inserted `<section>` blocks and one generalization
  of the build script — nothing else.
- **Not interactive.** All interactivity is deferred post-launch (see §7 YAGNI).
  v1 is static, real captured stills only.
- **Not new geometry or new capability.** Every still depicts a capability the
  repo already ships and the existing demo GIFs already prove.
- **Not a launch task.** Firing the external sends (Show HN / X / Reddit /
  LinkedIn / registry PRs) is Project B Task 10 and is **user-driven**. This
  enhancement ships *before* those sends so the Spine is at its best when they
  fire; it does not itself send anything.

---

## 2. Locked decisions

| # | Decision | Rationale |
|---|---|---|
| L1 | **Breadth is the absolute primary anchor; native-tree is the philosophy lead.** Safety + skimmability are secondary constraints woven into copy, not separate billboards. | User reasserted breadth as primary; a veteran's "is this a toy?" is answered by breadth, their "is the output real?" by the tree. |
| L2 | **Incremental — ships WITH the launch.** Two new `<section>` blocks inserted after the hero, before the doorways. Everything else on the page is untouched. | First impressions are brutal; the Spine must be at its best before any external send links to it. Minimal structural change keeps risk low. |
| L3 | **Real captured SOLIDWORKS imagery, never schematic illustration.** | A veteran discounts illustrations instantly. Real FeatureManager pixels are the proof; a drawn diagram is not. |
| L4 | **Reuse existing verified GIFs as the still source.** 5 workflow stills + the alive-tree still = ffmpeg single-frame extracts from the already-shipped, already-verified `docs/img/demo_*.gif`. | Zero new recording, zero seat needed for six of seven assets; the frames are already vetted content. |
| L5 | **Exactly one seat-gated asset: the dead-STEP `Imported1` screenshot.** | It is the only image the repo doesn't already have; it needs a live seat to produce (export the widget → STEP, re-import, screenshot the collapsed tree). Critical-path dependency, isolated to one step. |
| L6 | **Honesty (defensibility) over polish.** Every caption must be defensible against `docs/CAPABILITIES.md`; no phantom CLI; no implication of live in-browser SOLIDWORKS. | Carried standing constraint. Candor is the edge over a confident-but-thin competitor — a single overclaim spotted by a veteran forfeits the whole page. |
| L7 | **Source keeps `../`-relative paths; the build script does the publish rewrite.** `tools/build_pages.py` is generalized from one hero copy to a list of stills. | Preserves the on-disk lint convention (`check_launch_kit.py` verifies `../` paths); the existing "fail loudly if `../` survives" guard then covers every new still for free. |

---

## 3. Structure

Two new blocks are inserted between the existing `<header class="hero">` and the
existing "Who are you? → start here" `<section>`. Final page order:

```
hero  →  ① Dead-vs-Alive anchor  →  ② Workflow pipeline  →  doorways  →  essay  →  A4 explainer  →  CTA  →  footer
         └──────────────── NEW ────────────────┘            └──────────── all UNTOUCHED ────────────┘
```

Both new blocks live inside the existing `<main>` and reuse the page's existing
tokens and utility classes verbatim — `--accent:#1e4fd8`, `--bg:#fbfbfc`, the
`.container` (max-width 760px), `.card`, `.grid-2up`, the system font stack, and
the three-state theme structure (bare `:root` light / `@media
(prefers-color-scheme: dark)` / — the page has no `[data-theme]` toggle and this
enhancement does not add one). No new tokens, no new fonts, no CDN. New styles
are additive class rules appended to the existing `<style>` block.

---

## 4. Block ① — Dead-vs-Alive anchor

The first thing below the hero. Two real SOLIDWORKS FeatureManager screenshots
of the **same widget**, side by side. "Same widget" is a hard constraint: the
right (alive) tile is a frame of `demo_part.gif`, and the left (dead) tile's
`Imported1` capture (L5) **must be that same part** exported to STEP and
re-imported — so the two panes are provably one shape, one dead / one alive.
The widget is therefore whatever part `demo_part.gif` shows (the same one in the
hero and the Part chapter); the spec does not hard-name it, to avoid asserting a
part identity that could mismatch the recorded clip.

| | Left — the foil | Right — the bridge |
|---|---|---|
| **Eyebrow** | "what most 'AI CAD' gives you" | "what the bridge builds" |
| **Image** | STEP import: a single frozen `Imported1` body, no history | the full editable tree (Sketch1 → Boss-Extrude1 → Cut-Bore → Fillet → mount holes → chamfer) with a visible driving dimension / equation |
| **Treatment** | muted / desaturated, plain border | full color, **accent border** (`--accent`) |

**Hinge line** below the pair: *"Same shape. Opposite futures."*

- **Layout:** `.grid-2up` (already `repeat(auto-fit, minmax(260px, 1fr))`), so it
  is naturally two-up on desktop and single-column on mobile.
- **Mobile:** stacks; **dead solid on top**, so the "and then it comes alive"
  reveal reads top-to-bottom.
- **Alt text:** left = "STEP import collapsed to a single Imported1 solid, no
  feature history"; right = "the same part as a native SOLIDWORKS feature tree —
  sketch, extrude, cut, fillet, holes, chamfer — each still editable."
- **Honesty (L6):** both are real captured screenshots of a real seat; neither
  implies the browser is running SOLIDWORKS. No caption claims anything not
  visible in the pixels.

---

## 5. Block ② — Workflow pipeline filmstrip

Chosen by the user over a grid and over a fused single-image layout: an
arrow-connected filmstrip, because the arrows are **honest** — they depict the
real sequence produced from **one model**, not five disconnected features.

**Intro line:** *"It doesn't stop at the part. The same model runs the whole
job:"*

Five arrow-connected tiles. Each = a real still (§6) + a proof line + the real
tool that produces it:

| # | Tile | Proof line | Tool (verbatim) | Still source |
|---|---|---|---|---|
| 1 | **Part** | "Change one number → the real feature tree rebuilds." | `ai-sw-build` · `ai-sw-mutate` | `demo_part.gif` |
| 2 | **Assembly** | "Real mates, not fixed coordinates — the shaft seats through both bores." | `ai-sw-assembly` | `demo_assembly.gif` |
| 3 | **Observe / DFM** | "Interference, mass, bounding box — measured on SW's own kernel." | `ai-sw-observe` | `demo_observe.gif` |
| 4 | **Drawing** | "Section A–A, auto-BOM, balloons — all from the one model." | `ai-sw-drawing` | `demo_drawing.gif` |
| 5 | **Export** | "STEP / STL / 3MF — and STEP round-trips back, Δbbox = 0." | **spec export block** (NOT a CLI) | `demo_export.gif` |

**Phantom-CLI guard (L6):** tile 5 must **never** cite an `ai-sw-export`
command — no such entry point exists. Export runs via a spec `schema-v2` export
block (DXF via `ai-sw-export-dxf-flat`). The tile labels the mechanism as a
"spec export block," consistent with the README capability table.

**No Tour tile.** Tour is meta (it reads the tool's own surface); it is not a
workflow stage, so including it would blur the "one model, all the way" story.

**Micro-line under the filmstrip** folds in the two secondary constraints
without a billboard: *"Every stage is propose → approve → execute — and the
walls are labeled, not hidden →"* linking to `../docs/known_limitations.md`.

- **Desktop:** horizontal row of tiles with `→` connectors between them; wraps
  gracefully. Must never force a horizontal scrollbar on the page body (any
  overflow container scrolls within itself).
- **Mobile:** vertical stack with **down-arrow** (`↓`) connectors — no sideways
  scroll.
- **Honesty (L6):** every proof line is checked against `docs/CAPABILITIES.md`
  before ship (see §8). `min_wall` and `section_props` are **experimental** in
  the repo (the parent demo-suite spec's audit, §13 F2/F3), and a one-line tile
  caption cannot carry an "(experimental)" tag cleanly — so tile 3 deliberately
  lists only the **standard, non-experimental** reads (interference, mass,
  bounding box). Defensibility wins over completeness: the DFM depth
  (section sweep, min-wall) lives in the demo clip with its experimental label,
  not on the landing tile.

---

## 6. Proof medium & asset production

**Six of seven assets are seat-free** — single-frame extracts from existing,
already-verified GIFs via ffmpeg, e.g.:

```
ffmpeg -i docs/img/demo_part.gif -vf "select=eq(n\,<frame>)" -vframes 1 docs/img/still_part.png
```

The exact frame per clip is chosen by eye to show the most legible proof state
(tree visible, section drawn, BOM populated, etc.). Output PNGs land in
`docs/img/` alongside the GIFs. Assets:

| Asset | Source | Seat? |
|---|---|---|
| alive-tree (Block ① right) | frame of `demo_part.gif` showing the FeatureManager tree | no |
| part still | `demo_part.gif` | no |
| assembly still | `demo_assembly.gif` | no |
| observe still | `demo_observe.gif` | no |
| drawing still | `demo_drawing.gif` | no |
| export still | `demo_export.gif` | no |
| **dead-STEP (Block ① left)** | **new capture: export the widget → STEP, `ai-sw-import` back into a fresh doc, screenshot the collapsed `Imported1` tree** | **YES — the one seat-gated step (L5)** |

All captures are non-destructive (open → observe → close without saving) per the
standing renderer rule.

---

## 7. YAGNI — deferred post-launch

Everything interactive is cut from v1 and gated on the 14-day post-launch
measurement window:

- The `Spec → Feature Tree` interactive stepper mockup (throwaway artifact
  `https://claude.ai/code/artifact/4fdf83d4-3e30-4196-8423-c5f065a45573`) — a
  measurement-gated candidate, **not** shipped now.
- Any Dead ⇄ Alive toggle / hover-to-reveal on Block ①.
- Any animated or auto-playing filmstrip.

v1 is static real stills. This keeps the ship-with-launch change small, low-risk,
and fast to verify across themes and viewports.

---

## 8. Build, deploy & verification

**Source edits** (working tree; committed):
1. Extract the 6 seat-free stills (§6).
2. Author Block ① and Block ② as two `<section>`s in `site/index.html`, inserted
   after the hero, before the doorways; append their CSS to the existing
   `<style>` block. Source keeps `../docs/img/still_*.png` relative paths (L7).
3. **Generalize `tools/build_pages.py`:** replace the single `HERO_SRC_REL` /
   `HERO_OUT_REL` copy with a **list** of image assets (hero + the new stills),
   each copied into `assets/` and its `src` repointed. The existing "fail loudly
   if any `../` survives the rewrite" guard already covers the new stills. Add a
   small test asserting each still is copied and repointed.
4. Re-run `python tools/check_launch_kit.py` — the `../` on-disk paths must lint
   green.

**Seat-gated** (one step, no commit until produced):
5. Capture the dead-STEP `Imported1` screenshot (L5); drop it in `docs/img/`;
   wire it into Block ① left.

**Verification:**
- **Defensibility (L6):** every caption / proof line checked line-by-line
  against `docs/CAPABILITIES.md` and README; the phantom-CLI guard on tile 5
  confirmed; no claim implies in-browser SOLIDWORKS.
- **Local preview:** open `site/index.html` on disk — both blocks render, all
  seven images resolve, the essay/doorways/CTA are visually unchanged.
- **Theme:** eyeball light and dark (system-pref) — the muted/desaturated left
  tile and the accent-bordered right tile read correctly in both; no color is
  defined only inside the dark media block.
- **Mobile:** narrow viewport — Block ① stacks (dead on top), Block ② stacks
  with down-arrows, no horizontal page scroll.
- **Deploy:** `python tools/build_pages.py . _site`, confirm it copies every
  still and exits clean; publish `_site/` to `gh-pages` via the existing orphan
  flow; then verify every asset returns 200 on the live URL and both blocks
  render live.

---

## 9. Sequence

1. Extract the 6 seat-free stills.
2. Author the two `<section>` blocks + CSS in `site/index.html`.
3. Generalize `tools/build_pages.py` (list of stills) + add its test; re-lint
   with `check_launch_kit.py`.
4. Local preview + defensibility pass + light/dark + mobile eyeball.
5. **[seat]** capture the dead-STEP still; wire into Block ① left; re-verify.
6. Rebuild + redeploy `gh-pages`; verify every asset 200 on the live URL.
7. *(Then, separately and user-driven:)* Project B external sends fire against
   the improved Spine.

---

## 10. Deliverables

- `site/index.html`: two new `<section>` blocks (Dead-vs-Alive anchor + workflow
  pipeline filmstrip) + additive CSS. Hero / doorways / essay / A4 / CTA / footer
  unchanged.
- `docs/img/still_*.png`: 6 seat-free stills + 1 seat-gated dead-STEP screenshot.
- `tools/build_pages.py`: generalized to copy a **list** of image assets; new
  test covering still copy + repoint.
- Redeployed `gh-pages` artifact with every asset resolving on the live URL.

---

## 11. Risks

| Risk | Handling |
|---|---|
| A caption overclaims (e.g. min-wall / export CLI) and a veteran spots it → whole page loses trust | Line-by-line defensibility pass vs `docs/CAPABILITIES.md`; explicit phantom-CLI guard on tile 5; min-wall fallback wording (§5). |
| Extracted still is illegible at tile size | Frame chosen by eye for the clearest proof state; eyeball gate before ship; re-extract a different frame if weak. |
| Dead-STEP capture blocked (no seat available now) | It is the *only* seat-gated asset; the other six ship regardless. Block ① can hold with a placeholder note until the seat frees, but v1 is not "done" until the real capture lands (no schematic substitute — L3). |
| A still defined only for one theme goes invisible | Stills are theme-neutral PNGs on `--card-bg`; the desaturation on the left tile is a CSS filter over a real image, checked in both themes. |
| `build_pages.py` change drops a still on publish | The existing "fail loudly if `../` survives" guard + the new per-still copy test catch a missed asset before deploy; live-URL 200 check is the backstop. |
| Filmstrip forces horizontal page scroll on mobile | Vertical stack with down-arrows on narrow viewports; page body never scrolls sideways (§5). |
| Scope creep back into interactivity | YAGNI cut (§7) is explicit; interactivity is measurement-gated, not part of v1. |

---

## 12. Traceability

- Brainstorm checklist tasks #58–65; this document closes #62.
- Approved-design checkpoint: memory `project_index_enhancement_design`.
- Relates to Project B Task 10 (task #57) — this ships **before** the external
  sends, which remain user-driven.
