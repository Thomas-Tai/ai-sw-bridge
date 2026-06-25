# A4 Repository Hygiene Sweep — Execution Runbook

> ⚠️ **SUPERSEDED / EXECUTED (archived 2026-06-25).** The hygiene it planned has
> been carried out (worktrees pruned to 1, ~37 stale branches deleted, skills/
> clone evicted, spike outputs gitignored, docs archived to `docs/history/`,
> this index added). Kept for provenance. See
> [`docs/commercial_readiness_audit.md`](../commercial_readiness_audit.md).

> **Status:** PLAN — awaiting approval to execute. No destructive step has run.
> **Date:** 2026-06-22 · **Driver:** RFC `docs/v1_0_commercialization_rfc.md` §A4 (establish a clean baseline before touching API boundaries).
> **Branch context:** main worktree on `feat/w67-phase3 @ e6a452e` (active W76 line, 22 commits ahead of `master`).
> **Operator directive:** review this plan first; execute only on explicit "go".

---

## 0. Current state (already done / verified, non-destructive)

| Item | State |
|---|---|
| `--help` (66 KB accidental API-dump, untracked) | ✅ **already deleted** (prior accepted step) |
| Worktree + branch diagnostics | ✅ captured (read-only) — see §2 |
| Backup of dirty worktrees | ❌ NOT run (rejected) — is **Step B1** below |
| Everything else | untouched — 24 worktrees + 39 branches intact |

---

## 1. Safety model (applies to all destructive steps)

1. **Uncommitted changes are the only unrecoverable state.** Deleted branches/worktrees are recoverable from `git reflog` + `git fsck --lost-found` for the gc grace window (~90 days). So the priority is to back up *uncommitted* content before removal.
2. **Backup folder (outside the repo):** `C:/D/ai-sw-bridge-hygiene-backup-20260622/` — receives (a) `git diff HEAD` patches of every dirty worktree, (b) copies of untracked `.py` scripts, (c) a full pre-prune branch→SHA log. Regenerable spike `_results/*.json` are intentionally **not** backed up.
3. **Keep-list (never touched):** the main worktree, branch `master`, branch `feat/w67-phase3`.
4. **Branch deletion uses `-d` (safe) where `ahead=0`; `-D` (force, reflog-recoverable) only where `ahead≥1`, and every deleted tip SHA is logged first.**
5. **Worktree removal uses plain `remove` where clean; `remove --force` only after the dirty content is backed up.**
6. Each committable phase (A, C) is a **separate, reviewable commit**; Phase B is git-admin (no commit).

---

## 2. Inventory (from diagnostics, 2026-06-22)

### 2.1 Worktrees (24 linked + 1 main)

**KEEP (1):** `…/ai-sw-bridge` → `feat/w67-phase3` (main worktree).

**CLEAN — remove directly (14):**
`ai-sw-bridge-hinge`(w51-hinge-limit), `wt_integration`(par/w58-w59-integration), `wt_w59annot`(w59-annot-sig), `wt_w59checkgeom`(w59-checkgeom), `wt_w59doctrine`(w59-wall-doctrine), `wt_w59hem`(w59-hem), `wt_w59infra`(w59-infra), `wt_w59movecopy`(w59-movecopy), `wt_w59onb`(w59-onboarding), `wt_w59packgo`(w59-packgo), `wt_w59thread`(w59-thread), `wt_w59varfil`(w59-varfil-ctrlpts), `wt_w59vermatrix`(w59-vermatrix), `wt_w60sketchedit`(w61-sketchedit2).

**DIRTY w/ regenerable spike scratch only — back up `.py`, then `--force` remove (6):**
`ai-sw-bridge-drawannot2`, `ai-sw-bridge-rib`, `ai-sw-bridge-sheetmetal2`, `ai-sw-bridge-verifyaudit` (each: one `_results/*.json`), `wt_w59pierce` (spike `.py` + result jsons), `wt_w59rib` (10× `_results/rib2_v*.json`).

