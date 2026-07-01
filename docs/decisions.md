# Decision Log

Chronological record of strategic decisions for `ai-sw-bridge`. Each
entry is short by design — context, the decision, alternatives
considered, consequences. New entries append at the bottom under the
current date.

This file replaces the per-decision ADR pattern (see the 2026-05-28
entry below for the rationale). Append-only; reversed or superseded
decisions stay in place with a status update pointing to the new
entry.

**Format per entry:**

```
### YYYY-MM-DD — Short title

**Context:** what triggered the decision.
**Decision:** what we chose.
**Alternatives considered:** what we rejected and why.
**Consequences:** what this commits us to (and what it doesn't).
**Owner:** who decided.
**Status:** active | superseded by [date] | reversed [date].
```

> **Reconstruction note (2026-05-28):** Entries 1–7 below were
> originally drafted in `docs/central_idea/decisions.md` (gitignored
> local scratch). During the v0.13.0 release cleanup the scratch
> directory was deleted; these entries are reconstructed from the
> session record on the day of the cleanup. Going forward
> `docs/decisions.md` is the authoritative log and lives in git.

---

## 2026-05-23

### 2026-05-23 — Adopt "Paradigm 1.5" as the architectural positioning

**Context:** A 2026-05-23 external report (*State of AI-SolidWorks
Bridge Technologies — Comparative Analysis and Feature Tiering*)
introduces a four-paradigm taxonomy and creates a new slot —
"Paradigm 1.5: Declarative JSON Pipelines with Approval Guardrails" —
explicitly for ai-sw-bridge. The report places us at B-Tier and
credits the architecture with "entirely neutralizing ACE risks
without requiring a full MCP server."

**Decision:** Adopt Paradigm 1.5 as the bridge's customer-facing
positioning. The pitch is "declarative-JSON safety without MCP
overhead." (Lane M shipped in v0.13 but as an alternate transport,
not as a redefinition of the safety model — the validator still gates
every COM call regardless of whether the call came in via CLI or MCP.)

**Alternatives considered:**

- *Pursue full MCP (Paradigm 3) classification.* Rejected: MCP is
  useful but not essential for the AI↔SW loop; the existing CLI
  surface already closes the loop for any shell-capable agent.
  Pursuing MCP would inflate scope without unlocking new
  capabilities. (See the related Lane M decision below.)
- *Position as a Paradigm 2 fluent COM wrapper.* Rejected: that
  would imply we expose the SW API surface for human authoring; we
  don't — we constrain to a closed set of JSON-declarable primitives.
- *No external positioning.* Rejected: external report classification
  is a useful anchor for downstream conversations (recruiting
  contributors, defending against alternatives in selection
  processes).

**Consequences:** Marketing copy in `README.md` and other public docs
references Paradigm 1.5. Re-evaluation triggered if the external
taxonomy shifts or if the report is superseded by a newer analysis
with different framing.

**Owner:** Strategy lead.
**Status:** Active.

---

### 2026-05-23 — Demote Lane M (MCP wrapper) from precondition to adoption-driven

**Context:** Lane M was initially scoped as a sequencing precondition
(port `com_executor.py`, then ship the MCP wrapper before opening
other lanes). On re-check, MCP is useful for shell-less clients
(Claude Desktop, Cursor) but not essential for the AI↔SW loop — the
existing CLI surface already supports the full loop for any
shell-capable agent (Claude Code, Codex CLI, ChatGPT API with code
execution).

**Decision:** Lane M is deferred / adoption-driven. L1–L4 ship as
CLI-only first; Lane M opens only when external demand fires the
re-evaluation triggers.

**Alternatives considered:**

- *Ship Lane M first.* Rejected: would gate L1–L4 (the actual
  capability lanes) on transport plumbing the existing CLI already
  provides.
- *Drop Lane M from the roadmap entirely.* Rejected: Claude Desktop
  adoption was plausible enough that the bridge benefits from having
  the spec ready to execute when the trigger fires.

**Consequences:** Lane M's modules (`com/`, `mcp/`) were sketched and
the directory structure reserved. The `com_executor.py` port
prerequisite remained real and landed before Lane M opened, not as
part of it.

**Owner:** Strategy lead.
**Status:** Superseded 2026-05-28 — Lane M shipped in v0.13 after
Claude Desktop adoption fired the trigger. See the v0.13.0
`CHANGELOG.md` entry and `docs/mcp_server_design.md` for the design.

