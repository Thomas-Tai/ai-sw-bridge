# Industrial Design Intake - Design Specification

> **Status:** DRAFT for user review before writing-plans
> **Date:** 2026-07-07
> **Author:** Codex design session
> **Ratified direction:** Approach A - a guide-and-template design package generator before any CLI/MCP implementation.

---

## 1. Objective

Add an upstream engineering-intake layer that turns a Maker's single idea into a CAD-ready industrial design package before the existing SolidWorks automation layer is allowed to build anything.

The current product already answers: "Given a stable JSON CAD spec, can an AI safely build, observe, mutate, assemble, draw, and export through SOLIDWORKS?"

This design answers the earlier question: "How does a user who only has an idea reach a stable JSON CAD spec without skipping the product-management and systems-engineering work a 20-year professional would do first?"

The first release is deliberately a documentation, template, and agent-briefing layer. It does not add a public CLI, MCP tool, or CAD backend abstraction yet. Its job is to make the pre-CAD engineering process explicit, reviewable, and repeatable.

---

## 2. Problem Statement

`ai-sw-bridge` currently starts in the middle of the real industrial design process. It is excellent once the user or AI can describe a part, feature, assembly, drawing, mutation, or observation target in the bridge's declarative language.

But a Maker usually starts with:

> "I want to build an automated sorting machine."

A professional product manager and systems engineer would not open SOLIDWORKS immediately. They would first clarify the operational problem, constraints, system architecture, interfaces, COTS component choices, top-down CAD strategy, manufacturing route, tolerances, assembly sequence, safety boundaries, and verification plan.

Without that intake layer, an AI assistant can produce a plausible model too early. The result may be visually convincing but under-specified, hard to manufacture, hard to revise, or impossible to integrate with controls, sensors, actuators, and future CAD backends.

---

## 3. Goals

1. A non-expert Maker can begin with one idea and be guided step by step toward a professional engineering design package.
2. The workflow teaches and enforces the pre-modeling steps that precede industrial SolidWorks work: requirements, architecture, modules, interfaces, COTS selection, top-down strategy, DFM/DFA, and verification.
3. The output is stable enough for an AI assistant to hand off into the existing `ai-sw-build`, `ai-sw-assembly`, `ai-sw-drawing`, `ai-sw-properties`, `ai-sw-configurations`, observe, and export flows.
4. The design package is CAD-neutral at the handoff boundary so future open-source 3D model software can consume the same upstream intent.
5. The first release fits the current repository structure and avoids expanding the public API before the intake grammar is proven.

---

## 4. Non-goals

- No new CLI command in the first release. `ai-sw-intake` is a future candidate after the template grammar stabilizes.
- No new MCP tool in the first release. `sw_industrial_intake` is a future candidate after the written process proves useful.
- No direct model generation from the Maker's first idea. The workflow must produce a reviewable design package first.
- No GUI or web wizard. AI-chat-first is sufficient for the first release.
- No full CAD-backend abstraction implementation. The first release only defines a CAD-neutral handoff shape.
- No change to existing SolidWorks build, mutate, assembly, drawing, checkpoint, or observe behavior.

---

## 5. Ratified Anchors

- **A1 - Approach A:** ship guide-and-template artifacts first, not a CLI/MCP surface.
- **A2 - Industrial Design Intake:** name the layer around engineering intake, not "prompt templates" or "wizard".
- **A3 - Pre-CAD gate:** the assistant must not produce a SolidWorks build spec until the intake package has reached a CAD-ready state.
- **A4 - CAD-neutral handoff:** the package describes product intent, modules, parameters, constraints, interfaces, manufacturing assumptions, and verification criteria without binding to SolidWorks API calls.
- **A5 - Existing bridge remains the execution layer:** SolidWorks remains the first backend, reached through existing spec, assembly, drawing, and observe surfaces.

---

## 6. User Journey

### 6.1 Maker path

1. User gives a one-sentence idea.
2. The assistant opens `docs/industrial_intake/AGENTS.md`.
3. The assistant classifies the idea into a machine/system/product type and writes an initial `idea_brief.md`.
4. The assistant asks only the next most important questions. It does not ask the user to fill a long form.
5. Each answer updates the intake package.
6. When enough information exists, the assistant produces a CAD-ready summary and explains what is still assumed.
7. Only then does the assistant create or propose bridge-native SolidWorks specs.

### 6.2 Professional path

An experienced PM, systems engineer, or mechanical engineer can skip quickly through known fields, but the same artifacts are produced. The value for expert users is traceability: every CAD choice is connected back to a requirement, interface, standard part, manufacturing assumption, or verification criterion.

