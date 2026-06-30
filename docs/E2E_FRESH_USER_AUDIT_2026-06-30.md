# E2E Fresh-User Audit & Enhancement Report

**Date:** 2026-06-30
**Baseline:** `feat/w67-phase3` @ origin/master `9f6e3ab` (v1.6.1, post Issues #7/#8/#9)
**Persona:** a 20-year SOLIDWORKS veteran, *not* a Python developer, who found the repo
and wants to speed up their building process.
**Scope:** the full onboarding path — README → install → first build → authoring a part →
capability ceiling → an error → finding the manual.

---

## How this was produced

A multi-persona journey sweep with **adversarial verification**:

1. Seven personas each embodied the veteran at one journey stage and reported friction
   **grounded in the real files** they would hit at that stage.
2. A skeptic re-opened every cited file and either confirmed the finding (with evidence and a
   re-graded severity) or threw it out as overstated/false.
3. Every numeric/behavioral claim was checked against running code, not memory.

**Result:** of ~30 instinctive complaints, the skeptic **rejected ~22 as overstated or false**
and confirmed **14 real items** (mostly documentation). The engine, safety model, and the
onboarding hardening shipped in #7/#8 hold up well. The residual work is almost entirely
**truth-in-documentation**, not engineering.

> Honesty note for the reader: the single loudest persona claim — *"the README's '36 feature
> kinds' is inflated; only 27 are really registered"* — was **false**. `HANDLER_REGISTRY` holds
> exactly 36, matching the README table and `client.features.list_kinds()` one-for-one. The
> persona had read **stale inline docstring comments** ("UNFIRED until W0 fires") instead of the
> live `SPIKE_STATUS` constants. The count is honest.

---

## Priority summary

| # | Finding | Severity | Type | Effort |
|---|---------|----------|------|--------|
| 1 | Localized READMEs declare **MIT**; actual license is **Proprietary** | 🔴 P0 | legal / trust | XS |
| 2 | `±x/±y` faces documented as `NotImplementedError` — code implements all 6 | 🟠 P1 | doc↔code drift | XS |
| 3 | Exit-code table is incomplete **and** wrong | 🟠 P1 | doc↔code drift | S |
| 4 | Stale counts (`15` specs vs 20; zh `12` types vs 30) | 🟠 P1 | stale docs | XS |
| 5 | Fillet error string in docs is the wrong handler's string | ⚪ P3 | doc↔code drift | XS |
| 6 | Git is an unstated prerequisite | 🟡 P2 | install gap | XS |
| 7 | pip `[mcp]`/`[dev]` extras syntax unexplained | 🟡 P2 | install polish | XS |
| 8 | Parametric hole **positions** can't be variables (size can) | 🟡 P2 | feature asymmetry | M |
| 9 | Fillet edges by literal XYZ break on upstream dim change | 🟡 P2 | parametric fidelity | L |
| 10 | No `ai-sw-build --list-kinds` (authoritative list is Python-only) | 🟡 P2 | missing affordance | S |
| 11 | Multi-seat gate prints a bare "ambiguous" PID | ⚪ P3 | UX | S |
| 12 | `schema_version: 2` → cryptic `"1 was expected"` | ⚪ P3 | error clarity | S |
| 13 | `AddDimension2` popups in parametric mode | ⚪ P3 | known sharp edge | — |
| 14 | No human-CAD-user (non-AI) onboarding framing | ⚪ P3 | scope | M |
| 15 | README never shows a single `spec.json` (the artifact the tool produces) | 🟠 P1 | onboarding | S |
| 16 | Quickstart smoke test silently trips the `[y/N]` seat gate, unforewarned | 🟡 P2 | onboarding | XS |
| 17 | `ai-sw-probe` success output is never shown | ⚪ P3 | onboarding | XS |
| 18 | No first-run troubleshooting surface anywhere | 🟡 P2 | onboarding | S |
| S1 | `builder.py` is a 3,250-line module — already registry-seamed, never decomposed | 🟡 P2 | structure | M |
| S2 | Two feature-dispatch registries organized differently (`features/` pkg vs `builder.py` flat) | ⚪ P3 | structure | M |
| S3 | Three more 2k-line hand-written modules on hot paths (watch-list) | ⚪ P3 | structure | — |

Effort: XS ≈ minutes · S ≈ <½ day · M ≈ 1–2 days · L ≈ multi-day/design.
README-onboarding items (15–18) and structure items (S1–S3) were added in the
**2026-06-30 fold-in** (see the two sections before the execution plan); these came
from direct file inspection, not the persona sweep.

---

## P0 — Fix before any further launch claim

### 1. Localized READMEs declare the wrong license 🔴
- **Evidence:** `README.md:7` badge = **Proprietary**; `docs/i18n/zh-TW/README.md:11` and
  `docs/i18n/zh-CN/README.md:11` badges = **MIT**; the prose 授權 section at
  `docs/i18n/zh-TW/README.md:164` (zh-CN identical) also says *MIT*. `LICENSE` is a Commercial
  Software License Agreement governing **v1.5.0 and later**; current version is 1.6.1. Both
  translations are frozen at `translated-from: c8ce816` (pre-commercialization).
- **Impact:** an entire non-English audience is told a proprietary/commercial product is
  MIT-licensed (permissive). This is a legal and trust exposure, not cosmetic.
- **Fix:** hotfix the **four** lines now — two badges + two prose sections — to match the English
  Proprietary license. This is independent of, and more urgent than, the broader translation
  refresh (Issue #10). Recommend a standalone commit so it can ship immediately.

---

## P1 — Documentation that actively lies about the code

These are the highest-value engineering-adjacent items: each would cause a competent veteran to
do the *wrong* thing because the docs disagree with the implementation.

### 2. `±x/±y` faces falsely documented as unimplemented 🟠
- **Evidence:** `docs/known_limitations.md` §2 and `docs/spec_reference.md:122` state that
  `+x/-x/+y/-y` faces raise `NotImplementedError`. The code implements **all six faces**:
  `src/ai_sw_bridge/spec/_face_geometry.py::_face_frame` (full ±x/±y branch); the quoted error
  string exists **only** in the docs, never in `src/`.
- **Impact:** a veteran wanting a hole pattern on a box's side face will reorient the whole part
  (pick a different base plane) to dodge a wall that **no longer exists** — slower and more fragile
  than just doing it.
- **Fix:** delete/replace the stale limitation note in both docs. **Lock it down with a test** that
  builds a child sketch on each of the 6 faces, so the doc can't silently re-drift.

### 3. Exit-code documentation is incomplete and inaccurate 🟠
- **Evidence:** `docs/tools_reference.md:127` "Exit codes" lists only `0/1/2`. `cli/build.py`
  actually returns `3` (validation, :597), `4` (build failed / strict-addins, :704/:738),
  `5` (dry-run rhs-resolution, :664), `6` (lint findings, :654), `7` (identical-spec/auto-retry,
  :630) — and **never returns 1**. Codes 5/6/7 appear nowhere user-facing; `ONBOARDING.md:71-73`
  covers only 3/4.
- **Impact:** SOLIDWORKS automation is routinely wrapped in `.bat`/PowerShell/Excel. A scripter
  branching on `$LASTEXITCODE` against this table mis-handles failures (e.g. aborts on a
  validation error they meant to skip).
- **Fix:** regenerate the exit-code table from `build.py`'s real codes. Strongly consider emitting
  an `exit_code` integer field inside the JSON envelope so the contract is self-describing.

### 4. Stale capability/example counts 🟠
- **Evidence:** `docs/ONBOARDING.md:117` says *"all 15 working specs"* but `ls examples/` returns
  **20** — the doc's own suggested command falsifies its number. The localized READMEs
  (`:50`) say *"12 feature types"* vs the actual **30** (`schema.ALL_TYPES`).
- **Impact:** self-contradicting docs erode trust precisely at the "can I rely on this manual?"
  stage. (The English README is correct: 30 spec types / 36 feature_add kinds.)
- **Fix:** update ONBOARDING to 20; refresh the localized counts in the #10 pass. Best long-term:
  derive these counts from code in the doc-coverage test you already run
  (`schema.ALL_TYPES == 30` is already enforced).

### 5. Fillet error string drift ⚪ (small, but same class)
- **Evidence:** `docs/known_limitations.md:145` (the §4 *fillet* section) quotes
  `…point not on any edge of current geometry`. The live fillet selector
  (`builder.py:1128-1132`) raises `…matches no edge within 1um…`; the quoted wording is actually
  the **linear_pattern** path (`builder.py:1327-1331`).
- **Impact:** a user copy-pasting the documented error into search won't match what they saw.
- **Fix:** replace the quoted string with the live fillet message.

---

## P2 — Real friction (small, high-ROI)

### 6. Git is an unstated prerequisite 🟡
- **Evidence:** `README.md:46` opens install with `git clone …`, but Prerequisites
  (`README.md:35-41`) lists only Windows, SOLIDWORKS, and Python. Python even gets a
  *"if not found, add to PATH"* remedy; Git gets nothing. A grep for `git` in the README hits only
  line 46.
- **Fix:** add a Git bullet to Prerequisites mirroring the Python "verify / how to install"
  pattern, plus a "or download the ZIP from GitHub" fallback for the git-averse.

### 7. pip extras syntax unexplained 🟡
- **Evidence:** `README.md:50` (`pip install -e .`), `:191` (`pip install -e ".[mcp]"`),
  `CONTRIBUTING.md:12` (`.[dev]`). The bracket syntax and the Windows quoting are never spelled
  out (the README *does* say what `[mcp]` is *for*, but not what the notation means or that it's
  additive).
- **Fix:** one clause at first use — *"the `[mcp]` suffix adds optional MCP dependencies on top of
  the base install; the quotes are required on Windows PowerShell."*

### 8. Parametric hole **positions** can't be variables 🟡
- **Evidence:** `docs/spec_reference.md:197` — *"Circle positions are literal mm only — no `{rhs}`
  on `u` or `v`."* Schema confirms it: `descriptors.py:477-486` types `u`/`v` as plain numbers
  while `diameter` is `LENGTH_SCHEMA` (accepts `{rhs}`). Pattern spacing is also non-parametric
  (`spec_reference.md:828`). `examples/motor_mount_plate/spec.json:46` carries a `_comment`
  acknowledging the limit.
- **Impact:** to a parametric-design brain, *"I can drive the hole's size from a variable but not
  its pitch"* is a surprising asymmetry — exactly the kind of thing a veteran expects to "just
  work."
- **Fix (either):** (a) implement `{rhs}` resolution for `u`/`v` (and pattern spacing); or
  (b) until then, document the workaround (single seed hole + `linear_pattern`/`circular_pattern`)
  *at the point of use*, and make the validation error for `{rhs}` on `u`/`v` name the workaround.

### 9. Literal-coordinate edge selection breaks parametric edits 🟡
- **Evidence:** fillet/chamfer edges are addressed by `{x, y, z}` (`spec_reference.md:755`); the
  selector matches the nearest edge within 1µm (`builder.py:1128-1132`). Change an upstream
  dimension and the stored point no longer lands on the edge → `RuntimeError`.
  `docs/known_limitations.md` §4 documents this with a workaround and an `edges_by_face` roadmap
  note.
- **Impact:** SOLIDWORKS tracks edges by persistent topological IDs that survive dimension
  changes; this bridge uses coordinates that don't. The veteran's expectation that "the fillet
  follows the top +X edge" is legitimately violated — the most likely "the GUI was faster" moment.
- **Fix:** prioritize semantic edge addressing (the roadmap's `edges_by_face`, or
  feature+face+side selectors). This is design work (L), but it's the highest-value *engine*
  enhancement in this report.

### 10. No CLI to list supported feature kinds 🟡
- **Evidence:** the docs explicitly distrust their own static table — `docs/AGENTS.md:139` *"This
  paragraph is a tour, not the source of truth. Query the code:"* — and the only authoritative
  enumeration is `client.features.list_kinds()` (`client.py:416`, Python). None of the 23 CLI
  entry points exposes a `--list-kinds`/capability list (verified across every `argparse`).
- **Impact:** a non-Python veteran can read the README table but has no trustworthy, scriptable way
  to ask "what can it do *right now*?"
- **Fix:** add `ai-sw-build --list-kinds` (or a tiny `ai-sw-features list`) that prints
  `sorted(HANDLER_REGISTRY)` and the 30 spec types. Cheap, and it makes the docs' "query the code"
  guidance reachable without Python.

### 11. Multi-seat gate prints a bare "ambiguous" PID ⚪
- **Evidence:** `cli/build.py:101` → `f"{pids[0]} (1 of {len(pids)} running - ambiguous)"`.
  `_find_sw_pids` returns PIDs in raw tasklist order, so `pids[0]` is arbitrary.
- **Mitigation already present:** the same banner (`:112-114`) prints the **active-doc title**,
  which is the human-friendly disambiguator — so this is a nit, not a hazard (and `ai-sw-build`
  creates a *new* doc rather than mutating an existing part).
- **Fix (optional):** read the active doc per running PID and print a short list so the operator
  can pick by document name.

---

## P3 — Nits & inherent

### 12. `schema_version: 2` yields a cryptic error ⚪
- **Evidence:** `spec/schema.py:69` defines `schema_version` as `{"const": 1}`. Setting `2` with
  the (default-off) v2 flag yields `{"error":"validation_failed","path":"schema_version",
  "message":"1 was expected"}` with no hint about `--enable-flag schema_v2`.
- **Mitigation:** the `path` field *does* name `schema_version`, and docs steer users to v1
  (`spec_reference.md:18` *"Must be 1"*), so a doc-following user won't hit it.
- **Fix:** special-case `schema_version > 1 && flag off` with a message naming
  `--enable-flag schema_v2`.

### 13. `AddDimension2` popups in parametric mode ⚪
- Well-documented sharp edge (`docs/known_limitations.md` §3) with a clean `--no-dim` workaround
  that still produces correct geometry. A veteran recognizes the standard "Modify Dimension"
  dialog instantly. Inherent to the SW API; no action required beyond the existing docs.

### 14. No human-CAD-user onboarding framing ⚪
- All entry docs are framed for **AI agents** (`docs/AGENTS.md:3` *"Briefing for an AI
  assistant"*) or developers. Mitigated by CAD-vocabulary throughout and a modeler-oriented
  `USAGE.md` Workflow 3, and honestly disclosed. This reflects the product's actual scope
  (an AI/dev-driven bridge), so it's a positioning choice, not a defect — optionally add a
  one-line "Is this for me?" framing.

---

## README onboarding for a non-Python evaluator (2026-06-30 fold-in)

The README is, on balance, **one of the stronger ones audited** — quickstart on top
(`README.md:43-74`), a concrete smoke-test success criterion (`:62`), a data-flow mermaid a
CAD person can read (`:16-27`), an honest *"this is a Python developer tool"* heads-up (`:37`),
and a pre-adoption limitations section (`:255-263`). It is **not too thin**. The gaps below are
specific holes a *fresh* user falls into that a Python developer would not — none are systemic.

### 15. The README never shows a single `spec.json` 🟠
- **Evidence:** the artifact the entire tool produces — the JSON spec — appears only as a *box in
  the mermaid diagram* (`README.md:21`) and nowhere as actual content. All code blocks in the file
  are mermaid, the PowerShell install (`:45-51`), the `list_kinds()` snippet (`:152-156`), and the
  MCP JSON config (`:200-208`). No `spec.json` is ever shown inline; the reader must leave for
  `examples/` to see one.
- **Impact:** for a CAD veteran evaluating *"can this express my part?"*, seeing the JSON **is** the
  decision. Hiding it behind a click is the most likely silent-bounce point in the funnel.
- **Fix:** add ~15 lines of annotated box + hole + fillet `spec.json` right after the "30 feature
  types" line (`:29`), or inside Quickstart step 2. Highest-leverage README addition.

### 16. The Quickstart smoke test silently trips the seat gate 🟡
- **Evidence:** step 2 (`README.md:59`) tells the user to run
  `ai-sw-build examples/filleted_box/spec.json --no-dim` — which hits the `[y/N]` seat-confirmation
  gate (`cli/build.py:92-144`) because it does **not** pass `--yes`. The gate is only described 60
  lines later (`:118`); the Quickstart gives no forewarning.
- **Impact:** a veteran with unsaved work in a live licensed seat sees an unexplained PID +
  active-doc prompt within the first 10 seconds of the very first command. The gate is a *feature*
  (it's the best safety moment in the tool) — but unannounced it reads as alarming.
- **Fix:** one sentence in step 2 — *"`ai-sw-build` will show your SW seat (PID + open doc) and pause
  for `[y/N]`; that's the safety gate — press `y`."*

### 17. `ai-sw-probe` success output is never shown ⚪
- **Evidence:** Quickstart step 2 (`README.md:53-62`) gives the *build's* success criterion
  ("a small filleted box appears… within ~3 seconds") but never shows what a healthy `ai-sw-probe`
  prints, so the user can't tell whether the first half of the smoke test passed.
- **Fix:** show the one-line probe success output next to the command.

### 18. No first-run troubleshooting surface exists 🟡
- **Evidence:** a glob for troubleshooting / FAQ / first-run / getting-started docs returns **zero
  files**; `docs/ONBOARDING.md` has no failure section either. The README's "Stuck?" (`:76`) points
  only to `examples/README.md` and `docs/known_limitations.md` — neither answers the two failures
  every fresh user actually hits: `ai-sw-build: command not found` (venv not activated) and
  `ai-sw-probe` failing (SW not running / 32-vs-64-bit mismatch).
- **Fix:** a 4–6 row "first run didn't work?" table (in the README or a linked
  `docs/troubleshooting.md`): command-not-found → activate venv; probe fails → start SW / check
  bitness; build hangs on a dialog → `--no-dim`; `[y/N]` prompt → that's the seat gate.

---

## Codebase structure observations (2026-06-30 fold-in)

These came from a direct structural pass (largest hand-written modules + their internal shape), not
the persona sweep. None is a defect today — the code is well-layered and the suite is green — but
they are the load-bearing files that will get harder to change as the product grows.

### S1. `builder.py` is a 3,250-line module that already has its decomposition seam 🟡
- **Evidence:** `src/ai_sw_bridge/spec/builder.py` is **3,250 lines** — the largest hand-written file
  in the tree. It holds, in one flat module: RHS/locals resolution helpers (`:153-290`), low-level
  COM call wrappers (`_call_feature_extrusion` `:337`, `_cut4_args_2024/2025` `:417/:477`,
  `_call_feature_revolve` `:874`), **~30 inline `_build_*` handlers** (boss/cut-extrude variants,
  revolve, hole, fillet, chamfer, linear/circular/mirror patterns, and the whole `_build_sketch_*`
  segment family `:1704-1947`), a `_wire_handlers()` registry at `:2147`, and finally the top-level
  `build()` orchestration loop + save/locals/broad-except envelope (`:2838-3250`).
- **Why it matters:** the dispatch seam **already exists** (`_wire_handlers`), so the handlers don't
  *need* to live in this file — they were simply never moved out the way the sketch *containers*
  were (`spec/sketches/` uses a `SketchHandler` ABC + concrete modules). The cost is concentration:
  every spec-type change, every COM-arg fix, and the build loop all edit the same 3.2k-line file.
- **Fix (low-risk, M):** extract the handler families into `spec/handlers/*.py` modules that
  self-register through the existing `_wire_handlers` registry (extrude, revolve, dress-up,
  patterns, sketch-segments). The build loop + orchestration stays in `builder.py`. Mechanical and
  fully protected by the existing per-primitive coverage tests — no behavior change.

### S2. Two feature-dispatch registries, organized two different ways ⚪
- **Evidence:** the codebase dispatches features through **two** registries that are legitimately
  distinct lanes — `features/` (the 36 `feature_add` kinds, a *package* of self-registering modules
  gated on `SPIKE_STATUS == "GREEN"`) and `builder.py`'s `_wire_handlers()` (the 30 spec types, a
  *flat in-file* table). Same architectural idea, two different file organizations.
- **Why it matters:** a contributor adding a capability has to learn which lane they're in *and*
  which of two unrelated registration styles applies. S1's extraction is the natural moment to make
  the spec-type lane mirror the `features/` package layout, so there's one mental model.
- **Fix:** fold into S1 — when handlers move to `spec/handlers/`, give them the same
  self-registration shape as `features/`. No need to merge the lanes (they're correctly separate).

### S3. Three more 2k-line hot-path modules (watch-list) ⚪
- **Evidence:** after `builder.py` (3,250) and the *auto-generated* `sw_types.py` (2,896, exempt —
  header says "DO NOT HAND-EDIT"), the next-largest hand-written modules are
  `drawing/lifecycle.py` (2,390), `observe.py` (2,202), and `mutate.py` (2,181).
- **Why it matters:** each is a single-file engine for a whole surface (drawing PAE, the 22 observe
  lanes, the transaction layer). They aren't audited internally here, so this is a **monitor** flag,
  not a prescription — but they are the next files to feel the same concentration pressure as
  `builder.py`.
- **Fix:** none now. Re-evaluate for splitting (e.g. `observe.py` → one module per lane group) if/when
  they cross ~2.5k or start attracting merge conflicts.

---

## Keep these — verified strengths (do not regress)

- **Seat-identification gate** (`build.py:92-144`): prints PID + active-doc title and pauses for
  `[y/N]` (default-N) before the first COM write. The single best UX moment for an operator with
  unsaved work. *(Issue #7 — landed well.)*
- **`--validate-only` / `--dry-run`** resolve specs (and `{rhs}` bindings) **without booting SW**
  — maps perfectly to a CAD "see what it'll do first" instinct.
- **Structured JSON errors, no tracebacks on normal failures**, with a `hint_key`/`remedy`
  catalog for known COM failure modes.
- **`DEFERRED.md` explains *why* a feature is walled** (kernel vs API vs platform) and the registry
  **fails loud** (`DORMANT`) rather than silently no-opping — earns deep trust from a veteran.
- **Capability-count integrity**: registry == README table == `list_kinds()` == 36; spec types
  == 30 (test-enforced). The honesty discipline is real.
- **`propose → approve → execute` / "there is no `--yolo` flag"**, the `filleted_box` ~3s smoke
  test, explicit version compatibility (2021 SP5+), v1.6 production + 3,700-test suite + live-SW
  lane.

---

## Claims investigated and rejected (don't spend time here)

All of these were raised by the persona and **refuted with code/doc evidence** — listed so the
maintainer doesn't chase them:

- "36 kinds is inflated; only 27 registered" → registry is exactly 36, matches README + `list_kinds()`.
- "`seat-proven` hides UNFIRED kinds" → `_register_lane` structurally registers GREEN only; zero leakage.
- "Capability boundary only appears at build time" → README §"Feature kinds you can add (36)" + `docs/CAPABILITIES.md` publish it up front.
- "Validation errors need JSON-pointer literacy" → the `message` names the offending feature by the user's own authored name (e.g. `'SK_1'`); the pointer is supplementary.
- "'This is a Python developer tool' discourages users" → honest, on-ramped expectation-setting (Issue #8), correctly placed in Prerequisites.
- "No pre-flight that the part is linked to its locals file" → conflates `ai-sw-mutate` with `ai-sw-build`; **build creates a fresh part and links the locals file itself** (`builder.py:3064`).
- "`--dry-run` is buried in `--help`" → surfaced in the README table, AGENTS Quickstart step 3, ONBOARDING, and an example README.
- "Unexpected exceptions leak a Python traceback" → `build()`'s broad `except Exception` (`builder.py:3103`) converts any handler error into a JSON `BuildResult` with the traceback in a *field*.
- "JSON spec naming is unfamiliar / no CAD-strategy docs / side faces broken / positioning conflict" → field names mirror SW's own vocabulary; example READMEs carry "Key patterns"/"Things to try"; side faces work; positioning is coherent.

---

## Suggested execution plan

**Sprint A — "Documentation truth" (≈ half a day, all XS/S):**
Items **1, 2, 3, 4, 5** — plus **6, 7**. These are the launch-blocking and trust-eroding items, and
none is engine work. Land #1 (license) as its own immediate commit.

**Sprint A′ — "README onboarding" (≈ half a day, rides with Sprint A):**
Items **15** (inline `spec.json` — do this one first), **16** (forewarn the seat gate in Quickstart),
**17** (show probe output), **18** (first-run troubleshooting table). All docs-only, all XS/S, and
they directly raise the evaluate→first-build conversion rate.

**Sprint B — "Discoverability & ergonomics" (≈ 1 day):**
Items **10** (`--list-kinds`), **11** (seat disambiguation), **12** (schema_version hint).

**Sprint C — "Parametric fidelity" (design-led, multi-day):**
Items **9** (semantic edge addressing — highest-value engine enhancement) and **8** (parametric
hole positions / pattern spacing). Track as a v1.7/v1.8 epic.

**Structure (opportunistic, not urgent):**
Item **S1** (extract `builder.py` handlers into `spec/handlers/` via the existing `_wire_handlers`
seam) folding in **S2** (give them the `features/`-style self-registration). Do it the next time a
spec-type change would otherwise touch `builder.py` anyway — the seam is already there, so it's a
low-risk, test-protected refactor rather than a rewrite. **S3** is monitor-only.

**Regression guardrails worth adding alongside the fixes:**
- a test building a child sketch on all 6 faces (locks #2),
- a code-derived assertion for the exit-code table (locks #3),
- a single `test_readme_counts.py` that greps the README for its **four** magic numbers — 30 spec
  types (`README.md:29`), 36 feature kinds (`:132`), 21 CLI commands (`:93`), 37 MCP tools
  (`:171/:215`) — and asserts each against the live source of truth (`schema.ALL_TYPES`,
  `HANDLER_REGISTRY`, the CLI registry, `EXPECTED_TOOLS`). This converts "documentation truth" (#4)
  from a manual sprint into a CI invariant: the README cannot drift past green.
- the existing `schema.ALL_TYPES == 30` test already protects the spec-type count.

---

*Methodology: 7-stage persona journey × adversarial verification, 64 agents total, every finding
re-checked against `feat/w67-phase3` @ `9f6e3ab`. All severities are post-verification (the
persona's original grades were adjusted up or down by the skeptic).*
