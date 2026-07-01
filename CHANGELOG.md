# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.7.0] - 2026-07-01

**Semantic edges & CLI ergonomics release.** Fillet/chamfer edges can now be
addressed by topology (`{of_feature, face}` / `{of_feature, between_faces}`),
default-on and live-seat PAE-proven, so edge selections survive parametric dim
edits; plus `ai-sw-build --list-kinds`, a seat-identification banner with
`--yes`, an interactive build confirmation, and doc↔code drift guardrails.

### Added

- **Semantic edge addressing for fillet/chamfer (default ON).**
  `fillet_constant_radius` and `chamfer_edge` `edges[]` items now accept two
  topology-named forms in addition to the legacy literal `{x, y, z}` point:
  `{of_feature, face}` selects ALL edges bounding a named semantic face
  (`+x`/`-x`/`+y`/`-y`/`+z`/`-z`) of an earlier fixed-extent boss extrude, and
  `{of_feature, between_faces:[A, B]}` selects the single edge shared by two such
  faces. Unlike literal coordinates, these re-resolve against the current geometry
  on every build, so they survive upstream dim edits (change the box width and the
  filleted edge is still found). Forms may be mixed in one array and de-duplicate.
  Governed by the `semantic_edges` feature flag, **default ON** — the live-seat PAE
  of `IFace2.GetEdges` is green (of_face + between_faces both resolve and survive a
  40→80 mm width change; a literal point tuned to the old width correctly misses;
  see `spikes/spike_semantic_edges_pae.py` and `docs/pending_gates.md`).
  `--disable-flag semantic_edges` reverts to literal-only. The validator rejects a
  semantic selector when the flag is off, when `of_feature` is not an earlier
  fixed-extent boss extrude, and when `between_faces` names two faces that provably
  share no edge (e.g. `["+z", "-z"]`).
- **`ai-sw-build` seat-identification banner + `--yes` / `-y` flag.** Before the
  first COM write, `ai-sw-build` now prints which SOLIDWORKS seat it is about to
  drive — PID and active-document name — so a build can never silently land in the
  operator's foreground session. The new `--yes` / `-y` flag skips the confirmation
  prompt for non-interactive automation (the banner is still printed as the audit
  record). The banner is encoding-hardened: a non-cp1252 active-document title
  (e.g. CJK) degrades to a placeholder instead of crashing the build it guards.
- **`ai-sw-build --list-kinds`.** Prints the supported surface as JSON — the 30
  spec feature types (`schema.ALL_TYPES`) and the 36 `feature_add` registry kinds
  (`client.features.list_kinds()`) — then exits. Needs neither a spec nor a running
  SOLIDWORKS: the CLI-reachable, scriptable answer to "what can it build right now?"
  for operators who don't open a Python REPL.

### Changed

- **`ai-sw-build` default behavior: interactive builds now pause for confirmation.**
  On an interactive TTY, `ai-sw-build` prompts `Proceed with build? [y/N]` (default
  *no*) before the first geometry mutation. Non-interactive stdin (piped /
  agent-driven) and `--yes` proceed after the banner without prompting;
  `--validate-only` and `--dry-run` are unaffected (they never touch COM). Pass
  `--yes` to restore the old prompt-free behavior in scripts. Because this adds a
  flag and changes a default, the next release is a **minor** bump (v1.7.0).
- **README + AGENTS onboarding realignment.** README Prerequisites now flags the
  Python-developer audience and the "Python 3.10+ on `PATH`" requirement; the base
  install command is standardized to `pip install -e .` (the `[mcp]` extra scoped to
  the MCP section); capability counts are corrected to the code-derived figures —
  **30** spec feature types (`schema.ALL_TYPES`) and **36** `feature_add` registry
  kinds (`client.features.list_kinds()`), kept as two distinct surfaces — the
  hero-image placeholder is removed, and the example-spec count is trued to 20.
- **Documentation sanitization for the public boundary.** Trimmed `docs/` to the
  user/contributor-facing surface (71 → 36 tracked files). Internal maintainer-only
  material — release runbooks, AI-agent orchestration prompts (`docs/history/`),
  session reconstructions, and R&D spike reports — was relocated to an untracked
  `_internal/` directory (kept locally, off the repository). Stale pre-1.0 migration
  guides and the v0.14 hardening plan were removed. The `docs/README.md` index now
  reflects the sanitized structure. No code change.
- **`ai-sw-build` multi-seat banner lists every seat.** When more than one
  SOLIDWORKS instance is running, the banner now prints all PIDs and points to the
  active-document title as the real disambiguator, instead of flagging one arbitrary
  PID as "ambiguous" (the bound instance is the one in the COM Running Object Table,
  not necessarily the first PID).
- **README onboarding for a non-Python evaluator.** Added an inline example
  `spec.json` (the artifact the tool produces, previously shown only as a diagram
  box), a "first run didn't work?" troubleshooting table, a Git prerequisite + ZIP
  fallback, an explanation of the `pip install -e ".[mcp]"` extras syntax, and a
  Quickstart forewarning that the smoke-test build trips the `[y/N]` seat gate (plus
  the `ai-sw-probe` success output).

### Fixed

- **Eradicated the `pywin32` early-binding cache trap.** On any machine with a
  cached `gen_py` / makepy typelib for SOLIDWORKS (the installer, or any prior
  `EnsureDispatch` anywhere on the box, creates one), `GetActiveObject` returned an
  *early*-bound object graph in which zero-arg COM methods are bound methods rather
  than auto-invoked properties. Reading one bare returned the method object instead
  of its value — which silently broke the `SW_VERSION_VERIFIED` gate (it parsed a
  method repr and skipped the check), made `ai-sw-probe` print a bound-method repr
  instead of the revision string, and degraded
  `spec._version_resolver.read_running_major` to `None` (a back-compat hazard on
  SOLIDWORKS 2021). Fixed with a three-layer defense: late binding is forced at the
  `get_sw_app()` boundary, every property-style read routes through the
  binding-agnostic `sw_com.resolve()`, and an AST guard
  (`tests/test_no_direct_com_reads.py`) fails CI if a bare read reappears.
- **Synchronized `docs/AGENTS.md` with the code.** The agent guide's capability list
  was frozen at the v0.10-era count; it now reflects the code-derived surface and
  the live `client.features.list_kinds()` source of truth.
- **Documentation true-up — docs that disagreed with the code.** `known_limitations.md`
  and `spec_reference.md` no longer claim `±x`/`±y` faces raise `NotImplementedError`
  (all six extrusion faces are implemented; side faces require a rectangular
  Front-Plane parent). The `tools_reference.md` exit-code table now documents
  `ai-sw-build`'s real codes (`0`/`2`/`3`/`4`/`5`/`6`/`7`, never `1`) and that the
  seat banner goes to stderr. The §4 fillet error string is corrected to the live
  "matches no edge within 1um" message, and the `ONBOARDING.md` "15 working specs"
  count is trued to 20.
- **Localized READMEs declared the wrong license.** The zh-TW / zh-CN READMEs showed
  an **MIT** badge and prose for what is a **Proprietary/commercial** product. Both
  are corrected to Proprietary (with the historical note that v1.0.0–v1.4.0 were
  MIT), counts updated, and a prominent "this translation is stale — see the English
  README" banner added pending the full retranslation.
- **`ai-sw-build` no longer crashes on an unreadable spec file.** A file that exists
  but cannot be decoded (non-UTF-8) or read (permission / I/O error) now degrades to
  the same clean exit-2 JSON error as a missing file, instead of escaping as an
  uncaught traceback.
- **`schema_version: 2` gives an actionable error.** With the default-off `schema_v2`
  flag, declaring `schema_version: 2` now returns a hint naming
  `--enable-flag schema_v2` instead of a bare "1 was expected".
- **Regression guardrails against doc↔code drift.** New tests pin the README's
  headline counts (30 / 36 / 21) to their source constants, the six-face support, the
  documented exit codes, and the doc-quoted error strings — so this class of drift
  fails CI rather than reaching a user.

## [1.6.1] - 2026-06-26

**Documentation & audit release.** No code behavior change — this release captures
the v1.6.0 commercial-hardening artifacts in the public history and closes a
fresh-user documentation gap. Cut after the four-human-gates pass: the release was
published (Gate 2) and the resilience proofs were fired on a live seat (Gate 3).

### Added

- **`docs/CLASS_RELATION_MAP.md`** — navigational map of the architecture: the
  `SolidWorksClient` + five facades, the `_impl` cores they delegate to, the
  `feature_add` `HANDLER_REGISTRY`, the `verify.py` substrate, the RES-1 resilience
  envelope, and the COM substrate — with mermaid diagrams and the 22-layer
  import-linter hierarchy.
- **`docs/CODEBASE_AUDIT_2026-06-26.md`** — a commercial-standard audit (duplication /
  mode selection / redundancy / README completeness / commercial posture) with
  per-dimension verdicts and prioritized recommendations.
- **README — "Feature kinds you can add (36)"** — the 36 seat-proven `feature_add`
  kinds are now enumerated (grouped) with a `client.features.list_kinds()` pointer;
  previously a fresh user had to introspect the registry to discover them.

### Changed

- **Resilience claim upgraded to live-proven.** The five `SupervisedSession`
  destructive-recovery proofs (`tests/e2e_sw/test_supervised_recovery.py`) — apply-
  death, the customer `batch()` path (RES-1), open-death (Tier-1), save-death
  (Tier-2 snapshot restore), and the poison-cap — all passed on a live SOLIDWORKS
  2024 (v32.1) seat on 2026-06-26, with zero orphan seats after teardown. The 1.6.0
  "Live (armed, operator-gated)" status is now verified.

### Tooling

- `tools/release_v1.5_v1.6.sh` (guarded, idempotent release script) and
  `tools/remote_prune_plan.sh` (guarded pre-public remote sanitization) are included
  for the human-gated release/launch workflow (`docs/human_gates_runbook.md`).

## [1.6.0] - 2026-06-26

**Self-healing batch by default (Wave 2).** The `SupervisedSession` crash-recovery
envelope that shipped in 1.5.0 as an opt-in layer is now WIRED into the default
batch path: `client.mutate.batch()` and the `ai-sw-batch` CLI run inside the
envelope unless `supervised=False` is passed. A live SOLIDWORKS death mid-batch is
detected, the seat respawned, and the proposal list idempotently replayed (Tier-1
pristine / Tier-2 snapshot-restore) on the path a customer actually calls — and the
durable PENDING|COMMITTED ledger now has a production writer, so `sw_session_health`
reports real recovery data.

### Added

