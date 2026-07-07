# Intake Workflow

Two lanes, one gate. The gate checks **artifacts, not process** — however the
package came to exist, the same readiness criteria apply.

## Lane 1 — Maker (guided)

1. User states the idea in one sentence; the assistant writes `idea_brief.md`.
2. The assistant classifies the idea (machine / system / product) and asks the
   next one to three highest-leverage questions.
3. Each answer updates the package; artifacts fill in this order:
   idea_brief → requirements → engineering_specs → system_architecture →
   module_breakdown → calculations → cots_selection → top_down_cad_strategy →
   dfm_dfa_checklist → verification_plan → cad_ready_summary.json.
4. When the summary validates and the state reaches
   `cad_ready_with_assumptions`, the assistant writes the backend handoff
   (for SolidWorks: a `solidworks_handoff.md` with an ordered, verify-pointed
   build sequence — see the
   [example](examples/automated_sorting_machine/solidworks_handoff.md)).

## Lane 2 — Professional (direct entry)

Already have requirements, architecture, BOM, and calculations? Do not get
interviewed:

1. Map your existing documents onto the templates — or skip straight to
   filling `cad_ready_summary.json` against
   [the schema](templates/cad_ready_summary.schema.json).
2. The readiness criteria below check what exists, not how it was produced.
   A complete design passes in minutes.
3. Your real value is downstream: the ordered build sequence in the handoff,
   with a verify command per step.

## Package location

User packages live at `<project>/intake/` — beside the eventual `spec.json`
and assembly manifests, never inside this repository. This tree ships only
templates and the worked example.

## Readiness states

The first five states are ordered and cumulative — each row's criteria include
every row above it; `blocked` can be entered from any state.

| State | Entry criteria |
|---|---|
| `idea_only` | `idea_brief.md` exists. |
| `requirements_draft` | `requirements.md` and `engineering_specs.md` drafted; quantity, cost target, and safety scan captured. |
| `architecture_draft` | `system_architecture.md` and `module_breakdown.md` complete; interfaces enumerated with IDs. |
| `cad_ready_with_assumptions` | For the first build slice: calculations done, COTS candidates chosen (assumed values allowed), top-down strategy written including the executable split, DFM/DFA reviewed, verification plan drafted, `blocking_questions` empty, every assumption listed. |
| `cad_ready` | All of the above, plus no `assumed` status on slice-critical parameters and slice COTS confirmed with CAD assets. |
| `blocked` | Any blocking question with no resolution path. |

The assistant may only produce backend-specific specs at
`cad_ready_with_assumptions` or `cad_ready`, and must list the assumptions in
the handoff.

## Value statuses

Every number in the package carries exactly one status: `required` (the user
demands it), `assumed` (a placeholder to revisit), `measured` (verified
physically), `vendor_provided` (from a datasheet), `derived` (computed in
`calculations.md`).
