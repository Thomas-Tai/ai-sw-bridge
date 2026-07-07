# Industrial Design Intake - Design Specification

> **Status:** DRAFT v2.1 for user review before writing-plans
> **Date:** 2026-07-07 (v2: fresh-user audit folded in; v2.1: final pre-plan audit pass, consistency fixes only)
> **Author:** Codex design session; revised after a fresh-user audit (20-year SolidWorks / PM / SE lens)
> **Ratified direction:** Approach A - a guide-and-template design package generator before any CLI/MCP implementation, plus one routing sentence in the MCP server instructions so the pre-CAD gate also exists on the MCP path.

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
- No change to existing SolidWorks build, mutate, assembly, drawing, checkpoint, or observe behavior. The single code touch is one routing sentence appended to `_SERVER_INSTRUCTIONS` in `src/ai_sw_bridge/mcp/server.py`; it adds no tool and changes no tool behavior.
- No zh-CN/zh-TW mirrors for the new intake docs in the first release. The intake tree ships English-only; only the six existing front-door mirrors are governed by the i18n staleness gate (see section 13).

---

## 5. Ratified Anchors

- **A1 - Approach A:** ship guide-and-template artifacts first, not a CLI/MCP surface.
- **A2 - Industrial Design Intake:** name the layer around engineering intake, not "prompt templates" or "wizard".
- **A3 - Pre-CAD gate:** the assistant must not produce a SolidWorks build spec until the intake package has reached a CAD-ready state. The gate is published on both assistant surfaces: repo-checkout assistants read it in `docs/AGENTS.md` and `docs/industrial_intake/AGENTS.md`; MCP-connected assistants receive a one-sentence routing rule in the server instructions (section 10.1).
- **A4 - CAD-neutral handoff:** the package describes product intent, modules, parameters, constraints, interfaces, manufacturing assumptions, and verification criteria without binding to SolidWorks API calls.
- **A5 - Existing bridge remains the execution layer:** SolidWorks remains the first backend, reached through existing spec, assembly, drawing, and observe surfaces.

---

## 6. User Journey

### 6.1 Maker path

1. User gives a one-sentence idea.
2. The assistant opens `docs/industrial_intake/AGENTS.md`.
3. The assistant creates the working package in the user's own project directory — `<project>/intake/`, one file per template, with `cad_ready_summary.json` later sitting beside the eventual `spec.json` and assembly manifests. The repo's `docs/industrial_intake/` tree holds only templates and examples, never user packages.
4. The assistant classifies the idea into a machine/system/product type and writes an initial `idea_brief.md`.
5. The assistant asks only the next most important questions. It does not ask the user to fill a long form.
6. Each answer updates the intake package.
7. When enough information exists, the assistant produces a CAD-ready summary and explains what is still assumed.
8. Only then does the assistant create or propose bridge-native SolidWorks specs.

### 6.2 Professional path

An experienced PM, systems engineer, or mechanical engineer does not go through the guided interview. `workflow.md` defines a second lane for them:

1. **Direct entry.** The professional already has requirements, architecture, BOM, and calculations in their own documents. They (or their assistant) map those documents onto the intake templates — or skip straight to filling `cad_ready_summary.json` — instead of being interviewed.
2. **Gate on artifacts, not on process.** The readiness criteria in section 9 check what exists, not how it was produced. A complete design passes the same gate in minutes.
3. **Then the build sequence.** The professional's real need is downstream: the ordered build-sequence contract in `solidworks_handoff.md` (section 11) that says in what order to drive the bridge commands and where the verify points are.

The same artifacts are produced either way. The value for expert users is traceability: every CAD choice is connected back to a requirement, interface, standard part, calculation, manufacturing assumption, or verification criterion.

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
    calculations.md
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
      calculations.md
      cots_selection.md
      top_down_cad_strategy.md
      dfm_dfa_checklist.md
      verification_plan.md
      cad_ready_summary.json
      solidworks_handoff.md