**DIRTY w/ tracked edits — back up patch, then `--force` remove (4):**
- ⚠️ `ai-sw-bridge-bodyops` → `feat/w52-bodyops`: **`M src/ai_sw_bridge/mutate.py`** (the only real source edit — W52 combine/split, recorded as terminal OOP walls in memory `project_body_ops_epoch`, but **backed up to a patch regardless**).
- `wt_w60convert`, `wt_w60offset`, `wt_w60pattern`: each `M spikes/v0_2x/_sketch_edit_fixtures.py` (spike fixture scratch; W60/W61 shipped).

### 2.2 Branches (39 total)

- **KEEP (2):** `master`, `feat/w67-phase3`.
- **`ahead=0` of master → delete with `-d` (18):** w58-section-props, w58-version-matrix, w59-annot-sig, w59-hem, w59-movecopy, w59-onboarding, w59-varfil-ctrlpts, w59-vermatrix, w59-wall-doctrine, w60-convert, w60-offset, w60-pattern, w60-sketchedit, w61-sketchedit2, w67-verify-substrate, par/integration, par/w58-w59-integration, refactor/feature-handler-registry.
- **`ahead≥1` (squash-merge residue, all W51–W65) → delete with `-D` after SHA-logging (19):** w55-drawannot2(1), w59-checkgeom(1), w59-packgo(1), w59-thread(1), w60-trim(1), wip/w65-worker-mainrepo(1), w55-rib(2), w55-sheetmetal2(2), w55-verifyaudit(2), w57-design-table-exposure(2), w58-move-copy-body(2), w59-infra(2), w51-motion-ext(3), w52-bodyops(3), w56-gtol-revolve-merge(3), w59-pierce-v3(3), w51-hinge-limit(4), w58-doc-trueup(4), w59-rib(4).

> Note: a branch checked out in a worktree cannot be deleted until its worktree is removed → Phase B removes worktrees first, then deletes branches.

---

## 3. PHASE A — junk + gitignore  *(1 commit; low risk)*

- **A0.** ✅ `--help` already deleted.
- **A1.** Append to `.gitignore`:
  ```gitignore
  # External skills clone (anthropics/skills) — re-fetchable, not part of this repo
  skills/
  # Spike research outputs (regenerable; corpus slated for extraction to ai-sw-bridge-research)
  spikes/**/_results/
  ```
  (Root `_results/` is left alone — it holds tracked example fixtures.)
- **A2.** Verify: `git status --porcelain | grep -E '^\?\? (skills/|spikes/.*_results/)'` returns nothing.
- **A3.** Commit: `chore(hygiene): remove --help junk; gitignore skills clone + spike outputs`.

---

## 4. PHASE B — worktree + branch prune  *(git-admin; guarded, no commit)*

- **B1. Backup** (the rejected step, re-run): for every dirty worktree → write `git diff HEAD` to `…backup…/<name>.patch` and copy untracked `.py` files; then snapshot all branch tips: `git for-each-ref --format='%(objectname) %(refname:short)' refs/heads/ > …backup…/branches_pre_prune.txt`. **Verify** `ai-sw-bridge-bodyops.patch` is non-empty (contains the mutate.py diff).
- **B2. Remove clean worktrees (14):** `git worktree remove <path>` for each in §2.1 CLEAN.
- **B3. Remove dirty worktrees (10):** `git worktree remove --force <path>` for each in §2.1 DIRTY (only after B1 confirms backup).
- **B4. Prune admin:** `git worktree prune`; verify `git worktree list` shows only the main worktree.
- **B5. Delete `ahead=0` branches (18):** `git branch -d <name>` each (will refuse if not truly merged — that refusal is a stop-and-report signal).
- **B6. Delete `ahead≥1` branches (19):** confirm SHA is in `branches_pre_prune.txt`, then `git branch -D <name>` each.
- **B7. Verify:** `git branch` shows exactly `master` + `* feat/w67-phase3`.

---

## 5. PHASE C — docs archive + index  *(1 commit; self-guarded)*

