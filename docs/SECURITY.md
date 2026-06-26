# Security

Privacy posture and supply-chain security for ai-sw-bridge.

---

# Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report a suspected vulnerability privately via GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
(the **Report a vulnerability** button under the repository's **Security** tab),
or by email to **<SECURITY-CONTACT>**.

Please include:

- a description of the issue and its impact,
- the affected version (`ai-sw-bridge --version` / the git SHA),
- reproduction steps or a proof of concept, and
- any known mitigations.

**Response targets:** acknowledgement within 3 business days; an initial
assessment within 10 business days. We will coordinate a disclosure timeline
with you and credit you in the advisory unless you prefer to remain anonymous.

**Supported versions:** security fixes target the latest released minor version.
Older versions may receive fixes at the maintainers' discretion.

---

# Privacy review


Data inventory, sensitivity classification, egress paths, and consent
gates for `ai-sw-bridge`. This document is the public-facing
counterpart of the bridge's privacy posture — anything an
adopter / security reviewer / DPO needs to understand what the bridge
collects, where it stores it, and what (if anything) leaves the
machine.

**North-star principle:** *local-only by default; egress is opt-in,
explicit, and per-artifact-redacted.*

Last reviewed: 2026-05-28 (v0.13.0 release prep).

---

## 1. Data inventory

Everything the bridge can read, write, or store, classified by
sensitivity tier.

| Artifact | Where it lives | Tier | Egress path |
|---|---|---|---|
| **JSON spec** (e.g. `examples/<part>/spec.json`) | User-controlled directory | **PUBLIC** — declarative geometry definition, no user identity | None (user-owned) |
| **`*_locals.txt`** (parameter values for parametric specs) | Adjacent to spec | **SENSITIVE** — may encode internal part-number prefixes, project codenames, customer-confidential dimensions | Scrubbed by `tools/spec_redact.py` before sharing |
| **Built `.SLDPRT`** files | User's SW workspace | **SENSITIVE** — full 3D geometry, may be IP | None (SW owns the file; bridge writes via SW's SaveAs3) |
| **Checkpoint DB** (`.checkpoints/<part>.sqlite`) | Repo root by default; configurable via `--checkpoint-root` | **SENSITIVE** — `locals_snapshot` + `com_call_log` columns contain the parameter values + the COM call sequence. Encrypted at rest when `--checkpoint-encrypt <key-source>` is set (Fernet, see `docs/checkpoint_encryption_design.md`) | Scrubbed by `tools/checkpoint_redact.py` before sharing |
| **Telemetry SQLite** (`.telemetry/metrics.db`) | Repo root | **AGGREGATE-ONLY** — counters + histogram buckets + trace IDs. **No PII, no spec values, no file paths.** | Never auto-uploaded. Manual export via `tools/export_metrics.py` requires `.telemetry/consent.txt` to exist |
| **Bug-report bundles** (`bug_report_<ts>.zip` from `tools/bundle_bug_report.py`) | User's repo root | **SCRUBBED-SENSITIVE** — collects spec + error envelopes + telemetry; runs the redaction pipeline before zipping | Manual upload by user to wherever they file the report |
| **Build manifest sidecars** (`build_metrics.json`, `build_brep.json`) | Adjacent to built `.SLDPRT` | **SENSITIVE** — feature names + durations + B-rep fingerprints; same sensitivity as the part itself | None (user-owned) |
| **Spec validation errors** (stdout from `ai-sw-build` / MCP tool returns) | Caller's process | **SENSITIVE-IN-CONTEXT** — error messages may quote `*_locals.txt` values | Caller decides what to do with stdout |
| **Environment-derived state** (path to active SW doc, RevisionNumber, etc.) | Active SW process | **SENSITIVE** — file path reveals project structure | Observed by `sw_get_active_doc` etc.; user is the caller, never auto-collected |

## 2. Sensitivity tiers

- **PUBLIC** — fine to share verbatim. Spec JSON definitions of
  geometry primitives.
