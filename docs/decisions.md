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
level (`docs/ROADMAP.md`, `docs/release_engineering.md`,
`docs/supply_chain_security.md`, etc.). The code-level findings
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

**Context:** v0.13 W4.1 task: pick how the project records
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
  `CODESTYLE.md`. The W4.2 contributor pass executed this
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

- The seven `central_idea/decisions.md` entries (this file's
  entries above through 2026-05-28 CODESTYLE) were reconstructed
  from the session record during the cleanup — they live in git
  now and can't be lost.
- The MCP design that lived in `central_idea/spec.md` §6 had
  already been promoted to `docs/mcp_server_design.md` during W5.4.
- The checkpoint-encryption design from `central_idea/` was already
  in `docs/checkpoint_encryption_design.md` (W3.1).
- Future strategic initiatives create their design doc in
  `docs/<initiative>_design.md` from day one rather than going
  through a scratch phase.

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
