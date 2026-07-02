# The Performance Honesty Gate

`ai-sw-bridge`'s performance is gated by a **Model-B honesty contract**, the
same shape as the i18n staleness gate. CI has no SOLIDWORKS seat, so it cannot
*measure* performance — instead it enforces that a committed **Perf Receipt**
stays honest about the code it describes.

## The metric and the ceiling

The metric is the **end-to-end example build**: `tools/regression_check.py`
builds every `examples/*/spec.json` on a live seat and records per-build
wall-clock, reducing to p50/p95/p99. The ceiling is the SLO that shipped in
v0.11 (single-sourced in `regression_check.py`):

- **SLO-01:** p95 < 12 s
- **SLO-02:** p99 < 25 s
- **Regression:** p95 must not exceed the baseline p95 by >15%, nor p99 by >25%.

## The receipt

`tools/perf_baselines/receipt.json` records the last measurement's raw
percentiles plus `measured_at` (the commit SHA it was measured at), the
`baseline` it was compared against, and a `lag_acknowledged` flag. It carries
**no verdict** — CI re-derives pass/fail from the raw numbers, so editing a
boolean cannot fake a green.

## The gate (`tests/test_perf_receipt.py`)

- **Freshness biconditional (always):** the receipt is *stale* iff the
  feature-build hot path (`src/ai_sw_bridge/spec/`, `features/`,
  `cli/build.py`, `examples/*/spec.json`) advanced since `measured_at`. A stale
  receipt MUST set `lag_acknowledged: true` (+ a `lag_reason`); a fresh one MUST
  NOT. Silent rot and crying wolf both fail CI.
- **Green-when-current (only when not lag-acknowledged):** CI re-derives the
  SLO + regression verdict from the receipt's raw p95/p99 vs the referenced
  baseline. A fresh receipt that fails the SLO is a real regression → red.

Honest lag is allowed and visible; silent rot is impossible.

## The ritual (maintainer, on a live seat)

Regenerate the receipt after you change the build hot path:

    python tools/regression_check.py --check \
        --baseline-compare tools/perf_baselines/v0.10.json \
        --emit-receipt tools/perf_baselines/receipt.json

This is non-destructive (builds into fresh blank parts, never saves over your
files) but it drives a live seat, so it is never part of the automated suite.
Commit the refreshed `receipt.json` (it lands fresh, `lag_acknowledged: false`).

If you changed the hot path but cannot re-measure now, set
`lag_acknowledged: true` with a `lag_reason` and commit — CI stays green with
visible debt until the next measurement.

## Baseline-bump discipline

When performance regresses acceptably (e.g. a new, inherently slower feature),
bump the baseline rather than lying to the gate:

    python tools/regression_check.py --check \
        --baseline-compare tools/perf_baselines/v0.10.json \
        --write-baseline  tools/perf_baselines/v1.7.json \
        --emit-receipt    tools/perf_baselines/receipt.json

then repoint `receipt.baseline` to the new file. In this solo, fast-forward
repo, a "reviewed baseline bump" is a deliberate, self-documented baseline
commit. Keep the old baseline for provenance.
