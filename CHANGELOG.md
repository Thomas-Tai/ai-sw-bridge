# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

### Known limitations (deferred to v0.14)

- **`executor.is_sw_dead` does not auto-flip on dead-handle errors.**
  W5.6 catalogued death HRESULTs (`0x800401FD`/`0x80010108`), but
  pywin32 surfaces SW death as `AttributeError`, not the cataloged
  COM errors. `observe.*` catches the `AttributeError` into a string
  `error` field, so it never reaches the executor's exception
  handler. Manual `sw_reconnect` still works (user reads the error,
  invokes the tool); only the auto-detection promised by W5.6
  doesn't fire today.
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

Pre-merge full audit caught and fixed three ship blockers:
- MCP wire protocol (sync `list_tools` override broke JSON-RPC)
- `sw_checkpoint_info` schema mismatch
- `ServerRuntime.reconnect` cache leak

Plus phase-2 live-SW verification:
- 18 observation/build/apidoc/history tools exercised against a real
  SW session — all return well-formed payloads
- Death-recovery flow validated end-to-end (kill SW → call →
  reconnect → call → recover)
- Encryption composition (sw_build --checkpoint-encrypt → MCP
  sw_checkpoint_info + sw_history_part) verified; no plaintext leak

Full Wave 5 audit details in commit messages of `4a5f849`, `d91676e`,
`5069866`, and `f9dde03`.

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
behind default-OFF feature flags. See
[`docs/migration_to_v0.12.md`](docs/migration_to_v0.12.md) for the full
schema / CLI / sidecar diff.

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
