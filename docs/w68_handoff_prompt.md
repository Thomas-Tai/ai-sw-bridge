# W68 Handoff Prompt — for the concurrent execution session

**Status:** Kickoff prompt authored by W0 (architectural overwatch), 2026-06-20.
**Use:** paste the block below as the concurrent session's opening message. It is the literal,
self-contained handoff. The authoritative constraints live in
`docs/w0_w68_isolation_and_w58_directive.md`; this prompt operationalizes them.

---

```
You are the W68 execution session for the ai-sw-bridge project (a Python->SOLIDWORKS COM
bridge). You own the Route-C in-process ISwAddin harness and the API-reference domain.
W0 (the overwatch session) has just closed W67, synced and cleaned the GitHub remote, and
handed you the next epoch. Read this fully before touching git.

== CURRENT STATE (verified) ==
- Repo: github.com/Thomas-Tai/ai-sw-bridge -- PRIVATE. origin/master = aa78b2e (+ this prompt commit).
- Main checkout C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge is on branch
  feat/w67-phase3 and is RESERVED FOR W0 OVERWATCH. Do NOT do your W68 work in it.
- Parked remote branch feat/w58-doc-trueup holds 2 commits: a2126a5 (unique API-extraction
  tooling) and 808a192 (a DEFERRED.md hem line that is ALREADY SUPERSEDED on master).
- Authoritative brief: docs/w0_w68_isolation_and_w58_directive.md (read it -- it governs).
  Context: docs/w0_route_c_handoff_directive.md, docs/w0_api_tooling_handoff.md.

== W68 DEPENDENCY ORDER (ratified) ==
1. W58 tooling reconciliation  (foundation -- do this FIRST)
2. Route-C sheet-metal (jog / edge_flange / miter) + `wrap` classification via your ISwAddin
   harness -- sort each into COM-boundary-wall (shippable) vs true kernel-wall (defer)
3. net-new `sweep` (has prior art: swFmSweep=17, path must leave the profile plane)
`wrap` is deliberately in track 2, NOT a net-new feature -- it is a profile<->topology
projection, a prime boundary-vs-kernel question for the harness. Do not author it blind.

== YOUR IMMEDIATE TASK: STEP 1 (W58 reconciliation), in isolation ==
A) Isolate FIRST (mandatory -- a rebase/cherry-pick on the shared branch would shatter W0's
   linear history):
     git worktree add ../ai-sw-bridge-w68tooling -b feat/w68-tooling-reconciliation master
   Do all work in that worktree.
B) Cherry-pick ONE commit, not two:
     git cherry-pick a2126a5        # export_full_sw_api.ps1, verify_api_reference_against_dll.ps1, .gitignore hygiene
   DROP 808a192 entirely -- its hem line is already superseded by master line 56 (the
   "Production-wired...merged here" form). Rebasing it only manufactures a conflict.
C) Resolve the source-of-truth, explicitly, BEFORE merge-back. a2126a5 deletes
   docs/api_reference.json/.md and gitignores them; master still TRACKS them; your newer
   docs/sw_api_full.* is currently UNTRACKED. Rule it:
     - Which is canonical -- sw_api_full.* or api_reference.*?
     - Delete the loser.
     - Manage the winner: committed-as-canonical OR gitignored-as-generated with the harvest
       script as its declared source. Do not leave it untracked-and-unmanaged.
D) Verify: re-run the harvest and confirm it regenerates CLEAN against the live SOLIDWORKS
   redist DLLs. Run the offline test suite (pytest -n auto).

== DEFINITION OF DONE (W58 lane) ==
- feat/w68-tooling-reconciliation contains a2126a5's tooling, one SoT ledger only, harvest
  regenerates clean, tests green.
- Then PING W0: the merge to master goes through W0's guarded push discipline
  (verify private -> fast-forward -> no force). W0 owns the master merge. Do not push to
  master yourself.

== COORDINATION RULES ==
- Stay OFF feat/w67-phase3 (W0's checkout). All W68 work lives in your worktree.
- All master merges route through W0. You push your own feature branch freely.
- REPORT BACK NOW once you have created the isolated worktree and vacated feat/w67-phase3 --
  W0 is holding the formal W68 charter until you confirm isolation. That confirmation is the
  gate that lets W0 draft and open the charter.

Start with Step 1A (isolate), then report isolation before proceeding to 1B.
```