### 6.3 Future backend path

The same `cad_ready_summary.json` can later route to:

- SolidWorks through `ai-sw-build`, `ai-sw-assembly`, and `ai-sw-drawing`.
- FreeCAD through a future adapter.
- OpenSCAD or CadQuery for code-native parametric geometry.
- Blender or other mesh-oriented tools for visualization-only phases.

The first release does not implement those adapters; it keeps the handoff format neutral enough that they remain possible.

---

## 7. Repository Shape

New documentation tree:

```text
docs/industrial_intake/
  AGENTS.md
  README.md
  workflow.md
  templates/
    idea_brief.md
    requirements.md
    engineering_specs.md
    system_architecture.md
    module_breakdown.md
    cots_selection.md
    top_down_cad_strategy.md
    dfm_dfa_checklist.md
    verification_plan.md
    cad_ready_summary.schema.json
    cad_ready_summary.example.json
  examples/
    automated_sorting_machine/
      idea_brief.md
      requirements.md
      engineering_specs.md
      system_architecture.md
      module_breakdown.md
      cots_selection.md
      top_down_cad_strategy.md
      dfm_dfa_checklist.md
      verification_plan.md
      cad_ready_summary.json
      solidworks_handoff.md
```

Existing docs to update:

- `README.md`: add a short persona-router row for "Maker with one idea".
- `docs/AGENTS.md`: add a pre-CAD instruction that vague industrial ideas should start with `docs/industrial_intake/AGENTS.md`.
- `docs/CAPABILITIES.md`: add "Industrial Design Intake" as a planning/handoff capability, not a build capability.
- `docs/extension_contract.md`: no change for first release because no new CLI/MCP/feature/observe lane is added.

---

## 8. Intake Artifacts

### 8.1 `idea_brief.md`

Captures the raw idea, the user's words, the intended outcome, target users, operating context, and initial unknowns.

Required sections:

- Raw idea
- Intended job-to-be-done
- Target user/operator
- Target object/material/workpiece
- Desired output
- Known constraints
- Unknowns blocking engineering decisions

### 8.2 `requirements.md`

The product and engineering requirements. It separates what the system must do from how it might be implemented.

Required sections:

- Functional requirements
- Performance requirements
- Environmental requirements
- Physical constraints
- Safety and compliance constraints
- Maintenance and serviceability requirements
- Acceptance criteria

### 8.3 `engineering_specs.md`

Numeric and testable engineering assumptions. It is allowed to contain estimates, but every estimate must be marked as assumed, measured, or required.

Required sections:

- Throughput, speed, accuracy, repeatability
- Payload, force, torque, power, duty cycle
- Dimensional envelope and mass
- Materials and surface constraints
- Control and signal requirements
- Tolerance policy
- Units and reference coordinate conventions

### 8.4 `system_architecture.md`

The high-level system decomposition before CAD.

Required sections:

- Subsystems
- Interfaces
- Data flow
- Material flow
- Energy and force flow
- Sensor/actuator/control boundaries
- Failure modes and safe states

### 8.5 `module_breakdown.md`

The bridge between architecture and CAD. It names each module that may become a part, assembly, fixture, or purchased component.

Required sections:

- Module list
- Module responsibility
- Inputs and outputs
- Mechanical interfaces
- Electrical/control interfaces
- Dependencies
- Build/buy decision

### 8.6 `cots_selection.md`

Documents selected or candidate standard parts. Industrial CAD should depend on real or candidate COTS geometry before custom brackets are designed around it.

Required sections:

- Candidate motors, actuators, sensors, rails, bearings, belts, fasteners, controllers
- Vendor/model or generic standard
- Key dimensions
- CAD asset availability
- Selection rationale
- Open questions and substitutions

### 8.7 `top_down_cad_strategy.md`

Defines how the CAD model should be structured before any backend-specific spec is written.

Required sections:

- Global coordinate system
- Master origin and datum planes
- Skeleton/layout sketch strategy
- Global variables and parameter names
- Assembly structure
- Naming conventions for features, sketches, parts, and mates
- Rebuild and variant strategy

### 8.8 `dfm_dfa_checklist.md`

Manufacturing and assembly thinking before modeling details harden.

Required sections:

- Manufacturing process candidates
- Material/process fit
- Tolerance and fit strategy
- Tool access and minimum feature limits
- 3D print or CNC constraints where applicable
- Assembly order
- Service access
- Inspection method

### 8.9 `verification_plan.md`

