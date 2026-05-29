# Reference Repositories

Upstream repositories studied during the v0.11–v0.13 development of
ai-sw-bridge. Some contributed direct ports (see `CONTRIBUTING.md`
§"Port attribution" for the per-file table); others were read-only
references for API patterns and architectural ideas.

**Why they're not in this repo:** at peak, the local
`docs/central_idea/reference/` collection was ~150 MB of cloned
upstream code. Bloating the bridge repo with full copies of public
repos is bad form. Instead, this doc lists the canonical sources;
`tools/clone_references.sh` re-fetches them locally into a
gitignored `references/` directory when you need them.

When porting from any of these:

1. Run `tools/clone_references.sh` (or `git clone` directly) to fetch
   the upstream into `references/`.
2. Pin the upstream commit SHA in `CONTRIBUTING.md` §"Port
   attribution" (per-file row).
3. Update `tools/check_upstream_drift.py` config so the drift
   monitor catches divergence beyond the pinned commit.
4. Add SPDX + adaptation note to the ported file's module docstring
   (per `docs/decisions.md` 2026-05-23 three-surface attribution
   decision).

---

## Repositories with shipped ports

| Repo | License | Used for | Pinned commit |
|---|---|---|---|
| [andrewbartels1/SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) | MIT (ESPO Corp 2025) | STA-threaded `ComExecutor` (W5.1), `SolidWorksAdapter` factory + mock + pywin32 implementations (W5.2), `sw_type_info.flag_methods` (W5.3), `errors/circuit_breaker.py` | `82e505d8` |

These ports power Lane M (MCP server) and the W5.6 death-recovery
scaffolding. See per-file rows in `CONTRIBUTING.md` for what was
adapted from each upstream file.

## Repositories studied (no direct ports)

| Repo | License | What we studied |
|---|---|---|
| [codestack-master](https://www.codestack.net/solidworks-api/) (CodeStack examples) | Permissive (per-file headers; verify before any port) | SOLIDWORKS API patterns — specifically the `EquationMgr.Add2` 3-arg form used in the v0.2 Path-C dim-binding fix. Acknowledged in `README.md`. |
| [angelsix/solidworks-api](https://github.com/angelsix/solidworks-api) | MIT (2017) | C# add-in framework. Relevant only to deferred Lane L5 (see `docs/DEFERRED.md`). Open-call for contributions on per-version Adapter DLLs is documented; lane is non-trivial. |

## Reports + analyses (not code)

These are external reports / analyses referenced in
`docs/decisions.md` and `docs/ai_driven_architecture_review.md` but
not redistributed here. Re-fetch from their original sources:

- **State of AI-SolidWorks Bridge Technologies: Comparative Analysis
  and Feature Tiering** (2026-05-23) — introduced the "Paradigm 1.5"
  taxonomy slot we adopted as our positioning. See
  `docs/decisions.md` 2026-05-23 entry.

## Re-fetching the clones

```powershell
# From repo root
./tools/clone_references.sh
```

The script:

1. Creates a gitignored `references/` directory at the repo root.
2. Clones each repo listed above into `references/<name>/`.
3. Checks out the pinned commit SHA for repos with shipped ports
   (so what you read locally matches what we adapted from).

Re-run any time. Existing clones get a `git fetch` + checkout to the
pin; nothing is force-reset, so any local exploratory changes are
preserved.

## Adding a new reference

When studying a new upstream:

1. Add a row to either "Studied" or "Shipped ports" table above.
2. If porting code, also update `CONTRIBUTING.md` per-file table and
   the relevant module docstring (three-surface attribution).
3. Add the repo to `tools/clone_references.sh` so future contributors
   can fetch your context.
4. Update `tools/check_upstream_drift.py` (only if you pin a specific
   commit — pure-reference repos don't need drift monitoring).
