# W68 Handoff Prompt — for the concurrent execution session

**Status:** AUTHORITATIVE handoff, authored by W0 (architectural overwatch), 2026-06-20.
**Supersedes:** the prior pre-scrub kickoff. The repository history was **rewritten** by W0
(W68 IP scrub — `RouteCAddin.dll` excised from full history; see `project_w68_ip_scrub`),
so the state below is the only valid starting point.
**Use:** paste the block below as the concurrent session's opening message. The authoritative
constraints live in `docs/w0_w68_isolation_and_w58_directive.md`; this prompt operationalizes
them against the post-scrub reality.

---

```
W0 OVERWATCH DIRECTIVE: W68 PHASE 1 (TOOLING RECONCILIATION)

Status:       GREEN LIGHT / HISTORY REWRITTEN.
Target:       Concurrent W68 Session.
Prerequisite: STOP. Do not use your local `master` branch. The repository history was
              rewritten by W0 to perform an IP scrub. Your old local `master` (283d0d5)
              is dead. origin/master is now the clean, scrubbed baseline (22ea48c at the
              moment of the scrub; fetch for the live tip).

You are authorized to execute Phase 1 (W58 Tooling Reconciliation) strictly following
this sequence:

1. SYNC WITH REALITY
   - Run `git fetch origin` to pull down the newly secured origin/master.

2. ISOLATE THE WORKTREE
   - Spin up your isolated environment, explicitly branching off the REMOTE master:
       git worktree add ../ai-sw-bridge-w68tooling -b feat/w68-tooling-reconciliation origin/master
   - Do ALL W58/W68 work in that worktree. Stay OFF feat/w67-phase3 (W0 overwatch checkout).

3. THE 1-COMMIT CHERRY-PICK
   - The w58 branch on the remote (feat/w58-doc-trueup, tip a2126a5) was UNTOUCHED by the
     rewrite — it is pre-DLL, so its SHA is still valid.
       git cherry-pick a2126a5      # export_full_sw_api.ps1, verify_api_reference_against_dll.ps1, .gitignore hygiene
   - Do NOT rebase, and do NOT pull in the superseded DEFERRED.md update (808a192). Its hem
     line is already superseded by master; rebasing it only manufactures a conflict.

4. THE SOURCE-OF-TRUTH (SoT) DECISION
   - Adjudicate the double-ledger: sw_api_full.* vs api_reference.*.
   - a2126a5 deletes docs/api_reference.json/.md and gitignores them; master still tracks
     them; your newer docs/sw_api_full.* is currently untracked. Rule it explicitly:
       * Retain the canonical winner.
       * Permanently delete the loser.
       * Ensure the winner is properly managed — committed-as-canonical, OR gitignored-as-
         generated with the harvest script as its declared source. Not left untracked.

5. THE COMPLETION GATE
   - Regenerate the API harvest using the reconciled scripts; confirm it regenerates CLEAN
     against the live SOLIDWORKS redist DLLs.
   - Verify all tests pass against the new signatures (pytest -n auto).
   - Once clean, PING W0 OVERWATCH. W0 will handle the guarded fast-forward merge back to
     master (verify private -> fast-forward -> no force). Do NOT push to master yourself.
     You push your own feature branch freely.
```

---

## Context retained for after Phase 1

**Ratified W68 dependency order** (W0-governed):

> **W58 tooling reconciliation → Route-C sheet-metal (`jog`/`edge_flange`/`miter`) + `wrap`
> classification via the ISwAddin harness → net-new `sweep`.**

- `wrap` is deliberately in the Route-C classification track, NOT the net-new track — it is a
  profile↔topology projection, a prime boundary-vs-kernel question for the harness, not a
  blind-authorable feature.
- `sweep` has prior art: `swFmSweep=17`, the path must leave the profile plane.

**Governing brief:** `docs/w0_w68_isolation_and_w58_directive.md` (it governs).
**Context:** `docs/w0_route_c_handoff_directive.md`, `docs/w0_api_tooling_handoff.md`.

Once Phase 1 reconciliation is merged via the W0 guarded push, W0 drafts and opens the formal
W68 charter on the dependency order above.
