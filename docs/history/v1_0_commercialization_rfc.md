# RFC: `ai-sw-bridge` → v1.0 Commercial Release

> ⚠️ **SUPERSEDED (archived 2026-06-25).** Authored at v0.14.0; most of its
> blockers are resolved (version → 1.5.0, dual-API purged at v1.0, mutate.py
> strangled, worktrees pruned). Kept for provenance. Current state and the
> live plan live in [`docs/commercial_readiness_audit.md`](../commercial_readiness_audit.md).

> **Status:** DRAFT for review — no code changes yet.
> **Date:** 2026-06-22 · **Author:** audit pass (W0)
> **Driver (operator-selected):** *Commercialize toward v1.0.*
> **Vehicle (operator-selected):** *Design in detail first; no code changes until this RFC is approved.*
> **Supersedes the open items of:** [`docs/v0.14_commercial_hardening_plan.md`](v0.14_commercial_hardening_plan.md) (dated 2026-05-28; its view of `mutate.py` as 532 lines is now 8× stale).
> **Cross-refs:** [`reconstruction_recommendation.md`](central_idea/thoughts/reconstruction_recommendation.md) · `project_consolidation_policy` (memory) · [`deprecation_policy.md`](deprecation_policy.md) · [`cli_stability.md`](cli_stability.md).

---

## 0. TL;DR & recommendation

A "full reconstruction" of this repo is, mechanically, a **test-decoupling project** (the suite is welded to `mutate.py` internals via 68 `monkeypatch.setattr` calls across 109 files). Big-bang is therefore off the table by mechanics, not just by the standing policy — relocating handlers reddens the suite mid-flight and you lose the only net under the seat-proven COM recipes.

**But the chosen driver is commercialization, and that reframes everything:**

- The test-decoupling **spine (Steps 1–2)** only pays off by unblocking internal handler **relocation (Step 3)** — which commercialization does **not** require. For a v1.0 release, the spine is optional internal-quality work, invisible to a paying customer.
- The genuinely **v1.0-critical** work is: **(A1)** a frozen public/internal API boundary, **(A2)** resolving the dual public API, **(A3)** release/version hygiene, **(A4)** docs + repo presentation.

**Recommendation:** Ship v1.0 via **Track A** (days of work, low risk, high commercial value). Treat the strangler-fig **Track B** spine as a *separate, optional* investment justified only if you later add the *contributor-onboarding* goal — it is designed in full in §4 as requested, but it is not on the v1.0 critical path.

| | Track A — v1.0-critical | Track B — optional spine |
|---|---|---|
| Scope | API boundary + release hygiene + presentation | COM seam DI + test migration |
| Risk | Low (additive, no recipe bodies touched) | Medium (68 patch points, COM-sensitive) |
| Effort | Days | Weeks |
| Commercial payoff | **High** | Low (internal elegance) |
| Verdict | **Do for v1.0** | Defer unless onboarding becomes a goal |

---

## 1. Grounded findings (evidence, not memory)

All verified against the working tree at `feat/w67-phase3 @ e6a452e`, 2026-06-22.