- **SENSITIVE** — never auto-uploaded; must pass through a redaction
  pipeline before any sharing. Locals files, full geometry, paths.
- **SENSITIVE-IN-CONTEXT** — the bytes themselves aren't secret, but
  their relationship to the caller's context might be (e.g. an error
  message quoting a locals value). Treat as SENSITIVE when in doubt.
- **AGGREGATE-ONLY** — counter / histogram data with no per-call
  attribution; safe for opt-in export.

## 3. Egress paths

The bridge does **not** call out to the network. There is no
auto-upload of any artifact. The four egress paths are all
operator-driven:

1. **`tools/export_metrics.py`** — opt-in JSON export of telemetry.
   Refuses to run unless `.telemetry/consent.txt` exists. Output is
   AGGREGATE-ONLY data only. User uploads the JSON manually if they
   choose to.
2. **`tools/bundle_bug_report.py`** — opt-in bundling of recent
   builds + telemetry + spec submissions. Runs the redaction
   pipeline (path scrubbing, locals stripping, trade-secret-pattern
   masking per `.ai-sw-bridge.toml`) before producing the `.zip`.
   User uploads manually.
3. **`tools/spec_redact.py`** + **`tools/checkpoint_redact.py`** —
   user-invoked one-shot redactors for ad-hoc sharing.
4. **Spec / build artifacts that the user themselves chooses to
   share** — outside the bridge's responsibility.

The MCP server (`ai-sw-mcp`) speaks stdio JSON-RPC to a single
client process (typically Claude Desktop). It does not open network
sockets. Whatever the MCP client does with the responses is the
client's privacy boundary, not the bridge's.

## 4. Consent gates

Operations that *could* exfiltrate data are gated behind explicit
consent files or flags:

| Operation | Gate |
|---|---|
| Telemetry write to `.telemetry/metrics.db` | Always enabled; AGGREGATE-ONLY data; no PII so no consent gate. |
| Telemetry export via `tools/export_metrics.py` | **Requires `.telemetry/consent.txt` to exist.** Refuses otherwise. |
| Bug-report bundle telemetry inclusion | **Same consent file**, OR pass `--no-telemetry` to bundle without it. |
| Checkpoint snapshots | `--checkpoint` flag on `ai-sw-build`; opt-in per build. |
| Encrypted checkpoints | `--checkpoint-encrypt <key-source>` flag; implies `--checkpoint`. Bridge does NOT escrow keys; lost key = lost history. |

## 5. PII commitment

**The bridge does not collect PII.** The only identity-shaped fields
ever recorded are:

- Path components (which may reveal usernames if the user works under
  `C:\Users\<name>\...`). These are scrubbed to `<HOME>\...` by the
  redaction pipeline before any egress.
- SOLIDWORKS revision number (e.g. "32.1.0"). Aggregate only.

No telemetry counter has a per-user, per-machine, or per-session
attribution beyond a per-process UUID4 `trace_id` that exists for
debug-log correlation and is regenerated every process start.

## 6. Encryption at rest

Per `docs/checkpoint_encryption_design.md`:

- **Default:** plain SQLite. Acceptable for repos behind disk
  encryption (BitLocker / FileVault).
- **`--checkpoint-encrypt env:NAME`** — Fernet wrap of
  `locals_snapshot` + `com_call_log` columns. Key from env var.
- **`--checkpoint-encrypt file:/path`** — same, key from file.
- **`--checkpoint-encrypt keyring:SERVICE`** — same, key from OS
  keyring (Windows Credential Manager, macOS Keychain, etc.).
- **`--checkpoint-encrypt prompt`** — same, key derived from
  user-typed passphrase via PBKDF2-HMAC-SHA256 600k iterations.

`_meta` table (algo, fingerprint, encrypted columns) is plaintext by
design so `ai-sw-checkpoint info` works without the key.

## 7. Threats out of scope

The bridge does not defend against:

- **A compromised SOLIDWORKS install** — if the SW binary is
  malicious, COM calls are untrusted; encryption-at-rest of
  checkpoints doesn't protect against the SW process reading the
  spec live.