---

### 2026-05-23 — Three-surface attribution model with different granularity

**Context:** Initial three-surface attribution rule was uniform —
same per-file detail in docstring, `CONTRIBUTING.md`, and `README.md`
Acknowledgments. On re-check, listing every port as a separate
README line would make the project read as a citation index rather
than as architecture; per-repo consolidated structural credit at
README level is the right resolution.

**Decision:** Attribution lives in three surfaces with **different
granularity**:

1. **Module-level docstring** — per-file granular (LICENSE, upstream
   URL, commit hash, one-line adaptation note).
2. **`CONTRIBUTING.md` §"Third-party derivations"** — per-file
   granular (table row mirroring docstring + target path).
3. **`README.md` Acknowledgments** — per-repo consolidated (one line
   per upstream repo naming the structural pattern borrowed).
   Subsequent ports from the same repo do NOT add new README lines.

**Alternatives considered:**

- *Uniform three-surface granularity.* Rejected: bloats README with
  citation noise.
- *Single-surface attribution (docstring only).* Rejected:
  contributor visibility and license audit need the cross-references.
- *Per-port README lines.* Rejected: README becomes a citation
  index instead of describing our architecture.

**Consequences:** README stays curated at 3-5 headline structural
debts. CONTRIBUTING.md grows with every port. License-lint
automation (`tools/license_lint.py`) enforces docstring +
CONTRIBUTING parity; README is curated manually.

**Owner:** Strategy lead.
**Status:** Active.

---

### 2026-05-23 — Extend `src/ai_sw_bridge/` in place; no new top-level package

**Context:** v0.11 adds four new modules (`brep/`, `errors/`,
`rag/`, `checkpoint/`) plus two deferred ones (`com/`, `mcp/`).
Question: do they sit under `src/ai_sw_bridge/` or get a new
top-level package?

**Decision:** Extend `src/ai_sw_bridge/` in place. New modules are
flat siblings of `spec/`.

**Alternatives considered:**

- *New top-level package (`src/ai_sw_bridge_v2/`).* Rejected:
  bifurcates the bridge into two installable packages; users on
  v0.10 wouldn't get v0.11 transparently; double the install
  discipline.
- *Nest new modules under `spec/`.* Rejected: confuses ownership
  boundaries. `spec/` owns schema + handlers; `brep/`, `errors/`,
  etc., are services it consumes — not sub-components of it.

**Consequences:** `pip install -e .` continues to work across all
lanes including Lane M (shipped v0.13). The single chokepoint
pattern (`sw_com.py` today, `com/factory.py` post-Lane-M) is
preserved.

**Owner:** Strategy lead.
**Status:** Active.

---

### 2026-05-23 — SLOs are load-bearing reliability commitments, not aspirations

**Context:** v0.10 NFRs are time bounds (Cylinder ≤ 3 s) but lack
reliability commitments. The doc audit (P0-1) identified this as the
foundational gap; without measurable SLOs, every other metric is
wishful thinking.

**Decision:** Three SLOs gate v0.11 GA, each tied to a measurable
SLI in CI:

- **SLO-01:** 99% of `ai-sw-build --no-dim` invocations complete
  within NFR bound (latency).
- **SLO-02:** ≥ 99.5% of validation-passing specs succeed in build
  (success rate).
- **SLO-03:** 100% of Tier B errors caught by `errors/wrapper.py`
  (no Tier B → Tier C escapes).

Error budgets, breach response policy, and SLI instrumentation
requirements live in `requirements.md` §3.5 (and are now reflected
in committed code under `tools/regression_check.py` +
`tools/perf_baselines/`).

**Alternatives considered:**

- *No SLOs at v0.11; defer to v0.12.* Rejected: SLOs are foundational
  to every other metric (the audit's P0-1 ranking is on this
  rationale).
- *Tighter SLOs (99.9%).* Rejected at v0.11: not enough baseline data
  to justify the tightness. SLOs will tighten in later releases.
- *Looser SLO-03 (e.g., 95%).* Rejected: Tier C escapes are contract
  violations, not budget items. The budget is zero on purpose.

