# Human Gates Runbook — the four non-delegable release actions

> **Date:** 2026-06-26 · **Branch:** `feat/w67-phase3` (de-facto trunk) ·
> **Supersedes:** the now-stale §6 sequence in
> [`history/session_2026-06-25_commercial_hardening.md`](history/session_2026-06-25_commercial_hardening.md).

Everything required for a `v1.5.0` + `v1.6.0` cut is **code-complete and
offline-green**. What remains cannot be done by an agent — it needs an account
owner, a push credential, a physical SOLIDWORKS seat, or a lawyer. This doc is
the turnkey checklist: each gate names the blocker, the exact commands, and the
signal that closes it.

The four gates are **independent** except 2 depends on 1. Recommended order:
**4 → 1 → 3 → 2** (legal and the seat-fire can proceed in parallel with the
billing fix; the release push is last because it depends on billing).

---

## Pre-flight status (run 2026-06-26, this branch)

The release commit is **known-green** locally — every gate `release.yml` runs was
reproduced:

| Gate (CI/release.yml) | Command | Result |
|---|---|---|
| Format | `black --check .` | ✅ 883 files clean (2 reformats fixed this pass) |
| Lint | `flake8 src/` | ✅ clean |
| Types | `mypy --config-file mypy.ini src/ai_sw_bridge` | ✅ no issues, 215 files |
| Layers | `import-linter` (`pyproject [tool.importlinter]`) | ✅ 1 contract kept, 0 broken |
| Tests + coverage | `pytest -q --cov=ai_sw_bridge --cov-fail-under=60` | ✅ offline suite green ≥60% |
| MCP write-gate | `pytest tests/mcp_lane/ -m destructive_sw` | ✅ 80 passed (isolated lane) |

> **Caveat:** `mcp_lane` tests are auto-marked `destructive_sw` by
> `tests/mcp_lane/conftest.py` and are **skipped in the default suite** — make sure
> the isolated job (`-m destructive_sw`, with the `[mcp]` extra installed) runs in CI,
> or the new write-gate guard never executes.

---

## Gate 1 — Resolve GitHub Actions billing

**Blocker:** an account-level Actions billing limit refused every CI/release job in
the hardening session. This is owner-only (billing/plan settings on
`github.com/Thomas-Tai/ai-sw-bridge`). **Not a code problem.**

**To close:** restore Actions minutes / payment on the repo's billing plan, then
confirm a normal push triggers `ci.yml` and it goes green. Private repos include
2,000 free Actions minutes/month, so an "account-level limit" is often an exhausted
quota or a $0 spending cap — check the billing page before assuming you must pay.

**Option A — ship without waiting for billing (Actions-free manual release).**
You do **not** need CI to cut a release. The billing wall blocks the *automated*
`release.yml` pipeline, but the release itself can be done by hand:

- **Tagging is pure git** (`git tag` / `git push`) — no Actions.
- **Publishing is `gh release create`** — a REST API call, not an Actions run; it
  does not touch the billing block.
- **The release gate is already satisfied** — the pre-flight table above reproduces
  every check `release.yml` runs (`black`/`flake8`/`mypy`/import-linter/`pytest
  3750✓/65% cov`). That local run **is** the evidence the commit is green.

So you can execute Gate 2 today, privately, with the local pre-flight as the gate —
then restore automated CI later (paid minutes or a self-hosted runner), decoupled
from the publication decision. Do **not** flip the repo to public merely to get
free Actions minutes — that trades a few-dollar billing line for the irreversible
publication of a commercial product's full source + history (see the
pre-publication appendix below).

---

## Gate 2 — Synchronized release (`v1.5.0` + `v1.6.0`)

**Blocker:** pushing to `master` is **W0 guarded-push only** (isPrivate-guarded,
fast-forward, never `--force`), and publishing depends on Gate 1 (CI must be green
to tag off a verified commit). An agent must not push.

**The §6 sequence is STALE.** It tagged `v1.6.0` at `a2cbee4`, but two commits now
sit above that boundary (`6eac4f7` docs + `9ccbfb3` Option 3 write-gate) plus this
pass's pre-flight commit. The unreleased `v1.6.0` should tag at **HEAD**, not
`a2cbee4`. Tags currently stop at `v1.4.0`; `origin/master` is `8cefd01` (the
v1.5.0 boundary).