- **A compromised Python interpreter / pywin32** — bridge runs in
  the user's process; compromise of the host process compromises
  everything.
- **A compromised MCP client** — Claude Desktop / Cursor receives
  full tool payloads; if the client is compromised, the data it
  receives is exposed.
- **Side-channel inference from timing / metric data** — telemetry
  histograms could in principle leak structural info about specs
  (e.g., a long build duration implies many features). Out of scope;
  if you need this defense, disable telemetry by not creating
  `.telemetry/consent.txt`.

## 8. Audit log

Decisions affecting privacy posture are recorded in
[`decisions.md`](decisions.md). Material changes (new egress paths,
relaxed consent gates, new PII fields) must also update this
document and bump the "Last reviewed" date at the top.

Past entries:

- **2026-05-28** — v0.13.0 release: at-rest encryption layer
  shipped; `--checkpoint-encrypt` available across all four key
  sources; lost key explicitly documented as "lost history" per
  `CHANGELOG.md`. No new auto-egress paths.
- **2026-05-23** — Telemetry consent file requirement formalized;
  `tools/export_metrics.py` refuses without `.telemetry/consent.txt`.

---

## How to update this doc

When you add a new artifact, new egress path, or new sensitivity
classification:

1. Add the row to §1 or update the affected section.
2. Bump "Last reviewed" at the top.
3. If the change is material (new egress, new PII, relaxed gate),
   log a `decisions.md` entry referencing this section.
4. Mention in the relevant `CHANGELOG.md` entry.

---

# Supply-chain security


Controls on upstream port hygiene, CVE response, and license audit. Operational document for maintainers and security reviewers.

**Last updated:** 2026-05-23
**Companion:** *(retired v0.13.0; see decisions.md 2026-05-28 entry)* §4.10 (summary) + `CONTRIBUTING.md` §"Port attribution" §1, §7, §8, §9 (license matrix + upstream relationships + community contributions + license audit automation).

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

CI gate (per `CONTRIBUTING.md` §"Port attribution" §9): `tools/license_lint.py` (planned, v0.11) verifies that every file with a port docstring has a matching CONTRIBUTING row, and vice versa.

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

(Mirrors `CONTRIBUTING.md` §"Port attribution" §7.2 — repeated here for the security context.)

| Upstream change | Action |
|---|---|
| Security fix touching our ported lines | Re-port within 7 days. Cherry-pick or pull HEAD. Update commit hash. |
| Behavioral bug fix in our ported lines | Re-port within next MINOR cycle. |
| Refactor that doesn't change behavior | No action; opportunistic re-port. |
| New upstream feature we don't use | No action. |
| License change to copyleft | Initiate port rollback per `CONTRIBUTING.md` §"Port attribution" §5.7. |
| Upstream archived / unmaintained | Decision recorded in [`decisions.md`](decisions.md); options: continue with pinned version forever; fork; or rewrite. |

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
6. **Record** — log the review in **Appendix A** (the upstream-port CVE ledger) with the drift count and triage outcome.

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
4. If our port is not affected: document the evaluation in **Appendix A**; close the loop.

### 4.2 Ledger format (Appendix A)

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
4. Decision recorded in [`decisions.md`](decisions.md).

The default is "don't add a dependency." Stdlib-first; selective adoption only when the stdlib path is genuinely worse.

---

## 8. Incident response

### 8.1 If we discover a vulnerability in our own code

1. File a private security advisory via GitHub's security tab (when project enables this) or contact maintainers directly.
2. Assess severity + affected versions.
3. Develop a fix on a private branch.
4. Coordinate disclosure timeline with the reporter.
5. Release a PATCH following the project's standard release process.
6. Public disclosure includes:
   - CVE allocation (when applicable).
   - Affected versions.
   - Recommended action (upgrade to which PATCH).
   - Workaround if upgrade isn't feasible.
7. Postmortem in `docs/postmortems/<date>-security.md`.

### 8.2 If we discover a vulnerability in a ported upstream

