# Cold authorability: making Tier A predict the build

**Date:** 2026-09-02
**Status:** design approved, not yet planned or implemented
**Origin:** the cold-read friction audit that produced issues #28–#43
**Supersedes nothing.** Constrains PRs #44 and #45, both open.

---

## 1. The problem, stated as one sentence

`--lint` exiting `0` does not predict that the spec will build.

Everything below follows from that. A non-Claude model was given this repo's docs
and nothing else, authored a 46-feature spec, and reached a schema-valid,
`--lint`-clean, `--dry-run`-clean result **on its first attempt, exit 0**. On a
live seat that spec built three features and died at the fourth with
`FeatureCut4 returned None`.

The gap between those two facts is the whole design.

## 2. Why this is the right metric

The primary authoring path for this tool is **an agent writing a spec**, not a
human adapting an example. That makes the seat-free tier the only thing standing
between an author and a burned SOLIDWORKS seat, and it makes predictive validity
of Tier A the number that matters.

Under that metric the sixteen filed issues stop being equally weighted:

| Cost | Failure | Issues |
|---|---|---|
| **A session and a seat** | Tier A passes, the build dies | 40, 33, 42 |
| An iteration | The author must guess, then correct | 31, 32, 35, 36, 28 |
| A wrong belief | The author skips a feature that works | 29, 30, 43 |
| Nothing measurable | Human-facing polish | 34, 37, 38, 39, 41 |

The first row is the design. The rest is cleanup, and some of it is `wontfix`.

## 3. Root causes, not issues

Sixteen issues, four causes:

1. **Hand-maintained docs drift from machine-readable truth** — 28, 29, 30, 31, 32
2. **The checker's coverage is invisible and its model is partial** — 33, 40, 42
3. **The safety contract is advisory, not enforced** — 41
4. **The docs assume you are adapting an example, not authoring cold** — 35, 36, 38, 39, 43

Cause 2 is where the expensive failures live. Cause 1 is where the volume is.
Cause 3 is a decision, not a defect. Cause 4 is real but cheap.

## 4. Decisions taken

**D1 — Audience: both, own project first.** Cold usability is a real goal, but
sequencing follows what costs sessions today.

**D2 — Forcing function: agents author the specs.** Machine-authorability is
throughput. This is what makes the cold-read audit self-serving rather than
altruistic, and it is why §2's metric is the right one.

**D3 — #41 (the approval gate) is cut from engineering scope.** It reads as the
scariest issue and is on the wrong axis: it concerns rails placed *on* agents,
not authoring throughput. `cli/build.py:144` proceeds when stdin is not a tty and
on `EOFError` from a PTY — deliberate, documented, and correct for CI. The defect
is that it prints `Approve? [y/N]` before proceeding, so a transcript reads as if
consent was obtained. **Resolution: a documentation change stating that the gate
is advisory by design and that `--yes` is not a security boundary**, plus
suppressing the prompt on the non-interactive path so the transcript cannot
mislead. No strict mode. Close as documented-behaviour.

**D4 — #42 is misfiled and must be corrected before it is worked.** The issue
claims no doc mentions verification targets. False: `spec_reference.md:1014`
documents `_expect`, `cli/build.py:244` surfaces it, and
`examples/drive_roller/spec.json` uses it. What is *actually* true:

- `_expect` has **zero** occurrences in the published JSON Schema
- the code calls its checker "the upcoming P0.5 verifier" — it does not exist
- it is per-**feature** (`mass_delta_mm3`) while production practice is
  per-**part** (bbox, body_count, total volume)

So the work is *finish P0.5 and widen it to the shape authors actually use*, not
*add a field*. Correcting the issue text is a prerequisite to working it.

## 5. The dependency chain

The phase order is not a priority ranking. It is a dependency graph, and two
edges in it are not visible from the issue tracker.

```
Phase 1   #40 (PR #44)  +  #33
          └─ stops burning seats. No dependencies. Ship first.

Phase 2   schema descriptions  +  _expect in the schema
          └─ REQUIRED BY PR #45 (see E1)
          └─ REQUIRED BY Phase 3 (see E2)

Phase 3   P0.5 verifier
          └─ needs _expect in the schema

Phase 4   #35 #36 #38 #39 #43  +  #41 as a doc change
          └─ no dependencies, no urgency
```

**E1 — PR #45 cannot merge well until the schema carries descriptions.**
Generation emits an empty Description cell wherever the schema has no
`description`, so hand-written blurbs like "Rectangle width (mm)" become blank
rows. Merging #45 as-is trades drift-proofing for a real loss of prose. Backfill
first and #45 becomes a strict improvement.

**E2 — the verifier cannot validate against a field the schema does not define.**

## 6. Phase 1 — stop burning seats

