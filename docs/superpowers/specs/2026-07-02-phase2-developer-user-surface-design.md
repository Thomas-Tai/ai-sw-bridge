# Phase 2 — Developer-User Surface — Design Spec

**Status:** DRAFT (awaiting user review gate)
**Date:** 2026-07-02
**Branch:** `docs/commercial-elevation`
**Governs:** Phase 2 of `docs/superpowers/specs/2026-07-01-commercial-google-standard-elevation-design.md` (§9, lines 188 / 205 / 206)
**Predecessors:** Phase 0 (guardrails, `ee8ada4..bd6ed85`) and Phase 1 (operator product, `bd6ed85..2b3e297`) SHIPPED to master.

---

## 1. Intent

Turn the *developer/integrator* half of `ai-sw-bridge` into a documented, versioned, **enforced** supported surface — matching the polish Phase 1 gave the operator half. The public trio is:

| Leg | What it is | Enforced today |
|---|---|---|
| **CLI** (22 console scripts) | stable/experimental tiers | ✅ `tests/test_cli_stability.py` |
| **MCP server** (37 tools) | names + payload shapes | ✅ `EXPECTED_TOOLS` in `tests/mcp_lane/test_server_contract.py` |
| **`SolidWorksClient` facade** | sole supported Python entry point | ❌ **prose promise only** — no drift guard |

Phase 2 documents the trio coherently, writes an explicit deprecation policy, fixes two doc-drift defects (D9, D10), relocates the ~90-line MCP walkthrough out of README, and — per the "concrete not dirt" directive — closes the one unguarded leg (facade) and builds the deprecation-enforcement spine.

---

## 2. Locked decisions (from the Phase 2 brainstorm)

These were adjudicated by the user this session and are **not reopened** without new technical evidence.

### 2.1 Deprecation policy (grace numbers)

| Surface class | Deprecate in | Hard removal allowed | Floor |
|---|---|---|---|
| **Stable CLI / MCP Tool / Facade signature** | `1.N` | **only at `2.0`** | ≥ 2 minor releases between announce and the `2.0` cut (deprecate in `1.99` → must ship `1.100` **and** `1.101` before `2.0`) |
| **Experimental CLI / Spec handler** | `1.N` | `1.N+1` | 1 minor release |

Rationale (user): gating stable-API removals strictly on the major boundary is the only way to earn enterprise-integrator trust.

### 2.2 MCP deprecation warning — Option C (Both)

When an MCP tool is eventually deprecated, the warning is surfaced **twice**:

- **Human surface** — prefix the tool *description* with `[DEPRECATED in 1.N → use X]` (seen during tool discovery in the client).
- **Machine surface** — inject a `_deprecation: {replaces: "X", remove_in: "2.0"}` block into the tool's JSON response envelope (parsable by headless scripts).

**Plumbing status: DOCUMENTED, DEFERRED.** Zero MCP tools are deprecated at v1.7.0, so this runtime code would attach to nothing and cannot be integration-tested against a real deprecated tool. It is written into `PUBLIC_API.md` as binding policy; no serialization/description-prefix code is written until the first MCP tool is actually marked for deprecation. (User: "Code that isn't exercised by real, necessary usage immediately begins to rust… we build load-bearing walls, not stage props.")

### 2.3 Documentation architecture — Option A (Unify framing, keep separate)

`USAGE.md`, `docs/tools_reference.md`, `docs/PUBLIC_API.md` are **three distinct Diátaxis modes** (How-to / Reference / Contract) and stay physically separate. "Consolidate" = a cohesive, cross-linked experience, not a file merge. Delivered via a **shared navigation block** at the top of each of the three files stating its role and bidirectionally linking the other two.

### 2.4 Enforcement scope — build the concrete, document the speculative

- **BUILD NOW:** facade public-surface pin test + `DEPRECATIONS` registry & CI gate (both testable today against real code).
- **DOCUMENT & DEFER:** MCP dual-warning plumbing (see §2.2).

