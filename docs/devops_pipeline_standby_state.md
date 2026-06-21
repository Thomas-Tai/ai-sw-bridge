# DevOps Pipeline — Standby State & W0-Side Characterization

> **Banked:** 2026-06-21 (W69, at `v1.0-OOP-Baseline` / `abc9a51`).
> **Status:** W0 overwatch in **hard standby**. No active development; OOP frontier closed.
> **Purpose:** a down payment on the next epoch — record the W0-observable git/credential
> environment so the worker→origin pipeline debug starts *warm*, not cold.

## The problem (recap)

Across W68/W69, offline GLM/Sonnet **worker** sessions repeatedly reported "pushed branch
to origin" (e.g. `feat/w68-table_driven_pattern`, `feat/w68-chain_pattern`, the flex fix),
but `git fetch origin` + `git rev-parse --verify origin/<branch>` from W0 showed the branch
**absent every time**. The branches never reached `origin`. W0 worked around it by authoring
those lanes locally from the worker prompts; the pipeline itself was never fixed.

## ⚠️ Hard limit of this characterization

**The W0 overwatch environment CANNOT definitively diagnose the worker environment credential
wall.** The failure occurs in the *worker* session's `git push` step, in a different process /
sandbox that is not live here. W0 can only observe the **receiving** side (origin config,
branch protections, fork model) and the **shared** git config on this seat. W0 cannot reproduce
the failure precisely **because W0 holds a working credential** (see below). A real fix must be
attempted *with a live worker session in front of us*, where the push actually fails.

## W0-side findings (2026-06-21)

| Probe | Finding | Implication |
|---|---|---|
| `git remote -v` | `origin = https://github.com/Thomas-Tai/ai-sw-bridge.git` (HTTPS; push==fetch) | Single shared remote; HTTPS (token auth, not SSH key). |
| `git config` credential | global `credential.helper=manager` **AND** override `credential.https://github.com.helper = !gh.exe auth git-credential` | **On the W0 seat, GitHub auth is delegated to the authenticated `gh` CLI.** This is *why W0 pushes land* — and why W0 can't reproduce the worker failure. |
| `gh repo ... forkCount` | **0 forks** | Workers were NOT configured to push to a personal fork; they target shared `origin` directly. |
| branch protection API | `403 — "Upgrade to Pro / make public"` | Free-tier **private** repo: branch protection **cannot be configured** → protection is **NOT** the blocker. |
| repo visibility | `isPrivate = true` | Guarded-push invariant (isPrivate==true) holds; W0 FF pushes are authorized. |

## Leading hypothesis (UNVERIFIED — needs a live worker)

The worker environment lacks the `gh`-delegated github.com credential (or any push-scoped PAT
for `origin`). Its `git push` therefore commits to the local branch but never authenticates to
`origin` — failing **silently** (no fork to fall back to, no protection error to surface). The
worker reports local success while nothing leaves the box. Most likely root causes, in order:

1. **No credential in the worker sandbox** — `gh` not authenticated there, or no PAT in its
   credential store / `GH_TOKEN` env. (Most probable.)
2. **Network-isolated sandbox** — the worker has no egress to github.com; push fails or is
   swallowed by a sandbox shim.
3. **Wrong/expired token scope** — a PAT present but without `repo`/push scope on a private repo.

## When the next epoch needs the pipeline — first moves (with a live worker)

1. In the worker session: `gh auth status` and `git config --get credential.https://github.com.helper`
   — confirm whether the `gh`-delegated helper (or any token) is present.
2. Make the worker run `git push origin HEAD:refs/heads/probe-<id>` and **read the actual stderr**
   (not the worker's self-report). Silent success vs. auth error vs. network error discriminates
   hypotheses 1–3 immediately.
3. If no credential: provision a push-scoped PAT into the worker (`GH_TOKEN` env or
   `gh auth login`), or have workers push to a **personal fork** + W0 merges via PR (decouples
   worker creds from the protected shared remote).
4. Re-confirm `git rev-parse --verify origin/<branch>` from W0 before trusting any "pushed" report
   (the standing verify-ref-before-fire rule — see `project_w68_epoch_closed`).

## Posture

- **W0 overwatch: hard standby.** `master` pristine at `v1.0-OOP-Baseline`; seat a clean
  singleton; Route-C add-in unregistered; memory + boundary law banked.
- The pipeline has **no current consumer** (OOP frontier exhausted) — this debt is deliberately
  deferred until a future epoch (most likely the redefined COM-marshaling-only Route-C scope)
  actually requires parallel workers. Fix it *then*, *with a worker live*, not blind from W0.