**#40 — one-directional plane-sketched cuts.** PR #44 is open and verified: a
type/reference check erroring on `cut_extrude_{blind,through_all,midplane}` whose
sketch is `*_on_plane`, silent on `cut_extrude_two_direction`. Verified against
the originating spec: exit 0 → exit 6, flagging exactly the two illegal cuts and
leaving the legal one alone.

*Open question carried on the PR:* this prevents the trap without explaining it.
Whether the cause is a SolidWorks kernel constraint or a bridge-side
sketch-selection bug is unknown. If the latter, the guard is the wrong fix and
the builder should be repaired instead.

**#33 — coverage signal. This is the general form of #40 and has no PR.**
Pre-flight models 2 of 11 extrude types (`preflight.py:154`). It does emit 23
honest skip notes — but at `severity: "info"`, invisible to the exit code and to
`error_count` / `warning_count`. An agent reads "exit 0" as "will build."

Acceptance criteria:

- `--lint` output carries a coverage summary: modelled / skipped / total, and
  which feature types were not modelled
- a `--strict` mode exits non-zero when any feature was not geometrically checked
- the summary is machine-readable in the JSON output, not only prose
- no change to default exit-code semantics (`6` still means geometric ERROR only)

Phase 1 is the only urgent phase.

## 7. Phase 2 — one artifact an author can trust

Make the published schema complete and authoritative, then generate from it.

1. **Backfill `description` on every schema field.** Unblocks E1. The prose
   already exists in `spec_reference.md`; this moves it to the source of truth
   rather than writing it fresh.
2. **Add `_expect` to the published schema** (currently 0 hits). Unblocks E2.
3. **Merge PR #45** — generated field tables for all 31 feature types plus the
   sync gate — which now strictly improves the doc instead of thinning it.
4. **Extend generation to capability claims** — #29 and #30 are stale claims
   about what ships. #37 asks the honesty gate to catch that class. Generating
   the claims removes the class.

This collapses 28, 29, 30, 31, 32, 34 and 37 into one structural fix, in the
house idiom: the repo already runs nine CI gates, and the answer to drift here
has always been a gate rather than a correction.

## 8. Phase 3 — the P0.5 verifier

Build the checker `observe.py:550` and `cli/build.py:476` already reference.
Widen `_expect` from per-feature `mass_delta_mm3` to the per-part form production
authors actually write by hand today: expected bbox, body_count, total volume,
with a tolerance.

This closes the loop the audit exposed: Grok's build died at feature 4 having
produced a plate that measured *exactly right*, and nothing in the spec could
tell "correct so far" from "about to fail."

## 9. Phase 4 — cleanup, no urgency

- **#35** pattern `direction`/`axis` are points on edges, not vectors — doc fix
- **#36** open sketch primitives have no documented route into a solid — doc fix
- **#38** ship an example exercising uncovered fields — good first issue
- **#39** `AGENTS.md` mandates a Claude-Code-specific memory path — the only
  genuinely Claude-coupled instruction in the repo; make it tool-neutral
- **#43** state the parametric-vs-literal trade-off — one paragraph
- **#41** per D3: documentation, not engineering

## 10. What this design does not do

- It does not chase the root cause behind #40. That question stays open on PR #44.
- It does not touch `schema_v2`. It is default-off, validated-but-inert, 15
  references, no published v2 artifact — dormant, not a live migration.
  Generating v1 docs is therefore not throwaway work. Issues #16 and #17
  (v2 half-wiring) are out of scope here and owned elsewhere.
- It adds no feature flags. `flags.py` explicitly warns against
  flag-of-the-week growth.

## 11. Success criteria

The design succeeds when an agent that has read only this repo's published
artifacts can author a spec, and `--lint --strict` exit 0 means the build will
succeed — or the non-zero exit names the reason.

Measurable: re-run the cold-read trial. The same 46-feature exerciser spec, or a
freshly authored one, should either lint clean and build clean, or fail lint with
an actionable message. The current result — lint clean, dies at feature 4 — is
the baseline.

## 12. Decomposition for planning

Each phase is its own spec → plan → implement cycle. **Do not plan all four
together.** Phase 1 is the unit of the first implementation plan; it is the only
phase with no upstream dependency and the only one that is urgent.

Phase 2 should be re-scoped when it is reached — the description backfill is
mechanical but large (every field in a 114 KB schema), and may itself want
splitting between "fields an author touches" and the long tail.

## 13. Issue-to-phase map

| Phase | Issues | In flight |
|---|---|---|
| 1 | 40, 33 | PR #44 (=#40) |
| 2 | 28, 29, 30, 31, 32, 34, 37 | PR #45 (=#34), blocked by E1 |
| 3 | 42 | — (issue text needs correcting first, per D4) |
| 4 | 35, 36, 38, 39, 41, 43 | — |

All sixteen are assigned; none is dropped silently. #41 is resolved by
documentation rather than code, per D3.
