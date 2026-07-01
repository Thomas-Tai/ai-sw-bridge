# Design: Commercial-grade elevation of `ai-sw-bridge`

**Date:** 2026-07-01
**Baseline:** `feat/w67-phase3` @ HEAD `ee8ada4` (v1.7.0)
**Author:** Thomas-Tai
**Status:** Draft — awaiting user review before writing-plans
**Method:** Four parallel design agents (architecture, testing/CI, docs-IA, packaging) + one baseline/rubric research agent, each grounded in the real tree; synthesized here.

---

## 1. Executive summary

Elevate a proven v1.7 engine to a commercial, Google-standard product that a **non-coder operator can use first**, then a **developer-user**, then a **contributor** — without regressing the hard-won COM / live-seat correctness that took dozens of sessions to earn.

The engine is **concrete, not dirt**: the architecture is *mechanically enforced* (a 22-layer import-linter contract, CI-gated), there is one sealed public facade (`SolidWorksClient`), and the decomposition pattern we need has already been proven on this exact repo (the strangler-fig that emptied `mutate.py` of all its handlers into `features/`). The residual debt is **localized, seamed, and test-protected**: one 3,335-line module that never got cut, two coexisting registration idioms, real doc drift, and a greenfield operator-packaging layer.

The strategy (Approach A) is **incremental elevation, not a rewrite**, sequenced by audience, with a hard rule: **load-bearing concrete is poured and CI-gated in Phase 0 before anything stands on it.** Every improvement lands behind an invariant, so the degraded state becomes *un-mergeable* — the only way to regress is a visible, reviewable diff that deletes a guard.

## 2. Goals & non-goals

### Goals
1. A **non-coder SOLIDWORKS operator** can go from "found this" to "built their first part" with at most one terminal command.
2. A **developer-user** can script/embed against a stable, documented public surface with a SemVer + deprecation promise.
3. A **new contributor** can add a capability (feature kind / spec handler / CLI verb / MCP tool / observe lane) via **one** documented extension model, without reading a 3.3k-line file.
4. The codebase measurably conforms to a **Google engineering standard** across four dimensions: code/architecture rigor, testing/CI maturity, docs-as-a-product, and product packaging/UX.
5. The README becomes a **persona-routed front door**: operator content is the spine (~70% of length); developer and contributor material is signposted and **linked out**.
6. Future capability is **expandable through one contract**, enforced by CI.

### Non-goals
- No engine/COM behavior change. No rewrite.
- No GUI/wizard (AI-chat-first supersedes it for Phase 1; revisit only if chat-first proves insufficient).
- No merge of the two *registry lanes* — they are correctly separate transactions; only their *shape* unifies.
- No full i18n retranslation before the README structure settles.

## 3. Guiding principles

1. **Incremental, not big-bang.** Use the codebase's own proven strangler-fig seam; never rewrite the engine.
2. **Load-bearing concrete first, gated.** Foundational contracts and CI invariants land in Phase 0 so everything built on top stands on a slab.
3. **Degraded state becomes un-mergeable.** Every improvement is locked by a test/gate.
4. **Audience-sequenced value.** Operator-visible value ships early (Phase 1); foundation is poured *under* it (Phase 0), not deferred behind it.

## 4. Current-state assessment

### 4.1 Verdict: concrete with four localized soft patches

**Evidence of concrete:**
- **Enforced architecture.** `pyproject.toml [tool.importlinter]` — a 22-layer strict layering contract, CI-gated via `lint-imports`, with exactly two explicitly-blessed exceptions (`client → mutate`, `client → resilience`), each with written rationale.
- **One sealed public door.** `SolidWorksClient` (`client.py`, ~672 LOC) is the sole supported surface; the free `sw_*` functions were physically deleted at v1.0.0.
- **Proven decomposition precedent.** `features/` is ~30 self-registering modules gated on `SPIKE_STATUS == "GREEN"` via `_register_lane`; the strangler-fig that emptied `mutate.py` of handlers is shipped.

**The four soft patches (localized, seamed, test-protected):**