Defines how the model and eventual machine design are judged.

Required sections:

- Requirements traceability
- CAD checks
- Simulation or motion checks
- Physical prototype checks
- Operator acceptance checks
- Risks requiring manual engineering review

### 8.10 `cad_ready_summary.json`

The CAD-neutral handoff. It is not a SolidWorks spec. It is a compact structured representation that downstream agents can translate into backend-specific specs.

---

## 9. CAD-ready Summary Shape

The first release ships a schema document as documentation, not a runtime validator. The shape is intentionally conservative:

```json
{
  "schema_version": 1,
  "project": {
    "name": "automated_sorting_machine",
    "intent": "Sort mixed objects into bins by visual classification.",
    "maturity": "concept"
  },
  "units": {
    "length": "mm",
    "mass": "kg",
    "angle": "deg"
  },
  "requirements": [
    {
      "id": "REQ-001",
      "text": "Sort target objects into at least three output bins.",
      "priority": "must",
      "verification": "prototype_test"
    }
  ],
  "parameters": [
    {
      "name": "CONVEYOR_WIDTH",
      "value": 120.0,
      "unit": "mm",
      "status": "assumed",
      "rationale": "Wide enough for the largest target object plus side clearance."
    }
  ],
  "modules": [
    {
      "id": "MOD-001",
      "name": "infeed_conveyor",
      "role": "Move objects through the sensing zone.",
      "cad_intent": "assembly",
      "interfaces": ["IF-001", "IF-002"],
      "build_buy": "mixed"
    }
  ],
  "interfaces": [
    {
      "id": "IF-001",
      "from": "infeed_conveyor",
      "to": "vision_module",
      "type": "spatial",
      "description": "Camera field of view covers the belt inspection area."
    }
  ],
  "cots": [
    {
      "id": "COTS-001",
      "category": "motor",
      "selection_status": "candidate",
      "model": "Generic NEMA 17 stepper candidate",
      "critical_dimensions": {},
      "cad_asset": "missing"
    }
  ],
  "manufacturing": {
    "candidate_processes": ["3d_printing", "laser_cut_plate", "cnc_machining"],
    "tolerance_policy": "prototype_clearance",
    "notes": []
  },
  "cad_strategy": {
    "coordinate_system": "machine_origin_at_frame_center_front_bottom",
    "top_down": true,
    "global_variables": ["CONVEYOR_WIDTH"],
    "backend_targets": ["solidworks"]
  },
  "readiness": {
    "state": "cad_ready_with_assumptions",
    "blocking_questions": [],
    "manual_review_required": ["safety_guarding", "motor_torque"]
  }
}
```

Required readiness states:

- `idea_only`
- `requirements_draft`
- `architecture_draft`
- `cad_ready_with_assumptions`
- `cad_ready`
- `blocked`

The assistant may only produce backend-specific SolidWorks specs when the readiness state is `cad_ready_with_assumptions` or `cad_ready`, and must list any assumptions in the handoff.

---

## 10. Agent Rules

`docs/industrial_intake/AGENTS.md` defines the assistant contract:

1. Start from the user's raw idea and preserve it in `idea_brief.md`.
2. Ask small batches of questions. Prefer one to three high-leverage questions over long forms.
3. Do not produce a SolidWorks spec from a vague industrial idea.
4. Separate requirements from implementation choices.
5. Mark every numeric value as required, assumed, measured, vendor-provided, or derived.
6. Prefer COTS and standard parts before custom geometry.
7. Require explicit coordinate, datum, and naming strategy before CAD handoff.
8. Require DFM/DFA review before declaring CAD-ready.
9. Keep `cad_ready_summary.json` CAD-neutral.
10. Hand off to `docs/AGENTS.md` only after the package reaches a valid readiness state.

---

## 11. Handoff to Existing Bridge Surfaces

The first release uses a written handoff, not an automatic converter.

`solidworks_handoff.md` in each example explains:

- Which modules should become parts.
- Which modules should become assemblies.
- Which purchased components need imported STEP/IGES assets.
- Which parameters map to `locals.txt` variables.
- Which existing bridge commands apply:
  - `ai-sw-build` for simple parts.
  - `ai-sw-assembly` for module placement and mates.
  - `ai-sw-drawing` for manufacturing drawings.
  - `ai-sw-properties` for metadata.
  - `ai-sw-configurations` for variant families.
  - `ai-sw-observe`, `ai-sw-motion`, and `ai-sw-solver` for verification.

Future automation can consume `cad_ready_summary.json` to generate initial bridge-native specs.

---