- **`client.mutate.batch(..., supervised=True)`** — the batch transaction runs
  inside the resilience envelope by default; pass `supervised=False` for the bare
  best-effort engine. Degrades gracefully to the bare engine if the resilience
  layer cannot be constructed or the pre-run snapshot fails.
- **Production windowless-orphan reaper** (`ExecutorSeatController.reap_orphans`) —
  a respawn could leak a headless `SLDWORKS.exe` that pins a (costly) licensed
  seat; the reaper kills, **by PID only — never `/IM`**, any SLDWORKS spawned
  during the session that is neither a pre-session baseline seat nor the bound
  seat. Runs after each respawn and on batch teardown.
- `ExecutorSeatController` is now exported from `ai_sw_bridge.resilience`.

### Verification

- Offline: the supervised wiring is unit-proven — envelope engages, durable ledger
  written, `supervised=False` escape hatch, graceful fallback, teardown reap
  (`tests/test_batch_supervised.py`).
- Live (armed, operator-gated): `test_customer_batch_api_survives_seat_death`
  re-runs the Case-7 Parasolid assassination **through `client.mutate.batch()`** (the
  customer path) and asserts geometry identical to the golden run; auto-skipped
  until fired on a real seat (`-m destructive_sw`).

### Security

- **Unified MCP write-gate (Option 3).** `sw_build` is now async and
  **elicitation-gated**, matching `sw_batch_execute`: it validates the spec, then
  secures an explicit in-chat `approve=true` via MCP elicitation **before any COM
  write or `save_as` to disk**. No MCP tool persists geometry without a human in the
  loop — the approval surface is the CLI `[y/N]` **or** MCP elicitation, never
  autonomous. Degrades to the `ai-sw-build` CLI when the client cannot elicit.
  Pinned by `tests/mcp_lane/test_build_elicit.py` (the COM build callable is invoked
  only on approval; never on decline / cancel / timeout / unsupported) and the
  `COM_SAFE_VIA_MANUAL_DISPATCH` contract in `test_server_contract.py`.

### Changed

- **Documentation realigned to the shipped surface.** `README.md` and the new
  `docs/PUBLIC_API.md` contract now reflect 21 CLI commands (with stability tiers)
  and 37 MCP tools; the stale "no assemblies / mates / drawings" limitation was
  removed. `com/latebound.py` consolidates the previously-duplicated `_latebound`
  COM re-wrap (was byte-identical in three feature modules).

### Fixed

- **Drawing tolerance no-op now surfaces.** `_apply_tolerance_to_dims` previously
  counted a tolerance as applied without checking the kernel return; an explicit
  `False` from `SetToleranceType` / `SetToleranceValues` is now reported in the
  error manifest instead of being silently swallowed (live-seat PAE pending).

## [1.5.0] - 2026-06-25

**Runtime Resilience & Design Intelligence.** Two layers on top of the v1.4.0
batch/observability surface: an opt-in, live-proven supervised-session envelope
(`ai_sw_bridge.resilience`) that detects a SOLIDWORKS death mid-transaction and
replays the geometric intent — available to embed, **not yet the default batch
path** — and a local, on-device semantic memory over the operator's own design
history. Cross-cutting session/intelligence layers — no part-feature ribbon
surfaces change. Offline suite green at 3697 tests; the live destructive
`destructive_sw` lane proved Cases 7–10 on a real seat.

### Added

- **`SupervisedSession` crash-recovery envelope** (`ai_sw_bridge.resilience`) —
  wraps the fail-soft batch transaction in detect → respawn → idempotent-replay.
  A mid-transaction seat death is caught (a liveness oracle disambiguates a
  genuine geometric fault from a dead seat), the seat is auto-respawned (~8–9 s),
  and the full declarative proposal list is replayed to a geometrically identical
  result. **Tier 1** (open/apply death → pristine disk → replay) vs **Tier 2**
  (save death → restore a file snapshot → replay); a poison-proposal quarantine
  plus retry / wall-clock caps prevent an infinite respawn loop. All collaborators
  are injected so the state machine is unit-tested offline with no seat and no
  real sleep. Measured seat-death signatures: early-bound `com_error 0x800706BA`
  (RPC_S_SERVER_UNAVAILABLE), open-stage `0x800706BE` (RPC_S_CALL_FAILED), and
  dynamic-dispatch `AttributeError` — the envelope catches all three. Ships as
  an opt-in envelope you wrap around a batch run; the default `ai-sw-batch` /
  `client.mutate.batch()` path is unchanged (best-effort, fault-manifest) until
  you adopt it.
- **Durable Tier-2 ledger** (`checkpoint.TransactionStore` +
  `resilience.TransactionStoreJournal`) — a dedicated SQLite table for batch
  transactions (distinct from the per-feature `CheckpointStore`; a transaction
  carries an intent payload + status, not a geometry hash). PENDING → COMMITTED
  on recovery; a fatal/unrecovered run leaves the row PENDING as the host-crash
  resume anchor. The recovery summary (tier / replays / deaths) is persisted to a
  nullable `recovery_json` column when a death was actually caught.
- **Design-Memory RAG** (`ai_sw_bridge.rag.design_verbalizer` +
  `design_memory`) — a second, local `sqlite-vec` index over the operator's own
  design history so the agent can ground new proposals in proven past sequences.
  A kind-dispatched **verbalizer** turns each design into a syntax-free "recipe"
  (feature-add / drawing / assembly / part-build) — embedding raw JSON would
  cluster vectors on JSON-ness instead of intent. Backfilled from `proposals/` +
  `.checkpoints/` (≈169 recipes); `spikes/_results` excluded and reported.
  Embeddings are computed **on-device** (all-MiniLM-L6-v2 / a deterministic hash
  backend) — proprietary design history never leaves the machine. The index is a
  private, gitignored runtime artifact.
- **`ai-sw-memory` CLI** — `build` (backfill the index) / `search` / `stats`.
- **MCP tools** (all read-only, non-COM):
  - `sw_retrieve_design_memory` — semantic retrieval over the design-memory
    index, with `kind` / `recipe_kind` metadata filters.
  - `sw_session_health` — seat presence (PID-level) + the durable
    transaction-ledger audit (pending / committed / failed + recent + last
    recovery) → a degraded / attention / healthy verdict, so an agent can tell
    whether it is operating in a degraded or recently-recovered environment.

### Fixed

- **MCP tool-inventory contract** trued up — `sw_observe_mbd` (shipped in v1.4.0)
  was never added to the `EXPECTED_TOOLS` registration audit; the staleness was
  hidden because the `mcp_lane` suite is `destructive_sw` (skip-by-default). Added
  it alongside the two new tools.

### Internal