- **C1.** `mkdir docs/history`.
- **C2. Move only docs with ZERO inbound references** (guard each: `git grep -l "docs/<name>"` returns nothing → safe to `git mv docs/<name> docs/history/`). Target set (19):
  `w60_glm_worker_prompts.md`, `w61_glm_worker_prompts.md`, `w62_glm_worker_prompts.md`, `w64_glm_worker_prompts.md`, `w65_glm_worker_prompts.md`, `w66_glm_worker_prompts.md`, `w60_sketch_editing_worker_prompts.md`, `w68_wave4_worker_prompts.md`, `w68_handoff_prompt.md`, `w65_round2_fixture_fixes.md`, `w65_edge_flange_rework.md`, `w67_verify_substrate.md`, `w0_w68_isolation_and_w58_directive.md`, `w0_route_c_handoff_directive.md`, `w0_api_tooling_handoff.md`, `handoff_template.md`, `handoff_F1.md`, `deferred_dim_investigation.md`, `refactor_proposal_sketch_handlers.md`.
- **C3. Move + fix the 1 inbound link each (3):**
  - `migration_to_v0.14.md` → history (referenced only by the v1.0 RFC cross-ref → update that line).
  - `v0.14_commercial_hardening_plan.md` → history (referenced by the v1.0 RFC "Supersedes" line → update).
  - `migration_to_v0.12.md` + `ai_driven_architecture_review.md` → history, then update their links in `README.md`.
  - Also fold `launch_readiness_checklist.md`, `devops_pipeline_standby_state.md`, `audit_s1_cli_mcp_parallelism.md` into history (grep-guard each first).
- **C4. Leave in place (code/README-referenced durable docs):** `DEFERRED.md`, `com_failure_modes.md`, `addins_research.md`, `known_gotchas.md`, `known_limitations.md`, `why_no_addim2.md`, `checkpoint_encryption_design.md`, `mcp_server_design.md`, `spec_reference.md`, `AGENTS.md`, `ROADMAP.md`, `CAPABILITIES.md`, `ROLES.md`, `ONBOARDING.md`, `decisions.md`, `deprecation_policy.md`, `cli_stability.md`, `release_engineering.md`, `architecture.md`, `lane_designs.md`, `tools_reference.md`, `sketch_axes.md`, `reference_repos.md`, `sw_version_matrix_runner.md`, `supply_chain_*.md`, `privacy_review.md`, generated `api_reference.*`/`sw_api_full.*` (gitignored). `docs/central_idea/` (gitignored local scratch) — untouched.
- **C5.** Create `docs/README.md` — one-line index of every remaining top-level doc + a "history/ = archived process artifacts" note.
- **C6. Verify:** `git grep -l "docs/<moved-name>"` is empty for every moved file (no dangling links); `mypy`/tests unaffected (docs-only).
- **C7.** Commit: `docs: archive 22 ephemeral process docs to docs/history; add docs index`.

---

## 6. Commit strategy & post-conditions

- **Commits land on `feat/w67-phase3`** (the active line; matches the repo's guarded-push-to-master flow). Two commits total (Phase A, Phase C). **Nothing pushed** without explicit approval.
- **Post-conditions:** working tree clean (modulo intentional untracked); `git worktree list` = 1; `git branch` = 2; top-level `docs/` reduced from 53 → ~31 + `history/` + `README.md` index; backup folder retained until you confirm.

## 7. Rollback

- Restore an uncommitted edit: `git apply …backup…/<name>.patch` in a fresh checkout of that branch's SHA (from `branches_pre_prune.txt`).
- Restore a deleted branch: `git branch <name> <sha>` (SHA from the log; or `git reflog` / `git fsck --lost-found`).
- Restore a docs commit: `git revert <commit>`.

## 8. Sign-off

- [ ] Approve §2 keep-list and the `-D` deletions of the 19 `ahead≥1` branches.
- [ ] Approve the §5 docs archive set (and the 4 link-fix files).
- [ ] Confirm commits on `feat/w67-phase3` (vs a dedicated `chore/repo-hygiene` branch).
- [ ] "Go" → execute A → B → C in order.

---

## 9. Out of scope (separate, larger operations — not in this sweep)

- **Spikes corpus extraction** to `ai-sw-bridge-research` (RFC decision #4) — a `git filter-repo` history-preserving split; planned separately.
- **Public API boundary / class-as-API / version bump** (RFC Track A1–A3) — after this baseline is clean.
