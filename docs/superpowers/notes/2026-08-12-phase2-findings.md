# Phase 2 findings — deep vs shallow re-record (Task 8 / P2.0)

**Date:** 2026-08-12 · **Author:** demo-suite Phase-1 execution (non-seat)
**Plan:** `docs/superpowers/plans/2026-08-12-demo-gif-suite-enhancement.md` (Task 8)
**Spec:** `docs/superpowers/specs/2026-08-12-demo-gif-suite-enhancement-design.md` §8

This note is the concrete sub-plan for Tasks 9–11. It was produced **without a
SOLIDWORKS seat** by reading `tools/demo_full_system.py` (the chapter
step-builders) and the `ai_sw_bridge.cli.*` / `drawing/` source, and by probing
CLI `--help`. Every "record / verify" line below is seat-gated; the
classification work here is not.

---

## Headline finding

**The "shallow" look of the observe / drawing / export clips is a RECORDER gap,
not a capability gap.** The chapters already *run* the right CLIs — the numeric
proofs (interference JSON, mate-error JSON, the export manifest) print to the
**terminal**, but the Phase-1 gifs capture the **SOLIDWORKS graphics window**,
so those numbers are off-screen. Consequences:

- Most Phase-2 work is **renderer** work: compose frames that surface the
  already-produced terminal JSON as an on-screen HUD *beside* the SW view.
- Only three items need more than a renderer: the observe **section sweep**
  (a clip-plane render), the drawing **section A-A + balloons** (switch the demo
  from the legacy single-sheet drawing spec to the per-sheet spec — the
  capability already exists), and the export **STEP round-trip** (a small
  import + bbox-compare step).
- **No net-new SW handler code is required.** Everything the deep proofs need is
  already implemented; Task 52 ("new handler code as needed") is expected to be
  a no-op or near-no-op.

---

## What each chapter emits today (Phase-1)

**Observe** (`_observe_steps`, demo_full_system.py:532):
1. `observe_open_assembly` — open + activate `DemoWidget.SLDASM`
2. `ai-sw-observe interference`  → JSON (expect interference 0) **[terminal]**
3. `ai-sw-observe mate_errors`   → JSON (per-mate status) **[terminal]**
4. `ai-sw-observe screenshot --filename demo_widget.png`