- Destructive-test hygiene: a respawn-orphan reaper kills only SLDWORKS processes
  that appeared *during* a test run (the envelope's windowless respawns), never a
  pre-existing PID — the baseline-diff is the safety boundary that protects an
  operator's interactive seat. Every destructive kill remains singleton-guarded +
  PID-bind-checked (never `/IM`).

## [1.4.0] - 2026-06-24

**The PMI Observability Release.** Adds a read-only lane that serializes a part's
DimXpert / MBD **Product & Manufacturing Information** — datums, size dimensions
with tolerances, and geometric tolerances — to structured JSON, exposed both on
the `SolidWorksClient` class API and over the wire as an MCP tool so an agent can
read a model's manufacturing definition directly (no drawing required). The lane
is the product of measure-first reconnaissance that mapped 50 `IDimXpert*`
interfaces and proved the read graph marshals cleanly out-of-process while the
authoring path walls — so this ships pure-read by design. Backward compatible;
the public surface grows only additively. Offline suite green at 3648 tests; the
live-seat `destructive_sw` lane green (36 payload snapshots incl. the new tool).

### Added

- **`client.observe.mbd(file_path=None)`** (`observe_mbd.py`) — serialize DimXpert
  / MBD PMI on a part to categorized JSON: `datums` (`{label, attached_feature,
  name}`), `dimensions` (`{type, nominal, symmetric_tolerance, fit_code,
  asymmetric_extracted, upper_deviation, lower_deviation, attached_feature}`), and
  `geometric_tolerances` (`{symbol, tolerance_value, primary_datum,
  secondary_datum, tertiary_datum}`). Read-only and parts only; with `file_path`
  the part is opened, read, and closed (never modified or saved), otherwise the
  active doc is read in place. Uses the adaptive `DimXpertManager("", False)` call
  so it reads a part's *authored* schema rather than spinning up a fresh one.
- **`sw_observe_mbd` MCP tool** (`mcp/_tool_observe.py`) — the agentic wire surface
  for the lane, decorated with `@com_tool` (ComExecutor STA-thread dispatch). Its
  description instructs the model on exactly which PMI it can expect and on the
  asymmetric-tolerance fallback behavior.

### Known limitations

- **Asymmetric tolerance extraction is best-effort / live-PAE-pending.** The
  DimXpert API exposes no native upper/lower (+/-) deviation getters — only a
  nominal value, a single symmetric tolerance band, and the fit code. Asymmetric
  bounds (e.g. `+0.2 / -0.05`) are recovered via a defensive bridge to the display
  dimension (`GetDisplayEntity → IDisplayDimension → IDimension.Tolerance →
  ITolerance.{GetMaxValue, GetMinValue}`). On success `asymmetric_extracted` is
  `true` and the bounds are populated; on any fault the lane degrades to the
  symmetric base fields with `asymmetric_extracted=false` — it never raises.
  **Proven:** datum labels, nominal values, symmetric tolerances, fit codes, GTOL
  values, and datum references (offline dual-branch suite, 12 tests). **Pending:**
  the asymmetric success path awaits a GUI-authored PMI fixture for live-seat
  validation — authoring DimXpert PMI walls out-of-process, so the fixture cannot
  be generated programmatically (tracked in `docs/pending_gates.md`).

## [1.3.0] - 2026-06-24

**The Single-Surface Approval & Telemetry Release.** The human-in-the-loop batch
approval moves into the agent's chat surface. Where v1.2.0 split the loop across
two surfaces — plan over MCP, approve+commit on the CLI — v1.3.0 collapses
approval onto one surface via the MCP **elicitation** protocol: the agent runs a
single tool, the approval prompt appears in-chat (e.g. Claude Desktop), the human
clicks, and the commit fires. The CLI gate remains as the headless/non-interactive
fallback (nothing was removed). Shipped alongside a zero-red test-suite hygiene
pass that eliminates the last known-failing tests from the isolated destructive
lane. Backward compatible — the public surface grows only additively. Offline
suite green at 3636 tests; the live-seat `destructive_sw` lane green at 66.

### Added

- **`sw_batch_execute` MCP tool** (`mcp/_tool_batch_execute.py`) — the
  single-surface PLAN → approve-in-chat → COMMIT loop. An `async` tool that runs
  a hard-wired **dry-run** plan on the live kernel, presents the recovery manifest
  for approval via `ctx.elicit` (MCP elicitation), and — only on an explicit
  in-chat approval — fires the irreversible commit. A `300s` walk-away timeout and
  every non-approval path (decline / cancel / accept-but-unapproved / timeout)
  route to a clean no-op abort with **zero COM mutation**. Capability-gated: a
  client that does not advertise elicitation degrades gracefully to a refusal that
  points at `sw_batch_plan` + the `ai-sw-batch` CLI.
- **`run_on_executor` STA-dispatch primitive** (`mcp/tools.py`) — extracted from
  the `@com_tool` decorator (now a thin wrapper over it) so the async tool reuses
  the exact same ComExecutor STA-thread dispatch invariant. `sw_batch_execute`
  awaits `ctx.elicit` on the event loop *between* two `run_on_executor` COM phases
  (plan, then commit) — a pattern `@com_tool` structurally cannot express, since it
  submits the whole body to the event-loop-less STA worker.

### Fixed

- **Zero-red hygiene pass on the `destructive_sw` lane.** The payload-snapshot
  suite (`tests/mcp_lane/test_payload_snapshots.py`) carried a cross-test cached-
  dispatch leak: the observe tools build a fresh `SolidWorksClient()` whose COM
  dispatch is bound, via the module-level `sw_com` cache, to the executor STA
  thread that created it. Each test gets its own per-test runtime/executor thread
  but shares that module cache, so a later test reused an earlier (since-dead)
  thread's dispatch and raised `CO_E_OBJNOTCONNECTED`. The `mcp_server` fixture now
  drops the cache (`release_sw_app()`) around each test so every runtime
  re-attaches on its own thread. (The real server is one runtime/one thread per
  process, so the leak was a per-test-runtime artifact only — not a product
  defect.)

### Added (tests)

- Snapshot fixtures for `sw_feature_statistics`, `sw_analyze_stackup`, and
  `sw_batch_plan` — the last three registered tools that lacked one — generated via
  `tools/probe_mcp_tools.py` (now covers them) and hardened with union-marker
  shapes so a future re-probe against an open document cannot silently degrade a
  state-tolerant fixture to a single-state one.

## [1.2.0] - 2026-06-24

**The Agentic Batch & Extensibility Release.** A complete, human-gated batch
workflow that spans the agent↔transaction boundary: an agent validates a
multi-feature edit over MCP (dry-run, never persists), a human approves and
commits it via the CLI. Plus the final out-of-process feature extraction
(`intersect`) and a typed-transaction hardening fix. Every addition was
measure-first probed on a live seat and proven through the full zero-trust
gauntlet (offline suite, two-stream lint, import-linter, live seat PAE). Backward
compatible — the public surface grows only additively. Offline suite green at
3608 tests.

### Added

- **`client.mutate.batch(file_path, proposals, strict=False)`** — apply a sequence
  of feature-add proposals to an existing part in ONE `_open_doc_typed`
  transaction. Default semantics are **fail-fast best-effort**: execute in order,
  halt on the first handler failure, save the features that materialized. A
  ratified **recovery manifest** designed for agent resumption — a `committed`
  success trail (each with its verify-the-effect witness), a *singular* `fault`
  (with `stage` ∈ `open_doc`/`apply`/`save` and the offending proposal echoed
  verbatim), and a `skipped` resume queue. `strict=True` is all-or-nothing
  (close-without-save on any fault; SOLIDWORKS has no native rollback).
- **`sw_batch_plan` MCP tool** (`mcp/_tool_batch.py`) — the §6.5-aligned write
  *planning* surface. Runs the batch in a new hard-wired **dry-run** mode: every
  proposal's handler executes on the live kernel (each B-rep genuinely validated),
  but the document is **never saved** — the open-doc context is closed-without-save
  and all changes discarded. Returns the recovery manifest as the human-review
  artifact. The autonomous MCP surface can validate but can never persist; the
  commit stays a human-gated CLI action.
- **`ai-sw-batch` CLI command** (`cli/batch.py`) — the commit half of the
  workflow, closing the plan → approve → execute loop. Echoes a human-readable
  plan and an explicit `[y/N]` gate; decline (or EOF) exits cleanly with zero COM
  touch, approve fires the irreversible commit. Two-stream clean: plan/prompt/
  recovery render to stderr, the manifest JSON to stdout (pipe it back to the agent
  to resume a halted batch).
- **`intersect` feature_add lane** (`features/intersect.py`) — the final
  out-of-process feature extraction. A measure-first probe **falsified** the
  prediction that `intersect` joins the `combine`/`split` `ret=None` wall: its
  two-phase `IFeatureManager.PreIntersect2` (returns the mutual region list to the
  caller) → `PostIntersect` (commits a `Sculpt` feature) materializes
  out-of-process. This codified a **refinement of the boundary law**: the
  discriminator for OOP viability is the *transactional contract* (single-call
  solve-and-commit walls; two-phase explicit hand-back materializes), not the
  boolean nature of the operation. Registered GREEN (`BOOLEAN_INTERSECT` verify
  class). 36 feature_add kinds.

### Fixed

- **`bounding_box` typed-transaction hardening** (`features/bounding_box.py`). The
  handler resolved its reference plane via `IModelDoc2.FeatureByName`, which is
  absent on the makepy-typed proxy that `mutate._open_doc_typed` produces — so an
  advertised-GREEN feature silently *ghosted* on the production
  `propose → dry_run → commit` (and `batch`) path while passing on a raw
  late-bound doc. The lookup now routes through the callout-free
  `verify.find_feature_by_name` (a `GetFeatures` walk), which marshals on both doc
  flavors. Every registry kind now materializes through the typed transaction.

## [1.1.0] - 2026-06-24

**Post-GA hardening sprint.** Four backward-compatible additions on top of the
`1.0.0` GA architecture — one new `mutate` feature lane, two new read-only
`observe` lanes, and a transaction-binding hardening fix — each measure-first
probed on a live seat and proven through the full zero-trust gauntlet (offline
suite, two-stream lint, import-linter, live seat PAE). The public API surface
grows only additively; no existing contract changed. Offline suite green at
3547 tests.

### Added

- **`spiral` feature_add lane** (`features/spiral.py`). A flat (planar)
  Archimedean spiral — the closed-form curve sibling of `helix` — via the legacy
  `IModelDoc2.InsertHelix` call with `DefinedBy=3` (`swHelixDefinedBySpiral`) and
  `ConstantPitch=False`. Registered GREEN in `HANDLER_REGISTRY` (35 feature_add
  kinds). Authored as `{"type": "spiral", "pitch_mm": …, "revolutions": …}` on a
  base-circle sketch; verified by a real arc-length witness (CURVE gate).
- **`observe.import_diagnostics()`** (`observe_import_diag.py`). Read-only
  geometric health of the active part: solid/surface body breakdown, per-body
  `IBody2.Check3 → IFaultEntity` topology faults decoded via
  `swFaultEntityErrorCode_e`, the `IPartDoc.ImportDiagnosis` status flag, and a
  single-bool `clean` verdict. (`IModelDoc2.CheckModel` is absent from the SW2024
  DLL; `Check3` is the load-bearing fault source.)
- **`observe.body_interference()`** (`observe_body_interference.py`). Read-only
  pairwise solid-body clash detection within a multibody part —
  `IBody2.GetIntersectionEdges` for the clash signal and an exact interference
  volume computed on detached temp bodies (`Copy()` →
  `Operations2(SWBODYINTERSECT)` → `GetMassProperties`), guarded by a body-count
  mutation assertion. The parts complement to the W27 assembly `interference()`;
  kept a distinct, strictly-typed lane (never polymorphic). Logs the O(N²)
  pairwise count above 50 bodies.

### Fixed

- **Curve-lane typed-transaction binding** (`features/helix.py`). The disk
  transaction opens documents typed (`mutate._open_doc_typed`), on which
  `Extension.SelectByID2`'s `VARIANT(VT_DISPATCH, None)` callout and
  `InsertHelix` fail to marshal (`TypeError`). Both calls now route through a
  `_latebound` re-wrap seam (mirroring `ref_axis`/`spiral`), so `helix`
  materializes through the full `propose → dry_run → commit` transaction. A
  measure-first probe confirmed the sibling curve lanes (`composite`,
  `project_curve`, `curve_through_xyz`) were structurally immune (callout-free
  `select_entity` or no selection), so only `helix` required the fix.

## [1.0.0] - 2026-06-23

**General Availability.** The first stable release. `1.0.0` locks the commercial
architecture: a single public class API over a strictly-layered internal core
(`SolidWorksClient` → transaction pipeline → modular feature registry). The
legacy free-function surface is gone; the dependency graph is provably acyclic
and matches the conceptual architecture (import-linter: 0 violations).

This release is the culmination of the v0.18 grace line (which froze the
commercial boundary and deprecated the `sw_*` functions) and the 1.0.0
strangler-fig refactor (which dismantled the ~4,700-line `mutate.py` monolith
into a per-feature registry). The full offline suite is green at 3502 tests.

### Added

- **`SolidWorksClient` is the General Availability public API.** All capability
  is reached through one stateful, lazily-connected, injectable client and its
  five domain facades: `.observe` (read), `.mutate` (write — propose/dry-run/
  commit transactions), `.urdf`, `.export`, and `.features`.

### Changed

- **Modular feature registry.** Every `feature_add` handler now lives in its own
  `features/` module, registered in a `HANDLER_REGISTRY` and dispatched by a
  pure registry lookup. `mutate.py` retains only the transaction/orchestration
  pipeline (propose/dry-run/commit, the proposal store, validators) and holds
  **zero** feature handlers. This sharply improves maintainability and
  extensibility — a new feature is a new module + one registration line, with no
  edits to the monolith and no parallel-work collisions.
- The internal architecture is now strictly layered: `client` (facades) →
  `mutate` (transactions) → `features` (handlers). The `client → mutate`
  delegation is the single intended cross-layer edge, formally declared.

### Removed

- **The 44 legacy `sw_*` free functions are deleted.** They emitted
  `PendingDeprecationWarning` throughout v0.18 and were always slated for removal
  in 1.0.0. The implementation cores remain as module-private functions accessed
  exclusively by the client facades — the `SolidWorksClient` class is now the
  **sole** public interface.

### Migration

- Replace any remaining `sw_foo(...)` free-function call with the corresponding
  `SolidWorksClient` facade method (e.g. `sw_get_interference(doc)` →
  `SolidWorksClient().observe.get_interference()`; `sw_propose_feature_add(...)`
  → `client.mutate.propose_feature_add(...)`). The data contracts (return
  payloads) are unchanged — only the entry point moved.

## [0.18.1] - 2026-06-23

Finalizes the v0.18 commercial boundary. `0.18.0` introduced `SolidWorksClient`
and sealed the 44-verb `sw_*` surface behind `.observe` / `.mutate` / `.urdf`;
`0.18.1` completes the surface with the two remaining facade-only domains, so
every framework capability is reachable through the single client.

### Added

- **`SolidWorksClient.export` (`SolidWorksExportFacade`)** — `run(doc, requests,
  part_name)` wraps the `export.export_all` orchestrator. The internal build
  pipeline (`spec/orchestrator.py`) and URDF export now route file output through
  this facade, making the client the single export seam.
- **`SolidWorksClient.features` (`SolidWorksFeaturesFacade`)** — read-only
  introspection over the feature registry: `list_kinds()` returns the
  seat-proven feature kinds the build supports, `supports(kind)` tests
  membership. A discovery surface for consumers deciding what to dispatch; the
  feature-creation write path remains on `.mutate.propose_feature_add`.

These are facade-only (no `sw_*` free functions exist in these domains), so no
deprecation shims were added. The full client surface is now `.observe` /
`.mutate` / `.urdf` / `.export` / `.features`.

## [0.18.0] - 2026-06-23

The **class-based API grace line** release. Freezes the commercial-contract
boundary ahead of the 1.0.0 internal refactor by sealing the entire public
`sw_*` surface (≈27 observe + 17 mutate = 44 verbs) behind a single stateful
client, while every legacy free function keeps working behind a deprecation
shim. **All v0.17 scripts run unchanged** — the only behavioural change is a
`PendingDeprecationWarning` emitted by the legacy `sw_*` free functions.

This release also folds in the work tagged (but never changelogged) across
v0.15–v0.17: surfaces, sheet-metal completion, thread features, reference
geometry, drawing-annotation axis, and the read-only Evaluate cluster.

Design notes: `v1_0_commercialization_rfc.md` (internal, superseded by the
internal commercial-readiness dossier).

### Added

- **`SolidWorksClient` — the canonical entry point for the commercial API.**
  A single stateful owner of the SOLIDWORKS connection (`ISldWorks` app +
  makepy wrapper), acquired lazily and injectable for testing. Domain work is
  reached through cached facades that share that one context:
  - `.observe` (`SolidWorksObserverFacade`) — read / B-rep interrogation:
    bounding box, mass properties, inertia, measure (selection / angle / area /
    durable-pair), clearance / face-clearance, draft, undercut, min-wall,
    interference, section properties, feature statistics, and more.
  - `.mutate` (`SolidWorksMutatorFacade`) — the approval-gated write lifecycle:
    `propose_local_change` / `dry_run` / `commit` / `undo_last_commit`,
    `propose_feature_add` family, and the `assembly` / `drawing` / `properties`
    transaction families. The disk-backed, `proposal_id`-keyed transaction
    store is unchanged.
  - `.urdf` (`UrdfFacade`) — SOLIDWORKS assembly → ROS/URDF robot model.

      ```python
      client = SolidWorksClient()
      client.observe.measure_area()
      pid = client.mutate.propose_local_change("width_mm", "30")["proposal_id"]
      client.mutate.dry_run(pid); client.mutate.commit(pid)
      ```

- **`export_urdf` (W78)** — build a ROS/URDF robot model from a SOLIDWORKS
  assembly: joint origins from component placement, mesh export per link, with
  the co-residency STL lock handled via a two-phase read-then-standalone export.

### Changed

- **All public `sw_*` free functions are now thin deprecation shims.** Each
  emits `PendingDeprecationWarning` and delegates to a relocated `_impl` core;
  the logic is byte-identical to v0.17. The legacy in-module facades
  (`SolidWorksObserver`, `ProposalStore`) are retained and route to the same
  cores without warning. Internal callers (CLI runners, MCP tools) now consume
  `SolidWorksClient`.

### Deprecated

- **The public `sw_*` free functions** (e.g. `sw_get_measure_from_doc`,
  `sw_propose_local_change`, `sw_commit_assembly`) are deprecated in favour of
  the `SolidWorksClient().<facade>.*` methods. They remain fully functional in
  the 0.18.x line and are **scheduled for removal in 1.0.0**. Migrate by
  replacing a free-function call with the corresponding facade method.

### Fixed

- **`undo_last_commit` crashed on a shared proposal store.** When a committed
  proposal from another family (assembly / drawing / properties) sat in the
  shared store, the local-change undo bare-indexed local-only keys and raised
  `KeyError`. It now skips non-local-change records during candidate selection.

## [0.14.0] - 2026-05-29

The v0.14 commercial-hardening release. Fixes four shipped
correctness bugs surfaced by a full-codebase audit, removes one
broken-by-design legacy function, brings doc parity across README /
USAGE / AGENTS / tool-reference, and introduces class-based facades
(`SolidWorksObserver`, `ProposalStore`) over the observe and mutate
modules. **Specs that build in v0.13 build identically in v0.14**;
the only breaking change is the removal of `sw_run_macro` /
`ai-sw-mutate run_macro` (workaround unchanged: paste `.bas` into
VBE manually).

Audit + execution plan and migration guide were tracked in internal/superseded
docs (v0.14 era).

### Fixed

- **Parametric / `--deferred-dim` builds applied each equation
  binding twice.** `spec/builder.py` called `_collect_feature_bindings`
  + `_apply_bindings` in two adjacent blocks — once inside the
  `else:` of `if no_dim:`, once unconditionally outside it. The
  result: every `IEquationMgr.Add2` call fired twice and
  `BuildResult.bindings_added` carried duplicates. The Motor Mount
  Plate parametric build emitted 14 equation entries; the correct
  count is 7. v0.14 deletes the first (non-error-wrapped) block and
  keeps the canonical one with `com_error_boundary`. No spec change
  required; re-run any parametric/deferred-dim build to observe the
  fix.
- **`ai_sw_bridge.__version__` reported `0.1.0` forever.** The
  package-level constant was hardcoded; v0.14 reads from
  `importlib.metadata.version("ai-sw-bridge")` with a
  `"0.0.0+unknown"` fallback for source checkouts without
  `pip install -e .`.
- **Dead `deferred_watermark` assignment** inside the L4 checkpoint
  commit block (`spec/builder.py`). Cosmetic — the real watermark
  update happens in the deferred-dim replay path.
- **`test_excluded_tools_not_registered` was vacuously passing** —
  the test asserted that `sw_mutate_apply` is not in the MCP tool
  registry, but `sw_mutate_apply` never existed (the real mutate
  function names are `sw_propose_local_change`, `sw_dry_run`,
  `sw_commit`, `sw_undo_last_commit`). v0.14 replaces the fictional
  name with the four real ones, restoring meaningful coverage.

### Added

- **`SolidWorksObserver` class** (`ai_sw_bridge.observe`) — facade
  with 10 methods (`active_doc`, `feature_errors`, `equations`,
  `bbox`, `volume`, `screenshot`, `measure`, `mate_errors`,
  `custom_props`, `enabled_addins`) over the existing `sw_get_*`
  free functions. Recommended entry point for new code; the legacy
  free functions remain as backward-compatible shims and will be
  removed in v0.15 (`docs/DEFERRED.md` D-v0.14-06).
- **`ProposalStore` class + `ProposalState` enum**
  (`ai_sw_bridge.mutate`) — facade with 4 methods (`propose`,
  `dry_run`, `commit`, `undo_last`) and a typed state enum that
  mirrors the existing `ST_*` string constants. Recommended entry
  point for new mutate-lifecycle work.
- **Environment Variables section** in `README.md` — covers
  `AI_SW_BRIDGE_CAPTURES`, `AI_SW_BRIDGE_PROPOSALS`,
  `AI_SW_BRIDGE_FLAG_<NAME>`, `NO_COLOR`. Plus a note on the
  user-supplied `--checkpoint-encrypt env:NAME` variable.

### Changed

- **`ai-sw-build` row in `README.md`** now lists every flag
  (`--validate-only`, `--dry-run`, `--lint`, `--no-dim`,
  `--deferred-dim`, `--save-as`, `--save-format`, `--verify-mass`,
  `--reconnect`, `--checkpoint`, `--checkpoint-encrypt`,
  `--disable-addins`, `--strict-addins`, `--log-level`, `--verbose`,
  `--quiet`, `--locale`, `--enable-flag`, `--disable-flag`,
  `--auto-retry`) grouped by purpose. Manual upkeep until v0.15
  ships a CI doc-coverage gate (D-v0.14-05).
- **`ai-sw-mutate` row in `README.md`** lists the 4 surviving
  subcommands (`propose` / `dry_run` / `commit` /
  `undo_last_commit`) and the `AI_SW_BRIDGE_PROPOSALS` env var.
- **`ai-sw-apidoc` row in `README.md`** notes that fresh clones
  may need `python tools/build_api_index.py` to materialize the
  committed index.
- **Primitive count corrections.** README/AGENTS no longer say
  "12 primitives" / "12 working specs" — the real numbers (16
  primitives in the schema, 15 working specs in `examples/`) are
  used everywhere.
- **`sw_mutate_apply` references removed** from `README.md`,
  `docs/mcp_server_design.md`, `docs/lane_designs.md`,
  `docs/audit_s1_cli_mcp_parallelism.md`, and
  `src/ai_sw_bridge/mcp/server.py`. The MCP design doc also
  corrects the test names (`test_tool_inventory_matches_design`,
  `test_excluded_tools_not_registered`) that had drifted from
  reality.

### Removed (BREAKING)

- **`ai-sw-mutate run_macro` subcommand** and the underlying
  `ai_sw_bridge.mutate.sw_run_macro` Python function. The function
  was a 0.1.0-era stub that only worked on binary `.swp` files
  produced by SOLIDWORKS's own VBE editor; externally-generated
  `.swp` / `.bas` files were silently rejected. The supported
  workflow has always been to paste the generated `.bas` into VBE
  manually and press F5 — that remains unchanged. Code that
  imported `ai_sw_bridge.mutate.sw_run_macro` must remove the
  import; no in-process replacement exists. If/when binary-`.swp`
  write-back is figured out, `SldWorks.RunMacro` / `RunMacro2`
  can be called directly.

## [0.13.0] - 2026-05-28

The v0.13 closure release lands the **MCP server** (Lane M), the
**checkpoint encryption** layer (W3.1), **STA-threaded COM safety**
(W5.1 ComExecutor + W5.2 adapter pattern), and rounds out the v0.13
plan items across W1–W7. Adds an alternate stdio entry point
(`ai-sw-mcp`) so Claude Desktop / Cursor / other GUI MCP clients can
drive the same tool surface the CLIs already expose.

### Added

- **MCP server lane** (`ai_sw_bridge.mcp`, optional install
  `pip install ai-sw-bridge[mcp]`). New `ai-sw-mcp` stdio entry point
  registers 21 tools mirroring the existing CLI subcommands:
  10 observe (`sw_active_doc`, `sw_feature_errors`, `sw_equations`,
  `sw_bbox`, `sw_volume`, `sw_screenshot`, `sw_measure`,
  `sw_mate_errors`, `sw_custom_props`, `sw_enabled_addins`),
  `sw_build`, 5 apidoc (`sw_apidoc_search`/`detail`/`members`/
  `examples`/`enum`), 4 history/checkpoint
  (`sw_history_part`/`since`/`diff`, `sw_checkpoint_info`), and
  `sw_reconnect`. Design: `docs/mcp_server_design.md`. Excluded by
  design (CLI-only): mutate, codegen, probe, checkpoint
  genkey/rekey/migrate.
- **Clean-room implementation** — no code lifted from upstream
  `SolidworksMCP-python` MCP server (the upstream owns its own
  validator + checkpoint + safety surface; we own ours).
- **`@com_tool` decorator** (`ai_sw_bridge.mcp.tools`) — every
  COM-touching MCP tool runs on the W5.1 `ComExecutor` STA worker.
  Contract test enforces the decoration; forgetting it is a
  registration-time failure.
- **W3.1 — Checkpoint encryption** (`ai_sw_bridge.checkpoint.crypto`).
  App-layer Fernet (pure-Python, no SQLCipher install). Four key
  sources: `env:NAME`, `file:/path`, `keyring:SERVICE`, `prompt`
  (PBKDF2-HMAC-SHA256 600k iterations). Cell wrap format:
  `fernet_v1:<base64-token>` so future algorithms can dispatch by
  prefix. `_meta` table stores algo + key fingerprint + encrypted
  column list (plaintext metadata so `info` works without a key).
- **`ai-sw-build --checkpoint-encrypt <key-source>`** — passes the
  key source through to the L4 checkpoint store. Encrypted columns:
  `locals_snapshot`, `com_call_log`. **Bridge does NOT escrow keys;
  losing the key loses checkpoint history**.
- **`ai-sw-checkpoint` subcommands** — `genkey`, `info`, `rekey`,
  `migrate` for key lifecycle. `info` reads `_meta` without a key
  (plaintext by design).
- **W5.1 — `ComExecutor`** (`ai_sw_bridge.com.executor`) — single-
  threaded STA worker holding the COM apartment. Submit/run pattern
  with `Future`-propagated results and exceptions. Ported from
  `SolidworksMCP-python` 82e505d8 (MIT). Adaptations: stdlib logging,
  `is_dead` introspection, drain pending on shutdown.
- **W5.2 — Adapter factory** (`ai_sw_bridge.com.adapter`,
  `adapters/{pywin32,mock}.py`, `factory.py`) — `SolidWorksAdapter`
  abstract base; `AdapterFactory.create_adapter()` auto-selects
  pywin32 on Windows or mock elsewhere. Ported from
  `SolidworksMCP-python` 82e505d8.
- **W5.3 — `sw_type_info.flag_methods`** — per-interface COM method
  flagging for marshaling discipline. Ported from upstream.
- **W5.6 — `ComExecutor` death-recovery scaffolding** — `is_sw_dead`
  property, `reconnect()` method, recognises COM death HRESULTs
  (`0x800401FD` RPC_E_DISCONNECTED, `0x80010108` RPC_E_SERVER_DIED).
- **W7.1 — Add-in interference detection.** New
  `ai-sw-observe addins` subcommand + `--disable-addins` and
  `--strict-addins` flags on `ai-sw-build`. Enumerate-and-warn (NOT
  runtime unload — that's not a SW-supported API). 9 known-
  problematic add-ins curated: Toolbox, PDM Std/Pro, 3DEXPERIENCE,
  Routing, Electrical, Simulation, Inspection, Composer.
  Strict mode aborts a build with `rc=4` and
  `error: "strict_addins_blocked"`.
- **W2.1 — `ai-sw-observe custom_props`** subcommand. Reads every
  custom property from the active doc; structured JSON output.
- **W2.2 — Lazy B-rep interrogation mode.** Defers face/edge walking
  until a manifest entry actually needs topology, cutting startup
  cost for catalog/inventory use cases.
- **W2.3 — Terminal-aware color degradation.** Respects `NO_COLOR`
  env var and `isatty()` so piped output is plain text.
- **W2.4 — `ai-sw-build --save-format <version>`** — SaveAs3 to a
  specific SW year (`current`, `2024`, `2023`, `2022`, `2021`).
- **W3.2 — `tools/checkpoint_redact.py`** — produce a redactable
  `.sqlite.redacted.<ts>` from an encrypted (or plain) DB.
  `locals_snapshot` becomes `"<redacted_local>"`; com_call_log scrubbed
  via `_TRADE_SECRET_PATTERNS` regex.
- **W3.3 — `tools/spec_redact.py`** — parallel redactor for spec
  files.
- **W4.1 — `CODESTYLE.md`** — 11-section load-bearing style document
  (out-of-process marshaling, two-stream contract, fail-soft pattern,
  zero ACE surface, lane boundaries, etc.). Replaces the per-decision
  ADR pattern.
- **W4.2 — `CONTRIBUTING.md` contributor pass.** Adds "Designing new
  code" topic pointers to CODESTYLE.md sections; per-file port
  attribution table (7 ported files).
- **W4.3 — `tools/example_roundtrip.py`** doc-as-test. Re-runs every
  example spec through the validator + builder dry-run; CI catches
  schema drift in shipped examples.
- **W4.4 — `import-linter` lane-boundary contract.** Layer ordering
  enforced in CI: cli → mcp → spec/parameterize/observe/mutate →
  com/sw_com → checkpoint/rag/brep → errors/telemetry. Lower layers
  may not import higher.
- **W4.5 — Locale scaffolding (`locale/`).** i18n directory layout
  ready for translation contributions.
- **W5.5 — MCP payload pass-through snapshot tests.** 21 fixture
  files in `tests/mcp_lane/fixtures/`. Shape walker supports union
  markers (`["$str", "$none"]`) so state-dependent fields tolerate
  both empty- and live-SW runs without fixture regeneration.
- **Wire-level §11.5 end-to-end tests** (`test_wire_e2e.py`) — drives
  the real JSON-RPC layer (`initialize`/`tools/list`/`tools/call`)
  via in-memory anyio streams.

### Changed

- **CLI/MCP surface parallelism.** History tool success-path payloads
  no longer carry a redundant `ok: True` field. CLI never emitted it;
  MCP wrappers now match. Error paths still carry `ok: False` (MCP
  has no exit-code channel; documented as a deliberate divergence in
  design doc §7.2).
- **`pyproject.toml` layer ordering** — `mcp` slots between `cli`
  and `observe/spec`; cli stays topmost so it may import mcp (in
  practice neither imports the other today).

### Fixed

- **W3.1 privacy hotfix:** writes to an encrypted DB opened without a
  key source landed as PLAINTEXT in the encrypted store. Added
  `CheckpointStore._check_writable()` guard that raises
  `KeySourceError` from `insert_pending`/`commit`/`mark_failed`/
  `record_rollback` when the store was opened in encrypted-info-only
  mode. Regression test in `test_crypto_contract.py`.
- **MCP wire protocol:** `_Server.list_tools` was overridden as a sync
  method returning internal Tool records (so the contract test could
  walk `.fn`), but `FastMCP.list_tools` is `async def`. Every JSON-RPC
  `tools/list` and `tools/call` over the wire returned an error.
  Replaced the override with a new sync accessor `_Server.iter_tools()`
  for tests; the inherited async `list_tools` stays intact for the
  wire layer.
- **`sw_checkpoint_info` schema mismatch:** the MCP tool queried
  `SELECT key, value FROM _meta`, but the W3.1 `_meta` table is
  column-per-field (`encrypted_at`, `encryption_algo`,
  `encrypted_cols`, `kdf_algo`, `kdf_salt`, `key_fingerprint`).
  Every encrypted DB would have raised `OperationalError`. Fixed to
  mirror `cli/checkpoint.py:60` exactly. Regression test in
  `test_checkpoint_info.py`.
- **`ServerRuntime.reconnect` did not clear the sw_com dispatch
  cache.** `sw_reconnect` returned `ok: True` but the next observe
  call still surfaced the dead-handle `AttributeError`. Root cause:
  `sw_com._CACHED_SW_APP` is a module-level global that survives
  reconnect, and observe.* / mutate.* bypass the W5.2 adapter,
  calling `sw_com.get_sw_app()` directly. Fix calls
  `sw_com.release_sw_app()` first thing in
  `ServerRuntime.reconnect()`. Regression test in
  `test_reconnect_cache_clear.py`.
- **`executor.is_sw_dead` did not auto-flip on dead-handle errors.**
  W5.6 catalogued death HRESULTs (`0x800401FD`/`0x80010108`), but
  pywin32 actually surfaces SW death as
  `AttributeError('SldWorks.Application.<member>')` from dynamic
  dispatch. `observe.*` swallowed it into `result['error']`, so the
  exception never reached `ComExecutor._worker`'s HRESULT trap.
  Fixed by post-hoc detection in the `@com_tool` wrapper: after each
  tool call, inspect the returned payload for the dead-dispatch
  regex; if it matches, call new `ComExecutor.mark_sw_dead()` so the
  next call short-circuits with the `sw_reconnect` hint. False
  positives guarded against `<unknown>.<member>` patterns
  (legitimate late-binding misses on Extension etc.). Regression in
  `test_dead_dispatch_auto_flip.py` (3 tests); end-to-end check
  added to `test_e2e_death_recovery.py`.
- **MCP server spawned a ghost SW instance instead of attaching to
  the user's foreground session.** `sw_com.get_sw_app()` used
  `win32com.client.Dispatch("SldWorks.Application")`, which COM
  resolved by auto-launching a fresh SLDWORKS.exe when invoked from
  a subprocess (MCP server launched by Claude Desktop, IDE plugins,
  any out-of-process AI client). The ghost SW had no open
  documents, so every observation tool returned `no_active_doc`
  against the wrong SW process. Fixed by trying
  `win32com.client.GetActiveObject("SldWorks.Application")` first
  (queries the COM Running Object Table for an already-registered
  SW instance), falling back to `Dispatch` only if no running
  instance is visible. Verified live: Claude Desktop driving
  `ai-sw-mcp.exe` now attaches to the user's foreground SW and
  returns real geometry data (e.g. `sw_bbox` → 25×25×80mm against
  the open part).

### Known limitations (deferred to v0.14)
- **`observe.*` bypasses the W5.2 `MockAdapter`.** Calls
  `sw_com.get_sw_app()` directly instead of `runtime.adapter`. The
  W5.5 snapshot fixtures use union markers
  (`["$str", "$none"]`) to tolerate both no-SW and live-SW shapes,
  but a future task should route observe.* through the adapter for
  cleaner test isolation.
- **CI snapshot tests are SW-state-dependent on dev machines with
  pywin32 + live SW.** They lock in a tolerant union of both the
  empty and happy-path shapes; either runs fine.

### Test counts

- 944 tests pass excluding `solidworks_only` (was 689 at v0.12.2);
  **+255 new tests** across W1–W7.
- 1 test skipped (`§11.4 validation_error_maps_to_invalid_params`,
  separate follow-up).
- black: 262 files clean. flake8: 0 findings. mypy: 0 errors in
  85 source files. license-lint: 7 ported files validated.
  import-linter: 1 contract kept / 0 broken.

### Wave 5 integration audit (2026-05-28)

Pre-merge full audit caught and fixed five ship blockers:
- MCP wire protocol (sync `list_tools` override broke JSON-RPC)
- `sw_checkpoint_info` schema mismatch
- `ServerRuntime.reconnect` cache leak
- `executor.is_sw_dead` did not auto-flip on swallowed
  `AttributeError` death pattern
- `sw_com.get_sw_app()` spawned a ghost SW instance from MCP
  subprocess context instead of attaching to the user's foreground
  SW (now tries `GetActiveObject` before `Dispatch`)

Plus phase-2 live-SW verification:
- 18 observation/build/apidoc/history tools exercised against a real
  SW session — all return well-formed payloads
- Death-recovery flow validated end-to-end (kill SW → call →
  reconnect → call → recover)
- Encryption composition (sw_build --checkpoint-encrypt → MCP
  sw_checkpoint_info + sw_history_part) verified; no plaintext leak
- **Claude Desktop end-to-end smoke verified.** MCP server
  registers, tool discovery returns 21 tools, model-driven tool
  selection works, tool results render correctly in the chat
  surface. Verified happy-path against the user's live foreground
  SW: prompt "Call sw_bbox and give me the bounding box of the
  active part" → Claude Desktop selected the right tool → MCP
  attached to the foreground SW via `GetActiveObject` → returned
  real geometry (25×25×80mm for `dr_metrics_test.SLDPRT`) → model
  rendered the values + interpreted the part shape. Tested against
  Claude Desktop Cowork build (Windows Store package
  `Claude_pzs8sxrjxfjjc`).

Full Wave 5 audit details in commit messages of `4a5f849`, `d91676e`,
`5069866`, `f9dde03`, and `6e1778a`.

## [0.12.2] - 2026-05-27

Closes seven gaps surfaced by the post-v0.12.1 audit against
`docs/central_idea/`. Items #1–#3 were P0 (user-visible functional
requirements with no invocation path); items #4–#7 were P1 (privacy
gate, UX consistency, audit findings).

