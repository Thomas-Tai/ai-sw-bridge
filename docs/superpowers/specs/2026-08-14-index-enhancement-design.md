# Landing-Page Breadth Enhancement (`site/index.html`) — Design

**Date:** 2026-08-14
**Status:** Design — **enhanced (v3)**, approved by user (awaiting spec review → writing-plans)
**Owner:** repo maintainer
**Parent:** the landing page `site/index.html` exists and is live on the `gh-pages`
branch at `https://thomas-tai.github.io/ai-sw-bridge/`, built by
`tools/build_pages.py` (see `site/README.md`). It is the **"Spine"** every
Project B launch asset links back to. This spec is an **enhancement pass** over
that page, brainstormed through a 20-year-SOLIDWORKS-veteran lens.
**Target artifact:** a fresh visitor — especially a skeptical CAD veteran who
assumes "AI CAD" is another throwaway-kernel LLM wrapper — absorbs, in their
first ~15 seconds, that the bridge's output is **a real parametric model** (named
feature tree + driving equations that **survive an edit**, not a frozen
`Imported1` solid *and not a dumb one-shot tree*), that it **goes all the way to
manufacturing** (part → assembly → DFM → drawing → export), and that it does so
across a **wide feature/mate surface** (not just the prismatic demo part).

> **Revision history.**
> - **v1** (`c6da48d`): two-state "alive vs dead" anchor + 5-tile breadth
>   filmstrip; assumed the alive tree was a free frame-extract; essay/A4 frozen.
> - **v2** (`beb5051`): deepened Block ① to three states (dead → real parametric
>   model → survives the edit); corrected the seat scoping after frame inspection
>   (§13); added the phantom-CLI crop.
> - **v3** (this doc): after the visual proof landed up top, the existing essay +
>   A4 explainer became **redundant** with it. v3 adds a **subtractive flow pass**
>   (cut the repeated dead-vs-alive prose; re-point the survivors to *safety +
>   speed*, which the visuals don't narrate) and a **feature/mate breadth strip**
>   (answer "does it only do simple parts?" with defensible counts).

---

## 1. Goal & framing

The page today opens strong on the *thesis* ("drive your real SOLIDWORKS seat
from a JSON spec") but proves it almost entirely in **prose**. A veteran skims
prose in five seconds and bounces, pattern-matching to "just another LLM
wrapper," before the essay's real arguments land. The scarcest currency on a
launch landing page is the newcomer's first fifteen seconds.

**The veteran's real skepticism has three tiers, not two.** A 20-year seat-holder
distinguishes:

1. **Dead solid** — an `Imported1` STEP body, no history. (Obviously not a design.)
2. **Dumb tree** — a linear pile of `Sketch1 / Boss-Extrude1 / Boss-Extrude2…`,
   hard-coded dims, under-defined sketches. **An LLM can emit this.** It *looks*
   alive and **shatters on the first edit.**
3. **Real parametric model** — named features, dims driven by *named equations /
   globals*, driving constraints, and it **survives a dimension change with a
   clean rebuild.**

A static "here's a tree" screenshot doesn't separate tier 2 from tier 3 — and a
skeptic *assumes* tier 2. So the enhancement spends the fifteen seconds on the
three-sided trust coin (Block ①), then proves breadth (Block ②):

- **Output is a real parametric model** — Dead-STEP-vs-Named-Tree with the
  **Equation Manager** visible.
- **It survives the edit** — a short looping clip of `BORE_DIA 16 → 20`, tree
  rebuilds, **0 errors**.
- **It goes all the way** — a five-stage workflow pipeline.
- **…across a wide surface** — a compact breadth strip: **36 feature kinds** +
  **16 mate types**, so the pillow-block reads as one example, not the only trick.

**Third-pass refinement (the flow pass).** Once Block ① *shows* the
dead-vs-alive argument, three existing prose passages **repeat it in words**:
essay beat 1 ("The problem" — dead STEP dump), essay beat 3 ("Native editable
feature tree vs. foreign STEP"), and the entire A4 explainer ("Real seat" vs
"Throwaway-kernel → STEP dump"). On a page that has just grown by two blocks,
saying the same thing three-to-four times reads as padding. The veteran-grade
move is **cut, not add**: let the picture carry the dead-vs-alive argument, and
re-point the surviving prose to what the visuals *don't* narrate — the **safety
gate** (propose → approve → execute), the **honest kernel walls**, and the
**no-seat speed** to start.

**Primary anchor (locked, user-reasserted): breadth.** Parametric-reality is the
*philosophy lead*; breadth is the *absolute primary anchor*. Safety and honesty
are secondary constraints — now carried by the **re-focused essay** rather than
duplicated billboards.

### Non-goals

- **Not a redesign.** Untouched: the hero, wedge headline, the "Who are you?"
  doorways, the CTA, the footer, the page's tokens/theme structure. **Changed by
  the v3 flow pass:** the essay is **trimmed and re-pointed** (not restructured),
  and the A4 explainer is **removed** (its argument is now Block ①). See §6.
- **Not a general relaxation of the no-motion rule.** Exactly **one** motion
  asset ships (the live-edit GIF, L9); every other interactive/animated idea
  stays deferred (§8).
- **Not new geometry or new capability.** Breadth stills reuse existing verified
  clips; Block ① assets are new *captures of existing capability*; the breadth
  strip is text sourced from `docs/CAPABILITIES.md`.
- **Not a launch task.** Firing the external sends (Show HN / X / Reddit /
  LinkedIn / registry PRs) is Project B Task 10 and is **user-driven**. This ships
  *before* those sends; it does not itself send anything.

---

## 2. Locked decisions

| # | Decision | Rationale |
|---|---|---|
| L1 | **Breadth is the absolute primary anchor; parametric-reality is the philosophy lead.** | A veteran's "is this a toy?" is answered by breadth; their "is the output real, or a dumb tree?" by the named tree + equations + surviving-edit proof. |
| L2 | **Incremental — ships WITH the launch.** New content is inserted after the hero, before the doorways; the flow pass edits the essay + removes the A4 in place. | The Spine must be at its best before any external send links to it. |
| L3 | **Real captured SOLIDWORKS imagery, never schematic illustration.** | A veteran discounts illustrations instantly. Real FeatureManager / Equation-Manager pixels are the proof. |
| L4 | **Two seat-dependency tiers.** *Tier A (seat-free):* 5 Block ② breadth stills = ffmpeg extracts from shipped GIFs. *Tier B (one seat session):* 3 Block ① assets (dead-STEP still · alive-tree+Equation still · live-edit GIF) — none exist in any GIF (§13). | Frame inspection proved the GIFs are graphics-area renders with no tree/equation chrome. |
| L5 | **One focused seat session, before launch; Block ① + ② + flow pass ship together.** | The parametric-reality hook is the point; it must be present when first impressions form. |
| L6 | **Honesty (defensibility) over polish.** Every caption/number defensible against `docs/CAPABILITIES.md` + the CLI registry; no phantom CLI; the breadth strip lists only *supported* features (no lofts/ribs/wraps — those are the honestly-refused walls); no implication of live in-browser SOLIDWORKS. | Candor is the edge; one overclaim a veteran spots forfeits the page. |
| L7 | **Source keeps `../`-relative paths; the build script does the publish rewrite.** `tools/build_pages.py` generalizes to a **list** of assets. | Preserves the on-disk lint convention; the existing "fail loudly if `../` survives" guard covers new assets. |
| L8 | **Block ① proves tier-3, not tier-2.** Must show **named features** (not `Sketch1`) **and** the **Equation Manager** with named globals **and** a surviving edit. | The repo genuinely produces all three (`builder.py:12`, `builder.py:675`, deferred-dim machinery). |
| L9 | **Exactly one motion asset: the live-edit GIF.** | User relaxed the "static only" cut for the single highest-value proof, and only that one. |
| L10 | **Subtractive flow pass:** cut the redundant dead-vs-alive prose (essay beats 1 & 3, the whole A4 block); re-point the essay to **safety + honest walls + no-seat speed**. | With Block ① showing the argument, repeating it in prose is padding; the page should read tight. User-directed. |
| L11 | **Feature/mate breadth strip** adjacent to the filmstrip: **36 feature kinds** (extrude/cut/revolve + the CAPABILITIES table) and **16 mate types** (incl. gear, rack-and-pinion, cam-follower, slot, hinge, linear-coupler). Text only, no captures. | Answers "does it only do simple prismatic parts?" Counts verified against source (§13-F5). |

---

## 3. Structure

New blocks inserted between `<header class="hero">` and the "Who are you?"
`<section>`; the flow pass edits the essay and removes the A4 in place. Final
page order:

```
hero → ① Dead→Real→Survives anchor → ② Pipeline + breadth strip → doorways → essay(re-focused) → CTA → footer
       └────────────── NEW ──────────────┘                         └ trimmed ┘  └ A4 removed ┘
```

Both new blocks reuse the page's existing tokens/utility classes verbatim
(`--accent:#1e4fd8`, `.container` max-width 760px, `.card`, `.grid-2up`, the
system font stack, the three-state theme structure). No new tokens/fonts/CDN.
New styles are additive class rules appended to the existing `<style>` block.
The essay keeps its `id="essay"` (the doorways and CTA anchor to it).

---

## 4. Block ① — Dead → Real parametric model → Survives the edit

The enhancement's centerpiece. **All three zones are real captures of the same
widget on a live seat (Tier B, L4/L8).** "Same widget" is a hard constraint: the
alive tree, the dead-STEP `Imported1`, and the live-edit clip are the **same
part**, so the panes are provably one shape — one dead, one alive, one surviving
an edit.

**Zones 1 + 2 — the pair** (`.grid-2up`, two-up desktop / stacked mobile, dead on
top):

| | Left — the foil | Right — the bridge |
|---|---|---|
| **Eyebrow** | "what most 'AI CAD' gives you" | "what the bridge builds" |
| **Image** | STEP import: a single frozen `Imported1` body, no history | the **named** editable tree (`SK_Block → EX_Block → SK_Bore → Cut_Bore → FIL_Block → Hole_MountA/B → CHA_BoreLeadIn`) **with the Equation Manager visible** — `"BORE_DIA" = 16`, globals linked from `locals.txt` |
| **Treatment** | muted / desaturated, plain border | full color, **accent border** (`--accent`) |

**Hinge line:** *"Same shape. Opposite futures."*

**Zone 3 — the surviving-edit proof (the one motion asset, L9):** below the pair,
a short looping GIF — `ai-sw-mutate` changes `BORE_DIA 16 → 20`, the bore grows,
the tree **rebuilds with 0 errors**. Caption: *"…and it survives the edit."* A
one-line tag confirms it is a recording of a real seat, not a live browser kernel.

- **Alt text:** left = "STEP import collapsed to a single Imported1 solid, no
  history"; right = "the same part as a native tree with named features and an
  Equation Manager driving the dimensions"; GIF = "bore diameter changed 16→20 mm;
  the tree rebuilds with no errors."
- **Copy carries the tier-3 point plainly:** the right tile names *"named
  features, driven by equations"*; the GIF names *"rebuilds, 0 errors."*
- **Weight (L9):** short, looped, palette-optimized, ≤ ~1 MB; if a clean loop
  can't fit, fall back to a static 2-up before/after (no motion).
- **Honesty (L6):** all real captures; nothing implies the browser runs SW.

---

## 5. Block ② — Workflow pipeline filmstrip + breadth strip

An arrow-connected filmstrip (chosen over grid / fused image): the arrows are
**honest** — one model, real sequence. All five stills are **Tier A seat-free**
frame extracts (§7).

**Intro line:** *"It doesn't stop at the part. The same model runs the whole
job:"*

| # | Tile | Proof line | Tool | Still source |
|---|---|---|---|---|
| 1 | **Part** | "A real, authored `.SLDPRT` — the seed of everything below." | `ai-sw-build` | `demo_part.gif` (build-complete frame) |
| 2 | **Assembly** | "Real mates, not fixed coordinates — the shaft seats through both bores." | `ai-sw-assembly` | `demo_assembly.gif` |
| 3 | **Observe / DFM** | "Interference, mass, bounding box — measured on SW's own kernel." | `ai-sw-observe` | `demo_observe.gif` (keeps the honest `[experimental]` section card) |
| 4 | **Drawing** | "Section A–A, auto-BOM, balloons — all from the one model." | `ai-sw-drawing` | `demo_drawing.gif` (real sheet: views + BOM + section) |
| 5 | **Export** | "STEP / STL / 3MF — and STEP round-trips back, Δbbox = 0." | **spec export block** (NOT a CLI) | `demo_export.gif` (**crop the burned-in `ai-sw-export` label**, §13-F2) |

**De-duplication (v2).** The rebuild story lives **entirely in Block ①**, so the
Part tile is `ai-sw-build` — the **seed** of the breadth story, not a second
rebuild claim.

**Same-widget continuity (v2).** All five stills + Block ①'s three assets are the
**same** pillow-block. An explicit line — *"That's the same part in every frame —
one model, all the way."* — turns the "one model" arrows into proof.

### Breadth strip (v3, L11) — directly under the tiles, before the micro-line

A dense, scannable, **text-only** strip that answers *"does it only do simple
prismatic parts?"* — sourced from `docs/CAPABILITIES.md` and verified against
source (§13-F5). Two lines:

- **Features:** *"The demo part uses a handful of features. The bridge builds
  **extrude · cut · revolve** over 7 sketch primitives, plus **36 more feature
  kinds** — fillets, chamfers, shell, draft, linear/circular/mirror/sketch
  patterns, sweeps & sweep-cuts, dome, hole wizard, helix/spiral/projected curves,
  planar/offset/knit surfaces, sheet-metal (base flange · hem · bend), weldments,
  boolean (intersect · scale · delete-body)."*
- **Mates:** *"**16 mate types** — incl. gear, rack-and-pinion, cam-follower,
  slot, hinge, width, linear-coupler — not just coincident/concentric."*
- Cross-ref: *"(full matrix → `CAPABILITIES.md`)."*

**Honesty (L6, critical).** The strip lists only **supported** kinds. It must
**not** name **lofts, ribs, wraps, or combines** — those are the honestly-refused
kernel walls (essay + `known_limitations.md`). The pairing is deliberate: the
strip proves *wide* support; the essay owns *what it won't fake*. That contrast is
the trust signal, not a gap.

**Phantom-CLI guard (L6).** Tile 5 must never cite `ai-sw-export` — the CLI
registry has only `ai-sw-export-dxf-flat` + `ai-sw-import` (`pyproject.toml`).
The extracted export still gets the burned-in `ai-sw-export` lower-third cropped
(§13-F2).

**Assembly honesty (v2).** No MateGroup chrome is shown; the "real mates" claim
rests on the render + observe `interference = 0`, not a mate-tree screenshot.

**No Tour tile.** Tour is meta, not a workflow stage.

**Micro-line under the strip:** *"Every stage is propose → approve → execute — and
the walls are labeled, not hidden →"* → `../docs/known_limitations.md`.

- **Desktop:** horizontal tile row with `→` connectors; wraps; no page-body
  horizontal scroll. **Mobile:** vertical stack with `↓` connectors. The breadth
  strip wraps naturally on both.
- **Observe honesty (L6):** `min_wall` / `section_props` are **experimental**;
  tile 3 lists only the standard reads (interference, mass, bbox).

---

## 6. Existing-prose flow pass (v3, L10)

With Block ① carrying the dead-vs-alive argument visually, the essay and A4 are
edited **in place** to stop repeating it and to say what the visuals don't.

**Essay (`<article id="essay">`).** Current: 5 beats titled *"Driving real
SOLIDWORKS from an AI agent — and why it's hard."* Re-flow to a **safety + speed**
essay (~3 beats); keep the `#essay` anchor:

| Current beat | Action | Why |
|---|---|---|
| 1 — "The problem" (dead STEP/mesh dump) | **cut** | Block ① shows it. |
| 2 — "Propose → approve → execute" | **keep, lead with it** | Safety gate; visuals don't narrate it. |
| 3 — "Native editable tree vs. foreign STEP" | **cut** | Block ① + the GIF show it. |
| 4 — "The real kernel walls" | **keep** | Honesty/trust; pairs with the breadth strip's "no lofts." |
| 5 — "Try it with no seat" (Tier A) | **keep** | Speed/access to start. |

Retitle to a safety/speed framing (final copy an implementation detail, e.g.
*"Human-gated — and quick to try"*). Net: essay shrinks from 5 beats to 3, none
duplicating the visuals.

**A4 explainer block (`.a4-block` "AI + SOLIDWORKS — which fits your job?").**
**Remove entirely.** Its "real seat vs throwaway kernel" table is exactly what
Block ① now shows; keeping it is the largest single redundancy. (Its self-select
nuance — "which fits depends on what you'll do next" — is already implied by the
doorways + Block ①.)

**Scope guard:** this is trimming/re-pointing, not a rewrite of the page's voice.
The doorways and CTA (which anchor to `#essay`) are unchanged and stay consistent
with the now safety-led essay.

---

## 7. Proof medium & asset production

**Tier A — seat-free (5 assets):** single-frame ffmpeg extracts, e.g.
`ffmpeg -i docs/img/demo_part.gif -vf "select=eq(n\,<frame>)" -vframes 1
docs/img/still_part.png`. Frame chosen by eye. The **export still** additionally
gets its burned-in `ai-sw-export` lower-third cropped/masked.

**Tier B — one seat session (3 assets):** none exist in any GIF (§13); all new
non-destructive captures (open → observe → close without saving):

| Asset | How produced | Block |
|---|---|---|
| **dead-STEP `Imported1`** | export widget → STEP, `ai-sw-import` back into a fresh doc, screenshot the collapsed `Imported1` tree | ① left |
| **alive tree + Equation Manager** | open the built widget, expand FeatureManager (named features), open Equation Manager (named globals), screenshot | ① right |
| **live-edit GIF** | record `ai-sw-mutate` `BORE_DIA 16 → 20` (bore growth + tree rebuild, 0 errors); short palette-optimized loop ≤ ~1 MB | ① zone 3 |

The breadth strip (§5) is **text**, no asset. The flow pass (§6) edits HTML, no
asset.

---

## 8. YAGNI — deferred post-launch

Exactly **one** motion asset ships (the live-edit GIF, L9). Deferred (14-day
post-launch measurement gate): the `Spec → Feature Tree` interactive stepper
(artifact `4fdf83d4-…`); any Dead ⇄ Alive toggle; any animated filmstrip or tile
motion. Everything except the single Block ① GIF is a static still or plain text.

---

## 9. Build, deploy & verification

**Tier A + authoring + flow pass** (working tree; committed):
1. Extract the 5 seat-free breadth stills (§7); crop the export still's label.
2. Author Block ① + Block ② (incl. the breadth strip) as `<section>`s after the
   hero; append CSS. Block ① image slots reference the Tier-B assets (step 5).
3. **Flow pass (§6):** trim the essay to 3 beats + retitle; **remove** the A4
   block. Verify `#essay` anchor still resolves from the doorways + CTA.
4. **Generalize `tools/build_pages.py`:** the single `HERO_*` copy → a **list**
   (hero + 5 stills + dead-STEP still + alive-tree still + live-edit GIF), each
   copied to `assets/` and `src` repointed; the "fail loudly if `../` survives"
   guard covers them. Add a test asserting each asset is copied + repointed.
5. Re-run `python tools/check_launch_kit.py` — `../` paths lint green.

**Tier B — one seat session** (no final commit until produced):
6. Capture the 3 Block ① assets (§7); wire into Block ①; re-verify.

**Verification:**
- **Defensibility (L6):** every caption/number checked vs `docs/CAPABILITIES.md`
  + CLI registry; breadth strip counts (**36 kinds / 16 mates**) match source and
  list **no lofts/ribs/wraps**; phantom-CLI guard confirmed; GIF labeled as a
  real-seat recording.
- **Tier-3 check (L8):** Block ① right shows **named** features + the **Equation
  Manager** with named globals; the GIF shows **0 rebuild errors**. A bare tree
  fails.
- **Flow-pass check:** the essay no longer restates dead-vs-alive; the A4 is
  gone; the page reads tight; `#essay` anchor works.
- **Local preview:** both blocks + breadth strip render; all 8 assets resolve;
  hero/doorways/CTA/footer visually unchanged.
- **Theme + mobile + weight:** light/dark read; Block ① stacks (dead top, GIF
  below); tiles + strip stack with down-arrows, no horizontal scroll; GIF ≤ ~1 MB.
- **Deploy:** `python tools/build_pages.py . _site`, confirm every asset copied +
  clean exit; publish to `gh-pages`; verify every asset 200 on the live URL and
  both blocks render live.

---

## 10. Sequence

1. Extract the 5 seat-free stills; crop the export still's phantom label.
2. Author the two `<section>` blocks + breadth strip + CSS.
3. Flow pass: trim essay to 3 beats + retitle; remove the A4 block; verify anchor.
4. Generalize `tools/build_pages.py` (asset list) + test; re-lint.
5. **[seat session]** capture the 3 Block ① assets; wire into Block ①.
6. Local preview + tier-3 + flow-pass + defensibility + theme + mobile + weight.
7. Rebuild + redeploy `gh-pages`; verify every asset 200 on the live URL.
8. *(Then, user-driven:)* Project B external sends fire against the improved Spine.

---

## 11. Deliverables

- `site/index.html`: two new `<section>` blocks (Block ① three-zone anchor +
  Block ② filmstrip + breadth strip) + additive CSS; **essay trimmed to 3 beats +
  retitled**; **A4 block removed**. Hero / doorways / CTA / footer unchanged.
- `docs/img/`: 5 seat-free breadth stills (export cropped) + 3 seat-gated Block ①
  assets (dead-STEP still, alive-tree+Equation still, live-edit GIF).
- `tools/build_pages.py`: generalized to a **list** of assets; new copy/repoint test.
- Redeployed `gh-pages` artifact with every asset resolving on the live URL.

---

## 12. Risks

| Risk | Handling |
|---|---|
| Breadth strip overclaims (names a loft/rib/wrap the bridge refuses) | L6: strip lists only supported kinds from `CAPABILITIES.md`; lofts/ribs/wraps stay in the essay's "walls" beat; defensibility pass checks the list against source. |
| Breadth counts wrong (a veteran spots "16" or "36" off) | Counts verified against source (§13-F5: `MATE_TYPES` = 16; CAPABILITIES = 36 kinds); re-checked in the defensibility pass. |
| Flow-pass cut loses a genuinely useful nuance | Only the *dead-vs-alive* prose is cut (Block ① replaces it); safety / walls / no-seat beats are kept; the A4 self-select nuance survives via the doorways. |
| Cutting prose breaks the `#essay` anchor | Anchor kept on the trimmed `<article id="essay">`; verified from doorways + CTA in preview. |
| Block ① right reads as a *dumb tree* | L8 tier-3 check: re-capture until named features **and** the Equation Manager are legibly visible. |
| Live-edit GIF too heavy / janky | ≤ ~1 MB palette loop; fall back to a static 2-up before/after (L9). |
| Seat session unavailable → Block ① blocked | Per L5 launch waits on the one seat session; Tier-A breadth + flow pass are done meanwhile. |
| Extracted still illegible / theme-invisible | Frame chosen by eye; PNGs on `--card-bg`; left-tile desaturation is a CSS filter, checked both themes. |
| `build_pages.py` drops an asset | "fail loudly if `../` survives" guard + per-asset copy test + live-URL 200 check. |
| **Cross-ref:** shipped `demo_export.gif` carries the phantom `ai-sw-export` label | Out of scope here (landing crops it); recorded as a **demo-suite** defect to fix at source (§13-F2). |

---

## 13. Enhancement audit (2026-08-14)

Frame inspection of the shipped `docs/img/demo_*.gif`, a CLI-registry check, and
a source count of the feature/mate registries. Findings:

- **F1 — the GIFs are graphics-area renders, not UI-chrome clips (v2 blocker).**
  Every clip is a 3D render + lower-third caption + info-card; **none** shows the
  FeatureManager tree, Equation Manager, dim value, or MateGroup. → the Tier A /
  Tier B split (L4); Block ①'s three assets are all new seat captures.
- **F2 — phantom CLI in `demo_export.gif` (honesty, L6).** Its lower-third reads
  `ai-sw-export`, not a console script (registry: `ai-sw-export-dxf-flat` +
  `ai-sw-import` only; `pyproject.toml [project.scripts]`). → export still crops
  the label; the GIF itself is flagged for a demo-suite fix (cross-ref).
- **F3 — the clips are already honest + well-captioned (positive).** `observe`
  carries an `[experimental]` tag; `export` shows real numbers (bbox 40×28×30 mm,
  vol 26.58 cm³); `drawing` shows a real BOM (3 items) + section. Strong Tier-A
  stills as-is (modulo F2).
- **F4 — the repo genuinely produces tier-3 output (underpins L8).**
  `builder.py:12` renames features to the spec `name` (tree shows `SK_Block`,
  `Cut_Bore`, … not `Sketch1`); `_apply_bindings` (`builder.py:675`) writes
  `"D1@…" = "GLOBAL"` equations with globals from `locals.txt`; deferred-dim
  machinery keeps dims **driving**.
- **F5 — breadth counts verified (underpins L11).** `assembly/schema.py:16`
  `MATE_TYPES` frozenset = **16** (coincident, distance, concentric, parallel,
  perpendicular, tangent, angle, width, gear, rackpinion, camfollower, slot,
  hinge, symmetric, profile_center, linear_coupler). `docs/CAPABILITIES.md:41-59`
  = extrude/cut/revolve over 7 sketch primitives **+ 36 additional feature
  kinds** (the group table). **Lofts/ribs/wraps are NOT in the supported set** —
  they are refused kernel walls, so the breadth strip must exclude them (L6).