| # | Finding | Evidence | v1.0 impact |
|---|---|---|---|
| F1 | **Version source-of-truth drift** | `pyproject.toml` `version = "0.14.0"`; `git tag` reaches `v0.17.0` + `v1.0-OOP-Baseline` | **Blocker** — `pip install` reports the wrong version |
| F2 | **Dual public API (observe)** | `observe.py`: 13 free `sw_get_*` funcs **and** `class SolidWorksObserver` (:1914) coexist | **Blocker** — two supported ways to call; which is the API? |
| F3 | **Dual public API (mutate)** | `mutate.py`: free `sw_propose_local_change/sw_dry_run/sw_commit/sw_undo_last_commit` (+ assembly/drawing/properties/feature_add variants) **and** `class ProposalStore` (:4239) | **Blocker** — same problem on the mutate surface |
| F4 | **Test↔internals coupling** | 109 test files reference `mutate`; **68** `monkeypatch.setattr(mutate, …)`; COM seams patched: `select_entity` ×11, `wrapper_module` ×10, `typed` ×9, `get_sw_app` ×9, `typed_qi` ×8, `get_active_doc` ×6 | Gates any *relocation*; irrelevant to v1.0 if we don't relocate |
| F5 | **`mutate.py` monolith** | 4283 lines; 28 `_create_*`/`_build_*` handlers + proposal lifecycle + dispatch | Contained & test-pinned; **leave it** (policy) |
| F6 | **`observe.py` + sprawl** | 2172 lines + 10 root `observe_*.py` modules | Internal-elegance only; not v1.0-critical |
| F7 | **Public surface is well-defined** | 19 `[project.scripts]` CLI entry points + MCP tools (`mcp/server.py`, `mcp/tools.py`) | This **is** the product — freeze it |
| F8 | **`features/` registry is clean** | `features/__init__.py` `_register_lane` gate; per-lane modules patch COM on themselves | The forward pattern; new kinds already land here |
| F9 | **Repo presentation debt** | 24 git worktrees, 39 branches (19 merged), 66 KB `--help` junk file, 53 loose top-level docs, 645 in-repo spikes | Customer-visible if OSS/eval; cheap to fix |

---

## 2. What "commercial v1.0" actually requires

The bar is *"a paying SOLIDWORKS shop can deploy this with a straight face,"* not *"the modules are elegant."*

**Required (Track A):**
1. **One public API, documented and frozen.** A customer must know what they may call and what may change under them. Today there are two call styles (F2/F3) and no machine-enforced public/internal line.
2. **Honest versioning & clean install.** `pip install` → correct version (F1), working entry points, pinned deps, `py.typed` (already present).
3. **Stability/deprecation commitment.** You already drafted [`deprecation_policy.md`](deprecation_policy.md) + [`cli_stability.md`](cli_stability.md) — v1.0 activates and enforces them.
4. **Docs a buyer reads without tripping** + a repo that doesn't look like a workshop floor.