### Added

- **`ai-sw-history rollback <part> <id>`** subcommand (FR-v0.11-L4-02
  part A). Optional `--locals-path` writes the snapshot back to a
  locals file; without it, the rollback is audit-only. Exit codes:
  0 success, 8 verification failure.
- **`rollback_to(..., doc=, verify_tree_hash=)`** library extension
  (FR-v0.11-L4-02 part B). When `doc` is provided, calls
  `IModelDoc2.EditRollback` to rewind the SW feature tree, then
  re-computes the tree hash and compares against the checkpoint's
  `pre_tree_hash`. Mismatch raises `RollbackError`. The CLI still
  uses the software-side-only mode (`doc=None`); the live-SW leg is
  exposed for in-process callers.
- **`ai-sw-build --auto-retry`** flag (FR-v0.11-L2-04). Wires the
  existing `RetryGuard` into the build flow so an identical spec
  resubmission within the same session exits 7 with
  `identical_spec_resubmitted` payload. Off by default.
- **Uniform `--quiet` flag across all 7 CLIs** (UIUX §2.2, §3.3).
  New `cli/streams.py` centralizes the helper; each entry point
  wires it consistently. stdout JSON is unaffected.
- **4 sketch contour validity hints** (audit §6.4):
  `sketch_self_intersect`, `sketch_open_contour_needed_closed`,
  `sketch_construction_only`, `sketch_tangent_dim_conflict`. Catalog
  grows 9 → 13 entries.