| Patch | Evidence | Why it's a patch, not rot |
|---|---|---|
| `builder.py` = 3,335 LOC | largest hand-written module; holds ~30 inline `_build_*` handlers + `_wire_handlers` + the `build()` loop | Handlers are already discrete functions behind a dispatch seam; the sketch handlers were *already* extracted to `spec/sketches/` |
| Two registration idioms | `features/` self-register vs `builder.py` flat `_wire_handlers` (no status gate, no per-module boundary) | Cognitive tax for contributors; not a correctness issue |
| Doc drift | see §4.3 | Symptom of a missing doc-truth CI invariant (partially present) |
| Operator packaging | no installer/pipx/PyInstaller artifact exists | **Greenfield**, poured fresh on solid ground — not decayed |

### 4.2 Baseline scorecard (measured this effort)

| Dimension | Metric | Current |
|---|---|---|
| Code/arch | Largest hand-written modules (LOC) | `spec/builder.py` 3,335 · `sw_types.py` 2,896 (generated) · `drawing/lifecycle.py` 2,390 · `observe.py` 2,202 · `mutate.py` 2,181 · `spec/descriptors.py` 1,513 · `assembly/handlers.py` 1,191 · `export/dispatch.py` 1,006 — **10 modules total exceed 800 LOC** |
| Code/arch | Registration idioms | 2 (`features/` self-register + `builder.py` flat) |
| Typing | mypy strictness | `mypy.ini`: `files=src`, `no_implicit_optional`, `warn_unused_ignores`; **`disallow_untyped_defs` NOT set** — untyped defs pass. COM surface intentionally `Any`. |
| Testing | Tests collected | **3,941** |
| Testing | Live/destructive tests run in CI | **0 of ~110** (`solidworks_only` ∪ `destructive_sw`) |
| Testing | Coverage gate | fixed `--cov-fail-under=60` (measured 64% at v1.5.0); no ratchet, no per-package floor |
| CI | Gates (main job) | black → flake8 → mypy → `doc_coverage_gate.py` → `two_stream_lint.py` → `lint-imports` → `pytest --cov`; matrix `windows-2025` × py 3.10/3.12/3.14; + ubuntu import-check job + onboarding clean-install job |
| CI | Workflows | `ci`, `license_lint`, `security` (gitleaks + pip-audit), `upstream_drift`, `release` |
| Docs | Doc-truth locks present | `test_readme_counts.py` (3 of 4 README numbers), `doc_coverage_gate.py`, `test_exit_codes_documented.py`, `EXPECTED_TOOLS` (37 MCP tools) |
| Docs | Known drift surfaces | ONBOARDING, CONTRIBUTING, version banners, `architecture.md`, `USAGE.md`, i18n — see §4.3 |
| Packaging | Operator install | clone + venv + `pip install -e .` (developer workflow); no packaged path |

> Appendix A will be enriched with the research agent's grounded rubric + a per-item re-verification of the 2026-06-30 audit at HEAD.

### 4.3 Doc drift catalog (re-grep at execution — some already fixed)

| # | Claim | Actual | Location |
|---|---|---|---|
| D1 | ONBOARDING "All 15 CLI commands" (table lists 17 rows; 5 commands missing entirely) | 21 | `docs/ONBOARDING.md:142` |
| D2 | ONBOARDING "26 read-only + build tools" | 37 | `docs/ONBOARDING.md:128` |
| D3 | CONTRIBUTING "early-stage (v0.2)" | v1.7.0 | `CONTRIBUTING.md:3` |
| D4 | CONTRIBUTING "integration tests… manual for now" | `e2e_sw/` + markers wired | `CONTRIBUTING.md:53` |
| D5 | CONTRIBUTING feature recipe omits `features/` registry | 36-kind registry undocumented there | `CONTRIBUTING.md:80-89` |
| D6 | Version banners cite v1.6.0/v1.6.1 | 1.7.0 | README, `CAPABILITIES.md`, `PUBLIC_API.md`, `CLASS_RELATION_MAP.md` |
| D7 | i18n READMEs assert MIT + frozen `translated-from: c8ce816` | Proprietary | `docs/i18n/{zh-TW,zh-CN}/README.md` |
| D8 | `architecture.md` describes pre-facade shape | superseded 1:1 by `CLASS_RELATION_MAP.md` | `docs/architecture.md` |
| D9 | `USAGE.md` "package stays out of MCP transport" | ships `ai-sw-mcp` (37 tools) | `USAGE.md:136` |
| D10 | README/AGENTS link `docs/api_reference.md` | gitignored — dead link on GitHub | `.gitignore` |

