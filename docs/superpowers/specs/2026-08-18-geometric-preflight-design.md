# Geometric Pre-flight + Convention Capture — Design

**Date:** 2026-08-18
**Status:** Approved design, ready for implementation plan
**Targets:** ai-sw-bridge v0.11
**Branch:** `feat/geometric-preflight`

## Context

Across many part-build sessions, one bottleneck dominates when an **AI model**
drives ai-sw-bridge to build a part: **coordinate/face-convention friction and
silent geometry failures** — not the drafting logic. The pattern is consistent:

- **Plane→sketch coordinate mapping is baked in by hand and non-obvious.** On
  Top plane (XZ) sketch-local `(u, v)` maps to part `(X, −Z)`; on Right plane
  (YZ) `u` maps to `−Z`. The bridge does not auto-transform; the spec author
  must get it right blind.
- **Feature APIs fail *silently* (`None`)** when a sketch lands in empty space
  (a cut sweeping air, a hole missing material, an on-face profile off the
  material). No exception, no hint. The documented remedy today is a manual
  "extrude a 1μm slug and read the bbox" spike; a prior investigation burned
  ~3 hours on dead-end spikes before catching one plane-mapping bug.
- The failure surfaces **only at build time**, after a seat-bound cycle is
  already spent.

This is corroborated by the current code, which documents the gap in its own
words:

- `docs/known_limitations.md §6` ("Schema validation does not catch geometry
  impossibilities"): the validator does **not** check "whether a circle on a
  face will actually land on material," fillet-vs-edge sanity, or result
  validity — "These failures surface as runtime exceptions during the build
  (`FeatureCut4 returned None`)... The bbox sanity check after building is the
  cheapest way to catch the latter."
- `src/ai_sw_bridge/errors/hints.py` already **knows** these failure modes
  (`sketch_self_intersect`, `sketch_open_contour_needed_closed`,
  `sketch_construction_only`, `sketch_under_constrained`,
  `negative_offset_clash`, `face_no_longer_exists`) but only fires them
  **post-mortem**, keyed on the HRESULT *after* a build has already failed.
  Several entries literally say "the bridge does not currently lint for this."
- `src/ai_sw_bridge/spec/lint.py` runs seat-free semantic checks
  (`_check_unconsumed_sketches`, `_check_face_references`,
  `_check_top_plane_centerline_center_z`, `_check_center_z_thread_through`) —
  but these are **spec-structural, not geometric**.

**In short:** the AI cannot tell its spec is geometrically doomed until it burns
a seat-bound build cycle and hand-runs a slug spike to diagnose it. The
knowledge to catch these failures already lives in the codebase; it just runs
too late (post-mortem) and requires a live seat.

## Goal

Catch geometry-impossibility and coordinate-mapping errors **at author-time,
seat-free**, so an AI authoring a spec gets an actionable error with the fix —
not a silent `None` mid-build. Move the failure-detection *left*: from
post-mortem-on-a-seat to pre-build-without-a-seat.

## Non-Goals

- **Not** a CAD kernel. No exact CSG/boolean evaluation.
- **Not** modeling revolve / loft / swept / non-axis-aligned geometry — those
  honest-skip (see §3).
- **Not** the part-interrogation CLI ("ask the part": faces/holes/axes with
  stable IDs). That was considered and **deferred** to a later increment; it is
  seat-bound and does not help greenfield authoring, whereas this pre-flight is
  seat-free and prevents the failure before any body exists.
- **Not** replacing the post-build bbox sanity check (it already exists and
  catches silently-succeeded-but-broken geometry).

## Design Overview

A new seat-free module `src/ai_sw_bridge/spec/preflight.py`, reusing the
existing `LintFinding` type, containing **two independent analyzers**:

1. A **coordinate-mapping resolver** — exact and deterministic.
2. A **material-envelope tracker** — approximate and deliberately conservative.

Both run without SOLIDWORKS. They are wired into the existing seat-free `--lint`
path (Decision ①) so they run in the flow the AI already uses and in CI.

```
ai-sw-build <spec> --lint            (seat-free)
        │
        ├─ spec.lint.lint()          existing semantic checks (unchanged)
        └─ spec.preflight.preflight()  NEW
                ├─ coordinate_mapping_report()   → INFO echoes
                └─ material_envelope_scan()      → WARNING / ERROR / SKIP
```

## Component 1 — Coordinate-mapping resolver (exact)

**Purpose:** make the plane→sketch mapping visible and checkable, deterministically.

**What it does:** for every sketch-bearing feature, apply the plane transform
(Front / Top / Right, plus any plane offset / `start_offset`) to the sketch's
declared local geometry and report the part-frame coordinates the geometry
actually occupies. Example output (INFO):

> `Top` sketch `bore`: sketch-local `(u,v)` → part `(X, −Z)`; profile spans
> part-X `[10, 30]`, part-Z `[−12, −2]`, at part-Y `= +40` (offset).

**Mapping table (authoritative, encoded once):**

| Plane | SW plane axes | sketch `u` → part | sketch `v` → part | normal |
|-------|---------------|-------------------|-------------------|--------|
| Front | XY @ z=0      | `+X`              | `+Y`              | `+Z`   |
| Top   | XZ @ y=0      | `+X`              | `−Z`              | `+Y`   |
| Right | YZ @ x=0      | `−Z`              | `+Y`              | `+X`   |

(Right-plane `u→−Z` and Top-plane `v→−Z` are the two traps that have bitten
real builds; encoding them once removes the guesswork.)

**Why exact:** this is a linear transform of declared coordinates — no boolean
evaluation. It therefore has **zero false-positive risk** and is always emitted
at INFO. The two existing Top-plane convention checks in `lint.py`
(`_check_top_plane_centerline_center_z`, `_check_center_z_thread_through`)
**stay as-is**; this component *complements* them by adding the general
per-sketch echo plus Right-plane coverage, and must not duplicate or contradict
their findings.

**Interface:**
`coordinate_mapping_report(spec: dict) -> list[LintFinding]` (all `severity="info"`).

## Component 2 — Material-envelope tracker (approximate, conservative)

**Purpose:** catch the "cut sweeps empty air" / "sketch lands off material"
class before a build.

**Model:** material is represented as a **union of axis-aligned boxes** in the
part frame. Walk the feature list in order:

- **Additive** (`boss_extrude_blind`, `boss_extrude_midplane`,
  `boss_extrude_two_direction`, and their offset variants): add the swept
  axis-aligned box to the material set.
- **Subtractive** (`cut_extrude_blind`, `cut_extrude_midplane`,
  `cut_extrude_two_direction`, `cut_extrude_through_all`, `simple_hole`):
  compute the swept region (box for rectangular profiles, axis-aligned cylinder
  bbox for circular) and check it **intersects** the current material set. If
  the region is provably disjoint from all material → this is an empty-air cut.
- **On-face sketches:** resolve the target face's modeled extent (from the
  material set) and check the projected profile bbox lands within it.