→ The Phase-1 gif shows only the SW view (step 4's subject). Steps 2–3's numbers
are in the terminal, off-gif. Mass and bbox are **not** in the observe chapter
today (the part chapter runs `bounding_box` + `feature_statistics`; `volume`
reports mass but isn't wired into any chapter).

**Drawing** (`_drawing_steps`, :613; spec authored by `_drawing_prep_script`, :583):
- Writes `drawing.json` in **legacy single-sheet mode**: top-level
  `views: [front, top, right, isometric]`, `dimensions: true`, `bom: true`.
- `propose` → `dry_run` → `commit --out DemoWidget.SLDDRW`.

→ The gif shows ortho+iso views + a BOM table + model dims — all real. **No
section A-A, no balloons** (not requested by the legacy spec; and the legacy
dispatch path stubs section views — see below).

**Export** (`_export_steps`, :720; `export_block_wired=True` by default):
1. `ai-sw-build examples/demo_widget/export.json --no-dim --yes` — schema-v2
   export block emits **STEP + STL + 3MF**
2. `list_exports` — globs `demo_out` for `*.step* / *.stl / *.3mf`, prints them **[terminal]**

→ The gif shows the rotating model (the ai-sw-build viewport). The written-files
manifest is in the terminal, off-gif. No round-trip.

---

## Per-proof classification (the Task 9–11 work list)

Legend — **work**: `renderer` = compose/HUD only · `spec` = author a richer
input spec, capability already implemented · `code` = new SW handler code.

### Task 9 — Observe deep (`tools/demo_render_observe.py`)
| Deep proof (§8) | In Phase-1 gif? | Capability | Work | Notes |
|---|---|---|---|---|
| interference = 0 on-screen | ❌ (terminal only) | ✅ `observe interference` (W27/E4, assembly) | **renderer** | HUD the captured JSON over the SW view |
| mate health | ❌ (terminal only) | ✅ `observe mate_errors` | **renderer** | already run; HUD it |
| mass on a part | ❌ | ✅ `observe volume` (part-only; reports vol/area/**mass**) | **renderer** + add a `volume` step | needs an **assigned material** on the part, else mass is 0/■ — verify on seat |
| bbox | ❌ (part chapter, terminal) | ✅ `observe bounding_box` | **renderer** | HUD it |
| section sweep down bore axis, ***experimental*** tag | ❌ | ⚠️ clip-plane render — *not* an observe verb; `min_wall`/`draft`/`undercut` exist but are different DFM reads | **code (renderer-side)** | new: drive a section/clip plane along bore axis, SaveBMP each step. Tag on-screen `experimental`. Smallest genuinely-new piece. |

### Task 10 — Drawing deep (`tools/demo_render_drawing.py`)
| Deep proof (§8) | In Phase-1 gif? | Capability | Work | Notes |
|---|---|---|---|---|
| ortho + iso views | ✅ | ✅ legacy `STANDARD_VIEW` | done | keep |
| auto-BOM | ✅ | ✅ `lifecycle` BOM (`_find_bom_template`, W18) | done | keep |
| **section A-A** (shaft NOT hatched, bolts not sectioned) | ❌ | ✅ **implemented** in the **per-sheet** path: `lifecycle._create_section_view` → `CreateSectionViewAt5`. **But the legacy single-sheet path the demo uses STUBS it** (`dispatch.py:154` → "Section views are SEAT-gated (P2.x)") | **spec** | switch the demo `drawing.json` to the per-sheet `sheets[]` spec so it reaches the implemented section handler. Live-proof status of `_create_section_view` is UNKNOWN — confirm on seat. Hatch convention (shaft unhatched) is a SW component-property setting to verify. |
| **balloons** | ❌ | ✅ **seat-proven** per-sheet: `InsertBOMBalloon2` (W70, style=1 circular, size=2; persistence-proven) | **spec** | add `balloons[]` to the per-sheet spec; item numbers resolve only when a BOM is present (it is) |

**Drawing dual-path caveat (the key de-risk):** the demo currently writes a
*legacy* spec whose dispatch stubs section/projected views. All the deep drawing
capability lives in the *per-sheet* path (`drawing/lifecycle.py`,
`drawing/spec_schema.py`). Task 10 is therefore mostly **re-authoring the demo
drawing spec into per-sheet form** — no new handler code — plus seat verification
that `_create_section_view` renders cleanly for this assembly.

### Task 11 — Export deep (`tools/demo_render_export.py`)
| Deep proof (§8) | In Phase-1 gif? | Capability | Work | Notes |
|---|---|---|---|---|
| STEP/STL/3MF format fan + build manifest | ❌ (terminal list) | ✅ schema-v2 export block via `ai-sw-build` + `list_exports` | **renderer** | HUD the written-files manifest over/after the build |
| STEP round-trip: `bodies N/N · units mm · Δbbox 0.000 · origin ✓` | ❌ | ✅ re-import via `ai-sw-import` (`--verify-volume`); ground-truth bbox via `IComponent2.GetBox` / `observe bounding_box` | **renderer + tiny script** | import the just-written STEP into a fresh doc, compare bbox to the source. `Δbbox` compute is a pure helper — could be unit-tested offline if desired, but it's trivial; author it with the renderer in Task 11. |

---

## Non-seat work available now — assessment

I checked whether any Phase-2 piece is worth building **before** a seat is free:

- **Renderer scaffolds** (observe/drawing/export) can only be *verified* by the
  frames they produce on a live seat → building them now yields unverified code
  (violates the workstream's "eyeball before done" rule and
  `[[feedback_handoff_must_verify_before_pause]]`). **Deferred to the seat session.**
- **New handler code:** none required (see classification). Task 52 ≈ no-op.
- **Only genuinely-offline piece:** the export `Δbbox` compare helper — trivial,
  ~5 lines; not worth splitting from its renderer. **Deferred to Task 11.**

**Conclusion:** Task 8 (this note) is the last non-seat deliverable in Phase 2.
Everything downstream is seat-gated. No speculative code written.

---

## Seat-session entry checklist (when a seat is free)

1. Read this note + spec §8 + plan Tasks 9–11.
2. **Observe:** confirm the part carries an assigned material (for `volume` mass);
   build the interference/mass/bbox HUD renderer; add the clip-plane section
   sweep with an on-screen `experimental` tag.
3. **Drawing:** re-author the demo drawing spec into per-sheet `sheets[]` form
   with a section view + balloons; confirm `_create_section_view` renders and the
   shaft shows unhatched; re-caption.
4. **Export:** build the manifest HUD; re-import the STEP and HUD the round-trip
   `Δbbox 0.000`; re-caption.
5. **Task 12:** re-run `tools/demo_hero.py` (montage picks up the deep clips),
   re-run the README embed check, and **upgrade the README gallery "what to look
   for" copy** from the Phase-1 (honest-shallow) wording to the deep-proof
   wording. Eyeball the full README.

Non-destructive throughout: open → animate/read → `CloseAllDocuments(True)`,
never re-save a demo `.SLDPRT/.SLDASM`.
