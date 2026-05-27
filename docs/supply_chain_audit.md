# Supply-chain audit ledger

A flat ledger of reviewed upstream CVEs and license/repo events for
every harvested dependency tracked in [`harvest_plan.md`](central_idea/harvest_plan.md).

**Authority:** project lead reviews and signs off each entry.
**Cadence:** quarterly review even when no events; per-event review
on each new GitHub Security Advisory or upstream license change.
**Companion automation:** [`tools/check_upstream_drift.py`](../tools/check_upstream_drift.py)
flags commit drift; this doc captures the human review of what
that drift contains.

---

## How to add an entry

Per requirements.md §4.10 control row "CVE feed monitor" — this is
a process discipline, not tooling. When one of the following events
fires:

1. **GitHub Security Advisory** issued against an upstream repo we
   port code from.
2. **License change** at the upstream (MIT → AGPL, etc.).
3. **Compromised commit** disclosed against an upstream maintainer.
4. **Repo deletion / transfer / rename** at the upstream.

…add a row in §1 below. Cross-link to the GHSA ID, the upstream
commit range we ship from, and the bridge's reviewing PR.

When `tools/check_upstream_drift.py` flags >50 commits drift against
an upstream pin, run the drift review per §2 and record the outcome
under §3.

---

## 1. CVE / advisory review log

| Date | Upstream | Advisory | Affects ported code? | Action | Reviewer | PR |
|---|---|---|---|---|---|---|

*(empty as of 2026-05-27 — no advisories filed against pinned
upstream repos at this date)*

## 2. Drift-review checklist

When `tools/check_upstream_drift.py` flags an upstream:

- [ ] Pull the commit range `<pinned_sha>..<latest_sha>` from the
      upstream
- [ ] Filter to files we've actually ported (per
      [`CONTRIBUTING.md`](../CONTRIBUTING.md) "Third-party
      derivations" table)
- [ ] Review each change for: behavior change · API surface delta ·
      new failure mode · CVE-relevant fixes
- [ ] Decision tree:
  - **Behavior-neutral upstream cleanup** → bump the pin in
    [`harvest_plan.md`](central_idea/harvest_plan.md) §5; no code
    change
  - **API surface delta that doesn't affect our usage** → bump pin,
    note in §3 below
  - **Behavior change that affects us** → port the delta with a
    new attribution block; record in §3
  - **CVE fix** → port the delta + bump pin + record in §1 above
  - **License change** → record in §1; remove the port if license
    becomes incompatible (`harvest_plan.md` §1 matrix)

## 3. Drift-review outcomes

| Date | Upstream | Pinned SHA | Latest SHA | Commit count | Outcome | PR |
|---|---|---|---|---|---|---|
| 2026-05-27 | SolidworksMCP-python | `82e505d88da0` | (pinned via E4.2 bump) | 0 | Pin already advanced to current as of v0.12 cycle | (v0.12 release a9eb518) |

---

## 4. Scope boundaries

What this doc does NOT cover:

- **Transitive dependency CVEs** (numpy, sqlite-vec, jsonschema,
  pywin32) — those are tracked via pip-audit or equivalent in CI;
  this doc covers only **source-harvested ports** from
  [`harvest_plan.md`](central_idea/harvest_plan.md) §2 (currently:
  SolidworksMCP-python).
- **Vulnerabilities in our own bridge code** — those are tracked
  via private security advisories at the GitHub repo per
  [`privacy_review.md`](central_idea/privacy_review.md) §7.

## 5. Subscription setup (one-time)

To receive upstream advisories:

```powershell
gh repo watch andrewbartels1/SolidworksMCP-python --custom-events security-advisories
```

Repeat for every repo added to `harvest_plan.md` §2. The watch
fires GitHub notifications; the project lead routes each one to
this doc.

---

## See also

- [`harvest_plan.md`](central_idea/harvest_plan.md) §1 license
  compatibility matrix, §5 per-recipe pinned commits
- [`supply_chain_security.md`](supply_chain_security.md) — the
  control surface this ledger feeds
- [`privacy_review.md`](central_idea/privacy_review.md) §7
  disclosure process
- [`tools/check_upstream_drift.py`](../tools/check_upstream_drift.py)
  — the drift monitor