**Consequences:** v0.11 GA blocked on SLI instrumentation in
`tools/regression_check.py` + the fault-injection harness +
`.github/workflows/`. Tier C escapes are release blockers, not
deferrable.

**Owner:** Strategy lead.
**Status:** Active.

---

### 2026-05-23 — Apply audit doc-only findings in one pass

**Context:** The v0.11 doc audit identified 8 P0 + 10 P1 + 6 P2
findings. Initial application closed only P0-1 (SLOs); the execution
plan tracked the rest as 30/60/90-day work. User explicitly requested
applying the doc-only subset (i.e., everything that doesn't require
code) in a single pass.

**Decision:** Apply all doc-only audit findings in one pass:
`requirements.md`, `spec.md`, `UIUX.md`, `harvest_plan.md` (all in
the v0.11 scratch space) plus create seven new docs at the public
level (`docs/ROADMAP.md`, `docs/SECURITY.md`, etc.). The code-level findings
(telemetry module, feature flags module, anti-loop logic) remain on
the execution plan and are not blocked by this doc pass.

**Alternatives considered:**

- *Apply findings incrementally as lanes ship.* Rejected: the user
  explicitly requested the one-pass approach. Documenting upfront
  also makes the lane work more predictable.
- *Apply only the highest-priority subset.* Rejected: the doc-only
  changes don't cost meaningfully more than a curated subset would.

**Consequences:** v0.11 strategic docs reached "production-ready"
quality at the doc level. Code-level audit items remained on the
90-day plan and shipped across v0.11–v0.13.

**Owner:** Strategy lead.
**Status:** Active.

---

## 2026-05-28

### 2026-05-28 — Adopt `CODESTYLE.md`; do not adopt per-decision ADR files

**Context:** A v0.13 task: pick how the project records
architectural decisions and code-level conventions. Two patterns to
choose between: per-decision ADR files under `docs/adr/0001-*.md`
(the industry-standard "Architecture Decision Record" pattern), or a
single `CODESTYLE.md` consolidating code-level discipline.

The actual scattered surface at that point was *code-level norms*,
not strategic decisions:

- A working strategic-decision log already existed (this file) with
  a defined per-entry template (six entries from the 2026-05-23
  pass; the format conventions matched what most ADR repos achieve
  in seven separate files).
- Code-level discipline (pywin32 late-binding only, two-stream
  contract, fail-soft telemetry, no co-author trailers, persona
  vocabulary) was fragmented across `CONTRIBUTING.md`, code
  comments, agent memory files, and unwritten convention.
  Contributors and AI sessions re-derived these from inline comments
  rather than from a single source.

**Decision:** Adopt `CODESTYLE.md` at the repo root. Consolidate all
code-level discipline there. Keep `decisions.md` as the sole
strategic-decision log — no separate `docs/adr/` directory.
`CONTRIBUTING.md` continues to own onboarding and workflow; it links
to `CODESTYLE.md` for code rules.

**Alternatives considered:**

- *Adopt ADRs (per-decision files under `docs/adr/`).* Rejected:
  ceremony without filling a real gap. The decision log already
  works as a single-file ADR with a tighter per-entry template than
  most ADR repos achieve. Migrating seven entries to seven separate
  files would add navigation overhead, not reduce it.
- *Adopt both ADRs and CODESTYLE.* Rejected: duplicates the
  navigation surface. New contributors would have to learn which
  kind-of-decision goes where.
- *Inline all code conventions into `CONTRIBUTING.md`.* Rejected:
  `CONTRIBUTING.md` is contributor-facing onboarding; mixing it with
  load-bearing code discipline obscures both. `CONTRIBUTING.md`
  grew past 100 lines in v0.11 and the code-style subset was
  already cramped.
- *Do nothing; let convention emerge from code review.* Rejected:
  AI-pair-programming sessions cold-start with no project memory
  beyond what's in version-controlled docs. Without a single
  source, every session re-derives the same rules at random
  quality.

**Consequences:**