**Turnkey path:** the sequence below is packaged as a guarded, idempotent,
human-run script — [`tools/release_v1.5_v1.6.sh`](../tools/release_v1.5_v1.6.sh).
It enforces the W0 invariants in code (refuses unless the repo is private; pushes
master **fast-forward only**, never `--force`; tag creation is idempotent so a
re-run is safe) and prints the live SHAs before acting:

```bash
I_HAVE_RESOLVED_BILLING_AND_AM_RELEASING=yes bash tools/release_v1.5_v1.6.sh
```

The inline sequence below is the readable equivalent — use it to audit what the
script does, or to run the steps by hand.

**Manual sequence (run once Gate 1 clears). Re-confirm the SHAs first:**

```bash
# 0. Sanity — confirm the boundaries before tagging.
git fetch origin
git log --oneline -1 origin/master            # expect 8cefd01 (v1.5.0 boundary)
git log --oneline -1 feat/w67-phase3          # expect this pass's pre-flight commit (v1.6.0 tip)
gh repo view --json isPrivate -q .isPrivate   # MUST print "true" before any push

# 1. v1.5.0 — annotate + tag the already-published boundary.
git tag -a v1.5.0 8cefd01 -m "v1.5.0 — Runtime Resilience & Design Intelligence"
git push origin v1.5.0

# 2. Fast-forward origin/master to the v1.6.0 tip (the guarded FF push).
git push origin feat/w67-phase3:master        # FF only — fails loud if not a fast-forward

# 3. v1.6.0 — tag at the NEW tip (NOT a2cbee4).
git tag -a v1.6.0 "$(git rev-parse feat/w67-phase3)" \
  -m "v1.6.0 — Self-healing batch + unified MCP write-gate"
git push origin v1.6.0
```

**Signal it closed:** `release.yml` runs green on each tag and publishes the
GitHub Release; `gh release list` shows `v1.5.0` and `v1.6.0`.

---

## Gate 3 — Fire the live-seat proofs

**Blocker:** these assertions need a running SOLIDWORKS seat (SW 32.1.0); there is
none in the dev environment. They are **armed and auto-skipped** until fired.

> **Safety (from prior live runs):** the bridge attaches to the operator's **live**
> seat via the ROT. The destructive cases kill SW — run them **isolated** (`-m
> destructive_sw` only), never inside the full suite (SEH-crash risk wedges the
> batch). The reaper kills **by PID, never `/IM`**. Save your own open SW work first.

### 3a. RES-1 self-healing batch (flips "armed" → "live-proven")

```bash
# Isolated, one at a time. Each respawns the seat (~8–9 s).
pytest tests/e2e_sw/test_supervised_recovery.py -m destructive_sw -v
#   test_supervised_session_catches_real_seat_death   (Case 7, apply-death 0x800706BA)
#   test_customer_batch_api_survives_seat_death        (THE customer-path proof — RES-1)
#   test_case8_open_death_recovers_tier1               (open-death 0x800706BE)
#   test_case9_save_death_restores_snapshot_tier2      (Tier-2 snapshot restore)
#   test_case10_live_poison_cap_does_not_wedge         (poison-cap, no infinite respawn)
```
**Closes:** the CHANGELOG `[1.6.0]` "Live (armed, operator-gated)" line → upgrade to
"live-proven". Do **not** upgrade the claim until this passes on a real seat.

### 3b. M1 drawing-tolerance no-op (no offline cover)

The `_apply_tolerance_to_dims` fix (`is False` guard surfacing a kernel rejection)
has **no offline COM coverage** — it is regression-safe but its *positive* effect is
unproven live. On a seat, author a drawing with a dimension, apply a tolerance via
`ai-sw-drawing`, and confirm a kernel-rejected tolerance lands in the error manifest
rather than being counted as applied.

### 3c. `sw_build` MCP elicitation (offline-proven; live confirm)

`test_build_elicit.py` proves the COM build callable fires only on approval. A live
confirm wires `ai-sw-mcp` to Claude Desktop, asks it to build a spec, and verifies:
(1) nothing is written until you approve the in-chat elicitation; (2) `approve=false`
/ dismissing the prompt writes nothing; (3) `save_as` only reaches disk post-approval.

### 3d. (optional) MBD asymmetric bridge + weld-bead table

Tracked in [`pending_gates.md`](pending_gates.md) — both need a **human-authored
fixture** the COM API can't produce out-of-process (`tests/fixtures/mbd_block.sldprt`
with a bilateral `+0.2/-0.05` dimension; a weldment carrying weld beads). Lower
priority than 3a–3c; ship without them (documented enhancements).

