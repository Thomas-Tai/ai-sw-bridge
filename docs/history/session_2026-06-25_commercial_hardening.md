# Session Reconstruction Record — Commercial-Hardening Sprint (2026-06-25)

> **Purpose:** a durable, self-contained record of the v1.4.0 → v1.6.0
> commercial-hardening session, so a future operator/agent can reconstruct *what*
> changed, *why*, and *what remains* — without re-deriving it from `git log`.
> **Companion docs:** the *living plan* is [`../commercial_readiness_audit.md`](../commercial_readiness_audit.md);
> the *public contract* is [`../PUBLIC_API.md`](../PUBLIC_API.md). This file is the *narrative*.

---

## 0. TL;DR

A full commercial-readiness audit (9-dimension adversarial workflow) found the repo
far healthier than its own stale 0.14.0-era planning docs claimed, with a narrow set
of real gaps. Those gaps were then closed across four waves, taking the repo from an
advanced-but-brittle R&D tool to a hardened commercial product.

- **Start:** `c3476d5` (HEAD at session open), `pyproject` v1.4.0.
- **End:** `a2cbee4` on `feat/w67-phase3`, v1.6.0. **16 commits**, 95 files, +2483/−599.
- **origin/master = `8cefd01`** (the v1.5.0 boundary, pushed). The 4 commits above it
  (v1.6.0) are **local-only** — push/tag is human-gated (GitHub Actions billing block).
- **All gates green & enforced:** black · flake8=0 · mypy=0 (pinned 2.1.0) · import-linter ·
  license_lint (blocking) · pip-audit (blocking) · coverage ≥60% (65%) · `release.yml needs:[test]`.
  Offline suite **3734 passed / 54 skipped**.

---

## 1. The audit (how the work was scoped)

Ran a background **multi-agent workflow** (`commercial-audit`, 17 agents) over 9 dimensions —
git/branches, docs, architecture, code-quality, tests/CI, packaging+licensing, security,
API-surface, COM-resilience — each adversarially verifying its own blocker/high findings
against HEAD to catch claims inherited from the **stale** `v1_0_commercialization_rfc.md` /
`a4_hygiene_runbook.md` (authored at v0.14.0, pre-GA). The `api` dimension agent failed twice
on `StructuredOutput` retry-cap, so that dimension was **re-run by hand** (its findings turned
out *favorable* — CLI tiers and the MCP contract were already CI-enforced).

**Reconciliation — most of the old RFC's "blockers" were already resolved by the shipped v1.0 GA work:**
version drift fixed, dual-API purged, `mutate.py` strangled 4283→2172, worktrees 24→1.
What actually remained: release-integrity hotfixes, CI enforcement gaps, one shipped-but-dormant
feature (resilience), presentation hygiene, and the licensing model.

**Verified high-severity findings that drove the work:** `CQ-1` black RED on the release commit ·
`CQ-3` a shipped CLI (`ai-sw-export-dxf-flat`) with a latent ImportError from the strangler-fig ·
`CI-1` `release.yml` had no test gate · `RES-1` SupervisedSession built+live-proven but wired into
ZERO production paths · `LIC-1` MIT vs commercial intent · `PKG-1` version drift recurred ·
`SEC-1` checkpoint encryption opt-in (plaintext default).

---

## 2. Decisions taken (operator-adjudicated)

1. **Licensing → Proprietary EULA + CLA** (Option 1). MIT replaced for the product; v1.0.0–v1.4.0
   stay MIT; embedded SolidworksMCP-python MIT attribution preserved. All legal text is a
   **counsel-review template**, not final.
2. **Version → 1.5.0** (Waves 0–1), then **1.6.0** (Waves 2–3, additive resilience + security).
3. **Dropped** the only two genuinely-unmerged branches (`sketch_trim` / `check_geometry`) — stale;
   rebuild against the new architecture if ever needed.