- **`Manifest.active_configuration`** field (audit §6.2). Builder
  reads `IModelDoc2.IGetActiveConfiguration` once at build start;
  field is serialized only when non-None (additive, no schema bump).

### Fixed

- **`.checkpoints/` added to `.gitignore`** (privacy_review.md §4.1).
  The L4 checkpoint store contains full *_locals.txt snapshots per
  feature commit; the v0.11 GA requirement to exclude it from
  version control was documented but not implemented in v0.12.

### Test counts

- 689 tests pass excluding `solidworks_only` (was 647 at v0.12);
  +42 new tests across the seven items.
- 2 `solidworks_only` tests pass standalone against a live SW
  session.
- flake8: 0 findings; black: 141 files clean; mypy: 0 errors in
  65 source files.

## [0.12.1] - 2026-05-27

### Added

- **L1 P0-8 edge cases** (`brep/interrogator.py`): the three cases audit
  §1.8 enumerated but v0.12 only partially covered.
  - **Suppressed features** (`IFeature.IsSuppressed()`): interrogator
    skips face walking and returns `{"faces": [], "status": "suppressed"}`
    so resolvers see a well-formed manifest entry instead of stale data
    from before suppression.
  - **Hidden faces** (`IFace2.IsHidden`, fallback to `Visible`):
    `BrepFace.is_hidden` flag added to the dataclass and manifest
    serializer; surfaces in the resolver as a deprioritization signal.
  - **Imported features** (`GetTypeName2() == "ImportFeature"`):
    interrogator skips `IFeature.GetFaces` (which doesn't expose
    topology through the dispatch proxy for imports) and falls back to
    body-level walk via `IFeature.GetBody`. Records `status: "imported"`
    when even the body walk returns no faces.