---

## Gate 4 — Counsel review of the legal templates

**Blocker:** legal sign-off, not engineering. All three files are **internally
consistent** and carry explicit `TEMPLATE — NOT LEGAL ADVICE` banners; the
audit below confirms they are a clean package for counsel.

| File | State | Placeholders for counsel |
|---|---|---|
| `LICENSE` | Proprietary commercial EULA; MIT-vs-commercial boundary = "governs v1.5.0 and later" (matches the versioning decision) | `<LICENSOR>`, `<SEAT/FIELD-OF-USE TERMS>`, `<JURISDICTION>`, `<CONTACT>` |
| `CLA.md` | Inbound CLA granting relicense-to-commercial right; DCO `Signed-off-by` accepted as interim | `<LICENSOR>` |
| `THIRD-PARTY-NOTICES.md` | SolidworksMCP-python (MIT, ESPO 2025) + full MIT text; **all 7 attributed source files verified present** this pass | — (factual; keep the upstream-commit pin current) |

**To close:** qualified counsel reviews and fills the bracketed placeholders; replace
the banners with the finalized terms. No code change is required for this gate.

---

## Appendix — pre-publication secret/IP scan (2026-06-26)

Run before any decision to flip the repo **private → public**. Going public is a
separate, irreversible, business/legal call (the product is proprietary-commercial
and the license is still a counsel-review template — Gate 4). This appendix records
the *technical* readiness only.

**Scan results (gitleaks 8.30.1, full history + remote ref audit):**

- ✅ **IP scrub held.** Zero `.dll` / `.pfx` / `.snk` / key blobs reachable from any
  ref (including the stale `origin/feat/w68-*` remote-tracking branches). The W68
  `RouteCAddin.dll` removal is complete.
- ✅ **Pushable branch is clean.** `gitleaks git . --log-opts=feat/w67-phase3`
  (CI-equivalent single-branch scan, 684 commits) → **no leaks found**. The only
  gitleaks hits in the repo are the 9 documented SOLIDWORKS sketch-relation enum
  false positives (`"token": "sgHORIZONTAL2D"` …), allowlisted in `.gitleaksignore`
  by their on-branch SHA `a06ea3e3`. (They only re-surface on a `--all` scan, which
  pulls in the parallel-SHA stale worker branches — a local artifact, not a CI or
  push concern. Note: gitleaks fingerprints embed the commit SHA, so a future
  history rewrite would require regenerating that allowlist.)
- ⚠️ **The remote exposes more than the clean master.** `git ls-remote origin` shows
  the public surface would include, beyond `master` (`8cefd01`, scrubbed): four
  stale worker branches on the pre-scrub history line (`feat/w58-doc-trueup`,
  `feat/w68-curve-driven-pattern`, `feat/w68-fill-pattern`,
  `feat/w68-fillet-faceround`), five `dependabot/*` branches, and their
  `refs/pull/*` PR refs. None carry the DLL (verified), but half-finished worker
  branches and bot noise should not be a product's public face.

**Pre-publication checklist (human-gated, do NOT auto-execute):**

1. Decide that **source-available is the actual strategy** (not a default; the
   license is proprietary-commercial).
2. Finalize `LICENSE` / `CLA.md` with counsel (Gate 4) — never publish source under
   placeholder license text.
3. **Prune the remote to its intended public face** — delete the stale
   `feat/w58-*` / `feat/w68-*` worker branches and resolve/close the open dependabot
   PRs (#2–#6), leaving `master` (+ the release branch + tags). The exact, guarded,
   copy-paste sequence is drafted in [`tools/remote_prune_plan.sh`](../tools/remote_prune_plan.sh)
   (refuses to run until `I_HAVE_DECIDED_TO_GO_PUBLIC=yes`; never touches `master`
   or tags; notes the Dependabot-respawn caveat). Re-run `git ls-remote origin`
   to confirm.
4. Re-run this scan on the final ref set; confirm `no leaks found`.

Only then is a public flip + a tagged release a coherent launch moment.

## What an agent CAN keep doing between gates

- Keep the pre-flight green (re-run the table above after any commit).
- Re-derive the Gate 2 SHAs whenever new commits land on the branch.
- Keep `CHANGELOG.md` / `README.md` / `docs/PUBLIC_API.md` aligned to the surface.
- After a successful 3a run, prepare (not commit) the CHANGELOG wording that upgrades
  the resilience claim to "live-proven" for operator review.
