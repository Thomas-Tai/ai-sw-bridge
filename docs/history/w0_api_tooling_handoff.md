# W0 Hand-off — Parked W58 API-Extraction Tooling

**Status:** INFORMATIONAL hand-off from the overwatch session.
**Date:** 2026-06-20
**Author:** W0 (architectural overwatch)
**Audience:** the concurrent session working the API-reference / `sw_api_full.*` domain

> Not urgent and not a directive — a "don't reinvent / don't double-author" heads-up.

## The asset

The branch **`feat/w58-doc-trueup`** (remote tip `a2126a5`, **parked on `origin`**) holds the
original API-extraction tooling, which is **NOT in `master`**:

- `tools/export_full_sw_api.ps1` — **ABSENT from master**
- `tools/verify_api_reference_against_dll.ps1` — **ABSENT from master**
- plus a hygiene change: delete the generated `docs/api_reference.json` / `.md` and
  `.gitignore` them (master still **tracks** both, ~2,630 lines).

These are the same scripts cited as canonical in the project's API-authority record
(`reference_sw_interop_dll_authority.md`). They were authored 2026-06-16 and never merged
to master.

## The conflict

This is the **same domain you are live in right now** — your untracked
`docs/sw_api_full.json` / `docs/sw_api_full.md` and `docs/ribbon_api_progress_relation_audit.md`.
`a2126a5`'s `api_reference.*` outputs may already be **superseded** by your newer
`sw_api_full.*`. Overwatch deliberately did **NOT** cherry-pick or merge `a2126a5`, to avoid
colliding with your WIP in the shared working tree.

## The ruling — you own the reconciliation

`feat/w58-doc-trueup` is parked on the remote as a safe holding pen. Your call:

- **Cherry-pick** `a2126a5`'s two scripts into your line if they're still useful, **or**
- **Formally declare them superseded** by `sw_api_full.*` and let the branch be deleted in a
  later cleanup pass.

The branch's other commit (`808a192`, a one-line `DEFERRED.md` hem entry) is already
superseded by `master` line 56 — no action needed; it rides along harmlessly.

---

**Provenance:** part of the 2026-06-20 remote-hygiene pass that purged 8 fully-merged
`par/*` branches (zero history lost) and preserved this one branch precisely because it
carried unique, unmerged commits. See also `docs/w0_route_c_handoff_directive.md`.
