# Commercial-Readiness Audit & Reconstruction Plan

> **Date:** 2026-06-25 · **Baseline:** `feat/w67-phase3` == `origin/master` (was `c3476d5`) · **Target cut:** `v1.5.0`
> **Method:** 9-dimension adversarial audit (17 agents) + manual API-surface pass, every blocker/high finding independently verified against HEAD.
> **Supersedes:** [`history/v1_0_commercialization_rfc.md`](history/v1_0_commercialization_rfc.md) and [`history/a4_hygiene_runbook.md`](history/a4_hygiene_runbook.md) (both authored 2026-06-22 @ v0.14.0, now stale).

This is the living record of the v1.4.0 → v1.5.0 commercial-hardening pass: the audit, the
decisions taken, what was executed, and what remains. It replaces the two 0.14.0-era planning
docs, whose headline blockers (version drift, dual public API, the 4283-line `mutate.py`, 24
worktrees) were already resolved by the v1.0 GA work.

---

## 0. Executive summary

The repository is in **strong commercial shape** and materially healthier than its own (stale)
planning docs claimed. The strangler-fig refactor is complete (`mutate.py` holds zero feature
handlers; 36 GREEN kinds live behind a fail-loud `features/` registry), the import-linter layer
contract is green, the single `SolidWorksClient` facade is the public API, COM runs on one STA
thread, MCP writes are hard-wired `dry_run` + human-gated, and destructive seat-death recovery is
**live-proven** on a real seat. The offline suite is 3697 green.

What remained for a credible commercial cut was **release integrity, CI enforcement, one
"shipped-but-not-wired" feature, presentation hygiene, and one business decision (licensing)** —
not architecture. Those are tracked in §4–§5.

## 1. Current status (GitHub + repo)

| | |
|---|---|
| Remote | `github.com/Thomas-Tai/ai-sw-bridge` — **PRIVATE**; default branch `master` |
| Trunk | `feat/w67-phase3` is the de-facto trunk pointer and equals `origin/master`. Local `master` was re-pointed to `origin/master` (had drifted 68 behind). |
| Branches | Pruned from 39 → **2** (`master`, `feat/w67-phase3`); SHA-logged to `../ai-sw-bridge-branch-graveyard-20260625.txt` before deletion. |
| Worktrees | 1 (clean). |
| Version | `pyproject` → **1.5.0**; classifier → Production/Stable. Latest published GitHub Release is still v1.4.0 (the v1.5.0 tag is the gated next step). |
| Tests | 3697 passing offline; black + flake8 green; import-linter green. |
| Licensing | **Decision taken:** move to a proprietary commercial EULA + CLA (see §3). |

## 2. Consolidated findings (verified, severity-ranked)

Severities are post-adversarial-verification. ✅ = resolved this pass; ◻ = remaining.

| ID | Finding | Sev | Status |
|----|---------|-----|--------|
| CQ-1 | `black --check` RED on the release commit (`mutate.py:40`) | high | ✅ fixed |
| CQ-3 | `ai-sw-export-dxf-flat` broken import (strangler-fig left a stale `..mutate` import) | high | ✅ fixed |
| CI-1 | `release.yml` had **no test gate** — a tag could publish off a red commit | high | ✅ fixed (release `needs:[test]`) |
| PKG-1 | Version drift (HEAD 8 commits past v1.4.0, still labelled 1.4.0) | med | ✅ bump → 1.5.0 |
| PKG-2 | "Alpha" classifier on a GA product | med | ✅ → Production/Stable |
| CQ-2 | flake8 not in CI; 90 violations | med | ✅ driven to 0 + added to CI |
| GIT-1 | local `master` 68 behind `origin/master` | low | ✅ re-baselined |
| GIT-2 | 37 stale branches | med | ✅ pruned (SHA-logged) |
| GIT-4 | `skills/` nested clone + spike `_results` not gitignored | med | ✅ evicted + gitignored |
| DOC-1/5/8 | 19 ephemeral docs unindexed; no docs index | med | ✅ 18 archived + index added |
| LIC-1 | MIT vs commercial intent | high→med | ◻ EULA+CLA drafted (§3) |
| RES-1/2 | `SupervisedSession` live-proven but not wired into the batch path; CHANGELOG over-claimed | high→med | ◻ CHANGELOG made honest (opt-in); wiring deferred to next epoch |
| RES-3 | respawn orphan-reaper is test-only | med | ◻ deferred (lands with RES-1) |
| SEC-1 | checkpoint encryption opt-in (plaintext default) | high→med | ◻ planned (loud warning) |
| CQ-4 | mypy not in CI; ~21 None-safety + 6 stale ignores | med | ◻ in progress |
| CI-2/3 | no coverage gate; entry-point smoke covers 7/22 CLIs | med | ◻ planned |
| SEC-2/3 | no gitleaks / pip-audit / Dependabot in CI | med | ◻ planned |
| PKG-3/4 | floor-only deps, no lockfile; stale `requirements.txt` | med | ◻ planned |
| RES-4/5 | save-death no-auto-rollback + OOP walls not in `known_limitations.md` | low | ◻ planned |