- New gotcha entries in `docs/known_gotchas.md` for each of the three
  edge cases with how-to-recognize / workaround sections.

### Changed

- `Manifest.add_feature` now propagates the optional `status` key from
  the interrogator output into the brep block, alongside the existing
  `error` propagation.

## [0.12.0] - 2026-05-27

### Added — v0.12 capability lanes GREEN

Four additive lanes behind feature flags (all default OFF). Every v0.11
spec builds byte-identical with all flags disabled. 27 sub-tasks
across E1–E6 merged into `v0.12-integration` and audited (647/647 tests
pass; flake8/black/mypy clean on Py 3.10).

- **L1 — B-rep interrogation** (`brep_interrogation`, E2.1–E2.7):
  per-feature topological fingerprint manifest (`build_brep.json`) with
  face roles, normals, centroids, and body-local indices. Enables
  symbolic `face_role` targeting on downstream features. Marshal spike
  (E2.1) confirmed `IFace2.Normal/GetBox/GetArea` are zero-arg property
  reads under late binding; `IEntity.GetSelectByIDString` is
  unreachable through the dispatch proxy, so face identity uses a
  session-scoped `temp_id` + persistent `fingerprint` instead.
- **L2 — COM error envelope + hint catalog** (E1.1–E1.4):
  `BuildError` structured envelope (spec §3.2), `com_error_boundary`
  decorator wrapping every COM call site in `spec/builder.py`,
  9-entry hint catalog with `(hresult, iface_method, feature_type)`
  resolution, and hint-aware `RetryGuard` that surfaces the remedy to
  the next AI iteration.
- **L3 — RAG API-doc retrieval** (`rag_apidoc`, E5.1–E5.6): vector-
  indexed SolidWorks API docs surfaced via `ai-sw-apidoc` CLI (5
  subcommands: search / detail / members / examples / enum). Ships
  with a committed 262-chunk `api_index.sqlite` (HashEmbedder, 256-dim)
  built from `sldworksapiprogguide.chm`. `search` auto-detects the
  index's embedder dim; install `sentence-transformers` to switch the
  default `--backend auto` to SBERT when re-building against a larger
  corpus.
- **L4 — Checkpoint + rollback** (`checkpoint`, E3.1–E3.5):
  per-feature SQLite snapshot store (`<part>.sqlite`) with WAL mode,
  `ai-sw-history` CLI (list / show / diff subcommands), GC retention
  policy (audit §2.9), and a live-SW rollback regression test that
  validates round-trip on SW 32.1.0.

### Changed

- `ai-sw-build` now writes an optional `build_brep.json` sidecar when
  `brep_interrogation` is ON, alongside the existing
  `build_metrics.json` (additive — never replaces).
- `bundle_bug_report` and `export_metrics` migrated from raw `sys.argv`
  parsing to argparse (E4.1), with `--help` text that matches the
  v0.11 CLI stability conventions.
- `SolidworksMCP-python` upstream pin bumped to `82e505d88da0` (E4.2).

### Added — release docs

- `docs/ROADMAP.md` (E6.1) — six-quarter plan covering v0.12 → v1.0.
- `docs/launch_readiness_checklist.md` (E6.2) — pre-release gate list
  used by the final-audit reviewer.
- `docs/migration_to_v0.12.md` (E6.3) — schema / CLI / sidecar diff
  and additive-only backward-compatibility statement for v0.11
  consumers.

### Migration

Upgrading from v0.11 is additive-only. All new functionality sits
behind default-OFF feature flags. (The detailed v0.12 migration diff was a
pre-1.0 doc, since retired.)

### Dependencies

- New runtime deps: `numpy>=1.24`, `sqlite-vec>=0.1` (RAG L3).
- New optional dev dep: `sentence-transformers>=2.2` (RAG L3 high-
  quality embeddings; HashEmbedder fallback ships with the committed
  index so RAG works without a transformer install).

## [0.11.0] - 2026-05-27

### Added — v0.11 reliability, observability, and supply-chain bundle

Phase 1 of the strategic crossroads plan (B+ → S-tier upgrade). Fifteen
parallel lanes; all merged to master after a six-phase audit (static,
per-task acceptance, live-SW E2E on SW 32.1.0, CI matrix on Windows-2025
× Py 3.10/3.12/3.14, human review, push).

