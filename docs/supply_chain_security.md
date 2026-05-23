# Supply Chain Security

Controls on upstream port hygiene, CVE response, and license audit. Operational document for maintainers and security reviewers.

**Last updated:** 2026-05-23
**Companion:** [`requirements.md`](central_idea/requirements.md) §4.10 (summary) + [`harvest_plan.md`](central_idea/harvest_plan.md) §1, §7, §8, §9 (license matrix + upstream relationships + community contributions + license audit automation).

---

## 1. Threat model

The bridge ports code from MIT-licensed upstream repositories. Each port introduces:

- **CVE risk** — a vulnerability in the upstream might affect our port.
- **Compromised commit risk** — a malicious upstream commit (push-force or hijacked maintainer) could land in our codebase via re-port.
- **License drift risk** — upstream re-licenses to a copyleft license; our port becomes incompatible.
- **Maintenance abandonment risk** — upstream goes unmaintained; bugs we depended on the upstream to fix don't get fixed.

The bridge's controls are **process** more than tooling at v0.11 GA. Automated CVE feed integration is a v0.12+ target.

---

## 2. Pinned-commit policy

### 2.1 Per-port commit hash pinning

Every ported file's docstring records the upstream commit hash at port time:

```python
"""ai_sw_bridge.errors.circuit_breaker

Ported from SolidworksMCP-python (MIT, ESPO Corporation 2025).
Upstream: https://github.com/<owner>/SolidworksMCP-python
Commit: <full-40-char-sha>
Ported: 2026-XX-XX
Adaptation: <one-line description of bridge-specific tweaks>
"""
```

The commit hash is the load-bearing pin. Without it, "ported from X" doesn't pin to a specific point in history.

### 2.2 `CONTRIBUTING.md` "Third-party derivations" parity

The same metadata appears in `CONTRIBUTING.md`:

```
| Target file | Upstream repo | License | Upstream commit | Ported | DRI | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| src/ai_sw_bridge/errors/circuit_breaker.py | SolidworksMCP-python | MIT | <commit-sha> | 2026-XX-XX | TBD | <notes> |
```

CI gate (per [`harvest_plan.md`](central_idea/harvest_plan.md) §9): `tools/license_lint.py` (planned, v0.11) verifies that every file with a port docstring has a matching CONTRIBUTING row, and vice versa.

---

## 3. Upstream drift monitoring

### 3.1 The drift signal

For each upstream, "drift" is `count of commits between (our pin) and (upstream HEAD)`. The signal triggers review at thresholds:

| Drift threshold | Action |
|---|---|
| **0-20 commits** | No action; pin remains valid. |
| **20-50 commits** | Informational; the next quarterly review notes the drift. |
| **50+ commits** | Review trigger. Apply the §3.2 re-port decision matrix. |
| **Any security commit** | Immediate review regardless of drift count. |

### 3.2 Re-port decision matrix

(Mirrors [`harvest_plan.md`](central_idea/harvest_plan.md) §7.2 — repeated here for the security context.)

| Upstream change | Action |
|---|---|
| Security fix touching our ported lines | Re-port within 7 days. Cherry-pick or pull HEAD. Update commit hash. |
| Behavioral bug fix in our ported lines | Re-port within next MINOR cycle. |
| Refactor that doesn't change behavior | No action; opportunistic re-port. |
| New upstream feature we don't use | No action. |
| License change to copyleft | Initiate port rollback per [`harvest_plan.md`](central_idea/harvest_plan.md) §5.7. |
| Upstream archived / unmaintained | Decision recorded in [`central_idea/decisions.md`](central_idea/decisions.md); options: continue with pinned version forever; fork; or rewrite. |

### 3.3 Tooling (shipped, v0.11)

`tools/check_upstream_drift.py`:

- Reads pinned commits from `CONTRIBUTING.md` "Third-party derivations" table and/or `harvest_plan.md` §5 recipes.
- For each upstream + commit pin, queries the GitHub compare API (`/repos/{owner}/{repo}/compare/{sha}...HEAD`).
- Emits a table (or JSON with `--format json`) of `(repo, pinned_sha, commits_since_pin, last_commit_date, latest_sha)`.
- Flags (exit 1) when any repo exceeds the configurable threshold (default 50; override with `--threshold N`).
- CI workflow (`.github/workflows/upstream_drift.yml`) runs weekly on Monday 06:00 UTC; also triggerable via `workflow_dispatch`.