---

## 3. Design

### 3.1 Pillar A — Shared navigation block (Option A)

Inject a standardized blockquote header at the top of each of the three dev-surface docs. Proposed template (adapt link text per file):

```markdown
> **Developer surface — [How-to guide]**  ·  Part of the ai-sw-bridge developer documentation.
> This is the **how-to** layer (task-oriented recipes). For the exhaustive CLI/MCP
> **reference** see [`docs/tools_reference.md`](docs/tools_reference.md); for the supported-surface
> **contract** (stability tiers, SemVer, deprecation policy) see [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md).
```

Each file's block names its own role (How-to / Reference / Contract) and links the other two. Relative link paths differ (`USAGE.md` is at repo root; the other two are under `docs/`) — the plan must compute paths per file.

**Doc-truth constraint:** the block adds text; it must not alter any substring the doc-truth gate pins (`tests/test_doc_truth.py::DOC_SURFACES`).

### 3.2 Pillar B — Drift fixes

**D9 — `USAGE.md:136`.** Current text falsely claims the package "intentionally stays out of MCP transport details — point an MCP server at the CLIs and you're done." At v1.7.0 the package ships `ai-sw-mcp` with **37 native tools**. Rewrite to point at the real MCP server and cross-link the relocated walkthrough (§3.4) and `docs/mcp_server_design.md`. Must preserve `USAGE.md`'s existing Workflow-4 framing (cross-session AI driving via subprocess JSON is still valid and stays).

**D10 — dead `docs/api_reference.md` links.** That file is gitignored (CHM-derived, not committed), so the links 404 on GitHub. Scope for Phase 2 (English surface only):
- `README.md:368` — `[See the API reference →](docs/api_reference.md)`
- `docs/AGENTS.md:128` and `docs/AGENTS.md:176`

Replace each dead link with **"regenerate `api_reference.md` locally"** guidance (the CHM-extractor command / `tools/_api_extract_input.json` regeneration path already referenced at `AGENTS.md:128`) rather than a link to an uncommitted artifact. Point the reader at `docs/sw_api_full.md` (committed) as the browsable superset where useful.

**Explicitly deferred (out of Phase 2 scope):** the i18n mirror links (`docs/i18n/zh-CN/README.md:106`, `docs/i18n/zh-TW/README.md:106`, and the tree-diagram references) ride with the governing spec's out-of-scope "full i18n retranslation" track (design spec line 279). `docs/com_failure_modes.md:117` is a secondary English mention — fix opportunistically only if it does not expand blast radius; otherwise log it.

### 3.3 Pillar C — Deprecation anchor into `PUBLIC_API.md`

Integrate §2.1 + §2.2 directly into `PUBLIC_API.md`, and true up the staleness the restructure exposes:

- **§4 SemVer** — replace pre-1.0 language (lines ~219–220) with the v1.7.0-accurate promise; supersede the "at least one MINOR release" deprecation procedure (lines ~222–235) with the locked §2.1 per-surface grace table.
- **§1 CLI tiers** — fix the `add_tire()` → `add_tier()` typo (line ~177); delete or regenerate the stale "Current assignments" 5-command sub-table (lines ~191–197) that lists only build/observe/mutate/probe/codegen (the real tier set is the full 22, already correct in the §1 main table).
- Add a **Deprecation Policy** subsection stating the §2.1 grace math, the announce-before-remove rule, and the §2.2 MCP dual-warning mechanism (marked as policy, plumbing pending first real deprecation).
- Reference the `DEPRECATIONS` registry (§3.5) as the machine-checked enforcement of this prose.

**Doc-truth constraint:** every pinned count/version substring in `DOC_SURFACES` for `PUBLIC_API.md` (CLI count, 37 MCP tools, facade taxonomy, console-script count, version) must survive verbatim. The plan verifies the pin list *before* editing and re-runs the gate *after*.