**Honest-skip rule (load-bearing for trust):** any feature the box model cannot
represent exactly — `revolve_*`, `loft`, `sweep`, `sketch_polyline_on_plane`
with a non-axis-aligned profile, fillets/chamfers on non-modeled edges, or a
sketch on a face the model can't localize — is **SKIPPED with an INFO note**
naming the feature and why. The tracker **never guesses** on unmodeled
features, and once a feature has modified the body in a way the model can't
represent, downstream geometric checks that depend on that region also skip
(the coordinate echo still runs — it never depends on the material model).

**Interface:**
`material_envelope_scan(spec: dict) -> list[LintFinding]`.

## The Check Catalog

| ID | Check | Severity | Confidence basis |
|----|-------|----------|------------------|
| C1 | Empty-air cut: swept cut region ∩ material = ∅ | **ERROR** | provable from the box model; only fires when fully modeled |
| C2 | On-face sketch profile lands off modeled material | WARNING | approximate (face extent is modeled) |
| C3 | Coordinate-mapping echo per sketch | INFO | exact |
| C4 | Spec-detectable degenerate profile (construction-only sketch, open polyline where a closed profile is required, self-intersecting polyline) | WARNING | detectable from spec geometry; promotes existing post-mortem `hints.py` modes to pre-build |
| C5 | Fillet/chamfer radius ≥ smallest modeled adjacent edge | WARNING | only when the adjacent edges are modeled |

Every finding carries a `remedy` string and a cross-reference to the matching
`errors/hints.py` key (adding an `empty_air_cut` hint so the pre-flight and the
post-mortem path speak the same language).

## Decision ① — Delivery surface

Fold the pre-flight into the existing seat-free `--lint` path (invoked from
`src/ai_sw_bridge/cli/build.py`, which already imports `spec.lint.lint` as
`spec_lint`). Add a `--no-preflight` flag to silence the geometric analyzers
(the coordinate echo and semantic lint remain). Rationale: `--lint` is the path
the AI already runs and it already runs in CI, so no new habit is required.
Rejected alternative: a separate `--preflight` verb (adds a step the AI must
remember to run).