### 3.4 Drift response

When the drift check flags an upstream:

1. **Triage** — classify the drift per the §3.2 re-port decision matrix.
2. **Security commits** — if any commit since the pin is a security fix touching our ported lines, re-port within 7 days (per §3.2).
3. **Behavioral changes** — if the upstream fixed bugs or changed behavior our port depends on, file a re-port issue for the next MINOR release.
4. **Cosmetic drift** (renames, docs, dependency bumps) — no action; note the review date in the next quarterly audit.
5. **License change** — if the upstream relicensed to copyleft, initiate port rollback per `harvest_plan.md` §5.7.
6. **Record** — log the review in `docs/supply_chain_audit.md` (§4.2) with the drift count and triage outcome.

For testing and CI tuning, lower the threshold: `python tools/check_upstream_drift.py --threshold 0` simulates the flag on any drift.

---

## 4. CVE feed monitoring

### 4.1 The process (v0.11 — manual)

For each upstream MIT repo:

1. Subscribe to GitHub Security Advisories on the upstream's repo.
2. When an advisory lands, evaluate:
   - Does the CVE touch lines we ported? `git diff <upstream-commit-pin> <advisory-fix-commit> -- <relevant-files>`.
   - Severity (CVSS score)?
   - Affected versions — does our pin fall in the affected range?
3. If our port is affected: open a private security issue; follow §3.2 with the security-fix path.
4. If our port is not affected: document the evaluation in `docs/supply_chain_audit.md` (new — created on first CVE evaluation); close the loop.

### 4.2 `docs/supply_chain_audit.md` format

```
## CVE Log

| Date | CVE / Advisory | Upstream | Affected? | Action taken | Resolved |
|---|---|---|---|---|---|
| 2026-XX-XX | CVE-2026-XXXXX | SolidworksMCP-python | No (the CVE is in vba_adapter.py; we ported circuit_breaker.py only) | Logged; no action needed | 2026-XX-XX |
```

Append-only. Entries reference the specific files ported and the upstream commit pin at the time of evaluation.

### 4.3 Tooling (v0.13+, optional)

Automated CVE feed monitoring is a v0.13+ target. Implementation depends on a maintainer pool large enough to staff the on-call rotation — without that, automation paging no one is worse than manual quarterly review.

---

## 5. License compliance

### 5.1 Per-port license verification

Every port docstring states the upstream LICENSE (file name + copyright holder + year). The `harvest_plan.md` §1 matrix is the source of truth for license classification.

CI gate (`tools/license_lint.py`, v0.11):

- Scan every file in `src/` whose docstring matches the port pattern.
- Cross-reference upstream + license against `harvest_plan.md` §1 classification.
- Reject if classification disagrees, or if the file claims to port from a GPL or no-LICENSE repo (those are study-only per harvest plan).

### 5.2 Top-level license consistency

The bridge ships under MIT (`LICENSE` at repo root + `pyproject.toml` declaration). Any port from a non-MIT upstream is disallowed unless the upstream license is MIT-compatible (currently: only MIT-licensed upstreams are ported).

### 5.3 Vendored dependencies (none today)

If the bridge ever vendors a dependency (copies its source into `vendored/` rather than installing it from PyPI), the vendoring follows the same three-surface attribution as a port:

- Per-file docstring with upstream + commit hash + license.
- CONTRIBUTING.md row.
- README Acknowledgments line if it's a new upstream.

Per-file license-lint applies to vendored code identically.

---

## 6. Compromised-commit defenses

### 6.1 What we can prevent

- **Silent re-port from an unverified upstream HEAD.** Every port is a deliberate, reviewed PR. There is no auto-pull-from-upstream pipeline. A compromised upstream commit cannot reach our codebase without reviewer attention.
- **Drift past the pinned commit without review.** The drift monitor (§3.3) flags 50+ commits; until reviewed, the pinned commit remains in effect.

### 6.2 What we cannot prevent

