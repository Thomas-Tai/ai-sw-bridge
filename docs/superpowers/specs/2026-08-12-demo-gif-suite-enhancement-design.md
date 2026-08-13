# Demo GIF Suite Enhancement + README Wedge — Design

**Date:** 2026-08-12
**Status:** Design — audited 2026-08-12 (awaiting user go → implementation plan; see §13)
**Owner:** repo maintainer
**Parent:** builds on `2026-08-08-ai-sw-bridge-full-system-demo-design.md` (the chaptered
`tools/demo_full_system.py` and the six clips it produces already exist). This spec is an
**enhancement pass** over that deliverable, driven by a competitive audit.
**Target artifact:** a demo GIF suite + README top-of-page that make a **fresh repo
visitor** grasp ai-sw-bridge's capability fast and understand why it is not
interchangeable with a code-CAD generator.

---

## 1. Goal & framing

The six clips (`demo_part`, `demo_assembly`, `demo_observe`, `demo_drawing`, `demo_export`,
`demo_all`) render today, but the README embeds only three (part / assembly / observe);
`drawing` / `export` / `all` are rendered-but-commented-out `TODO`s, and a `tour` clip does
not exist. So "enhance all the demo gifs" spans three gap types: **wire-in**,
**content-enhance**, and **create-new**.

**Audience.** The parent spec targeted a *skeptical SOLIDWORKS evaluator*. This pass keeps
that lens but widens the job to **a fresh repo visitor who wants to know the capability**.
Chosen primary goal (user decision): a **blend** — one breadth-first hero as the first
impression, then per-chapter clips that reward a closer look with real depth. Ten seconds
to grasp the whole surface; then dwell anywhere for proof.

### Non-goals
- Not a rebuild of `tools/demo_full_system.py`'s chapter engine — it exists and works. We
  re-record content and restructure presentation.
- Not matching a code-CAD tool on *breadth* (CAE/CAM/robotics/slicing) — off-mission and
  unwinnable (see §2). We win on *fidelity*, not surface count.
- Not the distribution/reach effort (skill-packaging, launch) — that is **Project B**, its
  own spec → plan cycle (§3). This spec is **Project A** (conversion) only.

---

## 2. Competitive context (why this pass exists)

Audit of `earthtojake/text-to-cad` (2026-08-12): **13.3k stars**, MIT, **free / no CAD
seat**, Python 3.11+, an **agent-skills package** installed with one command
(`npx skills install earthtojake/text-to-cad`) into Claude Code / Codex. It generates
geometry in an open kernel and previews it in a browser; breadth spans 11 skills
(CAD, DXF, URDF, SRDF, SDF, G-code, SendCutSend, Bambu, …).

**Transferable presentation lessons (adopt):** hero GIF is the *first* thing; a scannable
`Skill | Summary | Source` table conveys the whole surface in ~15s; near-zero-friction
install; honest experimental labels build trust.

**Where we do NOT compete:** breadth of skills, zero-seat install, free/open kernel. Trying
to match those loses.

**The wedge (our honest differentiator).** text-to-cad hands you a *foreign STEP file* from
a throwaway kernel. ai-sw-bridge **drives a real SOLIDWORKS seat** — producing a native
`.SLDPRT` / `.SLDASM` / `.SLDDRW` with a **real, editable feature tree**, **real mates**, a
**real drawing + BOM**, and **DFM / mass / interference from SW's own kernel**. A code-CAD
generator structurally cannot demo any of that. Every "deepen content" proof below is
chosen precisely because it is a thing they cannot show.

**Honesty about the star goal.** GIFs move **conversion** (arrivals → "I need this"), not
**reach** (how many arrive). A 13.3k-star count comes from reach levers — being a
one-command agent skill, breadth novelty, viral pickup. This spec maximizes conversion; the
reach levers are **Project B**. The demo suite is necessary but not sufficient to surpass
13.3k, and the spec says so rather than implying a GIF silver bullet.

---

## 3. Project decomposition

| Project | Scope | Lever | Status |
|---|---|---|---|
| **A (this spec)** | Demo suite enhancement + README wedge | Conversion | Design → plan now |
| **B (separate spec)** | Skill-packaging (`npx skills install`-able) + launch checklist (HN/Reddit/Trendshift/HelloGitHub/Discord) | Reach | Brainstorm after A's design settles |

---

## 4. Locked decisions

