# Go-Public Commercial Readiness — Audit & Remediation Tracker (2026-07-07)

**Question that triggered this:** *"As a fresh reviewer of this repo, do a commercial check and recommend the steps to take before flipping the repository from **private → public**."*

**Short answer:** **GO, with one hard blocker and a short pre-flight list.** The technically-risky part of going public — permanent, world-readable exposure of the *entire git history* — is **clean**: no binary blobs, no secrets, no accidentally-tracked local/AI cruft. The gating issues are **legal/administrative**, not code: an unfinished LICENSE and some pre-flight cleanup.

**Method:** an evidence-based audit run against `master` @ HEAD `1f2ff25` (not asserted from memory). Every finding cites the command/file that produced it, and carries a **Verify** line that re-checks the fixed state. Public exposure is scoped to **tracked content + full history + all pushed refs** — so the audit deliberately covers history blobs, PII in commits, stale branches, and internal docs, not just the working tree.

**How to use this doc:** each finding has a **Verify** line. When every finding is `FIXED`/`ACCEPTED` and its Verify passes, the repo is ready to flip. **To re-check everything in one pass, jump to [§ Verification Protocol](#-verification-protocol--runnable-cross-check) at the end** — a single COM-free command block (`git`/`grep`/`gh` only, no live seat) with the expected result for every item. Do **not** "fix" anything in the *Already clean* section.

Status legend: `OPEN` (confirmed, not yet done) · `FIXED` (remediated + Verify passes) · `ACCEPTED` (owner reviewed a judgment call and chose to keep as-is) · `DEFERRED` (needs an outward-facing / counsel action).

---

## 🔴 BLOCKER — must resolve before a *commercial* public launch

### B1 — The LICENSE is an unreviewed placeholder · Status: OPEN
- **Evidence:** `LICENSE:1-6` — `"ai-sw-bridge — Commercial Software License Agreement"` then `"TEMPLATE — NOT LEGAL ADVICE."` and `"This is a PLACEHOLDER proprietary commercial license drafted during the v1.5…"`. `grep -c 'PLACEHOLDER\|TEMPLATE — NOT LEGAL ADVICE' LICENSE` → **3** (as-audited). The README badge (`license-Proprietary`) and `CLA.md` both point at this file.
- **Impact:** publishing a *commercial* product under a self-declared placeholder license is the one genuine legal exposure here. It is unenforceable as-is, and every contributor accepting the `CLA` would be agreeing to a template. This is the single go/no-go item.
- **Fix:** have counsel finalize the commercial license text; remove the TEMPLATE/PLACEHOLDER disclaimers; confirm `CLA.md` and the README badge reference the final terms. *(Outward-facing — counsel, not code.)*
- **Verify:** `grep -c 'PLACEHOLDER\|TEMPLATE — NOT LEGAL ADVICE' LICENSE` → **0**.

---

## 🟡 SHOULD-FIX — privacy & cleanliness (mechanical, ~15 min)

### S2 — Stale WIP branches would become world-readable · Status: FIXED (pruned 2026-07-07)
- **Evidence:** `gh api repos/Thomas-Tai/ai-sw-bridge/branches` lists (besides `master` + `dependabot/*`): `docs/commercial-elevation`, `feat/w58-doc-trueup`, `feat/w68-curve-driven-pattern`, `feat/w68-fill-pattern`, `feat/w68-fillet-faceround` — **5 branches**. These are the "parallel-SHA worker branches" flagged during the W68 campaign (they hold content not on `master`).
- **Impact:** a public repo would expose unfinished WIP and duplicate/abandoned history. Cosmetically unprofessional and needlessly enlarges the audit surface.
- **Fix:** after merging `docs/commercial-elevation`, `git push origin --delete <branch>` for each `feat/*` and the working branch. Leave `dependabot/*` (auto-managed).
- **Verify:** `gh api repos/Thomas-Tai/ai-sw-bridge/branches --jq '.[].name' | grep -vE '^(master|dependabot/)' | grep -c .` → **0**.

### S3 — Personal email is on 1,374 commits (permanent once public) · Status: FIXED (future→noreply 2026-07-07; historical ACCEPTED, no rewrite)
- **Evidence:** `git log --all --format='%ae' | sort | uniq -c` → `thomastai.uni@gmail.com` on **1,374** commits; `git config user.email` → `thomastai.uni@gmail.com` (as-audited).
- **Impact:** the personal Gmail becomes permanently public and scrapeable in every commit. The *historical* addresses cannot be changed without another full history rewrite (which re-breaks every SHA — not worth it), but *future* commits can use a private address.
- **Fix:** `git config user.email "<id>+Thomas-Tai@users.noreply.github.com"` for future commits; consciously accept (or accept-the-cost-of-rewriting) the historical Gmail exposure.
- **Verify:** `git config user.email` ends with `users.noreply.github.com` (going-forward). Historical exposure is **ACCEPTED** or rewritten — owner's call.

### S4 — Internal snapshot tags clutter the public tag list · Status: FIXED (pruned 2026-07-07)
- **Evidence:** `gh api …/tags` includes non-release scaffolding tags: `v1.0-OOP-Baseline`, `pre-refactor-class-hierarchy-start`, `pre-push-2026-05-20`, `pre-class-refactor-2026-05-20`, `0.10.0` (missing the `v` prefix) — **5 tags**.
- **Impact:** low — purely cosmetic; a public tag list reading only real SemVer releases looks more finished. Optional.
- **Fix:** `git push origin --delete <tag>` (and delete the local tag) for each internal snapshot; keep every real `vX.Y.Z` release.
- **Verify:** `gh api …/tags --jq '.[].name' | grep -cE '^(pre-|v1.0-OOP|0\.10)'` → **0**.

---

## 🟢 Owner's-judgment calls (not blockers — decide, then mark ACCEPTED)

### J5 — Internal engineering/process docs would go public · Status: ACCEPTED (KEPT public, 2026-07-07)
- **Evidence:** `git ls-files 'docs/superpowers/**'` → **13** SDD plan/spec files; `_results/` → **11** spike/PAE dumps; internal audit docs `docs/E2E_FRESH_USER_AUDIT_2026-06-30.md`, `docs/operator_experience_audit_2026-07-04.md`, `docs/pending_gates.md` (and this file).
- **Impact:** two-sided. It *demonstrates rigor* (a credibility asset) but also exposes your internal roadmap, phase plans, and historical defect lists.
- **Decision (2026-07-07): KEEP public.** The SDD plans + audit docs demonstrate a rigorous, results-oriented engineering process — a credibility asset for enterprise evaluators, not a liability. It reinforces that the bridge is built to strict standards and drives real outcomes. Kept as deliberate engineering transparency.
- **Verify:** decision recorded (ACCEPTED — kept public).

### J6 — "Lego Sorter V2" personal-project anecdote · Status: ACCEPTED (KEPT, 2026-07-07)
- **Evidence:** `git grep -n 'Lego Sorter'` → `USAGE.md:26`, `docs/i18n/zh-CN/USAGE.md:29`, `docs/i18n/zh-TW/USAGE.md:30`, `examples/grooved_shaft/README.md:26`. Your own hobby project; no third-party/confidential data.
- **Impact:** reads as an authentic real-world validation story (positive). Purely a question of whether you want the personal project named in a commercial doc.
- **Decision (2026-07-07): KEEP.** The anecdote grounds the tool in a real physical system (a hardware sorter driving toward strict performance metrics), proving it drives real-world outcomes rather than abstract AI demos — exactly the grounded, results-oriented context enterprise evaluators value.
- **Verify:** decision recorded (ACCEPTED — kept).

### J7 — No SOLIDWORKS trademark / non-affiliation disclaimer · Status: FIXED (`2ea6f13`, 2026-07-07)
- **Evidence:** `grep -ic 'not affiliated\|not endorsed\|Dassault' README.md` → **0** (as-audited). "SOLIDWORKS" is a registered mark of Dassault Systèmes.
- **Impact:** driving SOLIDWORKS via COM is permitted, but a *commercial* product built around the trademark should carry a nominative-use / non-affiliation notice. Cheap insurance.
- **Fix:** add a one-line disclaimer to README (and optionally LICENSE): *"SOLIDWORKS is a registered trademark of Dassault Systèmes. This project is independent and not affiliated with or endorsed by Dassault Systèmes."*
- **Verify:** `grep -ic 'not affiliated' README.md` → **≥1**.

### J8 — Legacy MIT releases are permanent (informational) · Status: ACCEPTED (intrinsic)
- **Evidence:** README states `v1.0.0`–`v1.4.0` were MIT-licensed; those tags exist. Once public, anyone can fork those snapshots under MIT forever.
- **Impact:** the proprietary license only governs `v1.5.0+`; the earlier MIT grant is irrevocable for the code as published then. Already acknowledged in the README — no action, just awareness.
- **Verify:** n/a (informational).

---

## ✅ Already clean — do NOT "fix" these (verified 2026-07-07 @ `1f2ff25`)

- **Git history carries no binary blobs.** `git rev-list --all --objects | grep -iE '\.(dll|exe|so|dylib|pdb)$'` → **empty**. The W68 IP-scrub of `RouteCAddin.dll` held across all 1,381 commits (5.24 MiB packed). Going public leaks no proprietary binary.
- **No secrets in full history.** The scheduled full-history `gitleaks` scan (Security workflow) is **green**; the only hits are 10 documented SOLIDWORKS sketch-relation enum false positives (`sgHORIZONTAL2D` …), allowlisted in `.gitleaksignore`. No real credentials.
- **Local / AI-tool cruft is gitignored.** `.qoder/`, `.claude/`, `.grimp_cache/`, `.import_linter_cache/` are untracked (`git ls-files | grep -E '^\.(qoder|grimp_cache|import_linter_cache)/'` → empty). The one tracked local file, `.claude/settings.json`, is a two-line permissions allowlist — no secrets, no absolute paths.
- **Security policy exists.** `docs/SECURITY.md` routes vulnerabilities to GitHub private reporting, not public issues.
- **Third-party licensing is handled.** `THIRD-PARTY-NOTICES.md` + per-file port attribution for the MIT `SolidworksMCP-python` code; the `license_lint` CI gate is green.
- **CI fork-secret risk is low.** `ci.yml`/`security.yml`/`license_lint.yml` trigger on `pull_request`, but on a **public** repo fork PRs get a restricted, read-only `GITHUB_TOKEN` and no access to other repo secrets; `release.yml` (which uses the optional GPG secret) triggers only on tags/dispatch. Keep "require approval for first-time contributors" on.

---

## Recommended go-public sequence (ordered)

1. **Finalize the LICENSE** with counsel; align `CLA.md` + README badge. *(B1 — the blocker.)*
2. **Merge `docs/commercial-elevation` → `master`, then delete the stale `feat/*` branches** and (optionally) the internal `pre-*`/`0.10.0` tags. *(S2, S4)*
3. **Add the SOLIDWORKS non-affiliation disclaimer** to README. *(J7)*
4. **Decide** on `docs/superpowers/` + internal audit docs (keep vs. private) and the Lego-Sorter mention; mark J5/J6 ACCEPTED. 
5. **Switch your commit email** to a `noreply` address for future commits. *(S3)*
6. **Enable branch protection** on `master`; confirm fork-PR Actions require approval (default).
7. **Flip to public**, then immediately re-run the gitleaks scan on the public default branch to confirm nothing changed.

### Post-flip turnkey (run after the flip)

```bash
# ── AFTER the LICENSE is finalized (B1) and the repo is flipped to public ──
gh repo view --json isPrivate,visibility --jq '{isPrivate,visibility}'   # expect visibility=PUBLIC, isPrivate=false
grep -c 'PLACEHOLDER\|TEMPLATE — NOT LEGAL ADVICE' LICENSE               # B1 verify -> must be 0

# trigger a fresh pipeline (public repos = unmetered Actions, so it will actually run this time)
git commit --allow-empty -m "ci: post-flip green stamp" && git push origin HEAD:master

# 1) prove the quota wall is gone + CI green
gh run watch "$(gh run list --workflow ci.yml       --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
# 2) gitleaks re-attests clean over the now-world-readable full history
gh run watch "$(gh run list --workflow security.yml --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status

# 3) validate + merge the 5 deferred Dependabot PRs through their now-live CI.
#    Before merging black #5: apply its reformat AND reconcile the hard-coded
#    black==25.12.0 pin in ci.yml + release.yml, or black --check will fail.
gh pr list --state open
```

Then re-run [§ Verification Protocol](#-verification-protocol--runnable-cross-check) — with the license finalized, **B1 now reads 0** and every row hits its Expected value.

### Post-flip hardening (do the moment visibility flips — all free on public repos)

Platform-level safety nets that only become available *because* the repo is public. They enforce, at the GitHub level, the discipline this campaign held by hand.

- [ ] **Branch protection on `master`** — require the CI status check + ≥1 PR review; block direct pushes. (Was 403/unavailable while private on the Free plan.)
- [ ] **GitHub secret scanning + push protection** — enable (Settings → Code security). Belt-and-suspenders alongside gitleaks; push protection blocks a secret *before* it lands, not after.
- [ ] **Private vulnerability reporting** — enable (Settings → Security). This is what makes the existing `docs/SECURITY.md` reporting link actually functional.
- [ ] **Retire the direct-push workflow.** The campaign pushed `docs/commercial-elevation → master` via refspec — correct for a solo private repo, wrong for a public one with contributors. Switch to feature-branch → PR → CI-green → merge (branch protection will enforce it anyway).
- [ ] **Validate the merged Action bumps before the next real release.** A `workflow_dispatch` of `release.yml` exercises `upload-artifact@v7` + `checkout@v7` + the installer build for free (no tag, no publish). `action-gh-release@v3` runs only on a real tag → either watch the next `v*` release closely (revert-ready) or float+delete a throwaway `v1.7.2-rc1` prerelease to prove it first.

---

## Remediation log (fill in as steps land)

| ID | Severity | Status | Notes |
|----|----------|--------|-------|
| B1 | BLOCKER | OPEN | LICENSE is a placeholder — counsel must finalize before commercial public launch |
| S2 | should-fix | FIXED | pruned `feat/w58-doc-trueup`, `feat/w68-{curve-driven-pattern,fill-pattern,fillet-faceround}`, `docs/commercial-elevation` — remote now shows only `master` + `dependabot/*` |
| S3 | should-fix | FIXED | future commits → `40379214+Thomas-Tai@users.noreply.github.com` (repo-local); historical Gmail ACCEPTED — no rewrite (would break every release tag/SHA) |
| S4 | should-fix | FIXED | pruned `v1.0-OOP-Baseline`, `pre-*` (×3), `0.10.0` (remote + local) |
| J5 | judgment | ACCEPTED | KEPT public — engineering transparency (SDD plans + audit docs show rigor) |
| J6 | judgment | ACCEPTED | KEPT — real-world (hardware) validation credibility |
| J7 | judgment | FIXED | `2ea6f13` — SOLIDWORKS non-affiliation disclaimer added to README (+ zh mirrors) |
| J8 | info | ACCEPTED | legacy MIT releases are irrevocable — awareness only |

---

## ✅ Verification Protocol — runnable cross-check

Paste from the repo root; each line prints a label + result, compared to **Expected**. COM-free (`git`/`grep`/`gh` only) — safe with SOLIDWORKS open. As-audited values are HEAD `1f2ff25`.

```bash
# ── run from the repo root ──────────────────────────────────────────────
# B1  LICENSE placeholder markers gone
echo "B1 placeholder=$(grep -c 'PLACEHOLDER\|TEMPLATE — NOT LEGAL ADVICE' LICENSE)"        # want 0 (audited 3)
# S2  no stale non-master/non-dependabot branches
echo "S2 stale_branches=$(gh api repos/Thomas-Tai/ai-sw-bridge/branches --jq '.[].name' | grep -vE '^(master|dependabot/)' | grep -c .)"  # want 0 (audited 5)
# S3  future commit email is a noreply address
echo "S3 email=$(git config user.email)"                                                   # want *users.noreply.github.com
# S4  internal snapshot tags removed
echo "S4 internal_tags=$(gh api repos/Thomas-Tai/ai-sw-bridge/tags --jq '.[].name' | grep -cE '^(pre-|v1.0-OOP|0\.10)')"  # want 0 (audited 5)
# J7  SOLIDWORKS non-affiliation disclaimer present
echo "J7 disclaimer=$(grep -ic 'not affiliated' README.md)"                                # want >=1 (audited 0)
# ── invariants that MUST stay clean (regression tripwires) ──────────────
echo "INV binary_blobs=$(git rev-list --all --objects | grep -icE '\.(dll|exe|so|dylib|pdb)$')"    # want 0
echo "INV untracked_leak=$(git ls-files | grep -cE '^\.(qoder|grimp_cache|import_linter_cache)/')"  # want 0
gh run list --workflow security.yml --limit 1 --json conclusion --jq '"INV gitleaks=\(.[0].conclusion)"'  # want success
```

| ID | Proves | Expected | As-audited 2026-07-07 |
|----|--------|----------|-----------------------|
| B1 | LICENSE is finalized (no placeholder) | `0` | ❌ `3` (OPEN — blocker) |
| S2 | no stale public branches | `0` | ❌ `5` |
| S3 | future commits use noreply email | `…users.noreply.github.com` | ❌ `thomastai.uni@gmail.com` |
| S4 | internal snapshot tags removed | `0` | ❌ `5` |
| J7 | trademark disclaimer present | `≥1` | ❌ `0` |
| INV | no binary blobs in history | `0` | ✅ `0` |
| INV | no untracked-dir leak into tracking | `0` | ✅ `0` |
| INV | full-history gitleaks green | `success` | ✅ `success` |

**Interpretation:** the ❌ rows are the pre-flight work (one blocker + cleanup + a disclaimer). The ✅ INV rows are the hard-won clean state — they double as **regression tripwires**: if a binary blob, an untracked-dir leak, or a gitleaks failure ever appears, do **not** flip public until it's resolved. When all five ❌ rows read their Expected value and the three INV rows stay ✅, the repo is ready to go public.

---

## Remediation session note (2026-07-07)

- **Executed:** J5/J6 ACCEPTED (kept public); **J7 FIXED** (`2ea6f13` — trademark disclaimer in README + zh mirrors, mirrors re-anchored/fresh); **S2 + S4 FIXED** (5 stale branches + 5 internal tags pruned; remote now shows only `master` + `dependabot/*` and real `vX.Y.Z` tags). **Remaining OPEN by design:** B1 (counsel) and S3 (owner's future-email choice).
- **⚠️ Tripwire event — CI/Security went RED from `d8a95fe` onward; ROOT CAUSE = GitHub Actions quota exhaustion, NOT a security finding.** The go-public flow was paused to investigate (correct halt behavior). **Diagnosis (confirmed by the run pattern):** every workflow (CI, Security, License lint) ran for real and **passed through `1f2ff25` @ 04:48 UTC** (CI ~9 min, Security ~1 min); then from `d8a95fe` @ 05:02 UTC onward, **all jobs across all workflows fail in 2–9 seconds with no step logs** and empty annotations — the unmistakable signature of runs that **never start because the account's included private-repo Actions minutes/spending limit is used up**. Corroboration: a **CI-faithful `pip-audit`** (fresh venv, `pip install -e .` → pillow 12.3.0 / numpy 2.5.1 / oletools 0.60.2 / jsonschema 4.26.0 / pywin32 312 / sqlite-vec 0.1.9) returned **"No known vulnerabilities found"**; the last *real* gitleaks scan (`1f2ff25`) was green; logs are `BlobNotFound` because no steps executed. **The code, dependencies, and history are clean — gitleaks isn't finding a leak and pip-audit isn't finding a CVE; the jobs can't even boot.**
- **Owner action (off-keyboard):** GitHub → **Settings → Billing & plans → raise the Actions spending limit / add a payment method**, or wait for the monthly minutes reset. **Note:** public repos get **unlimited free** Actions, so flipping public (after B1) *also* clears this outage. **Gate caveat:** the go-public security gate cannot be re-confirmed green until Actions can run at all — so "all workflows green" must be re-checked once billing is restored, before flipping public.
- **Dependabot PRs — RESOLVED 2026-07-07** (owner reversed the earlier defer). **4 Action bumps MERGED** (squash + branch-deleted), `master` `30aed82`→`233f988`: #4 checkout 5→7, #3 gitleaks-action 2→3, #2 action-gh-release 2→3, #11 upload-artifact 4→7. **black #5 CLOSED** — staying on `black==25.12.0` (adopting 26.5.1 was measured at a **99-file reformat** + 7 pin edits, for no functional gain). **Remote branch list is now `master` only.**
- **⚠️ The 4 merged Action bumps are UNVALIDATED (Actions quota) and are all MAJOR versions — confirm on the post-flip run.** Precise coverage: `actions/checkout@v7` (#4, all workflows) and `gitleaks/gitleaks-action@v3` (#3, security.yml) are exercised by a normal **CI/Security** run → validated by the post-flip push. **`softprops/action-gh-release@v3` (#2) and `actions/upload-artifact@v7` (#11) live only in `release.yml`, which runs on a TAG push (or `workflow_dispatch`)** → they are **NOT** validated by a normal CI run; they must be confirmed on the **next release/tag** (or a manual `workflow_dispatch` of the installer job). If any bump breaks its workflow, revert that single bump.