- New doc: `CODESTYLE.md` at repo root (not under `docs/`, because
  contributors find it via GitHub's top-level rendering).
- `CONTRIBUTING.md` §"Code style" reduces to a stub linking to
  `CODESTYLE.md`. A subsequent v0.13 contributor pass executed this
  consolidation.
- Future code-level conventions land in `CODESTYLE.md`, not as
  scattered comments. Conventions that change still go through
  `decisions.md` (the *why* of the change) and update `CODESTYLE.md`
  (the *what*).
- Design docs for individual subsystems (e.g.,
  `docs/checkpoint_encryption_design.md`,
  `docs/mcp_server_design.md`) remain their own files.
  `CODESTYLE.md` is for cross-cutting code discipline, not
  per-subsystem designs.

**Owner:** Strategy lead.
**Status:** Active.

---

### 2026-05-28 — Delete `docs/central_idea/`; replace with per-initiative committed design docs

**Context:** v0.13.0 release prep. `docs/central_idea/` had served as
a gitignored strategic scratch directory for the v0.11→v0.13
transition (requirements, spec, UIUX, audit_review, execution_plan,
todolist, harvest_plan, parallel_dev_prompt, user_research, plus
log/ and reference/ subdirectories holding upstream repo clones).
Total size 173 MB.

By v0.13 closure most contents were either superseded by committed
docs (CODESTYLE.md, CHANGELOG.md, ROADMAP.md, the per-subsystem
design docs) or had decayed (`todolist.md` still showed `[ ]` for
items that had shipped — the audit-trail-vs-live-state synchronization
problem that planning docs always hit).

**Decision:** Delete `docs/central_idea/` entirely. For ongoing
development, use three Git-tracked surfaces instead:

1. **`docs/<initiative>_design.md`** in git — one design doc per
   major initiative (e.g. `mcp_server_design.md`,
   `checkpoint_encryption_design.md`). Lives forever as historical
   reference once the initiative ships.
2. **`docs/decisions.md`** in git — this file. Cumulative
   append-only decision log.
3. **GitHub Issues / Discussions** — in-flight strategic
   conversations and open questions.

Plus `docs/DEFERRED.md` (single source of truth for v0.14+ backlog +
indefinitely-deferred items) and `CHANGELOG.md` for shipped state.

**Alternatives considered:**

- *Keep `central_idea/` as a permanent gitignored scratch space.*
  Rejected: drives doc rot (a planning doc that isn't enforced by
  CI inevitably falls out of sync with code); duplicates surfaces
  that committed docs already serve; the 173 MB reference/ subtree
  is a one-off download, not persisted state.
- *Move all `central_idea/` contents into git as-is.* Rejected:
  most contents are superseded; promoting them whole creates a
  permanent confused mess of historical-snapshot-vs-current-state.
- *Archive `central_idea/` to `docs/archive/`.* Rejected for the
  same drift reasons; an archive without "this is no longer the
  source of truth" markers reads as a parallel reality.

**Consequences:**

- The seven `decisions.md` entries (this file's
  entries above through 2026-05-28 CODESTYLE) were reconstructed
  from the session record during the cleanup — they live in git
  now and can't be lost.
- The MCP design that lived in `central_idea/spec.md` §6 had
  already been promoted to `docs/mcp_server_design.md` during the
  v0.13 cycle.
- The checkpoint-encryption design from `central_idea/` was already
  in `docs/checkpoint_encryption_design.md` (also during v0.13).
- Future strategic initiatives create their design doc in
  `docs/<initiative>_design.md` from day one rather than going
  through a scratch phase.

**Owner:** Strategy lead.
**Status:** Active.

---

## 2026-05-30

### 2026-05-30 — Reframe invariant #4 as "out-of-process Python"; adopt hybrid binding; close Route-C

**Context:** The durable-selection keystone (the "Persistent ID problem,"
`api_coverage_roadmap.md` §4 — Phase 0, the precondition for edit-robust
output) depends on `IModelDocExtension.GetObjectByPersistReference3`, whose
`[out] long` error parameter is the late-binding failure class. The
seat-run experiments (SW 2024 SP1, 2026-05-29) confirmed the wall empirically:
the persist-token and dispatch experiments came back **PARTIAL** — read works, the
OUT-param / Callout write-back does not marshal under dynamic (late) binding. Read
literally, that was the documented trigger for the in-process .NET
conversation ("Route-C", L5).

A decisive follow-up experiment, `spikes/v0_15/spike_earlybind_persist.py`
(**PASS**), tested whether the wall is the *API* or the
*late-binding marshaler*. Under a Python **early-bound** typed
`IModelDocExtension`, `GetObjectByPersistReference3(pid)` returns
`(<entity>, 0)`: the OUT error code arrives as the 2nd tuple element, the
object resolves, survives `ForceRebuild3`, and is selectable. The wall is
the marshaler, not the API — and clearing it does **not** require leaving
the out-of-process, `pip`-installable, JSON-only-agent design.

**Decision:**

1. **Reframe invariant #4.** The load-bearing guarantee is *"the bridge
   drives SOLIDWORKS out-of-process from Python, and the agent never
   touches COM directly"* — **not** "late binding specifically." Late
   binding was a means (avoid stale per-version gen_py wrappers, keep
   `pip install` free of a .NET SDK), never the end. Early-bound typed
   wrapping is still out-of-process Python; it does not re-admit any agent
   COM access and does not change the deployment story.

2. **Adopt hybrid binding.** Late binding stays the default for the whole
   surface. A narrow, sanctioned early-binding escape hatch
   (`com.earlybind.typed(obj, iface)`) typed-wraps *only* the specific
   objects whose `[out]` / Callout methods cannot marshal late-bound —
   built directly from the raw `_oleobj_`, because every win32com
   convenience path (`EnsureDispatch` / `Dispatch` / `CastTo`) trips on
   SW objects refusing `IDispatch::GetTypeInfo`. The agent-safety model
   (invariants #2 declarative-JSON-only and #3 zero-arbitrary-code) is
   untouched.

3. **Close Route-C (the C# in-process adapter / PythonNET, L5) as the
   answer to the durable-selection keystone.** Its sole remaining
   technical driver — OUT-param / Callout marshaling — is cleared
   out-of-process. L5 stays indefinitely deferred (it was already), now
   with no keystone dependency riding on it.

**Alternatives considered:**

- *Route-C — C# in-process adapter via PythonNET.* Rejected as the
  keystone path: it would add a .NET SDK to the install story (violating
  the deployment half of invariant #4) to solve a problem hybrid binding
  solves in-process-free. The S-tier reference (SolidPilot) uses it, but
  the early-binding experiment shows we don't need to.
- *Route-B — VBA emit-and-run.* Rejected: violates invariant #3
  (`run_macro` was deliberately removed in v0.14, a documented BREAKING
  change); reopening it is a security-model reversal.
- *Flip the whole codebase to early binding.* Rejected: early-bound
  typed objects expose the typelib's real property/method split, so
  some calls the bridge reaches as auto-invoked attributes (e.g.
  `RevisionNumber`) become methods that must be *called* — a wide, risky
  diff for no benefit on the ~16 primitives that already marshal fine
  late-bound. Hybrid is surgical; full early-binding is a rewrite.
- *Accept fingerprint-only reselection (the §4.4 RED fallback).*
  Rejected as the primary path: lossy across large edits. Kept as the
  documented degradation when a persist token is unavailable.

**Consequences:**

- New module `src/ai_sw_bridge/com/earlybind.py` (`typed`,
  `typed_extension`, `is_early_bound`, `EarlyBindError`) — capability
  only; no production call site yet. Built on `com.sw_type_info` (added
  `wrapper_module()`), which already owns makepy module loading.
- `CODESTYLE.md §2.1/§2.2` updated: "late binding only" becomes "late
  binding by default; early-binding typed-wrap is the sanctioned, narrow
  exception for OUT-param / Callout objects via `com.earlybind`." The
  `gencache.EnsureDispatch` ban stands (it fails on SW anyway); the
  committed-`gen_py/` ban stands.
- Unblocks the Phase-0 keystone work out-of-process: open-existing-doc
  build target + `mutate.py` feature-additions anchored to a durable
  persist token. These are gated on their own experiments per the
  measure-first rule before shipping.
- The four FAIL feature experiments (sheet metal / shell / draft / variable
  fillet / hole-wizard) must be **re-tested under early binding** before
  being declared blocked — their late-bound FAIL may be the same
  marshaler limitation, not an API one.

**Owner:** Lead maintainer, with the seat operator.
**Status:** Active.

---

## 2026-06-11

### 2026-06-11 — Multi-body booleans are terminal out-of-process walls; ship merge-on-create, park an OPTIONAL in-process add-in (Route-D)

**Context:** The multibody-boolean seat experiments proved `combine` and `split`
cannot **commit** out-of-process. `PreSplitBody` computes the temp bodies but
`PostSplitBody` will not commit (all `BodiesToMark` forms no-op);
`InsertCombineFeature` no-ops across 8 variants; no `swFmCombineBodies`
enum exists; and the `IInsertCombineFeature` array path cannot marshal a
body SAFEARRAY ("The Python instance can not be converted to a COM
object"). This is the **same VT_DISPATCH-SAFEARRAY finalize wall as
edge-flange** — a *commit-time marshaler* wall, distinct from the
2026-05-30 `[out]`-param wall. **Early binding does not clear it:** the
2026-05-30 fix marshals an `[out]` scalar back; here the failure is
committing a SAFEARRAY of *live body objects* across the o-o-p boundary at
finalize. Tested both bindings; the bodies drop regardless.

The wall is a **class, not a one-off**: combine, split, edge-flange
(normal-to-edge profile automation), loft (`CreateDefinition(9)` → None),
in-file native configs (`SetSuppression2` no-op/leak), and free-DOF
interactive drag (`Transform2` never commits headless) all need
in-process execution to commit.

**Decision:**

1. **Execute the tactical stand-in (`feat/w54-merge-on-create`).**
   Modeling-time boolean **UNION** via `FeatureExtrusion2` arg 18 `Merge`
   — `boss_extrude_blind` gains `merge: bool` (default `true`): `true`
   fuses the boss into the solid it overlaps, `false` keeps it a separate
   body. **Subtraction already ships** via `cut_extrude_*`. The LLM
   declares unions at the extrusion phase; there is no post-hoc combine.
   Invariant-clean: no add-in, no macro, `pip`-only, agent emits JSON
   only. Seat-proven (`spikes/_probe_merge_effect.py`): `merge=true` → 1
   body, `merge=false` → 2 bodies. This **removes the urgency** from the
   add-in.

2. **Open Route-D — an OPTIONAL in-process C# add-in — as a backlog item,
   NOT scheduled.** It would drain the whole commit-time wall class by
   executing the walled FeatureData / body-boolean / `SetSuppression`
   calls in-process, where the SAFEARRAY-of-bodies finalize succeeds.

   *IPC shape (proposed):* a thin SOLIDWORKS add-in registers a local IPC
   endpoint (named pipe / localhost socket); Python sends the **same
   declarative JSON** spec; the add-in deserializes and executes **only**
   the commit-time-walled operations in-process. It is **not** a general
   code-exec channel — it accepts the same closed JSON vocabulary,
   preserving invariants #2 (declarative-JSON-only) and #3
   (zero-arbitrary-code). The Python out-of-process path stays the default
   for everything that already marshals; the add-in is invoked only for
   the walled kinds, and only if installed.

   *Invariant #4 carve-out Route-D requires (must be written FIRST):*
   #4 (post-2026-05-30) = "out-of-process from Python, agent never touches
   COM" + "`pip`-installable, no .NET SDK in the **base** install."
   Route-D is admissible ONLY as an **optional, separately-installed
   power-user component**: the pip-only core stays the default and fully
   functional (merge-on-create + cut cover the common boolean need); the
   add-in is an opt-in that unlocks the walled kinds. The base install
   must **never depend on it**. This carve-out must be added to invariant
   #4 before Route-D is scheduled.

**Alternatives considered:**

- *Early-bind the combine/split FeatureData (the 2026-05-30 fix).*
  Rejected for this wall: it clears `[out]` scalars, not
  SAFEARRAY-of-dispatch commits; the experiments confirmed the bodies drop at
  finalize under both bindings.
- *Route-B — VBA emit-and-run.* Rejected again: violates invariant #3
  (`run_macro` removed v0.14, a security-model reversal). Re-affirms
  2026-05-30.
- *Do nothing.* Rejected: the union need is the most common multi-body
  intent and merge-on-create covers it cleanly. **`split` (one body → many)
  stays genuinely unsupported until Route-D — accepted as a logged gap.**
- *Ship Route-D now.* Rejected as premature: merge-on-create + cut covers
  the high-frequency boolean need; Route-D is a multi-week effort (C#
  add-in + IPC protocol + the #4 carve-out + an installer story) for the
  long tail. Park until the uncovered kinds accumulate demand.

**Consequences:**

- `merge: bool` ships on `boss_extrude_blind`; offline-guarded
  (`tests/spec/test_boss_merge_threading.py`, 4 tests) + seat-proven.
- Route-D logged as the strategic drain for the commit-time wall class
  (combine / split / edge-flange / loft / in-file-configs / drag), each of
  which already carries its own NO-GO/DEFER record; this entry names them
  as **one class with one answer**. Gated on the invariant-#4
  optional-component carve-out being written first.

**Owner:** Lead maintainer + strategy lead.
**Status:** Active (Option A shipped; Route-D parked, unscheduled).

---

## 2026-07-01

### 2026-07-01 — Salvage `architecture.md`'s surviving rationale before retirement

**Context:** Phase 0 Task Group G retires `docs/architecture.md` — its
phase-by-phase module walkthrough is superseded 1:1 by
`docs/CLASS_RELATION_MAP.md`, which reflects the current (post-facade,
post-features-registry) module shape. But its "Why this design" section
held three pieces of "why" that are not restated anywhere else in this
log, and would otherwise be lost with the file.

**Decision:** Preserve the three rationales here, inline, before deleting
the file:

1. **Why Propose-Approve-Execute (the `mutate.py` state machine).** An AI
   agent that can "edit the model" needs three properties: verifiable
   (the agent sees the delta before committing), reversible (one command
   undoes the last change), auditable (every change leaves a permanent
   on-disk record). `propose → dry_run → commit → undo` hits all three —
   the dry-run shows the delta, the rollback restores the snapshot, the
   JSON proposal records persist on disk.
2. **Why `*_locals.txt` as the source of truth (not in-SW dimension
   values).** SOLIDWORKS' Equation Manager can link to an external file
   instead of storing values inline. Doing so survives a SW version
   migration (the linked file is plain text), is version-controllable, is
   editable from outside SW under a lock + atomic-write discipline, and
   makes reload explicit (`EquationMgr.UpdateValuesFromExternalEquationFile`)
   so the bridge — not SW — controls when a change propagates. Editing
   inside SW directly is fragile: the next linked-file reload can silently
   overwrite an in-SW edit.
3. **Why late-binding pywin32 was the *original* choice** (context that
   pre-dates, and grounds, the 2026-05-30 "hybrid binding" entry above).
   `win32com.client.gencache.EnsureDispatch("SldWorks.Application")`
   reliably fails ("This COM object can not automate the makepy process")
   on most SW installs. Without a typelib, every COM call goes through
   `IDispatch::Invoke`, which cannot marshal certain argument types (the
   `Callout` OUT-object in `SelectByID2`; OUT parameters in
   `GetErrorCode2` and `Save3`; the third arg of `RunMacro2`). The
   original design accepted these limits and used the legacy single-call
   methods (`SelectByID`, `GetErrorCode`, `Save`) that marshal cleanly
   late-bound instead.

**Alternatives considered:**

- *Let the rationale evaporate with the file.* Rejected: a future
  contributor re-litigating "why not just edit dimensions in the SW UI"
  or "why not a fluent API" would have no record to check against.
- *Reproduce the full `architecture.md` phase-by-phase walkthrough here.*
  Rejected: that content (module list, dependency graph, per-phase
  function tables) is superseded 1:1 by `docs/CLASS_RELATION_MAP.md`,
  which reflects the current shape; only the "why", not the stale "what",
  was at risk of being lost.

**Consequences:** `docs/architecture.md` is removed (`git rm`);
`docs/CLASS_RELATION_MAP.md` is the canonical architecture doc going
forward. References to `architecture.md` across the docs tree are
repointed to `CLASS_RELATION_MAP.md`.

**Owner:** Strategy lead.
**Status:** Active.

---

## Reversed / superseded decisions

- 2026-05-23 "Demote Lane M to adoption-driven" — **superseded
  2026-05-28** by the v0.13.0 release that shipped Lane M after the
  Claude Desktop adoption trigger fired.

---

## Format conventions

- Dates are absolute (YYYY-MM-DD), never relative.
- One decision per entry; multi-decision sessions get multiple
  entries.
- "Alternatives considered" is a load-bearing field — capture what
  was rejected and why, not just what was chosen. Future readers
  re-litigate without this context.
- "Status: active" until superseded or reversed; either transition
  records the link.
- When a decision is reversed, the new decision points back here
  and updates the prior entry's Status field. Do not delete the
  prior entry.