### 3.4 Pillar D — README dev router + MCP walkthrough relocation

The **"For developers & integrators"** section (`README.md:348–357`) already routes to PUBLIC_API / tools_reference / AGENTS / USAGE. It is close to correct — Phase 2 confirms it lists the three pillars + AGENTS and adjusts wording only if a link target moves.

**Relocation:** the MCP walkthrough (`README.md:244–334`, ~90 lines: install, register-with-Claude-Desktop, 37-tool inventory, deliberately-not-exposed list) moves into `docs/mcp_server_design.md`. In README, replace it with a short **stub** (title + one-paragraph orientation + the mermaid transport diagram may stay or move — plan decides) that links to the relocated section. Constraints:
- The README's own cross-references into this section (e.g. `README.md:46` "Jump to the MCP section ↓", `README.md:168`, `README.md:203`) must keep resolving — either the stub keeps the anchor id `#mcp-server--drive-the-bridge-from-claude-desktop--cursor--etc` or every inbound link is repointed.
- **Doc-truth:** README pins (22 CLI + 37 MCP tools, entry-point names) must survive. If the `37 tools` string or the tool-inventory list is pinned to README specifically, either keep a pinned copy in the stub or move the pin's `DOC_SURFACES` entry to `mcp_server_design.md` in the same change (the gate must stay green and keep asserting the count *somewhere* authoritative).
- `docs/mcp_server_design.md` already exists and is the canonical MCP design doc → natural home. Verify no duplicate/contradicting inventory already lives there; merge, don't duplicate.

### 3.5 Enforcement build — the concrete (§2.4)

**(a) Facade public-surface pin** — new `tests/test_facade_surface.py` (name TBD by plan):
- Introspect `SolidWorksClient` and its domain facades (`.observe`, `.mutate`, `.export`, `.urdf`, `.features` — enumerate from the live class, do not hardcode blindly).
- Snapshot public method names + signatures (`inspect.signature`) into a frozen expected surface (analogous to `EXPECTED_TOOLS`).
- Fail on **removal or signature-narrowing** of any public method; **new** public methods are allowed (additive) but must be consciously admitted into the snapshot (so the test also flags un-snapshotted additions to force a review, matching the CLI/MCP contract discipline).
- COM must never be touched — instantiate/introspect with the same bare-`object()` / lazy-injection pattern `tests/test_client_api.py` already uses. **This test is COM-adjacent by proximity → seat-prefire-review applies before the implementer touches it.**

**(b) `DEPRECATIONS` registry + CI gate** — new `src/ai_sw_bridge/deprecations.py` + `tests/test_deprecations.py`:

*Landing decision (adjudicated 2026-07-02):* the module lands as a **top-level leaf** (`src/ai_sw_bridge/deprecations.py`), a peer of the existing cross-cutting leaves (`flags.py`, `units.py`, `sw_types.py`) — **not** under `cli/` (which would falsely scope it CLI-only and force `mcp/`/`client.py` to reach sideways). It imports **nothing** from `cli/`, `mcp/`, `client.py`, or `spec/` (stdlib only) → structurally acyclic. Entries reference their target by **opaque string id** (`"stable_cli:ai-sw-observe"`, `"mcp_tool:sw_bbox"`, `"facade:SolidWorksClient.observe"`), mirroring how `TIER_REGISTRY` keys on `__module__` and `EXPECTED_TOOLS` keys on tool names — the registry never imports the symbols it governs, and a governed surface reads *its own* entry by id (one-way). An **import-linter forbidden-imports contract** (allowed-imports = ∅ for this module) pins the leaf property so a future reach-into-a-lane fails CI.

