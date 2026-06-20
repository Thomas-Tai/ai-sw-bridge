# W0 Mandate — Workspace Isolation + W58 Tooling Reconciliation (W68 pre-charter)

**Status:** DIRECTIVE from the overwatch session. Action required **before** the W68 charter opens.
**Date:** 2026-06-20
**Author:** W0 (architectural overwatch)
**Audience:** the concurrent session (owner of the Route-C harness + API-reference domain)

## Context — why this is mandatory, now

Both sessions have been committing to `feat/w67-phase3` in the **same working tree**
(interleaved: `fd30229`[W0] → `cc8664b`[you] → `5a555f0`[W0] → `9e35559`[you]). It has
stayed linear by luck. Your next task — reconciling the W58 tooling — is a
**history-rewriting** operation. Run on this shared branch it would rewrite SHAs out from
under W0 and shatter that linear history. **We isolate before that happens.** The W68 charter
is on HOLD until you are isolated.

## Constraint 1 — Workspace split (do this FIRST)

Abandon the shared `feat/w67-phase3` checkout for your W68 work. Create a dedicated branch in
a **separate physical worktree**, based on the freshly-synced remote tip:

```bash
git worktree add ../ai-sw-bridge-w68tooling -b feat/w68-tooling-reconciliation master
```

Do all W58/W68 work there. This checkout (`feat/w67-phase3`) stays for W0 overwatch only.

## Constraint 2 — 1-commit cherry-pick, NOT a 2-commit rebase

The parked branch `feat/w58-doc-trueup` has 2 commits. Reconcile **only one**:

- **Cherry-pick `a2126a5`** — the API-extraction tooling (`export_full_sw_api.ps1`,
  `verify_api_reference_against_dll.ps1`, the `.gitignore` hygiene). This is the unique asset.
- **DROP `808a192`** entirely — its single `DEFERRED.md` hem line is **already superseded**
  by master line 56 (verified: master carries the more complete "Production-**wired**…merged
  here" form). Rebasing it only manufactures a conflict.

```bash
git cherry-pick a2126a5      # resolve the ~8 tooling-file conflicts; no full-branch rebase
```

## Constraint 3 — Declare the API source-of-truth BEFORE merging back

`a2126a5` deletes `docs/api_reference.json/.md` and gitignores them; **master still tracks
them**; your newer `docs/sw_api_full.*` is currently **untracked**. Two competing ledgers
cannot both live in the repo. Before any merge to master, rule explicitly:

1. **Which is canonical — `sw_api_full.*` or `api_reference.*`?**
2. **Delete the loser.**
3. **Ensure the winner is properly managed** — committed-as-canonical, OR gitignored-as-
   generated with the harvest script as its declared source. Not left untracked-and-unmanaged.

Re-run the harvest and confirm it **regenerates clean against the live DLLs** before the merge.

## Merge-back

The reconciled `feat/w68-tooling-reconciliation` merges to `master` through **one coordinated,
guarded step** (the W0 push discipline: verify private → fast-forward → no force). Ping W0
when it's ready; W0 owns the master merge.

---

Once you are isolated in the new worktree, W0 will draft and open the formal **W68 charter**
on the ratified dependency order:

> **W58 tooling reconciliation → Route-C sheet-metal + `wrap` classification → net-new `sweep`.**

(`wrap` is deliberately in the Route-C classification track, not the net-new track — it is a
profile↔topology projection, a prime boundary-vs-kernel question for the harness, not a
blind-authorable feature.)