4. **SEC-1 implemented at the app/CLI boundary**, not by flipping the `CheckpointStore` constructor
   default (which would break the 28 crypto-contract tests + be poor library design).

---

## 3. Commit ledger (16 commits, `c3476d5`..`a2cbee4`)

**Wave 0–1 (v1.5.0; pushed to origin/master at `8cefd01`):**
```
5832511 fix: repair release-blocking lint + broken ai-sw-export-dxf-flat import   (CQ-1, CQ-3)
e8ede59 style: drive flake8 to zero — dead locals, E402/F401 noqa, delegate E501 to black (CQ-2)
9faf1bb test(mcp): refresh tool-contract payload snapshots
3d488bf ci: gate releases on a green test job + enforce flake8 in CI               (CI-1, CQ-2)
94df103 chore(hygiene): gitignore skills clone + spike outputs; land resilience spikes (GIT-4/7)
7da589a docs: archive ephemeral process docs to history/, add index + commercial-readiness audit (DOC-1/5/8)
fb8ff82 release(1.5.0): bump version + Production/Stable classifier; enforce mypy in CI (PKG-1/2, CQ-4)
e5cfb8a fix(types): drive mypy to zero — None-safety guards + annotations          (CQ-4)
4d50e9d ci+packaging: coverage gate, all-22 entry-point smoke, dep ceilings, secret/CVE scanning (CI-2/3, PKG-3/4, SEC-2/3)
b364e78 license: move to proprietary commercial model + CLA (counsel-review templates) (LIC-1)
fe835f6 docs(release): finalize 1.5.0 CHANGELOG + resilience spec; honest resilience claim (RES-2)
8cefd01 chore(hygiene): gitignore coverage artifacts
```
**Wave 2–3 (v1.6.0; local-only, ahead of origin/master):**
```
5fdc83e feat(resilience): supervised batch by default + production orphan-reaper   (RES-1, RES-3)
fa1bd46 docs: mark Wave 1 + Wave 2 shipped in the readiness audit
56995c9 feat(security): checkpoint encrypt-by-default (SEC-1) + scanners blocking   (SEC-1, SEC-2/3)
a2cbee4 docs: PUBLIC_API contract + complete CLI tiers + merge supply-chain + OOP-wall limits (API, RES-5, DOC-3)
```
(Branch git-admin — re-baseline `master`→origin/master, prune 37 stale branches, evict `skills/` —
was done with git commands, not commits.)

---

## 4. What each wave did

- **Wave 0 — release integrity:** `black` mutate.py (the one RED file on the tagged release commit);
  repointed the broken `ai-sw-export-dxf-flat` import (`..mutate` → `..features.flanges`, a
  strangler-fig orphan); version → 1.5.0; classifier Alpha → Production/Stable; re-baselined local
  `master` to `origin/master` (it had drifted 68 behind).
- **Wave 1 — enforce health in CI:** drove flake8 (90→0; E501 delegated to black in `.flake8`) and
  mypy (26→0; pinned `mypy==2.1.0`, behavior-preserving asserts/annotations) to zero and into CI;
  added a coverage gate (`--cov-fail-under=60`, measured 65%); an all-22-CLI entry-point smoke test;
  dependency ceilings + regenerated `requirements.txt`; gitleaks + pip-audit + Dependabot; and the
  keystone `release.yml` `test` job so a tag can't publish off a red commit.
- **Wave 2 — wire the engine (RES-1/3):** `client.mutate.batch()` + `ai-sw-batch` now run inside the
  `SupervisedSession` envelope **by default** (`supervised=False` escape hatch; graceful bare
  fallback; durable `TransactionStoreJournal(TransactionStore())` ledger that `sw_session_health`
  reads); `ExecutorSeatController.reap_orphans()` kills (by-PID, never `/IM`) windowless SLDWORKS
  orphans spawned during a session. Offline-proven; live through-API destructive proof **armed**
  (`test_customer_batch_api_survives_seat_death`, `destructive_sw`-gated).