1. Verify our port is affected (the upstream might fix lines we didn't port).
2. If affected: §3.2 security-fix path + §8.1 PATCH process.
3. If not affected: log in **Appendix A** and move on.
4. Notify the upstream maintainer if our investigation surfaces something they don't yet know.

### 8.3 If we discover a malicious commit in an upstream

1. Pause any planned re-ports from that upstream.
2. Audit our current ports against the malicious commit window — did anything we ported land during the compromised period?
3. If yes: revert + re-port from a verified clean commit.
4. Notify the upstream maintainer and other downstream consumers (responsible disclosure).
5. Decision recorded in [`decisions.md`](decisions.md).

---

## 9. Audit history

This file maintains a brief audit history:

| Date | Activity | Outcome |
|---|---|---|
| 2026-05-23 | Initial supply-chain security review created | Process documented; tooling deferred to v0.11 / v0.12. |

Future audits append rows here. Material changes documented in [`decisions.md`](decisions.md).

---

## 10. Out of scope

This document does NOT cover:

- **User data privacy.** See *(retired v0.13.0; see decisions.md 2026-05-28 entry)*.
- **Cryptographic operations.** The bridge does not implement crypto; it consumes hashing (SHA-256 for fingerprints) via stdlib. Any cryptographic vulnerabilities are inherited from Python's `hashlib` and out of bridge scope.
- **Authentication / authorization.** The bridge runs as the user; there is no multi-user authentication model.
- **Code signing of releases.** Planned; tracked in the project's internal release-engineering notes.

---

## Appendix A — Upstream-port CVE ledger

> Merged from the former `supply_chain_audit.md` (v1.6.0). A flat, append-only
> ledger of reviewed upstream CVEs and license/repo events for every harvested
> dependency in `CONTRIBUTING.md` §"Port attribution". **Authority:** the project
> lead reviews and signs off each entry. **Cadence:** quarterly even with no
> events; per-event on each new GitHub Security Advisory or upstream license change.

### A.1 CVE / advisory review log

| Date | Upstream | Advisory | Affects ported code? | Action | Reviewer | PR |
|---|---|---|---|---|---|---|

*(empty as of 2026-05-27 — no advisories filed against pinned upstream repos.)*

When a (1) GitHub Security Advisory, (2) upstream license change, (3) compromised
commit, or (4) repo deletion/transfer/rename fires against a repo we port from,
add a row above cross-linking the GHSA ID, the shipped commit range, and the
reviewing PR.

### A.2 Drift-review checklist

When `tools/check_upstream_drift.py` flags an upstream (>50 commits drift):

- [ ] Pull the commit range `<pinned_sha>..<latest_sha>` from the upstream.
- [ ] Filter to files we ported (CONTRIBUTING.md "Third-party derivations" table).
- [ ] Review each change: behavior change · API surface delta · new failure mode · CVE fix.
- [ ] Decide: behavior-neutral cleanup → bump pin; API delta not affecting us → bump pin + note A.3;
      behavior change affecting us → port + attribute + record A.3; CVE fix → port + bump + record A.1;
      license change → record A.1, remove the port if incompatible.

### A.3 Drift-review outcomes

| Date | Upstream | Pinned SHA | Latest SHA | Commit count | Outcome | PR |
|---|---|---|---|---|---|---|
| 2026-05-27 | SolidworksMCP-python | `82e505d88da0` | (pinned via E4.2 bump) | 0 | Pin already advanced to current as of v0.12 cycle | (v0.12 release a9eb518) |

### A.4 Scope boundaries

This ledger covers only **source-harvested ports** (currently SolidworksMCP-python).
Transitive-dependency CVEs (numpy, sqlite-vec, jsonschema, pywin32) are covered by
**pip-audit in CI** (`.github/workflows/security.yml`). Vulnerabilities in the
bridge's own code are handled via the GitHub repo's private security advisories.

### A.5 Subscription setup (one-time)

```powershell
gh repo watch andrewbartels1/SolidworksMCP-python --custom-events security-advisories
```

Repeat for every repo added to the port-attribution table.