| # | Decision | Rationale |
|---|---|---|
| L1 | **Blend goal**: breadth hero + per-chapter depth. | 10s to grasp the surface; dwell for proof. |
| L2 | **All four work-types in scope**: complete the suite · on-clip storytelling · deepen content · restructure README. | User selected all; matches the competitive goal. |
| L3 | **Presentation-first, depth-phased** (Phase 1 no-seat / Phase 2 seat-gated). | Ships the whole conversion win without a seat or a commit; isolates expensive SW work. |
| L4 | **README wedge**: hero-first, differentiator stated as fact (never bashing text-to-cad), capability table, no-seat callout. | Adopts text-to-cad's presentation strengths; leads with our real advantage. |
| L5 | **Archive the original README** to `docs/archive/README_pre-wedge_2026-08-12.md` before restructure. | User-authorized; nothing lost. |
| L6 | **Honesty over polish** (carried from parent §3.4). | For the skeptical SW engineer, candor > a seamless-looking GIF. |

---

## 5. Architecture & phasing

**Phase 1 — Presentation (no seat; working-tree edits only; zero commits):**
1. Archive the current README (L5) — `mkdir -p docs/archive` first (the dir doesn't exist yet).
2. Restructure README top: hero → wedge headline → capability table → no-seat quickstart
   callout → per-clip "what to look for" gallery.
3. Wire in the 3 rendered-but-hidden clips (`drawing`, `export`, `all`).
4. Build the **caption-overlay system** (one consistent lower-third; §7) and apply it to the
   existing clips via ffmpeg re-encode — no SolidWorks.
5. Create the **tour** clip from `demo_full_system.py --chapter tour` (introspected surface;
   terminal/styled-text capture — no SolidWorks).
6. Re-cut a **tight hero** from existing `demo_all` frames *if still on disk*; else Phase 2.

**Phase 2 — Depth (needs a live seat; still no commit until git frees):**
7. Resolve the open item (§9): inspect which fidelity proofs the current observe/drawing/
   export chapters already emit vs. need new handler code.
8. Deep re-records: `observe` = section sweep + mass + interference; `drawing` = BOM +
   balloons + section (correct hatch conventions); `export` = STEP round-trip Δbbox=0.
9. Any new handler code the proofs require, built + verified on the seat.
10. Swap deep clips over the Phase-1 versions; re-run caption overlay; re-verify README.

**Reused throughout:** the proven `SaveBMP` frames → ffmpeg palette-gif + libx264-mp4
pipeline (same path behind the assembly clip), captions via ffmpeg overlay, all
non-destructive (open → animate in memory → close without saving).

---

## 6. README wedge (top-of-page)

```markdown
# ai-sw-bridge   [badges: tests · license · python · requires SOLIDWORKS 2021+]

> **Drive your real SOLIDWORKS seat from a JSON spec.**
> Native `.SLDPRT` / `.SLDASM` / `.SLDDRW` with a real, editable feature tree —
> not a foreign STEP dump from a throwaway kernel.

![hero](docs/img/demo_hero.gif)

*One spec → parts → assembly → observe/DFM → drawing → export, on a live
SOLIDWORKS seat, human-gated (propose → approve → execute).*

### Capability at a glance
| Chapter | What it proves | CLI |
|---|---|---|
| **Tour** | the whole surface — and its honest edges | *(reads sources)* |
| **Part** | change one number → the real feature tree rebuilds | `ai-sw-build` · `ai-sw-mutate` |
| **Assembly** | real mates, not fixed coordinates | `ai-sw-assembly` |
| **Observe / DFM** | interference · min-wall · mass — from SW's own kernel | `ai-sw-observe` |
| **Drawing** | drawing + BOM fall out of the same model | `ai-sw-drawing` |
| **Export** | one model → every format, round-trip verified | spec export block · `ai-sw-export-dxf-flat` |

**No SOLIDWORKS seat?** You can still author and validate specs with zero
license — [5-minute quickstart →](QUICKSTART.md)
```

Principles: (a) the wedge is stated as **fact, not a swipe** — "native feature tree, not a
foreign STEP" is true and is the one thing a code-CAD generator can't match; text-to-cad is
never named. (b) The capability table **doubles as the "know the capability" surface** — the
"What it proves" column pre-loads value so the clips below don't have to. (c) The no-seat
callout **defuses our biggest friction** immediately. (d) Parametric claims rest on `mutate`,
consistent with the parent spec's candor that `--no-dim` carries literal dims in the recorded
tree.

The existing `## Demo GIFs` section becomes the deeper **per-chapter gallery** (§8).

---

## 7. Caption system

One consistent lower-third across every clip so the suite reads as **one system**:
translucent dark band at frame bottom, white text, fixed font/size — bold **value line** +
optional `mono CLI`. Rendered as a **pre-composited PNG overlaid via ffmpeg** (gives font
control the bare `drawtext` filter lacks) so all clips share one visual language. The README
"what to look for" text stays as **editable markdown** beside each clip — richer, and
changeable without a re-render.

**GIF weight budget:** target ≤ ~1 MB per clip. `demo_all` (1.7 MB) and `demo_part` (1.5 MB)
are heavy — re-cut / optimize (palette, fps, scale), and make `demo_all` a **click-through
link** rather than an inline autoload so the page stays light. Each clip also emits an mp4
(kept alongside for docs/click-through; GitHub markdown embeds the gif).

---

## 8. Per-chapter gallery

| Clip | Burned-in caption | "What to look for" (README) | Phase |
|---|---|---|---|
| **hero** (new) | *One JSON spec → a real SOLIDWORKS build* | the whole pipeline in ~12s | P1 — composed from the chapter clips (concat + speed-ramp) |
| **tour** (new) | *The whole surface — and its honest edges* | kinds · CLIs · mates · formats → `DEFERRED.md` | P1 |
| **part** | *Change one number; the real feature tree rebuilds* | FeatureManager tree + bbox update on `mutate` | P1 (add caption) |
| **assembly** | *Real mates, not fixed coordinates* | shaft plunges through both bores, seated | P1 (add caption) |
| **observe** | *DFM is a build gate, not an afterthought* | interference 0 (assembly) · mass (part) · bbox — from SW's kernel; min-wall/section = labeled *experimental* cameo | P1 caption → **P2 deep** |
| **drawing** | *Drawing + BOM fall out of the same model* | section A-A · BOM · balloons | P1 wire+caption → **P2 deep** |
| **export** | *One model → every format, round-trip verified* | Δbbox 0.000 round-trip | P1 wire+caption → **P2 deep** |
| **full run** (`demo_all`) | *The whole build, unedited* | end-to-end, no cuts | P1 wire (click-through per §7) |

### Deep-record content (Phase 2)
- **observe:** anchored on the **proven** reads — **interference = 0** on the assembly,
  **mass** on a part (assigned material), and **bbox** — all from SW's own kernel. Shown with
  an on-screen *experimental* tag: a clip-plane **section sweep** down the bore axis (proves
  the seat, reveals the hidden O-ring groove) + **min-wall** DFM. NB the section sweep is a
  **render technique (new code)**, not an `ai-sw-observe` verb (`section_props` reads a
  pre-selected face, not an animated section). Reuses the `GetBox` ground-truth machinery.
- **drawing:** ortho + iso views; **section A-A through the bore axis** with correct
  conventions (**shaft NOT hatched**, bolts not sectioned — a veteran spots a wrong hatch
  instantly); **auto-BOM + auto-balloons**; title-block mass matching the observe clip.
- **export:** fan of formats (STEP / STL / 3MF / …) written with a build-manifest overlay,
  then **re-import the STEP into a fresh doc** and show `bodies N/N · units mm · Δbbox 0.000 ·
  origin ✓`. The single most credible frame for the target viewer.

---

## 9. Open items (resolved at planning / implementation)

| Item | Handling |
|---|---|
| Which deep proofs the current observe/drawing/export chapters already emit vs. need new handler code | **Task A/P2.0**: read `tools/demo_full_system.py` + view current gifs before estimating Phase 2. |
| ~~Whether `demo_all` frames survive~~ (audited: no tooling ref) | **Resolved:** hero is composed from the chapter clips (concat + speed-ramp) — a Phase-1 no-seat task. |
| ~~Export invocation~~ (audited) | **Resolved:** export = spec `schema-v2` export block (STEP/STL/3MF); DXF via `ai-sw-export-dxf-flat`. No `ai-sw-export` CLI — capability table corrected. |
| Section-view / BOM / balloon / round-trip APIs not yet wrapped | Scoped by A/P2.0; built under A/P2 (new handler code) if absent. |
| Assembly clip ↔ script divergence (F4) | **Note now, wire later:** shipped clip is hand-composed (scratch `build_twin.py`, 5 real mates); a git-gated task wires the twin into `--chapter assembly` so the script reproduces it. Doesn't block Phase 1. |

---

## 10. Verification plan

- **Phase 1 (no seat):** each media artifact renders; caption overlay is legible and
  consistent; tour clip captures the full introspected surface; README renders locally
  (preview) with every embed resolving and within the weight budget.
- **Phase 2 (seat):** per-chapter seat rehearsal → record → **eyeball each gif** before
  declaring done (the standing rule for this workstream); the deep proofs actually appear
  (section sweep, BOM+balloons, Δbbox=0); interference = 0.
- **Git:** working-tree edits only throughout; **no commits** until the hold lifts.

---

## 11. Deliverables

- Restructured `README.md` (wedge top-of-page §6 + per-chapter gallery §8); original archived
  to `docs/archive/README_pre-wedge_2026-08-12.md`.
- `docs/img/demo_hero.gif` (new) and `docs/img/demo_tour.gif` (new).
- Caption-overlaid versions of all chapter clips (one consistent lower-third).
- Phase-2 deep re-records of `demo_observe` / `demo_drawing` / `demo_export` (+ any new
  handler code they require), swapped in over Phase-1 versions.
- A recording/caption helper (extends the existing SaveBMP+ffmpeg pipeline; caption overlay
  reusable across clips).
- Updated `docs/demo_full_system.md` note on the caption/hero/tour additions if the exact
  commands change.

---

## 12. Risks

| Risk | Handling |
|---|---|
| Reader expects GIFs alone to surpass 13.3k stars | Spec states plainly: conversion ≠ reach; Project B owns reach. |
| Deep proofs need unwrapped SW APIs → Phase 2 balloons | A/P2.0 inspection gates the estimate; Phase 1 ships full value regardless. |
| `demo_all` frames gone → hero blocked in P1 | Hero cleanly slips to P2; Phase 1 still ships the wedge + wired suite. |
| Burned-in captions too small at 560 px | Pre-composited PNG overlay (not `drawtext`) for legible, controlled type; eyeball gate. |
| Page too heavy | Weight budget §7; `demo_all` click-through; optimize `demo_part`. |
| Wedge reads as competitor-bashing | Stated as fact, text-to-cad never named; candor as a trust feature (L6). |
| Git-hold forgotten → accidental commit | Every task labeled working-tree/seat only; no commit until hold lifts. |

---

## 13. Audit trail (2026-08-12)

A pre-implementation audit verified the spec's claims against the repo. **Spine confirmed:**
`ai-sw-drawing/observe/mutate/assembly/build` exist (`pyproject.toml:97–118`); all six
chapters incl. `tour` are real and wired (`demo_full_system.py:759–807`); the Tier-A no-seat
quickstart claim is accurate (`:824–852`). Findings + resolutions:

- **F1 — export CLI (blocker, fixed §6).** No `ai-sw-export` entry point exists; export runs
  via a spec `schema-v2` export block, with `ai-sw-export-dxf-flat` for DXF
  (`demo_full_system.py:704,800–803`). Parent §12's open export-invocation item is hereby
  resolved.
- **F2/F3 — observe honesty (blocker/major, fixed §8).** `min_wall` + `section_props` are
  **experimental** (`observe.py:28,29,466`); `section_props` reads a *pre-selected face*, not
  an animated section; interference is **assembly-only**, mass is **part-only**
  (`observe.py:19,257`). Resolution (user): anchor Observe on interference+mass+bbox;
  min-wall/section as a **labeled experimental cameo**; the section sweep is a **render
  technique (new code)**, not a claimed verb.
- **F4 — assembly clip ↔ script divergence (major).** Shipped `demo_assembly.gif` (hand-built
  twin via scratch `build_twin.py`) is not reproduced by `--chapter assembly` (`:780` still
  hedges "mates, once proven"; twin not wired in). Resolution (user): **note now, wire
  later** — git-gated task wires the twin in; Phase 1 unaffected.
- **F5 (minor, fixed §5).** `docs/archive/` doesn't exist → archive step `mkdir -p` first.
- **F6 (minor, fixed §8).** `demo_all` has no tooling reference → hero is **composed from the
  chapter clips**, not a frame re-cut.
- **F7 (minor, fixed §6).** Bare `SOLIDWORKS` badge → plain requirement badge
  ("requires SOLIDWORKS 2021+"), no endorsement implication.

**Net:** the fixes remove three quiet overclaims (`export`, min-wall, section) that would have
undercut the honesty-first wedge (L6) — candor is the edge over a confident-but-thin
competitor, so tightening these *strengthens* the competitive position.