```

Existing surfaces to update:

- `README.md`: add a short persona-router row for "Maker / system designer". This edit makes the zh-CN and zh-TW README mirrors stale, so the same change retranslates the affected mirror sections (surgical section update, repo convention) to keep `tests/test_i18n_staleness.py` green.
- `docs/AGENTS.md`: add a pre-CAD instruction that vague industrial ideas should start with `docs/industrial_intake/AGENTS.md` (not mirrored; gate-free).
- `docs/operator_guide.md`: add one intake-routing paragraph — this is the file the README tells operators to hand to their AI, so the operator path must see the gate here.
- `docs/README.md`: add the `industrial_intake/` tree to the documentation index so the layer is reachable from nav.
- `docs/CAPABILITIES.md`: add "Industrial Design Intake" as a planning/handoff capability, not a build capability (doc-truth pins only the version string here; safe). While editing, correct the pre-existing stale surfaces line: it claims "21 command-line tools" but names only 20, and the repo ships 22 — `ai-sw-batch` and `ai-sw-doctor` are missing from the list even though `docs/PUBLIC_API.md` tiers all 22. Neither the count nor the list is pinned by doc-truth.
- `src/ai_sw_bridge/mcp/server.py`: append one routing sentence to `_SERVER_INSTRUCTIONS` (section 10.1). No contract test pins the instructions string, so there is no test churn.
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
- Production quantity, unit-cost target, and timeline (quantity is the primary DFM driver)
- Safety and compliance constraints, including a machine-safety risk scan (pinch points, guarding, e-stop, lockout) in the spirit of ISO 12100
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
- Applicable standards: drawing standard and projection angle (ISO/ASME), thread standard, fit conventions
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

### 8.6 `calculations.md`

First-order engineering sizing between the specs and any component selection. Selecting a motor without a torque calculation is guesswork; this file holds the numbers that justify COTS choices, and it is where deferred items like `motor_torque` get computed instead of parked.

Required sections:

- Sizing calculations (torque, speed, force, inertia, power) with formula and inputs
- Structural checks (deflection, load paths) where relevant
- Tolerance stack-up for critical fits, where relevant
- Power and duty-cycle budget
- Inputs traceable to `engineering_specs.md`; every result carries the `derived` status
- Open calculations that block COTS selection

### 8.7 `cots_selection.md`

Documents selected or candidate standard parts. Industrial CAD should depend on real or candidate COTS geometry before custom brackets are designed around it.

Required sections:

- Candidate motors, actuators, sensors, rails, bearings, belts, fasteners, controllers
- Vendor/model or generic standard
- Key dimensions
- CAD asset availability
- Selection rationale
- Open questions and substitutions

### 8.8 `top_down_cad_strategy.md`

Defines how the CAD model should be structured before any backend-specific spec is written.

Required sections:

- Global coordinate system
- Master origin and datum planes
- Skeleton/layout sketch strategy
- Global variables and parameter names bound through per-part `*_locals.txt` equation files: module-owned parameters follow the repo's proven module-prefix convention (e.g. `S1B_BELT_T`); machine-global parameters (e.g. `CONVEYOR_WIDTH`) may omit the module prefix
- Executable-by-bridge vs manual-in-GUI split: per-part `*_locals.txt` parameters, component placement, and mates are executable today; skeleton parts and in-context references are manual-in-GUI and must be marked as such
- Assembly structure
- Naming conventions for features, sketches, parts, and mates
- Rebuild and variant strategy

### 8.9 `dfm_dfa_checklist.md`

Manufacturing and assembly thinking before modeling details harden.

Required sections:

- Manufacturing process candidates
- Process fit at the target production quantity from `requirements.md`
- Material/process fit
- Tolerance and fit strategy
- Tool access and minimum feature limits
- 3D print or CNC constraints where applicable
- Assembly order
- Service access
- Inspection method

### 8.10 `verification_plan.md`

Defines how the model and eventual machine design are judged.

Required sections:

- Requirements traceability
- CAD checks
- Simulation or motion checks
- Physical prototype checks
- Operator acceptance checks
- Risks requiring manual engineering review

### 8.11 `cad_ready_summary.json`

The CAD-neutral handoff. It is not a SolidWorks spec. It is a compact structured representation that downstream agents can translate into backend-specific specs.

---

## 9. CAD-ready Summary Shape

The first release ships a schema document as documentation, not a runtime validator. The shape is intentionally conservative:

```json
{
  "schema_version": 1,
  "project": {
    "name": "automated_sorting_machine",
    "intent": "Sort mixed objects into bins by visual classification."
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
      "verification": "test"
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
    "manual_review_required": ["safety_guarding"]
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

Each state has entry criteria, owned by `workflow.md` and checked against artifacts, not process (this is what lets the professional direct-entry lane pass in minutes). The first five states are ordered and cumulative — each row's criteria include every row above it; `blocked` can be entered from any state:

| State | Entry criteria |
|---|---|
| `idea_only` | `idea_brief.md` exists. |
| `requirements_draft` | `requirements.md` and `engineering_specs.md` drafted; quantity, cost target, and safety scan captured. |
| `architecture_draft` | `system_architecture.md` and `module_breakdown.md` complete; interfaces enumerated with IDs. |
| `cad_ready_with_assumptions` | For the first build slice: calculations done, COTS candidates chosen (assumed values allowed), top-down strategy written including the executable split, DFM/DFA reviewed, verification plan drafted, `blocking_questions` empty, every assumption listed. |
| `cad_ready` | All of the above, plus no `assumed` status on slice-critical parameters and slice COTS confirmed with CAD assets. |
| `blocked` | Any blocking question with no resolution path. |

Schema notes:

- `parameters[].status` (and every numeric status in the package) enumerates exactly the five values of agent rule 5: `required`, `assumed`, `measured`, `vendor_provided`, `derived`.
- `interfaces[].type` enumerates at least `spatial`, `mechanical`, `electrical`, `data`, `thermal`.
- `cots[].critical_dimensions` maps a dimension name to `{ "value": number, "unit": string }`.
- The remaining closed vocabularies are fixed here so the schema file does not invent them: `modules[].cad_intent` = `part` | `assembly` | `fixture` | `purchased` (the four outcomes named in section 8.5); `modules[].build_buy` = `build` | `buy` | `mixed`; `cots[].selection_status` = `candidate` | `selected`; `cots[].cad_asset` = `available` | `missing`; `requirements[].priority` = `must` | `should` | `could`; `requirements[].verification` = `inspection` | `analysis` | `demonstration` | `test` (the classic IADT verification methods).

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
11. If the user already has a complete design (their own requirements, architecture, BOM, calculations), switch to the direct-entry lane: map their documents onto the package or fill `cad_ready_summary.json` directly. Map, do not interrogate.

### 10.1 MCP surface routing

An assistant connected through `ai-sw-mcp` never reads repo docs, so the gate must also exist in the server instructions. Append one sentence to `_SERVER_INSTRUCTIONS` (`src/ai_sw_bridge/mcp/server.py`), in the spirit of:

> "If the user starts from a vague product or machine idea rather than a concrete part or spec, run the Industrial Design Intake process first (`docs/industrial_intake/` in the repo, or ask the user for their intake package) before proposing any build."

This is a routing string, not a tool: the MCP tool contract, tool count, and write-gate behavior are unchanged, and no contract test pins the instructions text.

---

## 11. Handoff to Existing Bridge Surfaces

The first release uses a written handoff, not an automatic converter.

`solidworks_handoff.md` in each example explains:

- Which modules should become parts.
- Which modules should become assemblies.
- Which purchased components need imported STEP/IGES assets.
- Which parameters map to per-part `*_locals.txt` variables.
- Which existing bridge commands apply:
  - `ai-sw-import` for purchased-component STEP/IGES assets.
  - `ai-sw-build` for simple parts; `ai-sw-batch` for transactional multi-feature slices.
  - `ai-sw-assembly` for module placement and mates.
  - `ai-sw-drawing` for manufacturing drawings.
  - `ai-sw-properties` for metadata.
  - `ai-sw-configurations` for variant families.
  - `ai-sw-checkpoint` for state save/restore at step boundaries.
  - `ai-sw-observe`, `ai-sw-motion`, and `ai-sw-solver` for verification.

`solidworks_handoff.md` must also contain an **ordered build sequence**, not only a mapping. The required shape, matching the repo's verify-the-effect culture:

1. Import COTS assets (`ai-sw-import`); verify by import diagnostics.
2. Build custom parts (`ai-sw-build` / `ai-sw-batch`); verify each by its geometric effect (volume/bbox).
3. Assemble the slice (`ai-sw-assembly`); verify by interference and clearance checks.
4. Produce drawings (`ai-sw-drawing`) and metadata (`ai-sw-properties`).
5. Close the loop against the package: `ai-sw-observe equations` diffed against the declared parameters, plus the checks named in `verification_plan.md`.

Every step names its verify command and expected effect; `ai-sw-checkpoint` marks step boundaries.

Future automation can consume `cad_ready_summary.json` to generate initial bridge-native specs.

---

## 12. Example Project

Ship one complete example: `automated_sorting_machine`.

The example should stay compact enough to read, but complete enough to demonstrate professional thinking:

- The raw Maker idea.
- Requirements for throughput, sorting accuracy, object size, and footprint.
- A subsystem architecture: infeed, sensing, classification, diverter, bins, frame, controls.
- A calculations page that sizes the conveyor motor (torque, speed) and belt from the throughput requirement.
- A COTS selection page with candidate belt, motor, camera, sensor, controller, and fasteners.
- A top-down CAD plan with coordinate system and key parameters.
- DFM/DFA choices for prototype manufacturing.
- A CAD-ready JSON summary.
- A SolidWorks handoff note that maps the first buildable slice to existing bridge commands as an ordered, verify-pointed build sequence.

The example does not need to build the entire machine in SOLIDWORKS. It must show how to reach the first safe build slice.

---

## 13. Testing and Review

First-release verification is documentation-focused:

1. `python tools/doc_coverage_gate.py` must continue to pass (it is schema-type-driven; intake adds no feature types).
2. Existing doc-truth tests must not drift (`docs/CAPABILITIES.md` keeps its `v{version}` string; no derived counts change).
3. `tests/test_i18n_staleness.py` must pass: the README persona-row edit makes both README mirrors stale, so the same change retranslates the affected mirror sections (surgical section update). `docs/AGENTS.md`, `docs/operator_guide.md`, and `docs/CAPABILITIES.md` are not mirrored.
4. Add `tests/test_industrial_intake_docs.py` — committed, not optional, because the repo already has both patterns: (a) validate `cad_ready_summary.example.json` and the example project's summary against `cad_ready_summary.schema.json` with `jsonschema` (already a runtime dependency), and (b) assert every relative link in the intake tree resolves (the dead-link pattern from the i18n test).
5. Manually review all new templates for placeholders, contradictions, and unclear readiness rules.
6. MCP lane: `_SERVER_INSTRUCTIONS` is not pinned by any contract test; the routing sentence causes no test churn.

No SOLIDWORKS seat is required for this release.

---

## 14. Phased Implementation Plan

Phases are implementation order, not separate merges: land phases 1-3 as one change (or keep links forward-consistent per phase) so no gate ever sees a dangling reference.

### Phase 1 - Documentation spine

- Add `docs/industrial_intake/README.md`.
- Add `docs/industrial_intake/AGENTS.md`.
- Add `docs/industrial_intake/workflow.md` — both lanes (guided Maker flow and professional direct entry), the package-location convention, and the readiness-state entry-criteria table.
- Update `README.md` (persona row) with the surgical zh-CN/zh-TW mirror retranslation in the same change.
- Update `docs/AGENTS.md`, `docs/operator_guide.md`, `docs/README.md` (nav), and `docs/CAPABILITIES.md`.
- Append the routing sentence to `_SERVER_INSTRUCTIONS` in `src/ai_sw_bridge/mcp/server.py`.

### Phase 2 - Templates and schema document

- Add all Markdown templates (including `calculations.md`).
- Add `cad_ready_summary.schema.json` (statuses, interface types, and `critical_dimensions` shape per section 9).
- Add `cad_ready_summary.example.json`.

### Phase 3 - Complete example

- Add `examples/automated_sorting_machine/` under `docs/industrial_intake/examples/`.
- Include a `solidworks_handoff.md` that maps the design package to existing commands.

### Phase 4 - Review and gates

- Run documentation checks (doc-coverage gate, doc-truth, i18n staleness).
- Add and run `tests/test_industrial_intake_docs.py` (schema validation + link existence).
- Run the relevant offline test suite.

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
| Experts experience the gate as bureaucracy | Professionals abandon the layer | Direct-entry lane in `workflow.md`; readiness gates check artifacts, not process |
| MCP-connected assistants never see the gate | The layer is invisible in the primary product UX | One routing sentence in `_SERVER_INSTRUCTIONS`; full MCP intake tooling stays a future phase |

---

## 16. Acceptance Criteria

- A user can start from one vague industrial idea and know which intake document to use first.
- The user's own package location is defined (`<project>/intake/`), separate from repo templates and examples.
- The assistant has explicit rules preventing premature SolidWorks spec generation, on both surfaces: repo docs and the MCP server instructions.
- A professional with a complete design can enter through the direct-entry lane and reach the handoff without the guided interview.
- Every template has clear required sections and placeholder guidance.
- The CAD-neutral summary has a documented schema and example.
- The automated sorting machine example demonstrates the full path from idea to CAD-ready summary.
- Existing build/mutate/assembly/drawing behavior remains unchanged.
- The written handoff clearly tells a downstream AI when to return to existing `ai-sw-bridge` build docs, and gives an ordered build sequence with a named verify step per stage.

---

## 17. Deferred Decisions and Defaults

These decisions are intentionally deferred to implementation details, with defaults chosen here so the plan has no ambiguous gaps.

- The example uses the automated sorting machine as the whole project, but the first CAD slice is the infeed conveyor.
- `cad_ready_summary.schema.json` is a formal JSON Schema from day one because this repo already treats schemas as first-class artifacts.
- The README persona row uses "Maker / system designer" to include both non-expert inventors and more systematic planners.
- The intake docs ship English-only in the first release; mirroring the intake tree is a future decision.
- User packages live in the user's project at `<project>/intake/`; the repo tree holds only templates and examples.

---

## 18. Spec Self-review Notes

- No CLI/MCP public surface is added in this first release, so `PUBLIC_API.md` and `extension_contract.md` do not need public-contract changes. The `_SERVER_INSTRUCTIONS` routing sentence is informational text, not a tool or contract change, and no test pins it.
- The design keeps the current propose-approve-execute CAD safety model intact.
- The CAD-neutral JSON is intentionally not a SolidWorks spec; backend-specific translation remains a future phase.
- The only execution-path touches are routing surfaces (README, `docs/AGENTS.md`, `docs/operator_guide.md`, the docs nav index, and the MCP instructions string) that tell assistants when to use intake before build.
- This v2 folds in the 2026-07-07 fresh-user audit: i18n gate handling, MCP-path routing, `calculations.md`, quantity/cost capture, executable-split top-down strategy, readiness entry criteria, professional direct-entry lane, ordered build-sequence contract, package-location convention, and the committed docs test.
- The v2.1 final pre-plan audit (same day) made consistency-only fixes: the illustrative JSON no longer parks `motor_torque` for manual review (section 8.6 computes it in `calculations.md`); `project.maturity` was dropped as redundant with `readiness.state`; the remaining schema vocabularies (`cad_intent`, `build_buy`, `selection_status`, `cad_asset`, `priority`, `verification`) are pinned in section 9; the readiness-state table is explicitly cumulative; `calculations.md` gains tolerance stack-up; the parameter-naming rule distinguishes module-owned from machine-global names; and the stale `docs/CAPABILITIES.md` surfaces line is corrected in passing. Every command, path, and gate claim was re-verified against the repo (`ai-sw-observe equations` exists; `*_locals.txt` is the real convention; `_SERVER_INSTRUCTIONS` is pinned by no test; the dead-link pattern lives at `tests/test_i18n_staleness.py`).