**Explicitly NOT required for v1.0** (and therefore out of scope here):
- Internal module reshuffle (`observe/` subpackage, folding `mutate.py` handlers into `features/`). Invisible to customers; risks the moat.
- Test-decoupling for its own sake. Only matters if relocating (it isn't).
- Migrating off late-bound `pywin32`. Long-standing deferral; not unblocked by commercialization.

---

## 3. Track A — the v1.0-critical path (recommended)

### A1 · Public/internal API boundary  *(the core deliverable)*

**Decision:** The **product surface = the 19 CLI commands + the MCP tools** (F7). Everything else under `ai_sw_bridge.*` is `_internal` and may change without a major bump.

**Mechanism (additive, low-risk):**
1. **Declare the public Python API** (for the subset of customers who import the library, not just the CLI): a curated `ai_sw_bridge/__init__.py` `__all__` exporting only the sanctioned classes/functions. Everything else stays importable but undocumented and unguaranteed.
2. **Enforce the line in CI.** Add an `import-linter` contract: nothing outside `ai_sw_bridge.cli` / `ai_sw_bridge.mcp` may be imported by *consumers* of the public package; internal modules form a `_internal` layer. (You already run `lint-imports` in CI — this is one more contract, not new infra.)
3. **Document the surface.** A single `docs/PUBLIC_API.md` (or a generated reference) listing every public CLI command, every MCP tool, and the public Python entry points — with each marked by its stability tier per `cli_stability.md`.
4. **Mark stability tiers** on each CLI (`stable` / `beta` / `experimental`) so you can ship v1.0 without promising forever-support on the bleeding-edge OOP lanes (weldment, scale, auto_resolve_clearance).

**Acceptance:** `import-linter` green with the new public/internal contract; `docs/PUBLIC_API.md` enumerates the surface; every CLI `--help` states its tier.

### A2 · Resolve the dual public API  *(F2/F3)*

For each of `observe` and `mutate`, **pick one public form and demote the other**:

- **Recommended:** the **classes** (`SolidWorksObserver`, `ProposalStore`) are the public API — they take injectable providers, which is the commercial-friendly, testable shape the v0.14 plan already chose.
- The **free `sw_*` functions** become either (a) thin deprecated shims that delegate to the class and emit a `DeprecationWarning` (per `deprecation_policy.md`), kept through the v1.x line; or (b) explicitly `_internal`.

This is a real API decision a commercial release must make once — not a refactor. It touches signatures only at the seam, not recipe bodies.

**Acceptance:** `docs/PUBLIC_API.md` lists exactly one call style per capability; the demoted form warns (or is `_`-prefixed); CHANGELOG documents the choice; suite green.

### A3 · Release & version hygiene

1. **Single version source of truth.** Resolve F1: bump `pyproject.toml` to the real release (`1.0.0`), and verify `ai_sw_bridge.__version__` (already reads `importlib.metadata`) reports it after `pip install -e .`. Decide tag policy: tags must match `pyproject`.
2. **Clean wheel/sdist build** + an entry-point smoke test (each of the 19 `console_scripts` resolves and `--help` exits 0). Add to CI.
3. **Dependency pinning** appropriate for a shipped product (floor + ceiling on `pywin32`, etc.).
4. **CHANGELOG** consolidation to a dated `1.0.0` section; **`docs/migration_to_v1.0.md`** covering the A2 API decision (mirrors the existing `migration_to_v0.14.md` pattern).
5. **`docs/ROADMAP.md`** marks the v1.0 line; the OOP frontier (W62–W76) is recorded as shipped capability.

**Acceptance:** fresh `pip install` reports `1.0.0`; all 19 entry points smoke-green in CI; CHANGELOG + migration guide exist.

### A4 · Presentation hygiene  *(the first-audit cleanup, folded in)*

A commercial/eval repo shouldn't ship with a workshop floor visible. These are the reversible, guarded items from the repo audit (F9):

- **Junk + gitignore** — delete the 66 KB `--help` accidental-redirect file; gitignore `skills/` (an external clone of `anthropics/skills`) and `spikes/**/_results/`.
- **Worktrees + branches** — guarded prune of the 24 worktrees and ~38 branches (all W51–W61 era; current is W76). Per-item clean-check + unmerged-commit check; nothing force-removed; exceptions reported.
- **Docs consolidation** — move the ~20 *unreferenced* ephemeral process docs (`w*_glm_worker_prompts.md`, `w0_*_directive.md`, handoffs, version-migration plans) into `docs/history/`; add `docs/README.md` index. **Leave code-referenced docs in place** — ~40 inbound references from `src/`, `README.md`, `CONTRIBUTING.md` would otherwise break (verified). `docs/central_idea/` is gitignored local scratch — untouched.
- **Spikes** — for v1.0 OSS/eval optics, optionally extract the 645-file spike corpus to a sibling `ai-sw-bridge-research` repo (via `git filter-repo`), shedding ~50% of file count. *Optional* — they're harmless if private.

**Acceptance:** working tree clean; `git worktree list` shows 1; top-level `docs/` is navigable with an index.

---

## 4. Track B — the strangler-fig spine *(designed in full, as requested; OPTIONAL for v1.0)*

> Included because you asked for the spine designed in detail. **It is not on the v1.0 critical path** (§0). Do it only if you also adopt the *contributor-onboarding* goal, where unifying the dual dispatch and decoupling tests genuinely lowers the onboarding tax.

### B1 · Step 1 — the COM boundary port *(the keystone)*

**Problem (F4):** every COM-touching module re-imports the seam functions into its own namespace —
```python
# mutate.py today
from .sw_com import get_active_doc, get_sw_app
from .com.earlybind import typed, typed_qi, read_persist_reference
from .com.sw_type_info import wrapper_module
from .selection import select_entity
```
so tests must patch each name on each module (`monkeypatch.setattr(mutate, "get_sw_app", fake)`), and a relocated function silently escapes its patch.

**Target — one injectable provider object:**
```python
# com/provider.py  (NEW — the single sanctioned COM port)
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class ComProvider:
    get_sw_app:            Callable[[], Any]
    get_active_doc:        Callable[[Any], Any | None]
    typed:                 Callable[..., Any]
    typed_qi:              Callable[..., Any]
    select_entity:         Callable[..., Any]
    wrapper_module:        Callable[[], Any]
    read_persist_reference: Callable[..., Any]

def default_provider() -> ComProvider:
    from .sw_com import get_active_doc, get_sw_app
    from .com.earlybind import typed, typed_qi, read_persist_reference
    from .com.sw_type_info import wrapper_module
    from .selection import select_entity
    return ComProvider(get_sw_app, get_active_doc, typed, typed_qi,
                        select_entity, wrapper_module, read_persist_reference)
```
Handlers/observers take `com: ComProvider = default_provider()` and call `com.typed_qi(...)`. Tests pass a fake `ComProvider` — **no monkeypatch**.

**Lighter alternative** (if full DI is too invasive): keep free functions but route every module through a single `com.seams` module and patch *that one place*. Less clean than DI, far less churn. Recommended if Track B is ever done piecemeal.

### B2 · Step 2 — test migration *(the actual cost)*

This is the bulk of Track B and the only place real regressions hide.

1. **Introduce a `provider` pytest fixture** returning a configurable fake `ComProvider`.
2. **Migrate in batches by capability** (proposals → holes → refgeom → …), converting `monkeypatch.setattr(mutate, "<seam>", fake)` call-sites to inject the fake provider. **Suite stays green after every batch** — never a big-bang flip.
3. **Handler-internal patches** (`mutate._create_edge_flange`, `mutate._apply_feature`, etc., ~30 sites) are migrated only if/when those handlers move; for the lighter alternative they can stay.
4. **Discipline:** move *locations* and *patch targets* only — **never recipe bodies**. The moat rides through untouched.

**Why optional for v1.0:** the payoff of B1+B2 is that handlers become freely relocatable (Step 3). Commercialization doesn't relocate, so this is churn without a commercial return — pure internal quality.

### B3 · What Track B explicitly does NOT include

The internal reshuffle (Step 3: fold `mutate.py` handlers into `features/`; split `observe/`), the spike extraction (Step 4, which is in A4 as optional), and the `comtypes` migration. Those are separate decisions, none v1.0-blocking.

---

## 5. Sequencing & effort

```
v1.0 release line (recommended):
  A3 release hygiene ──▶ A1 API boundary ──▶ A2 dual-API decision ──▶ A4 presentation ──▶ tag v1.0.0
   (version SoT first so everything downstream stamps correctly)

Optional, later, only if onboarding becomes a goal:
  B1 COM port ──▶ B2 test migration (batched, suite-green each step)
```

- **Track A:** order is A3 → A1 → A2 → A4. Each is an independent, reviewable commit; suite green at each. Days, not weeks.
- **Track B:** strictly after A and only on an explicit onboarding decision. Weeks, COM-sensitive.

---

## 6. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| A2 demotion breaks an external caller of the free `sw_*` funcs | MED | Ship deprecated shims (not deletion) through v1.x; document in migration guide |
| Version bump misses a sidecar that hardcodes a version | LOW | A1 acceptance greps for hardcoded versions; `__version__` already reads metadata |
| import-linter public/internal contract over-restricts and reddens CI | LOW | Introduce as `warn` first, promote to `error` once green |
| Worktree/branch prune loses unmerged work | LOW | Guarded: clean-check + `git log master..<branch>` per item; nothing force-removed; report exceptions |
| Docs move breaks an inbound link | LOW | Only *unreferenced* docs move; `git mv` preserves history; the one README link fixed in the same commit |
| Spike extraction loses provenance | LOW | `git filter-repo` into a sibling repo preserves history; original stays in a backup bundle |

---

## 7. Decision points / sign-off

- [ ] Operator approves the **Track A scope** as the v1.0 cut (and Track B as deferred-optional).
- [ ] **A2 direction:** classes-as-public + deprecated free-function shims? (the recommended default)
- [ ] **A3 version:** cut as `1.0.0`? (vs `0.18.0` if you want a 0.x grace line first)
- [ ] **A4 spikes:** extract the 645-file corpus to a research repo, or leave private?
- [ ] Authorize executing **A4 presentation hygiene** now (it's reversible/guarded and independent of the API work).

---

*No code has been changed. This RFC is the requested design artifact; execution waits on the sign-off above.*