- **A malicious commit that was the upstream HEAD at the time we originally ported.** Mitigation: review every port PR with security-mindedness; commit hashes are recorded so a post-hoc audit can identify what was ported when.
- **An upstream maintainer compromise that we didn't notice.** Mitigation: drift review + CVE feed subscription provide eventual detection.

### 6.3 Signed-commit policy (post-v0.11)

When the project pool is large enough to sustain it:

- All maintainer commits MUST be GPG-signed.
- Release tags MUST be signed.
- `git log --show-signature` is part of the release verification step.

Until that pool exists, this is documented intent, not enforced practice.

---

## 7. Dependency security (PyPI packages)

The bridge has runtime dependencies declared in `pyproject.toml`:

- `pywin32 >= 305`
- `Pillow >= 10.0`
- `oletools >= 0.60`
- `jsonschema >= 4.0`

### 7.1 Monitoring

- **GitHub Dependabot** (when enabled): auto-PRs on CVE in declared dependencies.
- **`pip-audit`** (planned, v0.11 CI step): runs against the installed environment; fails CI on known CVEs.

### 7.2 Pinning policy

- Minimum versions in `pyproject.toml` reflect the actual API surface used (e.g., `pywin32 >= 305` is the floor we tested against).
- We do NOT pin maximum versions; users are free to upgrade dependencies past our tested minimum.
- For dev / CI determinism (`black == 25.12.0`), we pin exactly to keep formatting consistent across Python versions.

### 7.3 New-dependency review

Adding a new runtime dependency requires:

1. Justification in the PR description (why this dep, what we considered).
2. License audit (must be MIT or compatible).
3. Maintenance signal check (recent commits, responsive issues).
4. Decision recorded in [`central_idea/decisions.md`](central_idea/decisions.md).

The default is "don't add a dependency." Stdlib-first; selective adoption only when the stdlib path is genuinely worse.

---

## 8. Incident response

### 8.1 If we discover a vulnerability in our own code

1. File a private security advisory via GitHub's security tab (when project enables this) or contact maintainers directly.
2. Assess severity + affected versions.
3. Develop a fix on a private branch.
4. Coordinate disclosure timeline with the reporter.
5. Release a PATCH per [`release_engineering.md`](release_engineering.md) §10.2.
6. Public disclosure includes:
   - CVE allocation (when applicable).
   - Affected versions.
   - Recommended action (upgrade to which PATCH).
   - Workaround if upgrade isn't feasible.
7. Postmortem in `docs/postmortems/<date>-security.md`.

### 8.2 If we discover a vulnerability in a ported upstream

1. Verify our port is affected (the upstream might fix lines we didn't port).
2. If affected: §3.2 security-fix path + §8.1 PATCH process.
3. If not affected: log in `docs/supply_chain_audit.md` (§4.2) and move on.
4. Notify the upstream maintainer if our investigation surfaces something they don't yet know.

### 8.3 If we discover a malicious commit in an upstream

1. Pause any planned re-ports from that upstream.
2. Audit our current ports against the malicious commit window — did anything we ported land during the compromised period?
3. If yes: revert + re-port from a verified clean commit.
4. Notify the upstream maintainer and other downstream consumers (responsible disclosure).
5. Decision recorded in [`central_idea/decisions.md`](central_idea/decisions.md).

---

## 9. Audit history

This file maintains a brief audit history:

| Date | Activity | Outcome |
|---|---|---|
| 2026-05-23 | Initial supply-chain security review created | Process documented; tooling deferred to v0.11 / v0.12. |

Future audits append rows here. Material changes documented in [`central_idea/decisions.md`](central_idea/decisions.md).

---

## 10. Out of scope

This document does NOT cover:

- **User data privacy.** See [`central_idea/privacy_review.md`](central_idea/privacy_review.md).
- **Cryptographic operations.** The bridge does not implement crypto; it consumes hashing (SHA-256 for fingerprints) via stdlib. Any cryptographic vulnerabilities are inherited from Python's `hashlib` and out of bridge scope.
- **Authentication / authorization.** The bridge runs as the user; there is no multi-user authentication model.
- **Code signing of releases.** Documented separately in [`release_engineering.md`](release_engineering.md) §6.3.