**Reliability**

- **Task 1.1 — Feature-flag module** (`src/ai_sw_bridge/flags.py`). Four-level
  precedence resolver: CLI override → env var (`AI_SW_BRIDGE_FLAG_*`) →
  `.ai-sw-bridge.toml` `[flags]` section → module default. Curated registry
  (no general-purpose config framework). Every v0.11 lane ships behind a
  flag so a subtle bug in one lane can be disabled per-installation.
- **Task 1.2 — Circuit breaker** (`src/ai_sw_bridge/errors/circuit_breaker.py`).
  Three-state machine (closed/open/half-open) with configurable threshold,
  cooldown, and half-open probe. Ported from
  [`SolidworksMCP-python`](https://github.com/andrewbartels1/SolidworksMCP-python)
  `adapters/circuit_breaker.py` at SHA `a10fb74933bb681a5d1569621b33bdcb213faae0`
  (MIT, ESPO Corporation 2025) — sync wrapper extracted from the upstream
  async version.
- **Task 1.12 — Reconnect-on-stale-handle** (`src/ai_sw_bridge/com/connection.py`,
  `ai-sw-build --reconnect`). HRESULT detector for `RPC_S_SERVER_UNAVAILABLE`
  (0x800706BA), `RPC_E_DISCONNECTED` (0x80010108), and
  `CO_E_OBJNOTCONNECTED` (0x800401FD); `with_reconnect()` decorator drops
  the cached SwApp and re-dispatches when the stale-handle predicate fires.
- **Task 1.14 — Fault-injection harness** (`tests/fault_injection/`).
  `FaultInjector` fixture maps `(iface_method, attempt_number) → ComError`,
  with HRESULT catalog mapped to Tier A/B/C per `spec.md §3.2`. CI job
  runs the suite as a separate matrix entry.
- **Task 2.1 — Anti-loop retry guard** (`src/ai_sw_bridge/errors/auto_retry.py`).
  Canonical spec hashing (`spec_hash()` over JSON with `sort_keys`,
  whitespace-normalized); `RetryGuard` raises `IdenticalSpecError` on
  re-submission of a spec hash seen within the window. Prevents the
  AI-assisted "try the same broken spec again" failure mode.

**Observability**

- **Task 1.3 — SLI instrumentation + baseline regression**
  (`tools/regression_check.py --baseline-compare`,
  `tools/perf_baselines/v0.10.json`). Per-build wall time recorded as
  `build_duration_seconds` histogram; p50/p95/p99 computed and compared
  against the previous version's baseline. Regression gate fails CI on
  >15% p95 or >25% p99 deltas. Baseline captured from live SW (15 example
  specs): p50=5.985s, p95=11.933s, p99=12.537s.
- **Task 1.4 — Telemetry module** (`src/ai_sw_bridge/telemetry/`). Local
  SQLite store at `~/.ai-sw-bridge/telemetry.sqlite`; seven mandatory
  counters (`builds_total`, `com_errors_total`, `hint_emissions_total`,
  `auto_retry_outcomes_total`, `checkpoint_writes_total`,
  `feature_flag_state`, `com_disconnects_total`); one mandatory histogram
  (`rag_query_seconds`); trace-id propagation via contextvar. Per
  `spec.md §8.8`: `Counter.inc < 100 µs` budget enforced with warning
  on overrun. No PII, no automatic upload (`privacy_review.md`).

**Supply chain & releases**

- **Task 1.5 — License-compliance lint** (`tools/license_lint.py`,
  `tests/test_license_lint.py`). Three-surface attribution check:
  (1) per-file SPDX docstring tags
  (`Port-Source`/`Port-Commit`/`License-Identifier`); (2) per-file row in
  `CONTRIBUTING.md` "Third-party derivations" 7-column table;
  (3) consolidated per-repo line in README "Acknowledgments". License
  classification (MIT/Apache/BSD/GPL) gated against compatible-license
  matrix; 40-char SHA pinning required.
- **Task 1.6 — Upstream drift monitor** (`tools/check_upstream_drift.py`).
  Reads pinned SHAs from `harvest_plan.md` §5 recipes + `CONTRIBUTING.md`
  derivations table; queries GitHub compare API for commit count since
  pin. Flags repos with >50 commits drift. As of this release:
  `SolidworksMCP-python` is 51 commits ahead of the pinned SHA — first
  trip of the gate; bump pin or vendor scoped delta in the next cycle.
- **Task 1.7 — AGENTS.md drift CI check** (`tools/agents_md_drift.py`
  + CI step). Three structural assertions: schema-type list parity with
  `src/ai_sw_bridge/spec/schema.py`, example-spec list parity with
  `examples/`, and command-table parity with `pyproject.toml`
  `[project.scripts]`.
- **Task 1.13 — Release engineering** (`.github/workflows/ci.yml`,
  `docs/release_engineering.md`). Windows-2025 × Py 3.10/3.12/3.14 matrix
  with separate onboarding job (no SW required), import-check, and
  fault-injection job. Trigger config: `push` to `master` and
  `v*-integration`, `pull_request` to `master`.

**DX & contract**

- **Task 1.8 — Quickstart smoke test** (`tests/onboarding/`,
  `@pytest.mark.onboarding`). No-SW-required quickstart that a fresh
  developer can run in under 30s. CI runs it as a separate job.
- **Task 1.9 — CLI stability tier markers**
  (`src/ai_sw_bridge/cli/stability.py`, `@cli_stability(Tier.STABLE)`).
  Decorator registers each CLI entry point with a stability tier (STABLE/
  BETA/EXPERIMENTAL); registry is queryable via `--stability` flag.
- **Task 1.10 — Bug-report bundler** (`tools/bundle_bug_report.py`). Zips
  last N spec.json files, telemetry export (last 24h), pip freeze,
  best-effort SW version — all run through `telemetry.scrub` (path
  redaction, `S1B_*` locals scrubbing, configurable trade-secret
  patterns). Consent gate: refuses unless `.telemetry/consent.txt`
  exists or `--no-telemetry` is passed.
- **Task 1.11 — Two-stream contract enforcement**
  (`tools/two_stream_lint.py`, `tests/test_two_stream_contract.py`). AST
  scan asserts all CLI entry points emit JSON to stdout and human text
  to stderr only. No mixed streams; no `print()` to stdout outside the
  JSON envelope.

### Changed

- **`pyproject.toml`** — added `[tool.pytest.ini_options]` with
  `pythonpath = ["."]` so `tests/` can import from `tools/` (`tools/` is
  not a package). Added two pytest markers: `onboarding`, `fault_injection`.
- **`pyproject.toml`** — pinned `black==25.12.0` and
  `[tool.black] target-version = ["py310"]` so local + CI matrix entries
  produce identical output. Without the pin, black 25.x auto-targets py315
  on the CI runners and older Python versions cannot re-parse the result.

### Fixed

- **`CONTRIBUTING.md` derivations table** — schema raised from 5 to
  7 columns to match the drift script + tests (target / upstream / license
  / commit / ported / DRI / notes).
- **`tools/check_upstream_drift.py`** — corrected
  `SolidworksMCP-python` repo mapping to `andrewbartels1/...` (was
  pointing at an empty fork); added markdown-link regex
  (`[name](https://github.com/owner/repo)`) so the parser handles all
  three notation forms; skips recipes without a `Commit:` line.
- **CI trigger** (`.github/workflows/ci.yml`) — added `v*-integration`
  to the `push` branch list so integration branches get the same matrix
  as master.
- **CI onboarding job** — install was `pip install -e .` but pytest is
  in `[dev]`; changed to `pip install -e . pytest` so the onboarding
  smoke test can actually run.
- **`telemetry/counters.py` docstring** — listed 8 mandatory counters
  but only 7 are counters; `rag_query_seconds` is a histogram. Rewrote
  the heading and cross-referenced `histograms.py`.

### Known limitations (v0.11)

- **`tools/bundle_bug_report.py` and `tools/export_metrics.py` use raw
  `sys.argv` instead of argparse.** `--help` is silently consumed as a
  positional argument (output filename / no-op flag), so neither tool
  prints usage on `--help`. Both work correctly when called with valid
  args. Will be migrated to argparse next cycle.
- **Upstream drift gate is at 51/50 for `SolidworksMCP-python`** as of
  release. The pinned SHA is still the porting source-of-truth; the
  bump-or-vendor decision goes through the standard derivations PR
  flow next cycle.

## [0.10.0] - 2026-05-22

### Added — v0.10 reliability + DX bundle

- **`--lint` flag** for `ai-sw-build`. Semantic checks beyond validation:
  unconsumed sketches, missing `center.z` on Top Plane centerlines,
  `center.z` thread-through, and face references on parents without clean
  orthogonal faces. Exit code 6 on findings.
- **`--verify-mass` flag** for `ai-sw-build`. Per-feature CreateMassProperty
  volume check against `_expect` blocks. Fail-fast on mismatch.
- **`_expect` schema** for per-feature postcondition expectations
  (`mass_delta_mm3`, `tolerance_mm3`). Validated before `_strip_comments`.
- **`--log-level` flag** for `ai-sw-build` (debug/info/warning/error);
  `--verbose` is the shorthand for `--log-level debug`.
- **`build_metrics.json` sidecar** written next to a `--save-as` part:
  per-feature build timings, total time, mode, binding/mass-check counts.
- **`build_time_s`, `mode`, `feature_metrics`** fields in BuildResult.
- **Structured logging** via Python stdlib `logging` in builder.py.
- **`--dry-run`** now reports a `locals_resolved` count.
- **Type stubs** for 21 COM interfaces in `src/ai_sw_bridge/_sw_stubs/`,
  with a README on why late binding is load-bearing.
- **Pre-commit framework**: `.pre-commit-config.yaml` (black, flake8, mypy,
  spec-lint) plus `mypy.ini` and `.flake8`. Enable with `pre-commit install`.
- **Doc-coverage gate**: `tools/doc_coverage_gate.py`, wired as a CI step;
  checks all 16 schema types are documented in spec_reference.md.
- **Golden volume regression**: `tools/regression_check.py --capture/--check`
  builds each example with `--verify-mass` and records total part volume.
- **SW version floor**: `get_sw_app()` fails fast below SW 2024 SP1
  (`SW_VERSION_VERIFIED` in `sw_com.py`).
- **PM-pane dismiss spike**: `spikes/v0_10/spike_p16_pm_dismiss.py`.
- **New docs**: `docs/sketch_axes.md`, `docs/com_failure_modes.md`,
  `docs/deprecation_policy.md`, `docs/handoff_template.md`,
  `examples/drive_roller/README.md`.
- **spec_reference.md**: added `revolve_boss`, `revolve_cut`,
  `circular_pattern`, `simple_hole` sections; `center.z` and `centerline`
  docs; `_expect` postcondition docs; lint checks section.
- **AGENTS.md**: quickstart, 16-type feature table, late-binding explanation,
  session handoff + memory enforcement rules.

### Fixed — v0.10 live-SW validation

- **`--verify-mass` was dead on arrival**: `CreateMassProperty()` was called
  with parens, but pywin32 late binding auto-invokes the zero-arg COM method
  on attribute access, so `()` called the returned object and raised
  DISP_E_MEMBERNOTFOUND. Drop the parens.
- **Relative `locals` paths**: the builder resolved them against the process
  CWD while the validator used the spec directory, so `minimal_cylinder_v2`
  passed validation then failed the build. Normalized to absolute at the CLI
  entry point.
- **`examples/drive_roller/spec.json`**: 4 of 5 `_expect.mass_delta_mm3`
  values were mis-authored (uncheckable until `--verify-mass` worked).
  Corrected to SW-measured, analytically cross-checked actuals.

### Changed

- The pre-commit hook is now the standard `pre-commit` framework
  (`.pre-commit-config.yaml`); the earlier bespoke `tools/pre_commit_hook.py`
  was removed in favor of it.

### Added — `ai-sw-build --no-dim` (zero-popup build mode)

- **`--no-dim` flag** for `ai-sw-build`. When set, every `{"rhs": "..."}`
  reference in the spec is resolved against `spec['locals']` in Python
  upfront (literal mm value substituted), and the builder skips every
  `AddDimension2` call and the entire `EquationMgr.Add2` binding pass.
  Eliminates the ~16 manual ticks per MMP build that the Modify-Dimension
  popup imposes on SW 2024 SP1.
- New helpers in `src/ai_sw_bridge/spec/builder.py`:
  `_load_locals_map`, `_eval_rhs`, `_resolve_rhs_in_spec`. Handle quoted
  variable refs (`"VAR"`), arithmetic, and recursive locals (one var
  referencing another). Cycles raise; unknown refs raise KeyError.
- `BuildContext` gained a `no_dim: bool` field; every per-feature
  handler in `builder.py` gates its `AddDimension2` block on
  `if not ctx.no_dim`. Geometry creation paths are unchanged.

**Trade-off**: the resulting SLDPRT has NO equation link to `locals.txt`.
Editing `locals.txt` will NOT propagate to existing parts; user must
re-run `ai-sw-build`. The locals file is still the single source of
truth — it's just resolved at build time instead of runtime.

**Validation** (SW 2024 SP1):
- Cylinder `--no-dim`: 1.72s, 0 ticks, Ø25 × 80mm verified
- MMP `--no-dim`: ~3s, 0 ticks, 10/10 features, screenshot-verified
  (50×50 plate, Ø12 coupler, Ø20.5 flange recess, 2× Ø3.2 motor holes,
  2× Ø3.4 frame holes, all positioned correctly)

**Why this exists**: three separate community-canonical workarounds for
the AddDimension2 popup were investigated in this session — all toggle-
based, all failed empirically on this build via pywin32:
- Spike I (prior): toggle 8 (`swInputDimValOnCreate`) — confirmed dead
- Spike M: toggle 78 (`swSketchEnableOnScreenNumericInput`-class) — confirmed dead
- Spike O: probed whether SW auto-creates queryable D1/D2 internal
  params without AddDimension2 — none found, confirming linkability is
  unobtainable without the popup. `EquationMgr.Add2` needs a real named
  dim to target.

The toggle works inside SW's VBA editor (the context all the community
advice assumes); it does not work from external pywin32 COM clients on
SW 2024 SP1. `--no-dim` is the only zero-popup path that doesn't require
a VBA-macro round-trip.