- **Wave 3 — final hardening:** SEC-1 checkpoint **encrypt-by-default** (`crypto.default_key_source()`
  → env `AI_SW_CHECKPOINT_KEY` or auto `.sw_agent_key` gitignored + loud warning; build write-default,
  history read-fallback, `--no-checkpoint-encrypt` opt-out); `docs/PUBLIC_API.md` (contract + SemVer
  promise); tiered the last two CLIs (`sketch-relations`/`sketch-edit`); OOP-wall limits in
  `known_limitations.md` (RES-5); merged `supply_chain_audit.md` into `supply_chain_security.md`
  Appendix A; promoted license_lint + pip-audit to **blocking**.

---

## 5. Key engineering decisions / "honest calls" (the *why*, for reconstruction)

- **mypy fixes used fail-loud `assert`s** for COM-guaranteed-non-None invariants (not silent `if`
  bypasses) so behavior is preserved on the happy path. The mypy gate itself caught a real bug in
  the Wave-2 wiring (`ExecutorSeatController` not exported → supervised path would have silently
  fallen back to bare forever).
- **RES-2 (CHANGELOG honesty):** before wiring, the resilience claim was reworded to "opt-in, not
  default"; after Wave 2 wiring it became "self-healing by default" — but the *live through-API*
  proof is **armed, not fired** (no seat in the dev environment), and the record says so. Do not
  upgrade that claim to "live-proven" until the seat-fire passes.
- **SEC-1 at the app boundary** (see §2.4): a library constructor must not do filesystem/stdout
  side-effects; the operator-facing default (`ai-sw-build --checkpoint`) is what encrypts.
- **pip-audit promoted to blocking unverified** (not installed locally, no network) — if its first
  CI run reds on a transitive CVE, that's intended; triage with `--ignore-vuln <GHSA-id>`.
- **E501 delegated to black** in `.flake8` (black owns line length; flake8 enforces logical defects)
  — the standard black+flake8 resolution, avoids churning unsplittable lines.

---

## 6. Remaining work — ALL human-gated (not code)

1. **Resolve GitHub Actions billing** (account-level block; refused every CI/release job this session).
2. **Synchronized release** once billing clears:
   ```bash
   git tag v1.5.0 8cefd01 && git push origin v1.5.0
   git push origin feat/w67-phase3:master            # FF origin/master to v1.6.0
   git tag v1.6.0 a2cbee4 && git push origin v1.6.0
   ```
3. **Fire the live proof** on a single-seat machine to flip RES-1 armed → live-proven:
   `pytest tests/e2e_sw/test_supervised_recovery.py::test_customer_batch_api_survives_seat_death -m destructive_sw -v`
4. **Counsel review** of `LICENSE` / `CLA.md` / `THIRD-PARTY-NOTICES.md` (proprietary templates).

---

## 7. Recovery breadcrumbs & resumption

- **Deleted branches:** `../ai-sw-bridge-branch-graveyard-20260625.txt` (SHA log; recover with
  `git branch <name> <sha>`). 37 pruned; only `master` + `feat/w67-phase3` remain.
- **Evicted `skills/` clone:** `../skills_clone_evicted_from_repo` (was an accidental nested
  `anthropics/skills` checkout; now gitignored).
- **Wave-3 residual (Wave 4 backlog):** check `sketch-relations`/`sketch-edit` aren't in
  `test_cli_stability`'s iterated list (tiers added but assertion coverage unconfirmed); consider
  TransactionStore (resilience ledger) encryption parity with checkpoints; SemVer auto-version
  (setuptools-scm) to make tag/artifact divergence structurally impossible.
- **To resume:** read `docs/commercial_readiness_audit.md` (§5 wave status) and the auto-memory
  `project_v1_5_commercial_hardening` for current state. HEAD should be `a2cbee4` (v1.6.0) unless
  the release sequence in §6 has been executed.