- A registry of entries: `(id, surface_class, deprecated_in, remove_in, replacement)` where `surface_class ∈ {stable_cli, mcp_tool, facade, experimental_cli, spec_handler}`.
- **Data/logic split for zero-pollution testing:** `DEPRECATIONS: tuple[DeprecationEntry, ...] = ()` (empty **and immutable** — an accidental `.append` raises). Validation is a **pure function** `validate_registry(entries, current_version) -> list[Violation]` that reads its arguments, never the global. The production gate calls it on the real (empty) tuple; the synthetic tests feed it **test-local** entry lists (one valid + one per invalid case) → production `DEPRECATIONS` is never mutated. Cross-surface reality checks (entry names a real live surface; no live surface has a served-grace `remove_in`) live in `test_deprecations.py`, which may import `TIER_REGISTRY`/`EXPECTED_TOOLS`/the facade snapshot — the coupling stays in the test graph, never the production graph. `current_version` sources from `importlib.metadata.version("ai-sw-bridge")` (the single pin doc-truth already asserts).
- The gate enforces, from the version strings alone (no live calls):
  1. **Grace-floor math** per §2.1 — stable classes: `remove_in` must be `≥ 2.0` **and** ≥ 2 minors past `deprecated_in`; experimental classes: `remove_in ≥ deprecated_in`'s next minor.
  2. **Announce-before-remove** — no entry may declare a `remove_in ≤ current package version` while the surface still exists (i.e. "refuses to compile" if someone tries to remove without the grace served).
  3. **No early removal** — a removed surface must have had a registry entry whose grace was fully served.
- Registry starts **empty** (zero deprecations today). The gate is proven against a **synthetic/self-test fixture entry** (a fake surface with valid + invalid version tuples) so the math is exercised even with an empty live registry.
- This module is pure version arithmetic — **not COM-adjacent** (no Dispatch surface). Seat-prefire not required for (b), but the plan states this explicitly so the reviewer confirms.

**(c) MCP dual-warning plumbing — NOT built.** Documented in PUBLIC_API §Deprecation (§3.3) and given a home in the registry (`mcp_tool` class already modeled). First real MCP-tool deprecation triggers a follow-up task to wire the description-prefix + `_deprecation` envelope and its integration test.

---

## 4. Safety & invariant constraints (non-negotiable)

1. **Seat-prefire-review** before any subagent touches a COM-adjacent file — static grep for COM-trigger patterns (`Dispatch`, `DispatchEx`, `GetActiveObject`, `EnsureDispatch`, `CoCreateInstance`, `win32com`) **plus** a dynamic tripwire (monkeypatch those to raise, import the target, assert `TRIPPED == []` and the SLDWORKS PID is unchanged). Applies to §3.5(a) (facade introspection). Does **not** apply to pure-Markdown tasks (§3.1–3.4) or §3.5(b) (version arithmetic) — but each task's COM-adjacency is stated explicitly so the reviewer can confirm.
2. **Seat-safe suite only** — `pytest -m "not solidworks_only and not destructive_sw"`. Never a bare `pytest`; never execute `tests/e2e_sw/` or `tests/mcp_lane/` bodies.
3. **Doc-truth gate is absolute** — no pinned substring in `tests/test_doc_truth.py::DOC_SURFACES` may drop. Verify the pin list before editing each doc; re-run the gate after. If a pin must move files (§3.4 MCP-inventory relocation), move the `DOC_SURFACES` entry in the same change so the gate keeps asserting the fact from its new authoritative location.
4. **HELD push** — no `git push` until all of Phase 2 is complete and the full gauntlet is green, then a single `isPrivate`-guarded fast-forward push (verify `gh repo view --json isPrivate` == true, `origin/master` is an ancestor of HEAD, HEAD unchanged since the check).
5. **Branch** — all work on `docs/commercial-elevation`. Never commit to `feat/w67-phase3`.
6. **Concrete not dirt** — expand CI pins so the fixed drift can't recur (D9/D10 truths become doc-truth-pinned where practical); patch mechanisms, not symptoms; no cosmetic-purity chasing at velocity's expense while invariants hold.

---

## 5. Non-goals (Phase 2 does NOT do)