**Process rule:** the `docs/E2E_FRESH_USER_AUDIT_2026-06-30.md` is a *punch list to re-grep at execution*, not act on verbatim. Most items are already fixed at HEAD; the re-verified status is in **Appendix A.2** (still OPEN: #8, #14, S1, S2, S3 — the rest FIXED). **Trap:** the `(#14)`/`(#15)` tags in recent commit subjects are informal follow-up-task numbers for semantic-edge work, *not* audit findings #14/#15 — see Appendix A.4.

## 5. Approach & recorded decisions

**Approach A — incremental elevation, audience-sequenced, load-bearing-first.**

Decisions ratified with the user (2026-07-01):
- **D-ORDER:** Phase 0 strictly first — complete foundation gates before Phase 1 operator work binds to any contract. ("Pour the concrete before we build the house.")
- **D-DECOMP:** Full `builder.py` decomposition — all six `_build_*` families move to `spec/handlers/`, leaving `builder.py` as pure orchestration (~800 LOC target).
- **D-SPEC:** One e2e spec covering all five phases (Phase 0–1 detailed, 2–4 lighter); writing-plans then produces per-phase implementation plans.

## 6. The Extension Contract (the crown jewel)

One documented recipe per capability type. Each has a canonical directory, one gated self-registration call, one uniform signature, and one CI conformance test. The *registry object* stays lane-local (each gates a different transaction); the *shape* unifies.

| Add a… | Directory | Register via | Uniform signature | CI gate |
|---|---|---|---|---|
| **feature_add kind** | `features/<kind>.py` | `_register_lane(kind, handler, SPIKE_STATUS)` | `create_<kind>(doc, feature, target) -> (bool, str\|None)` | registry-disjoint + fail-loud |
| **spec type/handler** | **`spec/handlers/<family>.py`** (new) | `register_spec_handler(name, handler, status)` mirroring `_register_lane`; `_wire_handlers` calls it | `_build_<kind>(ctx, feat) -> BuiltFeature` | `doc_coverage_gate` + "no inline handler in builder.py" import contract |
| **CLI verb** | `cli/<verb>.py` | `@cli_stability(tier)` + `[project.scripts]` | `def main() -> int` (two-stream) | `two_stream_lint` + `TIER_REGISTRY` test |
| **MCP tool** | `mcp/_tool_<name>.py` | `@mcp.tool()` + `@com_tool` | tool fn (COM phase via `run_on_executor`) | `test_all_com_tools_have_decorator` + `EXPECTED_TOOLS` |
| **observe lane** | `observe_<x>.py` + facade method | facade property; optional MCP `_tool_observe` | `_sw_get_<x>_impl(doc) -> dict` | facade/equivalence tests |

The canonical "one way to add each thing" becomes a single five-row recipe table in the rewritten `CONTRIBUTING.md`.

## 7. Phase 0 — Foundation (the concrete pour)

**Objective:** freeze the load-bearing contracts and install the CI invariants that make every later phase un-regressible. **Nothing in Phase 1 starts until Phase 0 exits.**

### 7.1 Architecture spine
- Write the **Extension Contract** (§6) as a doc + a **weak-form conformance test** (registry-membership ↔ doc-membership for all three extensible surfaces).
- Add `tools/module_size_gate.py`: **800-LOC ceiling** for new `src/` modules; a **shrink-only ratchet waiver** for today's offenders (the **10 modules currently over 800 LOC** are baselined at current LOC and can only decrease); `sw_types.py` permanent waiver (generated). **Warn mode** in Phase 0.
- Extend import-linter with a `spec.handlers` sub-layer beneath `spec`, plus a "no inline builder handler" contract (added when handlers begin moving in Phase 3; the layer is declared now). Leave the two blessed exceptions untouched.
- Enable mypy strictness (`disallow_incomplete_defs`/`disallow_untyped_defs`) **module-by-module on the pure-Python spine only** (`features/`, `spec/handlers/`, `cli/`, `mcp/tools.py`) via `[mypy-…]` overrides; COM surface stays `Any`.
- **Imports:** enforce absolute imports on **new** modules (flake8 tidy-imports); do *not* blanket-convert the 152 existing relative-import files — low value, high churn, merge-conflict risk (see Appendix A.1). A Google-standard-but-context-aware judgment call.

### 7.2 Testing spine
- Replace the fixed `--cov-fail-under=60` with a **coverage ratchet** against a checked-in `coverage_baseline.json` (never-decrease, with a ~1pt tolerance band for the 3-interpreter matrix); a legitimate rise bumps the baseline via a reviewed PR.
- Add **per-package coverage floors** on `spec/`, `features/`, `errors/` at their *current measured* levels (not aspirational).
- Consolidate doc-truth into **one `tests/test_doc_truth.py`** (a `DOC_SURFACES × DERIVED_FACTS` table) that absorbs `test_readme_counts.py` and covers README + ONBOARDING + CAPABILITIES + tools_reference + CONTRIBUTING. Fixes D1–D3, D6 permanently. For ONBOARDING specifically, assert both the CLI **count** *and* **table completeness** (every command present) — catching the missing-5-rows drift in Appendix A.3.
- **De-duplicate** the two independently-hardcoded MCP tool lists: `test_e2e_mcp_lifecycle.py` imports `EXPECTED_TOOLS` from `test_server_contract.py`.
- **Resolve the 110-un-CI'd-tests gap honestly:** add a hermetic **proxy** test (the `EXPECTED_TOOLS` cross-check) that runs in the main job, and reconcile `_internal/docs/human_gates_runbook.md` Gate 3 so the doc and CI reality agree. (A real live job needs a self-hosted Windows+SW runner — named as a residual risk, not silently worked around.)
- Add an **i18n staleness-banner structural check** (banner present ⇔ `translated-from` SHA not current), needing a minimal `fetch-depth` on the checkout.
- Add a **marker split** so `destructive_sw` stops conflating "kills the process" with "risky in bulk" (`mcp_lane_live` for the MCP write-gate lane).

### 7.3 Load-bearing contract freeze (what packaging binds to)
- Freeze and document in `docs/PUBLIC_API.md`, each with a contract test:
  - the **console-script names** (`[project.scripts]`),
  - the **CLI exit-code contract** (2/3/4/5/6/7; never 1),
  - the **MCP tool-name set** (`EXPECTED_TOOLS`).

### 7.4 Cheap doc hygiene that unblocks Phase-1 links
- Fix the **4-line i18n Proprietary-license misstatement** (legal exposure; independent of the full translation refresh) — D7.
- **Retire `architecture.md`** (merge surviving rationale into `decisions.md`; promote `CLASS_RELATION_MAP.md` as canonical) — D8.
- Establish a **freshness-ownership rule** in the `CONTRIBUTING.md` PR checklist.

### 7.5 Phase-0 Definition of Done
- `module_size_gate.py` live (warn); baseline JSON covers every `src/**/*.py`.
- Extension Contract doc + weak conformance test green.
- import-linter `spec.handlers` layer declared; blessed exceptions intact.
- mypy strict on the spine; COM `Any` by design.
- Coverage ratchet + per-package floors live.
- `test_doc_truth.py` green; D1–D3, D6 fixed and covered.
- Duplicate `EXPECTED_TOOLS` removed; 110-test gap reconciled in runbook + proxy test.
- Script-name / exit-code / MCP-tool contracts documented in `PUBLIC_API.md` + contract-tested.
- i18n license fixed; `architecture.md` retired; freshness rule in CONTRIBUTING.

## 8. Phase 1 — Operator product + README front door

**Objective:** a non-coder operator gets to their first part with ≤1 terminal command, from inside a chat window they already use.

### 8.1 Distribution
- **Primary:** `pipx install ai-sw-bridge[mcp]` — rides the existing console scripts with zero engine change; isolates deps; scripts land on PATH. The **pywin32 post-install must be scripted** (`python -m pywin32_postinstall -install` inside the pipx venv) — the top footgun.
- Operator install one-pager: install Python 3.x (64-bit, "Add to PATH") → `pip install --user pipx` → `pipx install ai-sw-bridge[mcp]`.
- Deferred to Phase 4: a signed Inno Setup installer bundling a private Python for the true no-Python operator.

### 8.2 The one new command: `ai-sw-doctor`
A tiny leaf command (wraps `probe()`) — the *entire* required terminal vocabulary for a chat-first operator. Checks: Python bitness, `pywin32` imports, SW seat answers, Claude Desktop MCP entry registered — then prints operator-legible next steps. COM/engine-inert.

### 8.3 Day-one flow: AI-chat-first
The productive surface already exists (37-tool MCP server + in-chat elicitation write-gate). "Install" collapses to **register the MCP server + drop `docs/AGENTS.md` into the chat.** Operator authors a sentence; plan-review + Approve is native MCP elicitation; packaged default is `--no-dim` so no blocking popup ever appears. A bespoke GUI is explicitly deferred.

### 8.4 Error & safety UX (operator-legible)
- **command-not-found / venv:** chat-first operators never hit it; `ai-sw-doctor` detects "scripts not on PATH" → "run `pipx ensurepath`, reopen terminal."
- **probe fails:** two-branch verdict — "(a) is SOLIDWORKS open? open it and retry; (b) if it's open, your Python is 32-bit but SW is 64-bit — reinstall 64-bit."
- **build "hangs" on AddDimension2:** invisible to operators — chat-first + packaged default is `--no-dim`.
- **seat `[y/N]` gate reframed as reassurance:** "*I'm about to build in the SOLIDWORKS window showing **‹active doc›** (PID ‹n›). This adds a new part; it will not overwrite your open work. Approve? [Approve] / [Cancel]*" Preserve the no-autonomous-write invariant.

### 8.5 README information architecture
New skeleton (operator ~70% of length; dev/contributor = teasers that link out):
- `# ai-sw-bridge` + badges + language links + one-line pitch
- **Who are you? → start here** (Operator / Developer-integrator / Contributor router)
- What this is · **What a spec looks like** (inline `spec.json`)
- **For operators — 5-minute quickstart** (prerequisites incl. Git; install; smoke test with probe output + seat-gate forewarning; hand keys to AI; first-run troubleshooting table)
- What ships in the box (short command table) · Feature kinds (short) · Limitations (inline — operator-critical)
- **For developers & integrators** (~10-15 lines, teaser + links to `PUBLIC_API.md`, `tools_reference.md`, `AGENTS.md`, `USAGE.md`; MCP walkthrough **moves out** to `mcp_server_design.md` with a stub)
- **For contributors** (~8-10 lines → `CONTRIBUTING.md`, `CODESTYLE.md`, `CLASS_RELATION_MAP.md`)
- Project status (version fixed) · Layout · License · Acknowledgments

Merge `ONBOARDING.md` into a canonical **Operator Guide** (= fixed ONBOARDING + `known_limitations.md` + `CAPABILITIES.md`), framed for a non-coding SW veteran, with `AGENTS.md` cross-linked ("if you pair with an AI assistant, hand it this file").

### 8.6 Guardrail
Extend the existing `onboarding` CI job with a **packaged-install smoke stage** (no SW): build the wheel, install the *artifact* (not `-e`), assert `where ai-sw-probe/ai-sw-mcp/ai-sw-doctor`, assert `ai-sw-build --list-kinds` works with no SW, assert probe/doctor fail *gracefully* (documented message, exit 1, no traceback), assert `import ai_sw_bridge.mcp.server` succeeds.

### 8.7 Phase-1 DoD
One documented non-coder install path (pipx) with scripted pywin32 post-install; `ai-sw-doctor` on PATH giving pass/fail verdicts; chat-first flow works end-to-end defaulting to `--no-dim`; seat banner/elicitation reads reassuringly; three first-run failures produce plain-English guidance; README persona-router live with operator content >2/3; ONBOARDING merged with fixed counts; operator-install smoke green on `windows-2025`.

## 9. Phase 2 — Developer-user surface

**Objective:** a developer can script/embed against a stable contract.
- Document the public trio (`SolidWorksClient` facade + CLI + MCP) as *the* supported surface in `PUBLIC_API.md`, with an explicit **versioning/deprecation policy** (SemVer already in force; make the promise legible).
- Relocate the ~90-line MCP walkthrough out of README into `mcp_server_design.md` with an inline stub.
- Consolidate `USAGE.md` + `tools_reference.md` + `PUBLIC_API.md` framing as the dev-user guide; fix D9 (USAGE MCP claim); fix D10 (say "regenerate `api_reference.md` locally," not a dead link).
- **DoD:** dev-user guide is coherent and cross-linked; MCP walkthrough relocated with stub; D9/D10 fixed; deprecation policy written.

## 10. Phase 3 — Contributor & architecture rigor

**Objective:** a new engineer extends safely; `builder.py` becomes pure orchestration.

### 10.1 `builder.py` decomposition (full, all six families)
Move `_build_*` families to `spec/handlers/*.py` via the existing `_wire_handlers` seam (a pure relocation — the dispatch key and `HANDLERS[name]` resolution are unchanged), in **ascending risk order**, each independently shippable:
1. `sketch_primitives.py` — the 8 `NotImplementedError` stubs (no live COM) — **first**.
2. `pattern.py` — linear/circular/mirror.
3. `revolve.py` — revolve boss/cut + `_call_feature_revolve`.
4. `hole.py` — simple_hole + face-select helpers.
5. `dress_up.py` — fillet/chamfer + the self-contained edge-selection block.
6. `extrude.py` — boss/cut families + `_call_feature_extrusion/_cut`, the `@versioned` `_cut4_args_2024/2025` — **last** (most shared helpers).

**Stays in `builder.py`:** the `build()` loop, `_build_one_feature`, `_apply_bindings`, `_apply_deferred_dims`, RHS/locals resolution, doc setup, checkpoint/brep/mass-verify wiring, and the `DESCRIPTORS` + `_wire_handlers` assembler. Target ~800 LOC.

### 10.2 Decomposition discipline (the concrete-not-dirt guarantee)
- **Measure-first monkeypatch-seam audit** per family: tests patch COM seams on the *module namespace*; a naive move breaks them. Audit each family's patched seams, then re-point patches or re-export moved symbols back into `builder`'s namespace (the `client.py` `_impl` re-export precedent).
- **Byte-identical moves;** carry each module constant with its handler (missing imports pass offline — mocks patch the seam — and fail only at the live seat).
- **Spot live-seat re-proof** on ≥1 relocated GREEN family (run `seat-prefire-review` first); WALL-NO-AMNESTY (never promote a walled/dormant kind while moving it).
- **`@versioned` import-order:** the new module must be imported so the version-resolver registry populates before first dispatch.

### 10.3 Other Phase-3 work
- Promote the module-size gate warn→**block** once the five offenders are under budget or re-baselined.
- **Strengthen the conformance test** to the architecture-defined contract (it grows in place; it isn't replaced).
- Expand mypy strictness across the newly-extracted handler modules.
- Rewrite `CONTRIBUTING.md`: fix D3/D4, add the missing `features/` registry recipe (D5), publish the five-row Extension Contract; promote `CLASS_RELATION_MAP.md` as canonical architecture doc.

### 10.4 Phase-3 DoD
All six families relocated under the unified self-registration shape; `builder.py` holds only orchestration; `HANDLERS` dispatch unchanged; module-size gate blocking; strong conformance test green; CONTRIBUTING rewritten; full offline suite green + a spot live-seat re-fire on ≥1 relocated GREEN family; no behavior change; no walled-kind promotion.

## 11. Phase 4 — Expandability

**Objective:** future capability slots into one contract.
- Fully document + generalize the unified extension model; the `SPIKE_STATUS`/status-gate pattern generalizes to spec handlers.
- **Signed Inno Setup installer** bundling a private Python + auto-registering the MCP server (the true no-Python operator). Needs a **code-signing certificate** — a procurement line-item flagged early.
- Scoped **i18n retranslation** against the new persona-routed README; bump `translated-from`.
- **Perf-regression gate** (`tools/regression_check.py`) *if/when* a Windows+SW runner exists.
- **DoD:** extension model documented + generalized; signed installer ships; i18n refreshed; perf gate wired if infra allows.

## 12. Cross-track reconciliations

- **Extension contract ↔ conformance test:** weak-form (membership) in Phase 0; strengthens in place in Phase 3 after the contract formally lands. The test grows; it is not replaced. Prevents the testing track from inventing a contract unilaterally.
- **Doc-counts ownership:** **one** `test_doc_truth.py`, not competing tests. Testing track owns the mechanism; docs track extends the `DOC_SURFACES` table.
- **Packaging ↔ Phase-0 contracts:** installer + `ai-sw-doctor` bind to the frozen script-names/exit-codes/MCP-tool-set — which is *why* those are Phase-0 load-bearing, not Phase-2.
- **Audit hygiene:** re-grep the 2026-06-30 audit at execution; do not act verbatim.

## 13. CI invariant inventory

| Gate | Checks | Blocks/Warns | Phase |
|---|---|---|---|
| `module_size_gate.py` | new module ≤800 LOC; offenders shrink-only | Warn → Block | 0 → 3 |
| Weak conformance test | registry ↔ doc membership (3 surfaces) | Block | 0 |
| Strong conformance test | architecture-defined contract | Block | 3 |
| import-linter `spec.handlers` + "no inline builder handler" | layer acyclicity | Block | 0 (layer) / 3 (contract) |
| mypy strict (spine) | typed defs on `features/`, `spec/handlers/`, `cli/`, `mcp/tools.py` | Block | 0 → 3 |
| Coverage ratchet + per-package floors | never-decrease; `spec`/`features`/`errors` floors | Block | 0 |
| `test_doc_truth.py` | counts/version across 5 docs derive from code | Block | 0 |
| `EXPECTED_TOOLS` single-source + proxy | MCP tool set; kills 110-gap silent drift | Block | 0 |
| i18n staleness-banner check | banner ⇔ stale SHA | Block | 0 |
| Operator-install smoke | packaged wheel install, scripts on PATH, graceful no-SW failure | Block | 1 |

## 14. Risks & mitigations

1. **No self-hosted Windows+SW runner** → 110 live/destructive tests can't run in true CI. *Mitigation:* hermetic proxy tests + an honest manual-gate doc; don't claim CI covers what it doesn't.
2. **Monkeypatch-seam drift** during decomposition (the concrete-not-dirt risk itself). *Mitigation:* measure-first + byte-identical moves + live-seat re-proof + WALL-NO-AMNESTY.
3. **Code-signing cost** for the Phase-4 installer (SmartScreen). *Mitigation:* Phase-1 `pipx` sidesteps it; procure the cert before Phase 4.
4. **Coverage ratchet flakiness** across 3.10/3.12/3.14. *Mitigation:* ~1pt tolerance band.
5. **Module-size false positives** on cohesive files. *Mitigation:* ratchet against *growth*, not an absolute ceiling on pre-existing files.
6. **pywin32 in isolated environments** — post-install DLL step must be scripted or COM dispatch fails opaquely. *Mitigation:* script it in the pipx one-pager + `ai-sw-doctor` detection.

## 15. Out of scope
GUI/wizard; full i18n retranslation before the README settles; merging the two registry lanes; any engine/COM behavior change; a committed/CI-published `api_reference.md` (flag to a separate tooling track).

## 16. Overall Definition of Done
- Phases 0–4 DoDs met.
- A non-coder installs via one path and builds a part chat-first.
- Public surface documented with a SemVer/deprecation promise.
- `builder.py` is pure orchestration; one Extension Contract governs all five capability types, CI-enforced.
- README is a persona router with operator content as the spine.
- Every improvement is locked by an invariant; the degraded state is un-mergeable.

## Appendix A — Grounded Google-standard rubric & audit re-verification

*Grounded by a research pass against the published Google standards ([Python Style Guide](https://google.github.io/styleguide/pyguide.html), [eng-practices review standard](https://google.github.io/eng-practices/review/reviewer/standard.html) + [small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html), [Test Sizes](https://testing.googleblog.com/2010/12/test-sizes.html)) and a re-verification of the 2026-06-30 audit at HEAD `ee8ada4`.*

### A.1 Rubric (highest-leverage rows)

| Google standard | Rule | Repo state | Rubric line | Verdict |
|---|---|---|---|---|
| Pyguide §2.21/3.19 | type hints on public APIs, enforced | mypy never sets `disallow_untyped_defs`; ~78% of `def`s annotated (est.) | `disallow_untyped_defs=True` on the spine, COM exempt | **Adopt** (P0 spine → P3 handlers) |
| Test Sizes | small/medium/large by resource contract | no size markers; only SW-dependency markers | size taxonomy + time budgets | **Adopt** (P0) |
| Test Sizes / CI | every tier runs in CI on a matched cadence | **~110 live/destructive tests run in NO CI job** | proxy test now + honest manual gate; real job needs a seat runner | **Adopt** (P0) + named risk |
| Pyguide §3.8.3 | docstrings with Args/Returns/Raises | ~23% of files sectioned; `client.py` public methods aren't | `flake8-docstrings` D417 scoped to `client.py`+`features/` | **Adopt, scoped** (P3) |
| Pyguide §3.2 | 80-col | repo uses black 88, documented+consistent | keep 88; record the deviation in a style doc | **Keep deviation** (document) |
| Pyguide §2.2.4 | absolute imports, no `from .` | 152/215 files use relative imports | absolute-only for **new** modules | **Judgment call:** do NOT blanket-convert 152 files (low value, high churn); enforce on new modules only |
| eng-practices small-CLs | ≤~200-line self-contained CLs | commits range 9–1559 lines, mixing doc+code+test | non-blocking diff-size report | **Advisory** (not blocking) |
| Pyguide §3.16/§3.8.1/comments | naming, module docstrings, narrative comments | **conforms (strong)** | no action | **Already meets** |

### A.2 Audit re-verification at HEAD (18 commits past the audit baseline)

**FIXED (14):** #1 (i18n license), #2 (±x/±y faces — *and extended* to Top/Right parents post-release), #3 (exit codes), #4 (audited counts), #5 (fillet string), #6 (Git prereq), #7 (extras syntax), #9 (semantic edges — shipped default-on, released in v1.7.0), #10 (`--list-kinds`), #11 (multi-seat PID), #12 (schema_version hint), #15 (inline spec.json), #16 (seat-gate forewarning), #17 (probe output), #18 (troubleshooting table).

**OPEN (by design or scheduled):** #8 (hole u/v `{rhs}` — a parametric-fidelity epic), #13 (AddDimension2 — inherent, no action), #14 (human-CAD onboarding framing — **our Phase 1 addresses this directly**), **S1** (`builder.py`, now **3,335** LOC — our Phase 3), **S2** (two registry idioms — our §6 Extension Contract), **S3** (2k-line watch-list — monitor).

### A.3 New drift the research pass surfaced (fold into D1)
`docs/ONBOARDING.md:142` heading "**All 15 CLI commands**" is stale on two counts: the table beneath lists **17** rows, and `[project.scripts]` defines **21** `ai-sw-*` commands — **5 are missing from the table entirely** (`ai-sw-batch`, `ai-sw-sketch-edit`, `ai-sw-memory`, `ai-sw-solver`, `ai-sw-urdf`). This survived the June-30 truing because that pass fixed a *different* "15" (the specs-count, audit #4). The Phase-0 `test_doc_truth.py` must assert both the count **and** table completeness.

### A.4 Trap for the implementer (do not misread git history)
The `(#14)`/`(#15)` tags on commits `7d6fe8e`/`ee8ada4` are **informal follow-up-task numbers for the semantic-edge generalization** (successor to audit #9) — they are **NOT** audit findings #14/#15. Audit #15 (inline spec.json) was closed by `e8fc163`; audit #14 (onboarding framing) remains open. A skim of git log alone would misattribute this and wrongly close #14. Confirmed via commit bodies ("Task #14 follow-up") + `gh issue list` (only 4 issues ever filed).

## Appendix B — Source chapters
This design synthesizes four grounded design chapters (architecture foundation, testing/CI maturity, docs-IA + README, operator packaging/UX), produced by parallel agents against `feat/w67-phase3` @ `ee8ada4`, plus a baseline/rubric research pass. The chapters' `path:line` evidence backs every claim above.