## Decision ② — Severity model

- Coordinate echo (C3) → **INFO** (always safe).
- Geometric findings (C2, C4, C5) → **WARNING** by default, because the box
  model is approximate; a warning informs without blocking.
- **ERROR only for C1**, and only when the cut is *fully modeled* and provably
  disjoint from all material — the one case the box model can assert with
  certainty.

This protects trust: the pre-flight never emits a false ERROR. **Requirement:**
the `--lint` exit code must gate on ERROR only (WARNING/INFO do not fail the
command), so adding advisory geometric warnings does not start failing the
currently-green example builds. The implementation must confirm the existing
`--lint` exit-code behavior and introduce ERROR-only gating if it does not
already work this way.

## Decision ③ — Model scope

Axis-aligned box/cylinder features only — which covers ~90% of Lego Sorter
parts (plates, mounts, brackets built from Front-plane bosses + `+z` holes).
Everything else honest-skips per §Component 2. No CSG kernel. This is the YAGNI
line: model what is common and high-value, punt honestly on what is rare.

## Convention-capture rider (C)

Harvest the hard-won conventions (currently living only in session memory) into
the repo so both the AI and the pre-flight's messages reference one source:

1. **New `docs/coordinate_conventions.md`:**
   - the plane→sketch mapping table (§Component 1) as the canonical reference
   - offset-part recipes: `start_offset` always grows +normal and ignores
     `flip` (direction via `flip_start_offset`); `cut_extrude_two_direction`
     with symmetric blind depths to hole a body across an air gap (through-all
     returns `None` across a gap)
   - the Front-plane-boss + `+z`-face-hole pattern for flat parts (avoids the
     unreliable side-face select)
   - silent-`None` triage: suspect geometry-in-air first; run `--lint`
     (pre-flight) or the slug spike before suspecting the API
   - the assembly placement quirk (rpy=0 → bbox-center; rpy≠0 → part-origin)
     as a cross-reference pointer
2. **`docs/AGENTS.md`:** a short "before you build, run `ai-sw-build <spec>
   --lint`" pointer plus a link to `coordinate_conventions.md`. (Keep it brief;
   AGENTS.md is the AI briefing, not the reference.)
3. **`src/ai_sw_bridge/errors/hints.py`:** cross-reference the relevant hints to
   the pre-flight and `coordinate_conventions.md`; add the `empty_air_cut` hint.

## Testing & false-positive discipline

Seat-free tests (no SOLIDWORKS), the invariant being **no false positives on
known-good parts**:

- **No-false-positive invariant (CI-locked):** every buildable example spec
  (`examples/*/spec.json`, `examples/*/spec_parametric.json`) must pre-flight
  with **zero WARNING/ERROR** geometric findings. INFO echoes are allowed. This
  is the primary guard and runs in CI.
- **Honest-skip coverage:** a revolve/turned example (`drive_roller`,
  `grooved_shaft`, `minimal_cylinder`, `patterned_disc`) must produce SKIP
  notes, never a false flag.
- **True-positive coverage:** synthetic bad specs — an empty-air cut (C1 →
  ERROR), an off-material on-face sketch (C2 → WARNING), a construction-only
  sketch and an open-profile polyline (C4 → WARNING) — must each be caught.
- **Coordinate-echo correctness:** unit tests asserting the exact part-frame
  spans for a known sketch on each of Front/Top/Right, including the
  `−Z` traps.

## Out of scope (YAGNI)

- Exact CSG / boolean evaluation.
- Revolve / loft / swept / non-axis-aligned geometric checks (honest-skip).
- The part-interrogation CLI (deferred B).
- Live-seat validation (the post-build bbox check already exists).

## Module boundaries

- `spec/preflight.py` — pure functions over the spec dict; returns
  `list[LintFinding]`; imports only stdlib + `spec.lint.LintFinding` (or a
  shared findings type). No SW, no I/O. If `LintFinding`'s severity vocabulary
  does not already include `info` / `warning` / `error`, extend it (the
  implementation must check `lint.py`'s current severity values and reconcile,
  keeping existing findings' severities unchanged).
- `cli/build.py` — wires `preflight()` into the `--lint` path and the
  `--no-preflight` flag; owns exit-code gating (unchanged ERROR-gating).
- `errors/hints.py` — data-only additions (new hint + cross-refs).
- `docs/coordinate_conventions.md`, `docs/AGENTS.md` — documentation.

Each unit is independently testable seat-free; `preflight.py` is the one new
logic module and is bounded to the two analyzers above.