### Added — v0.2 declarative build pipeline (in progress)

- **`ai-sw-build`** — new CLI that takes a JSON spec and drives SOLIDWORKS via
  direct-COM to produce the part. Cylinder example builds end-to-end with
  parametric bindings (Ø25 × 80mm, 2 dims bound to `*_locals.txt`).
- **Spec schema** (`src/ai_sw_bridge/spec/schema.py`) — 7 feature types:
  `sketch_rectangle_on_plane`, `sketch_circle_on_plane`, `sketch_circle_on_face`,
  `sketch_circles_on_face`, `boss_extrude_blind`, `cut_extrude_through_all`,
  `cut_extrude_blind`. Length fields accept literal numbers or
  `{"rhs": "<expression>"}` for parametric binding.
- **Spec validator** (3 layers): jsonschema → strict-topological feature refs
  → locals-file variable references.
- **Direct-COM builder** (`src/ai_sw_bridge/spec/builder.py`) — feature dispatch,
  4-call `EquationMgr` link, plane-and-face sketch creation, `FeatureExtrusion2`
  for bosses, `FeatureCut4` (27-arg form) for cuts.
- **CHM-verified API reference** — `docs/api_reference.md`, `docs/api_reference.json`,
  `src/ai_sw_bridge/sw_types.py` (auto-generated enum constants + runtime
  arg-count assertion). Sourced from decompiled `sldworksapi.chm`. Three
  tools support the workflow: `tools/chm_extract.py`, `tools/gen_api_markdown.py`,
  `tools/gen_sw_types.py`.

### Fixed

- **`FeatureCut4` arg count** — was 24 in builder; CHM says 27. The missing
  args were `AutoSelectComponents` (22), `PropagateFeatureToParts` (23),
  `OptimizeGeometry` (27). Spike E7 verified the 27-arg form produces a
  real "Cut-Extrude1" feature. Earlier "cuts unreachable via pywin32"
  conclusion (commit `cad76c2`) was wrong.
- **`swEndCondThroughAll` enum value** — was 4 in builder; CHM says 1. The
  value 4 is `swEndCondUpToSurface` (deprecated, requires a target). This
  is why through-all cuts returned None even when the call succeeded.
- **Face selection robustness** — face-based sketches in MMP would fail when
  the parent face had material cut away at the center by an earlier feature.
  Now tries center first, then 1/5/15mm offsets in the tangent plane.

### Known limitations (v0.2)

- **`AddDimension2` opens a Modify Dimension popup** that requires manual
  ticking. The `swInputDimValOnCreate` toggle (ID 8) does not suppress it
  on SW 2024 SP1 in our testing. MMP-scale builds need ~16 manual clicks.
  Full investigation in `spikes/phase0/MMP_DEBUG_SESSION.md`.
- **Only +/-z faces supported** for face-based sketches in v1. +/-x and +/-y
  faces of extrusions are not yet wired. Adding them is mechanical (extend
  `_select_extrude_face` and the X-mirror logic).
- **SW emits a "warning beep" each time the builder closes a sketch.**
  Caused by sketches being under-constrained (geometry-relation-wise) at
  close time. We bind values numerically via `EquationMgr.Add2`, which
  fully determines the resulting part, but SW prefers full geometric
  constraint (e.g. coincident-to-origin relations). The beep is transient
  and leaves no error in the tree (`ai-sw-observe feature_errors` returns
  empty after a successful MMP build). Adding `sgFIXED` or coincident
  relations per sketch is a future polish item.

### Fixed (continued)

- **Placeholder dim values vs target geometry**: previously all parametric
  bindings were applied AFTER all features were built. This caused MMP's
  flange recess (parametric Ø20.5mm with placeholder Ø6mm) to fail its cut
  because the placeholder circle sat entirely inside the existing Ø12mm
  through-hole at the time `FeatureCut4` ran. **Fix**: interleave bindings
  -- apply each feature's Add2 and rebuild immediately after the feature is
  built, so downstream geometry sees target sizes.
- **-z face X-axis mirror**: SW mirrors the sketch X axis when viewing a
  -z face from outside. `CreateCircle` uses sketch-local coords but
  `SelectByID("SKETCHSEGMENT",...)` uses part-frame. On -z faces with
  off-origin circles, the SKETCHSEGMENT click missed the circle entirely.
  **Fix**: mirror u in the click coords for -z (-x, -y) faces.
- **Rectangle dim-resize was asymmetric**: `CreateCornerRectangle` makes an
  unconstrained rect; dim binding could anchor it at an arbitrary corner
  rather than the origin, putting all downstream features off-center.
  **Fix**: use `CreateCenterRectangle` which anchors via center diagonals.

### MMP demonstration (the v0.2 milestone)

The Motor Mount Plate from S1b conveyor §13.4 now builds 10/10 features
end-to-end from JSON spec via `ai-sw-build`:
  SK_PlateSlab (center rect, 50×50) → Extrude_Plate (boss blind 5mm) →
  SK_CouplerHole (circle on -z face) → Cut_CouplerHole (through-all) →
  SK_FlangeRecess (circle on +z) → Cut_FlangeRecess (blind 1mm) →
  SK_MotorHoles (2 circles on +z at ±12.5mm) → Cut_MotorHoles (through-all) →
  SK_FrameHoles (2 circles on -z at ±15mm) → Cut_FrameHoles (through-all)

7 parametric bindings to `s1b_conveyor_locals.txt` applied via
`EquationMgr.Add2`. Geometry verified centered via the `ai-sw-observe
screenshot` capture.

## [0.1.0] - 2026-05-13

Initial release. Extracted from a private prototype after validating end-to-end
parametric part creation against a real SOLIDWORKS 2024 install.

### Added

- **Phase 1 — Observation tools** (read-only, run freely):
  - `ai-sw-probe` — COM connectivity sanity check
  - `ai-sw-observe active_doc | feature_errors | equations | screenshot | measure | mate_errors`
- **Phase 2 — Mutation tools** (Propose-Approve-Execute, dry-run + rollback):
  - `ai-sw-mutate propose | dry_run | commit | undo_last_commit`
  - Locals-file I/O with exclusive locking and atomic writes
- **Path C — Macro record + parameterize** (parametric part creation):
  - `ai-sw-codegen parameterize <recorded.swp> <spec.json>` produces a `.bas`
    that, when pasted into SolidWorks VBE and run, creates the recorded part
    with dimensions bound to a `*_locals.txt` source of truth.

### Known limitations

- `RunMacro` / `RunMacro2` cannot consume plain-text `.swp` files — the user
  must paste the generated `.bas` into the SOLIDWORKS VBA editor and press F5.
- Recorded macros embed runtime-generated feature names (e.g. `Sketch2` if
  the doc already had `Sketch1`). Always record from a fresh-doc state.
- The "Modify dimension" popup interrupts replay; user dismisses with Enter.
  A future release will inject `SetUserPreferenceToggle swInputDimValOnCreate`
  to suppress it automatically.
