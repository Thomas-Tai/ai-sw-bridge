# Launch Readiness Checklist

The gate every release candidate must pass before a `vX.Y.0` GA tag is cut.
One checkbox per load-bearing readiness concern. Each item names the audit
finding or spec section that motivates it, the signal that closes it, and
the DRI who signs off.

**Scope.** This checklist applies to minor-version GA tags
(`v0.11.0`, `v0.12.0`, ...). Patch releases (`v0.11.1`, ...) re-run only the
items a patch could have affected — typically CI matrix, live-SW regression,
CHANGELOG, and migration doc.

**When to run it.** Open this doc at the start of the release cycle and walk
it in the release-review meeting. A checkbox moves from `[ ]` to `[x]` only
when the named evidence is produced and linked; do not pre-check.

**Origin.** Derived from *(retired v0.13.0; see decisions.md 2026-05-28 entry)*
section 5.4 ("No explicit launch readiness checklist"), which pointed to
Google's Launch Readiness Review as the model. The fifteen items below are
the concrete signal set for this project — each maps back to a P0 / P1
audit gap.

---

## The checklist

### Observability and performance

- [ ] **1. SLI/SLO dashboards green.**
  Every mandatory SLI defined in *(retired v0.13.0; see decisions.md 2026-05-28 entry)*
  section 3.5 has a live dashboard; the last 7 days of data are inside
  the error budget.
  - Closes audit section 1.1 (P0: "define SLOs and error budgets explicitly").
  - Evidence: link to the dashboard snapshot in the release PR.

- [ ] **2. Performance baselines current.**
  `tools/perf_baselines/` holds a baseline no older than the previous
  minor release; the current release's regression check exits 0 on the
  CI matrix (audit section 2.3). The v0.10 -> v0.11 baseline was captured
  at commit `0dffa96`.
  - Evidence: `python tools/perf_regression_check.py` exits 0; output
    attached to the release PR.

### Supply chain and security

- [ ] **3. Upstream drift gate clean.**
  `python tools/check_upstream_drift.py` exits 0; every pinned upstream
  in `CONTRIBUTING.md` §"Port attribution" section 5.2 is
  within the drift threshold (audit section 1.4,
  [`supply_chain_security.md`](supply_chain_security.md)).
  - Evidence: CI job `drift-gate` green on the release commit.

- [ ] **4. License-lint clean.**
  `pytest tests/test_license_lint.py` exits 0; no GPL or no-license
  upstream has been introduced since the last GA (audit section 1.4,
  `harvest_plan.md` section 2 matrix).
  - Evidence: CI job `license-lint` green on the release commit.

- [ ] **5. Supply-chain audit re-affirmed.**
  The [`supply_chain_security.md`](supply_chain_security.md) controls
  table still matches reality: SBOM generation works, CVE-response runbook
  is reachable, signing keys are current. Annual re-sign-off by the
  security DRI.
  - Evidence: signed statement linked from the release PR.

### Privacy and trust

- [ ] **6. Privacy review re-affirmed.**
  *(retired v0.13.0; see decisions.md 2026-05-28 entry)*
  reflects the current data-flow reality — no new egress paths, no new
  PII captures introduced since the last review. Telemetry consent UX
  still matches audit section 2.4.
  - Evidence: diff of `privacy_review.md` since last GA; reviewer
    sign-off in the release PR.

### Documentation

- [ ] **7. Doc-coverage gate clean.**
  `python tools/doc_coverage_gate.py` exits 0; every `AGENTS.md` promise
  has a corresponding shipped behavior (audit section 2.6).
  - Evidence: CI job `doc-coverage` green on the release commit.

- [ ] **8. CHANGELOG entry current.**
  `CHANGELOG.md` has a `vX.Y.0` section with all user-visible changes
  grouped under Added / Changed / Fixed / Removed, following the SemVer
  policy in [`release_engineering.md`](release_engineering.md).
  - Evidence: CHANGELOG diff in the release PR.

- [ ] **9. Migration doc drafted.**
  `docs/migration_to_vX.Y.md` exists; covers schema-layer changes,
  CLI-layer changes, new manifest sidecars, and a backward-compat
  statement. Cross-linked from the CHANGELOG entry.
  - Evidence: link in CHANGELOG and in the relevant per-subsystem
    design doc under `docs/`.

- [ ] **10. README current.**
  Top-level `README.md` reflects the shipped primitive count, the
  active capability lanes, and the Acknowledgments list (one line per
  upstream repo per the consolidated-structural-credit rule).
  - Evidence: README diff in the release PR.

### Build and CI

- [ ] **11. CI matrix green.**
  All required CI jobs pass on the release commit across the supported
  Python matrix (3.10, 3.12, 3.14). Black / flake8 / mypy clean.
  - Evidence: the GitHub Actions run URL in the release PR.

- [ ] **12. Fault-injection suite green.**
  `pytest -m fault_injection` passes against the synthetic `ComError`
  catalog in `tests/fault_injection/conftest.py`. Circuit breaker,
  reconnect, and anti-loop guard all exercise their failure modes.
  - Evidence: CI job `fault-injection` green on the release commit.

- [ ] **13. Live-SW regression green.**
  `pytest -m solidworks_only` passes on a machine running the target
  SOLIDWORKS version (currently SW 32.1.0). MMP and at least two other
  example specs build end-to-end.
  - Evidence: test report attached to the release PR (live-SW runs are
    not on the hosted CI matrix — a developer workstation signs off).

### Examples and external signal

- [ ] **14. Examples build.**
  Every example spec under `examples/` builds end-to-end via
  `ai-sw-build ... --no-dim`; the resulting part file opens in SW without
  rebuild errors. Run on the release commit after live-SW is up.
  - Evidence: per-example pass/fail matrix attached to the release PR.

- [ ] **15. External beta ack.**
  At least one external user (not a core contributor) has run the
  pre-release tag (`vX.Y.0bN` or `vX.Y.0rcN`) end-to-end and confirmed
  the onboarding path works on their machine.
  - Evidence: link to the beta tester's report or sign-off message in
    the release PR.

---

## Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Release DRI | | | `GO` / `NO-GO` |
| Security DRI | | | `GO` / `NO-GO` |
| Documentation DRI | | | `GO` / `NO-GO` |
| External beta tester | | | `ack` / `block` |

A release is cut only when all four sign-offs are `GO` / `ack` **and**
every checkbox above is `[x]`.

---

## Related documents

- The audit gap this checklist closes:
  *(retired v0.13.0; see decisions.md 2026-05-28 entry)*
  section 5.4.
- The release engineering process that consumes this gate:
  [`docs/release_engineering.md`](release_engineering.md).
- The roadmap this checklist guards: [`docs/ROADMAP.md`](ROADMAP.md).
- The supply-chain and SLO documents referenced above live under
  `docs/` ([`supply_chain_security.md`](supply_chain_security.md),
  [`release_engineering.md`](release_engineering.md),
  [`decisions.md`](decisions.md)).
