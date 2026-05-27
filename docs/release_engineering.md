# Release Engineering

How releases work for `ai-sw-bridge`. Operational document — referenced from [`requirements.md`](central_idea/requirements.md), the [`ROADMAP.md`](ROADMAP.md), and [`launch_readiness_checklist.md`](launch_readiness_checklist.md).

**Last updated:** 2026-05-23
**Authority:** project lead. Operational handoff documented per-release in [`central_idea/decisions.md`](central_idea/decisions.md).

---

## 1. Versioning policy

Semantic versioning per [`semver.org`](https://semver.org), with bridge-specific interpretation.

### 1.1 MAJOR.MINOR.PATCH

- **MAJOR** — increment for breaking changes to the spec schema, the stdout JSON envelope shape, or the CLI surface contract. Requires a `schema_version` bump if the JSON schema changes. Examples that would qualify: removing a feature primitive, renaming a CLI subcommand without an alias, changing the meaning of an exit code.
- **MINOR** — increment for additive features. New feature primitives, new CLI subcommands, new manifest blocks, new flags. Backward-compat preserved. v0.11.0 is a MINOR bump over v0.10.
- **PATCH** — increment for bug fixes only. No new features, no schema additions, no behavioral changes beyond the fix. Multiple PATCH releases per MINOR are expected.

### 1.2 Pre-release tags

Pre-MAJOR/MINOR releases use the standard SemVer pre-release suffix:

- `<X.Y.Z>a1`, `a2`, ... — **Alpha.** Internal release. Used to dogfood new lanes before opening to external users. Schema may shift between alphas.
- `<X.Y.Z>b1`, `b2`, ... — **Beta.** Invited external users. Schema additions are stable from b1 onward; bug fixes only between betas. Schema-breaking changes between b1 and GA are forbidden (would need to ship as a new MINOR).
- `<X.Y.Z>rc1`, `rc2`, ... — **Release candidate.** Only bug fixes. CHANGELOG locks; migration guide locks. Each rc is a 1-week soak.
- `<X.Y.Z>` — **GA.** Released to the public.

### 1.3 What never causes a version bump

- Documentation-only changes.
- Test-only changes.
- Internal refactors that preserve the public API surface.
- New `Experimental`-tier surfaces (per `requirements.md` §4.8.1) — they can change without MAJOR bump until promoted to Stable.

### 1.4 Pre-1.0 caveat

The bridge is pre-1.0 (v0.X today). SemVer's pre-1.0 latitude means MINOR releases MAY introduce breaking changes if necessary, with a documented migration. We minimize this — v0.11 is fully backward-compatible with v0.10 — but reserve the right.

---

## 2. Compatibility contract

### 2.1 Schema compatibility

- The spec schema is versioned via `schema_version` (currently `1`).
- A v0.11 GA must build every v0.10-era example spec unchanged. CI gates on this — `tests/compat/test_v010_examples.py` runs each shipped example spec under the v0.11 codebase and asserts the build manifest matches a v0.10 golden snapshot.
- Schema additions are additive: new fields, new feature types, new manifest blocks. Never reordered. Never removed without a `schema_version` bump.

### 2.2 CLI compatibility

- v0.11 preserves the v0.10 CLI surface verbatim. `ai-sw-build spec.json` (no new flags) behaves identically.
- New flags are opt-in. Default behavior with no new flags is v0.10 behavior.
- Exit codes are stable per [`UIUX.md`](central_idea/UIUX.md) §3.2.

### 2.3 Output compatibility

- The stdout JSON envelope shape is Stable per `requirements.md` §4.8.1. Field additions OK; reordering OK (JSON is unordered); renames or removals require MAJOR.
- The `build_metrics.json` sidecar shape is Stable.
- The `brep`, `errors`, `checkpoints` blocks are additive — consumers that don't know about them ignore them safely.

### 2.4 Module / API stability

- Public modules (`spec/`, `cli/`, `sw_com.py`) are Stable.
- New modules (`brep/`, `errors/`, `rag/`, `checkpoint/`) start as Experimental and promote per the §4.8.1 criteria.
- Underscore-prefixed modules and the `telemetry/` wire format are Internal — no stability promise.

---

## 3. Migration guides

Every MINOR release ships a migration guide at `docs/migration_to_v<MAJOR>.<MINOR>.md`. The guide covers:

- **What's new** — additive features and their opt-in surface.
- **What's deprecated** — flags or behaviors that will be removed in a future release. Each deprecation references [`docs/deprecation_policy.md`](deprecation_policy.md).
- **What's removed** — never happens at MINOR; included for completeness.
- **Schema changes** — none at MINOR by definition; this section documents additive fields when they exist.
- **Behavioural changes that aren't schema changes** — e.g., a bug fix that changes output text. Even non-breaking, list them.
- **Recommended adoption order** — when shipping a feature requires a sequence (e.g., enable feature flag → run smoke test → enable in production).

**Template:** `docs/migration_to_<version>_template.md` (planned, ships with v0.11). The first migration guide (`docs/migration_to_v0.11.md`) doubles as the template.

---

## 4. Deprecation policy

Existing policy at [`deprecation_policy.md`](deprecation_policy.md). This document references and extends it; it does not replace it.

**Summary of the policy (for context):**

- Deprecation warning at MINOR N.
- Removal at MINOR N+2 minimum (i.e., users have at least two MINOR cycles of warning before a surface goes away).
- MAJOR bump on removal of a Stable-tier surface.
- Internal-tier surfaces can change at any time without warning.
- Experimental-tier surfaces emit a `[deprecated]` warning at change/removal but don't require the N+2 cycle.

**Extension:** v0.11 begins citing the policy from per-CLI `--help` output. Each command whose surface has a deprecation candidate lists it in `--help` under "Compatibility notes" with the planned removal version.

---

## 5. Release cadence

Target cadence:

- **MAJOR:** ≤ 1 per year. Major architectural shifts (e.g., L5 in-process pivot when it opens).
- **MINOR:** ~3 months. Capability lanes ship as MINOR releases.
- **PATCH:** ad-hoc, ideally ≤ 2 weeks turnaround on a reported bug.

These are targets, not commitments. Slipping is allowed with notice on the relevant GitHub release issue.

---

## 6. Release process — concrete steps

The release engineer runs these in order. Total expected time: ~3 hours for a MINOR with a good pre-release cycle; ~30 minutes for a PATCH.

### 6.1 Pre-release checklist

1. All [`launch_readiness_checklist.md`](launch_readiness_checklist.md) items checked (MINOR only; PATCH is a subset).
2. CHANGELOG updated with all changes since the last release.
3. Migration guide drafted (MINOR only).
4. Pre-commit hooks pass on `master`.
5. Full CI matrix green on `master` (py 3.10 / 3.12 / 3.14).
6. SLO measurements collected and within bounds for the release candidate.
7. CONTRIBUTING.md "Third-party derivations" table up to date.
8. README Acknowledgments line consolidated for any new upstream repo.

### 6.2 Tagging

1. `git checkout master`
2. `git pull --rebase` (ensure local matches origin)
3. `git tag -a v<X.Y.Z> -m "Release v<X.Y.Z>"`
4. Tag annotation includes: release date, headline features, top 3-5 changes.
5. `git push origin v<X.Y.Z>` (only this tag — don't bulk-push)

### 6.3 Artifact build

1. `python -m build` — produces `dist/ai_sw_bridge-<X.Y.Z>.tar.gz` and `dist/ai_sw_bridge-<X.Y.Z>-py3-none-any.whl`.
2. Compute SHA-256 checksums: `python tools/release_checksums.py dist/ > dist/SHA256SUMS`.
3. Sign checksums (when GPG signing is enabled): `gpg --detach-sign --armor dist/SHA256SUMS`.

### 6.4 GitHub release

1. Open the GitHub Releases page; create a new release from the tag.
2. Title: `v<X.Y.Z> — <one-line headline>`.
3. Body: copy from CHANGELOG entry; add links to migration guide if MINOR.
4. Upload artifacts: sdist, wheel, `SHA256SUMS`, `SHA256SUMS.asc` (if signed).
5. Mark pre-releases as "pre-release"; mark GA as the latest.

### 6.5 Post-release

1. Post a brief summary to relevant channels (project Discord/Slack/mailing list if/when they exist).
2. Update [`docs/central_idea/README.md`](central_idea/README.md) status table.
3. Update [`docs/central_idea/decisions.md`](central_idea/decisions.md) with any release-driven decisions (e.g., features promoted from Experimental to Stable).
4. Open a tracking issue for the next release's planning.
5. If any incidents surfaced during release: write a postmortem note in `docs/postmortems/<date>.md`.

### 6.6 Hotfix process (for critical bugs in a released version)

1. Branch from the tag: `git checkout -b hotfix/v<X.Y.Z+1> v<X.Y.Z>`.
2. Apply the minimal fix. NEVER bundle other changes.
3. Run full CI on the branch.
4. Tag and release as PATCH following §6.2-§6.5.
5. Backport the fix to `master` after release.

---

## 7. PyPI publication

The bridge is currently distributed via GitHub releases only. PyPI publication is deferred until:

- v0.11 GA ships with sufficient external usage to justify the maintenance commitment.
- A second maintainer is identified to share PyPI account control (avoid bus-factor 1).
- The trademark / package name registration is reviewed.

When publication opens, the process extends §6 with:

- `twine check dist/*` — verify metadata.
- `twine upload dist/*` — publish.
- Verify install: `pip install --upgrade ai-sw-bridge` in a clean venv; run the README quickstart.

---

## 8. Rollback / yank policy

If a released version is found to be broken (regressions, security issues):

- **Within 24 hours of release with no significant downloads:** delete the GitHub release. Document the deletion in a brief postmortem.
- **After significant download or > 24 hours:** do NOT delete. Tag a PATCH (§6.6) that fixes the issue + adds a clear CHANGELOG entry naming the affected version + (when on PyPI) yank the broken version with `pip` install instructions for the fix.
- **Security issues:** see [`supply_chain_security.md`](supply_chain_security.md) §"CVE response."

---

## 9. CI/CD pipeline

The bridge's CI workflow (`.github/workflows/`) gates every PR. Pipelines:

| Workflow | Trigger | Purpose | Gate level |
|---|---|---|---|
| `tests.yml` | Every push, every PR | Run py3.10/3.12/3.14 test matrix | Required |
| `lint.yml` | Every push, every PR | black, flake8, mypy, spec-lint, doc-coverage | Required |
| `slo-check.yml` (planned, v0.11) | PRs touching `src/` or `tools/regression_check.py` | SLI baseline comparison | Required |
| `license-lint.yml` (planned, v0.11) | PRs touching `src/` or `CONTRIBUTING.md` | License attribution audit | Required |
| `upstream-drift.yml` (planned, v0.12) | Scheduled (weekly) | Report upstream commits beyond pinned hashes | Informational |

Workflows marked "planned" land with the release that adds the relevant capability per [`ROADMAP.md`](ROADMAP.md).

---

## 10. Out-of-band release engineering scenarios

### 10.1 Emergency patch for a deployed user

User reports a critical bug; we don't yet have a public release cadence formalized. Process:

1. Confirm the issue is real and the fix is minimal.
2. Ship a PATCH via §6.6.
3. Direct the affected user to the new tag.

### 10.2 Security incident affecting upstream

A CVE lands on an upstream repo we ported from. Process documented in [`supply_chain_security.md`](supply_chain_security.md). Triggers a PATCH if the CVE affects ported code; no release if it doesn't.

### 10.3 SW version-skew incident

A SW service pack release breaks the bridge. Process:

1. Reproduce on the new SW version.
2. File a GitHub issue with `sw-version-skew` label.
3. If a fix is feasible, ship a PATCH per §6.6.
4. Update `requirements.md` §4.1 SW version-floor documentation.
5. If a fix is NOT feasible immediately, document a workaround in `docs/known_limitations.md`.

### 10.4 Major version bump (MAJOR release)

Beyond the scope of v0.X. Process recorded for completeness:

1. Decision logged in [`central_idea/decisions.md`](central_idea/decisions.md) with full rationale.
2. Multi-release deprecation cycle for any Stable-tier surface that changes.
3. Migration guide doubles in length and detail.
4. Pre-release cycle minimum: 3 alphas + 2 betas + 2 release candidates.
5. Public notice ≥ 60 days before GA.

---

## 11. Performance baseline generation

The SLI instrumentation in `tools/regression_check.py` (v0.11+) captures per-spec wall-clock times and emits p50/p95/p99 percentiles. Baseline files under `tools/perf_baselines/` anchor regression detection.

### 11.1 Generating a baseline

On a clean Windows machine with SOLIDWORKS running:

```powershell
python tools/regression_check.py --capture --write-baseline tools/perf_baselines/v0.10.json
```

This builds every example spec in `--no-dim --verify-mass` mode, records golden volumes, captures timings, and writes the baseline JSON.

### 11.2 Comparing against a baseline

```powershell
python tools/regression_check.py --check --baseline-compare tools/perf_baselines/v0.10.json
```

Fails (exit 1) when p95 regresses by >15% or p99 by >25% vs the baseline, or when SLO-01 (p95 < 12 s) or SLO-02 (p99 < 25 s) is breached.

### 11.3 Updating a baseline

Baselines are updated only when a deliberate performance improvement lands or when the hardware baseline changes. CI gates the update: the PR must carry the `perf-baseline-bump` label (per spec.md §8.3).

---

## 12. Automated release pipeline (CI)

The `.github/workflows/release.yml` workflow runs when a `v*.*.*` tag is pushed. It:

1. Builds sdist + wheel via `python -m build`
2. Computes SHA-256 checksums into `checksums.txt`
3. Signs `checksums.txt` with the project GPG key
4. Creates a GitHub Release with all artifacts + generated release notes
5. Marks pre-release if the tag contains `a`, `b`, or `rc`

**Required GitHub secrets:**

- `GPG_SIGNING_KEY` — ASCII-armored private key export
- `GPG_PASSPHRASE` — key passphrase

### 12.1 Cutting a release via CI

```bash
# 1. Bump version in pyproject.toml
# 2. Update CHANGELOG.md
# 3. Commit and tag
git commit -am "v0.11.0"
git tag v0.11.0
git push origin master v0.11.0
```

The CI workflow handles build, signing, and GitHub Release creation. This is the preferred path; the manual procedure in §6 is the fallback.

---

## 13. Manual fallback (CI unavailable)

If GitHub Actions is unavailable (outage, runner quota, network issue), the release engineer can cut the release locally:

```bash
# 1. Build
python -m build

# 2. Checksum
sha256sum dist/*.tar.gz dist/*.whl > checksums.txt

# 3. Sign
gpg --default-key ai-sw-bridge-release --detach-sign --armor checksums.txt

# 4. Create release via gh CLI
gh release create v0.11.0 \
  dist/*.tar.gz dist/*.whl \
  checksums.txt checksums.txt.asc \
  --title "v0.11.0" \
  --notes-file /tmp/release_notes.txt

# 5. Verify
gpg --verify checksums.txt.asc
```

If GPG is unavailable, unsigned checksums may be published with a note in the release body: *"Checksums are unsigned due to [reason]. Verify against the CI run log for commit <sha>."*

---

## 14. GPG key management

### 14.1 Key details

- **Key type:** RSA 4096 or Ed25519
- **User ID:** `ai-sw-bridge-release <maintainer@example.com>`
- **Storage:** GPG secret key stored in GitHub Secrets (`GPG_SIGNING_KEY`). The corresponding public key is committed to the repo at `release-key.asc` for user verification.

### 14.2 Key rotation policy

- Rotate if the private key is suspected compromised.
- Rotate every 2 years as a hygiene measure.
- Rotation procedure:
  1. Generate a new key pair.
  2. Update `GPG_SIGNING_KEY` and `GPG_PASSPHRASE` in GitHub Secrets.
  3. Commit the new public key to `release-key.asc`.
  4. Sign the next release with the new key.
  5. Document the rotation in this file's changelog below.
- Old public keys remain in the repo (renamed to `release-key-<year>.asc`) so historical releases can still be verified.

### 14.3 Verification (user-facing)

Users verify a release with:

```bash
# Import the project's public key (one-time)
gpg --import release-key.asc

# Verify
gpg --verify checksums.txt.asc
sha256sum -c checksums.txt
```

### 14.4 Initial key setup

Before the first signed release, a maintainer must:

1. Generate a signing-only subkey under an existing or new key:
   ```bash
   gpg --quick-add-key <fingerprint> rsa4096 sign 2y
   ```
2. Export the ASCII-armored private key (subkey only):
   ```bash
   gpg --export-secret-subkeys --armor <subkey-id> > /tmp/signing-subkey.asc
   ```
3. Store the export in the `GPG_SIGNING_KEY` GitHub secret.
4. Store the passphrase in `GPG_PASSPHRASE`.
5. Export and commit the public key:
   ```bash
   gpg --export --armor <subkey-id> > release-key.asc
   git add release-key.asc && git commit -m "chore: add release signing public key"
   ```

Until this setup is complete, releases carry unsigned checksums with a note in the release body (see §13).

---

## 15. First release dry-run

Before trusting the automated pipeline on a real tag, run a dry-run:

```bash
# Build locally
python -m build
ls dist/

# Verify the wheel is importable
pip install dist/*.whl
python -c "import ai_sw_bridge; print(ai_sw_bridge.__version__)"

# Test the checksum flow
cd dist && sha256sum *.tar.gz *.whl > ../checksums.txt && cd ..
cat checksums.txt
```

If the local build succeeds, push a pre-release tag (e.g. `v0.10.1a1`) to test the CI pipeline end-to-end without affecting real users. Verify the GitHub Release appears with all four artifacts. Delete the pre-release and its tag once verified.