## 12. Example Project

Ship one complete example: `automated_sorting_machine`.

The example should stay compact enough to read, but complete enough to demonstrate professional thinking:

- The raw Maker idea.
- Requirements for throughput, sorting accuracy, object size, and footprint.
- A subsystem architecture: infeed, sensing, classification, diverter, bins, frame, controls.
- A COTS selection page with candidate belt, motor, camera, sensor, controller, and fasteners.
- A top-down CAD plan with coordinate system and key parameters.
- DFM/DFA choices for prototype manufacturing.
- A CAD-ready JSON summary.
- A SolidWorks handoff note that maps the first buildable slice to existing bridge commands.

The example does not need to build the entire machine in SOLIDWORKS. It must show how to reach the first safe build slice.

---

## 13. Testing and Review

First-release verification is documentation-focused:

1. `python tools/doc_coverage_gate.py` must continue to pass.
2. Existing doc-truth tests must not drift.
3. Add a lightweight docs test only if the repository already has a matching pattern for checking file existence or README links.
4. Manually review all new templates for placeholders, contradictions, and unclear readiness rules.
5. Validate `cad_ready_summary.example.json` with a generic JSON parser if a test is added.

No SOLIDWORKS seat is required for this release.

---

## 14. Phased Implementation Plan

### Phase 1 - Documentation spine

- Add `docs/industrial_intake/README.md`.
- Add `docs/industrial_intake/AGENTS.md`.
- Add `docs/industrial_intake/workflow.md`.
- Update `README.md`, `docs/AGENTS.md`, and `docs/CAPABILITIES.md`.

### Phase 2 - Templates and schema document

- Add all Markdown templates.
- Add `cad_ready_summary.schema.json`.
- Add `cad_ready_summary.example.json`.

### Phase 3 - Complete example

- Add `examples/automated_sorting_machine/` under `docs/industrial_intake/examples/`.
- Include a `solidworks_handoff.md` that maps the design package to existing commands.

### Phase 4 - Review and gates

- Run documentation checks.
- Run relevant offline tests.
- Decide whether a file-existence/link test is needed.

### Future Phase - Automation

After the written intake proves useful:

- Add `ai-sw-intake` as an experimental CLI.
- Add `sw_industrial_intake` as an MCP planning tool.
- Add a converter from `cad_ready_summary.json` to bridge-native part/assembly/drawing draft specs.
- Add backend adapters for open-source CAD tools.

---

## 15. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| The intake becomes a bureaucratic form | Makers abandon it | Keep the agent rules conversational and ask only the next high-value questions |
| The CAD-ready JSON becomes too backend-specific | Future CAD adapters become harder | Keep SolidWorks-specific details in `solidworks_handoff.md`, not in the neutral summary |
| The assistant still jumps to modeling too early | Output remains under-specified | Add explicit pre-CAD gate rules in both intake AGENTS and root `docs/AGENTS.md` |
| COTS fields are unknown early | Users get blocked | Allow candidate and missing statuses, but mark them as assumptions |
| The example becomes too large | It stops teaching the first slice | Scope the example to the first buildable subsystem, not the whole factory |

---

## 16. Acceptance Criteria

- A user can start from one vague industrial idea and know which intake document to use first.
- The assistant has explicit rules preventing premature SolidWorks spec generation.
- Every template has clear required sections and placeholder guidance.
- The CAD-neutral summary has a documented schema and example.
- The automated sorting machine example demonstrates the full path from idea to CAD-ready summary.
- Existing build/mutate/assembly/drawing behavior remains unchanged.
- The written handoff clearly tells a downstream AI when to return to existing `ai-sw-bridge` build docs.

---

## 17. Deferred Decisions and Defaults

These decisions are intentionally deferred to implementation details, with defaults chosen here so the plan has no ambiguous gaps.

- The example uses the automated sorting machine as the whole project, but the first CAD slice is the infeed conveyor.
- `cad_ready_summary.schema.json` is a formal JSON Schema from day one because this repo already treats schemas as first-class artifacts.
- The README persona row uses "Maker / system designer" to include both non-expert inventors and more systematic planners.

---

## 18. Spec Self-review Notes

- No CLI/MCP public surface is added in this first release, so `PUBLIC_API.md` and `extension_contract.md` do not need public-contract changes.
- The design keeps the current propose-approve-execute CAD safety model intact.
- The CAD-neutral JSON is intentionally not a SolidWorks spec; backend-specific translation remains a future phase.
- The only direct execution-path docs touched are routing docs that tell assistants when to use intake before build.
