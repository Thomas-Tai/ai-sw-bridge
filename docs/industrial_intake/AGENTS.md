# AGENTS.md — Industrial Design Intake

Briefing for an AI assistant running the intake process. Read this whole file;
it is the assistant contract for everything upstream of CAD.

**The pre-CAD gate:** do not produce any SolidWorks (or other backend) build
spec until the package's readiness state is `cad_ready_with_assumptions` or
`cad_ready` (states: [`workflow.md`](workflow.md)). When you do hand off, list
every assumption.

**Where files live:** create the package in the user's project at
`<project>/intake/`, one file per template in
[`templates/`](templates/idea_brief.md). Never write user packages into this
repository.

## The rules

1. Start from the user's raw idea and preserve it verbatim in `idea_brief.md`.
2. Ask small batches of questions — one to three high-leverage questions at a
   time. Never hand the user a long form.
3. Do not produce a SolidWorks spec from a vague industrial idea.
4. Separate requirements (what) from implementation choices (how).
5. Mark every numeric value as `required`, `assumed`, `measured`,
   `vendor_provided`, or `derived`.
6. Prefer COTS and standard parts before custom geometry.
7. Require an explicit coordinate, datum, and naming strategy
   (`top_down_cad_strategy.md`) before CAD handoff.
8. Require DFM/DFA review before declaring CAD-ready.
9. Keep `cad_ready_summary.json` CAD-neutral — SolidWorks specifics belong in
   `solidworks_handoff.md`, never in the summary.
10. Hand off to [`../AGENTS.md`](../AGENTS.md) only after the package reaches
    a valid readiness state.
11. If the user already has a complete design (their own requirements,
    architecture, BOM, calculations), switch to the direct-entry lane: map
    their documents onto the package or fill `cad_ready_summary.json`
    directly. **Map, do not interrogate.**

## Working style

- Update the package after every answer; keep `readiness.state` honest.
- Put open questions in `readiness.blocking_questions`; anything a human must
  judge (safety guarding, always) in `readiness.manual_review_required`.
- Validate the summary against
  [`templates/cad_ready_summary.schema.json`](templates/cad_ready_summary.schema.json)
  before declaring any `cad_ready*` state.
- The worked example
  ([`examples/automated_sorting_machine/`](examples/automated_sorting_machine/idea_brief.md))
  shows the expected depth — match it, do not exceed it for a first slice.
