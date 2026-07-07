# Industrial Design Intake

From **one idea** to a **CAD-ready industrial design package** — before any
SolidWorks spec is written.

`ai-sw-bridge` is excellent once a part, assembly, or drawing can be described
in its declarative language. But a real project starts earlier: requirements,
architecture, calculations, purchased-part selection, a top-down CAD strategy,
manufacturability, and a verification plan. This layer makes that pre-CAD work
explicit, reviewable, and repeatable. It is **documentation and templates
only** — no new CLI or MCP tool.

## How it works

- **Maker with only an idea** → the guided lane: an AI assistant interviews
  you a few questions at a time and fills the package artifact by artifact.
- **Professional with a complete design** → the direct-entry lane: map your
  existing documents onto the templates, or fill
  [`templates/cad_ready_summary.example.json`](templates/cad_ready_summary.example.json)'s
  shape directly. The gate checks **artifacts, not process** — a complete
  design passes in minutes.

Both lanes are defined in [`workflow.md`](workflow.md); the assistant contract
(including the pre-CAD gate) is [`AGENTS.md`](AGENTS.md).

Your package lives in **your project**, at `<project>/intake/` — this repo
tree holds only templates and one worked example.

## The artifacts

| Order | Template | Answers |
|---|---|---|
| 1 | [`templates/idea_brief.md`](templates/idea_brief.md) | what is the idea, really? |
| 2 | [`templates/requirements.md`](templates/requirements.md) | what must it do (incl. quantity, cost, safety)? |
| 3 | [`templates/engineering_specs.md`](templates/engineering_specs.md) | which numbers, with what status? |
| 4 | [`templates/system_architecture.md`](templates/system_architecture.md) | which subsystems and interfaces? |
| 5 | [`templates/module_breakdown.md`](templates/module_breakdown.md) | what becomes a part/assembly/fixture/purchase? |
| 6 | [`templates/calculations.md`](templates/calculations.md) | do the numbers justify the components? |
| 7 | [`templates/cots_selection.md`](templates/cots_selection.md) | which standard parts anchor the design? |
| 8 | [`templates/top_down_cad_strategy.md`](templates/top_down_cad_strategy.md) | how is the CAD structured? |
| 9 | [`templates/dfm_dfa_checklist.md`](templates/dfm_dfa_checklist.md) | can it be made and assembled? |
| 10 | [`templates/verification_plan.md`](templates/verification_plan.md) | how is it judged? |
| 11 | [`templates/cad_ready_summary.schema.json`](templates/cad_ready_summary.schema.json) | the CAD-neutral handoff (JSON Schema) |

## Worked example

[`examples/automated_sorting_machine/`](examples/automated_sorting_machine/idea_brief.md)
walks the full path from *"I want to build an automated sorting machine"* to a
validated [`cad_ready_summary.json`](examples/automated_sorting_machine/cad_ready_summary.json)
and an ordered, verify-pointed
[`solidworks_handoff.md`](examples/automated_sorting_machine/solidworks_handoff.md)
for its first buildable slice (the infeed conveyor).

## After intake

When the package reaches `cad_ready_with_assumptions` or `cad_ready`, hand off
to the build surfaces: [`../AGENTS.md`](../AGENTS.md) for spec authoring,
[`../CAPABILITIES.md`](../CAPABILITIES.md) for what the bridge can build. The
handoff format is CAD-neutral by design — future non-SolidWorks backends can
consume the same package.