- Build the MCP `_deprecation` envelope / description-prefix runtime (deferred, §2.2/§3.5c).
- Merge the three doc files into one (rejected, §2.3).
- Physically merge the CLI-tier registry and the new DEPRECATIONS registry (out of scope per governing spec line 279 "merging the two registry lanes").
- i18n retranslation or fixing the i18n mirror D10 links (out of scope, governing spec line 279).
- Commit/CI-publish `api_reference.md` (governing spec line 279 — separate tooling track).
- Any engine/COM behavior change.

---

## 6. Definition of Done (from governing spec §9 line 206 + this design)

- [ ] Dev-user guide coherent + cross-linked: shared nav block atop `USAGE.md`, `docs/tools_reference.md`, `docs/PUBLIC_API.md`, each naming its Diátaxis role and bidirectionally linking the other two.
- [ ] MCP walkthrough relocated from README into `docs/mcp_server_design.md` with an inline README stub; all inbound anchors still resolve.
- [ ] D9 fixed (`USAGE.md:136` reflects the 37-tool `ai-sw-mcp` reality).
- [ ] D10 fixed (English `README.md:368` + `docs/AGENTS.md:128,176` → "regenerate locally", no dead link).
- [ ] Deprecation policy written into `PUBLIC_API.md` (§2.1 grace table + §2.2 MCP dual-warning as documented policy); stale SemVer/grace/typo/sub-table trued up.
- [ ] Facade public-surface pin test built and green (closes the ❌ leg).
- [ ] `DEPRECATIONS` registry + CI gate built and green (empty live registry, proven via synthetic fixture).
- [ ] Doc-truth gate green; every prior pin preserved (or relocated with its fact).
- [ ] Full seat-safe gauntlet green; then single isPrivate-guarded FF push.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Doc-truth pin dropped during MCP relocation | Enumerate `DOC_SURFACES` pins for README + `mcp_server_design.md` *before* editing; move the pin entry in the same commit; re-run gate. |
| README anchor breakage (inbound `#mcp-server…` links) | Stub keeps the exact anchor id, or repoint every inbound link in the same change; grep for the anchor before/after. |
| Facade introspection accidentally instantiating COM | Reuse `test_client_api.py`'s bare-`object()` lazy pattern; seat-prefire tripwire mandatory on that task. |
| DEPRECATIONS gate under-tested because registry is empty | Synthetic fixture entries (valid + each invalid case) drive the math; the live-registry check is separate and may pass trivially at zero entries. |
| Facade "new methods flagged" too strict / churny | Additive methods allowed but must be admitted to the snapshot — mirrors the deliberate-review discipline of `EXPECTED_TOOLS`; documented in the test's docstring. |

---

## 8. Self-review (pre-user-gate)

- **Grounded, not invented?** Yes — every target line was read this session (README 244–363, USAGE full, tools_reference full, PUBLIC_API prior-read, D9/D10 grep-confirmed). `mcp_server_design.md` confirmed to exist.
- **Honors locked decisions?** Yes — §2.1–2.4 transcribe the user's verbatim adjudications; no closed decision reopened.
- **Concrete-not-dirt satisfied?** Yes — D9/D10 fix the mechanism (real MCP reality, regenerate-guidance), and the facade pin + DEPRECATIONS gate expand CI so the gaps can't recur; the one un-testable piece (MCP plumbing) is honestly deferred, not stubbed.
- **Safety invariants explicit per task?** Yes — §4 states COM-adjacency per task class and where seat-prefire applies.
- **Open ambiguities for the plan (not the design):** exact home for `DEPRECATIONS` (new module vs existing policy module); whether the mermaid diagram stays in the README stub or moves; exact new test filenames. These are implementation choices, deferred to the writing-plans step.

---

**NEXT:** user review gate on this design. On approval → invoke writing-plans to cut the Phase 2 implementation plan (SDD task decomposition, per-task seat-prefire flags, checkpoints + telemetry), then execute.