**Already commercial-grade (do not churn):** strangler-fig registry, import-linter layers,
`SolidWorksClient` facade, CLI stability tiers (CI-enforced via `test_cli_stability.py`), MCP
tool contract + payload snapshots, STA COM safety, kill-safety (singleton-guard + bind-check),
OOP walls fail-closed, live-proven destructive recovery, zero network egress, checkpoint
encryption implementation, telemetry local-only + consent-gated.

## 3. Decisions taken

- **Licensing model → Proprietary commercial EULA + CLA.** MIT is replaced for the product;
  the embedded `SolidworksMCP-python` (MIT, ESPO) attribution is retained as a third-party
  notice. A CLA covers inbound contributions so the owner can license commercially. (Placeholder
  legal text is committed for counsel review — it is not a substitute for legal advice.)
- **Version → 1.5.0** (additive resilience + RAG epoch; SemVer minor).
- **Unmerged minor lanes `sketch_trim` / `check_geometry` → DROPPED** (stale; rebuild cleanly
  against the 1.5.0 architecture if ever needed).

## 4. Merge & reconstruction plan — DONE this pass

1. Re-baseline local `master` → `origin/master`.
2. Commit the working tree (resilience CHANGELOG/README/spec + MCP contract snapshots).
3. Prune 37 stale branches (SHA-logged graveyard outside the repo); keep `master` + `feat/w67-phase3`.
4. Evict the `skills/` nested clone; gitignore it + spike `_results`.
5. Archive 18 ephemeral process docs → `docs/history/`; add `docs/README.md` index; relocate the
   two stale planning docs with superseded banners.

## 5. Enhancement plan (the one-time fix-all) — waves

- **Wave 0 — release integrity (DONE):** CQ-1, CQ-3, GIT-1, version → 1.5.0, classifier.
- **Wave 1 — enforce health in CI (in progress):** ✅ `release.yml` test-gate, flake8 in CI;
  ◻ mypy → green + CI, coverage floor, entry-point smoke (all 22), gitleaks + pip-audit +
  Dependabot, dependency ceilings + lockfile, drop/regenerate `requirements.txt`.
- **Wave 2 — commercial hardening (next epoch):** wire `SupervisedSession` into the batch path +
  production orphan-reaper (RES-1/3); checkpoint-encryption loud-warning/default (SEC-1); write
  `docs/PUBLIC_API.md` + SemVer compatibility promise; add OOP-wall + save-death notes to
  `known_limitations.md` (RES-4/5).
- **Strategic:** finalize licensing (EULA + CLA) with counsel; promote `license_lint` to blocking.

**Then:** tag `v1.5.0` (now gated by the in-workflow test job) as the clean commercial cut.

## 6. Recovery / provenance

- Deleted branches: `git branch <name> <sha>` from `../ai-sw-bridge-branch-graveyard-20260625.txt`.
- Evicted skills clone: `../skills_clone_evicted_from_repo` (re-fetchable from `anthropics/skills`).
- Archived docs: `docs/history/` (history-preserving `git mv`).
