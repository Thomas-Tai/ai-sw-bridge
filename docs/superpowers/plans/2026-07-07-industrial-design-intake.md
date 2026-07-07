# Industrial Design Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Industrial Design Intake layer — a docs/templates/example tree that turns a raw product idea (or a professional's complete design) into a CAD-ready, CAD-neutral design package before any SolidWorks spec is written — plus one routing sentence in the MCP server instructions.

**Architecture:** Everything lands under `docs/industrial_intake/` (spine + templates + one complete example), guarded by a new committed test (`tests/test_industrial_intake_docs.py`: JSON-Schema validation + dead-link walk). Five existing routing surfaces then point into the tree (root README persona row + zh-CN/zh-TW mirror retranslation, `docs/AGENTS.md`, `docs/operator_guide.md`, `docs/README.md` nav, `docs/CAPABILITIES.md`), and one sentence is appended to `_SERVER_INSTRUCTIONS` in `src/ai_sw_bridge/mcp/server.py`. Tasks are ordered bottom-up (content before links into it) so **no commit ever contains a dangling reference** — this satisfies the spec's "land phases 1-3 as one change" rule as one branch sequence.

**Tech Stack:** Markdown, JSON Schema draft 2020-12, `jsonschema` (already a runtime dependency), `pytest`. No SOLIDWORKS seat required anywhere in this plan.

**Spec:** `docs/superpowers/specs/2026-07-07-industrial-design-intake-design.md` (v2.2, commit `c629f05`). Section references (§) below point there.

## Global Constraints

- Work on the current branch `docs/commercial-elevation`. Do **not** push; the user pushes.
- The working tree has an **uncommitted user change to `.gitignore`**. NEVER run `git add -A`, `git add .`, or `git add -u`. Every commit stages explicit paths only, exactly as written in each commit step.
- No `Co-Authored-By` or any other trailer in commit messages (CONTRIBUTING.md:62).
- All new intake docs are **English-only** (spec §4). The ONLY translated content in this plan is the README persona-router row in the two README mirrors (Task 9).
- No new CLI command, no new MCP tool, no change to any tool behavior (spec §4). The single code touch is the `_SERVER_INSTRUCTIONS` string append (Task 10).
- Every relative Markdown link inside `docs/industrial_intake/` must resolve on disk — Task 7's test enforces this forever. Use forward slashes in links.
- Python files must pass `black --check` (black==25.12.0, target py310, 88 cols) and `flake8`. Never write `assert not x, (f"...")` — parenthesized-tuple asserts fail the repo's black gate.
- The i18n gate (`tests/test_i18n_staleness.py`) works on `translated-from: <sha>` frontmatter in each mirror; the sha must already exist in history. Therefore the README edit and the mirror retranslation are **two separate commits in the same branch push** (Task 9 explains the exact dance).
- Preflight (run once before Task 1): `git -C . status --short` must show only `M .gitignore`; `python -c "import jsonschema, pytest"` must succeed (else `pip install -e ".[dev]"`).
- Vocabulary pins from spec §9 — the schema is the single source of truth downstream, but these exact enums are non-negotiable:
  - `parameters[].status`: `required | assumed | measured | vendor_provided | derived`
  - `interfaces[].type`: `spatial | mechanical | electrical | data | thermal`
  - `modules[].cad_intent`: `part | assembly | fixture | purchased`
  - `modules[].build_buy`: `build | buy | mixed`
  - `cots[].selection_status`: `candidate | selected`; `cots[].cad_asset`: `available | missing`
  - `requirements[].priority`: `must | should | could`; `requirements[].verification`: `inspection | analysis | demonstration | test`
  - `readiness.state`: `idea_only | requirements_draft | architecture_draft | cad_ready_with_assumptions | cad_ready | blocked`

## File Map

| Path | Task | Responsibility |
|---|---|---|
| `docs/industrial_intake/templates/cad_ready_summary.schema.json` | 1 | Formal JSON Schema for the CAD-neutral handoff |
| `docs/industrial_intake/templates/cad_ready_summary.example.json` | 1 | Minimal valid summary (spec §9 verbatim) |
| `docs/industrial_intake/templates/*.md` (10 files) | 2 | Fill-in templates, one per intake artifact (§8.1–8.10) |
| `docs/industrial_intake/examples/automated_sorting_machine/*.md` (5+5 files) | 3, 4 | Complete worked example (§12) |
| `.../automated_sorting_machine/cad_ready_summary.json` + `solidworks_handoff.md` | 5 | Example handoff: valid summary + ordered build sequence (§11) |
| `docs/industrial_intake/README.md`, `AGENTS.md`, `workflow.md` | 6 | Spine: overview, agent contract (§10), both lanes + states (§6, §9) |
| `tests/test_industrial_intake_docs.py` | 7 | Committed gate: schema validation + dead-link walk (§13.4) |
| `docs/AGENTS.md`, `docs/operator_guide.md`, `docs/README.md`, `docs/CAPABILITIES.md` | 8 | Non-mirrored routing surfaces (§7) |
| `README.md` + `docs/i18n/zh-CN/README.md` + `docs/i18n/zh-TW/README.md` | 9 | Persona row + surgical mirror retranslation (§7, §13.3) |
| `src/ai_sw_bridge/mcp/server.py` | 10 | One routing sentence in `_SERVER_INSTRUCTIONS` (§10.1) |

---

### Task 1: CAD-ready summary schema + example JSON

**Files:**
- Create: `docs/industrial_intake/templates/cad_ready_summary.schema.json`
- Create: `docs/industrial_intake/templates/cad_ready_summary.example.json`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: the schema every later JSON must validate against; Task 5's example-project summary and Task 7's test both consume these two exact paths. The enums are the Global Constraints vocabulary pins.

- [ ] **Step 1: Create the directory and write the schema**

Create `docs/industrial_intake/templates/cad_ready_summary.schema.json` with exactly:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CAD-ready summary — Industrial Design Intake handoff",
  "description": "CAD-neutral handoff produced by the Industrial Design Intake process (docs/industrial_intake/). It describes product intent, modules, parameters, constraints, interfaces, manufacturing assumptions, and readiness — never backend-specific CAD calls. Version 1.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "project",
    "units",
    "requirements",
    "parameters",
    "modules",
    "interfaces",
    "cots",
    "manufacturing",
    "cad_strategy",
    "readiness"
  ],
  "properties": {
    "schema_version": { "const": 1 },
    "project": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "intent"],
      "properties": {
        "name": { "type": "string", "pattern": "^[a-z0-9_]+$" },
        "intent": { "type": "string", "minLength": 1 }
      }
    },
    "units": {
      "type": "object",
      "additionalProperties": false,
      "required": ["length", "mass", "angle"],
      "properties": {
        "length": { "type": "string" },
        "mass": { "type": "string" },
        "angle": { "type": "string" }
      }
    },
    "requirements": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "text", "priority", "verification"],
        "properties": {
          "id": { "type": "string", "pattern": "^REQ-[0-9]{3,}$" },
          "text": { "type": "string", "minLength": 1 },
          "priority": { "enum": ["must", "should", "could"] },
          "verification": {
            "enum": ["inspection", "analysis", "demonstration", "test"]
          }
        }
      }
    },
    "parameters": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "value", "unit", "status", "rationale"],
        "properties": {
          "name": { "type": "string", "pattern": "^[A-Z][A-Z0-9_]*$" },
          "value": { "type": "number" },
          "unit": { "type": "string" },
          "status": {
            "enum": ["required", "assumed", "measured", "vendor_provided", "derived"]
          },
          "rationale": { "type": "string", "minLength": 1 }
        }
      }
    },
    "modules": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "name", "role", "cad_intent", "interfaces", "build_buy"],
        "properties": {
          "id": { "type": "string", "pattern": "^MOD-[0-9]{3,}$" },
          "name": { "type": "string", "pattern": "^[a-z0-9_]+$" },
          "role": { "type": "string", "minLength": 1 },
          "cad_intent": { "enum": ["part", "assembly", "fixture", "purchased"] },
          "interfaces": {
            "type": "array",
            "items": { "type": "string", "pattern": "^IF-[0-9]{3,}$" }
          },
          "build_buy": { "enum": ["build", "buy", "mixed"] }
        }
      }
    },
    "interfaces": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "from", "to", "type", "description"],
        "properties": {
          "id": { "type": "string", "pattern": "^IF-[0-9]{3,}$" },
          "from": { "type": "string" },
          "to": { "type": "string" },
          "type": { "enum": ["spatial", "mechanical", "electrical", "data", "thermal"] },
          "description": { "type": "string", "minLength": 1 }
        }
      }
    },
    "cots": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "category",
          "selection_status",
          "model",
          "critical_dimensions",
          "cad_asset"
        ],
        "properties": {
          "id": { "type": "string", "pattern": "^COTS-[0-9]{3,}$" },
          "category": { "type": "string", "minLength": 1 },
          "selection_status": { "enum": ["candidate", "selected"] },
          "model": { "type": "string", "minLength": 1 },
          "critical_dimensions": {
            "type": "object",
            "additionalProperties": false,
            "patternProperties": {
              "^[a-z0-9_]+$": {
                "type": "object",
                "additionalProperties": false,
                "required": ["value", "unit"],
                "properties": {
                  "value": { "type": "number" },
                  "unit": { "type": "string" }
                }
              }
            }
          },
          "cad_asset": { "enum": ["available", "missing"] }
        }
      }
    },
    "manufacturing": {
      "type": "object",
      "additionalProperties": false,
      "required": ["candidate_processes", "tolerance_policy", "notes"],
      "properties": {
        "candidate_processes": {
          "type": "array",
          "minItems": 1,
          "items": { "type": "string" }
        },
        "tolerance_policy": { "type": "string", "minLength": 1 },
        "notes": { "type": "array", "items": { "type": "string" } }
      }
    },
    "cad_strategy": {
      "type": "object",
      "additionalProperties": false,
      "required": ["coordinate_system", "top_down", "global_variables", "backend_targets"],
      "properties": {
        "coordinate_system": { "type": "string", "minLength": 1 },
        "top_down": { "type": "boolean" },
        "global_variables": {
          "type": "array",
          "items": { "type": "string", "pattern": "^[A-Z][A-Z0-9_]*$" }
        },
        "backend_targets": {
          "type": "array",
          "minItems": 1,
          "items": { "type": "string" }
        }
      }
    },
    "readiness": {
      "type": "object",
      "additionalProperties": false,
      "required": ["state", "blocking_questions", "manual_review_required"],
      "properties": {
        "state": {
          "enum": [
            "idea_only",
            "requirements_draft",
            "architecture_draft",
            "cad_ready_with_assumptions",
            "cad_ready",
            "blocked"
          ]
        },
        "blocking_questions": { "type": "array", "items": { "type": "string" } },
        "manual_review_required": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

- [ ] **Step 2: Write the minimal example (spec §9 verbatim)**

Create `docs/industrial_intake/templates/cad_ready_summary.example.json` with exactly:

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

- [ ] **Step 3: Validate the example against the schema right now**

Run (from the repo root):

```powershell
python -c "import json, jsonschema; d='docs/industrial_intake/templates/'; jsonschema.validate(json.load(open(d+'cad_ready_summary.example.json', encoding='utf-8')), json.load(open(d+'cad_ready_summary.schema.json', encoding='utf-8'))); print('VALID')"
```

Expected output: `VALID`. If it raises `ValidationError`, fix the JSON — do not loosen the schema.

- [ ] **Step 4: Prove the schema can reject (spot check)**

```powershell
python -c "import json, jsonschema; d='docs/industrial_intake/templates/'; doc=json.load(open(d+'cad_ready_summary.example.json', encoding='utf-8')); doc['readiness']['state']='totally_ready';
try:
    jsonschema.validate(doc, json.load(open(d+'cad_ready_summary.schema.json', encoding='utf-8'))); print('BUG: accepted')
except jsonschema.ValidationError:
    print('REJECTS-INVALID')"
```

Expected output: `REJECTS-INVALID`.

- [ ] **Step 5: Commit**

```powershell
git add docs/industrial_intake/templates/cad_ready_summary.schema.json docs/industrial_intake/templates/cad_ready_summary.example.json
git commit -m "docs(intake): add cad_ready_summary JSON Schema + minimal example"
```

---

### Task 2: The ten intake artifact templates

**Files:**
- Create: `docs/industrial_intake/templates/idea_brief.md`
- Create: `docs/industrial_intake/templates/requirements.md`
- Create: `docs/industrial_intake/templates/engineering_specs.md`
- Create: `docs/industrial_intake/templates/system_architecture.md`
- Create: `docs/industrial_intake/templates/module_breakdown.md`
- Create: `docs/industrial_intake/templates/calculations.md`
- Create: `docs/industrial_intake/templates/cots_selection.md`
- Create: `docs/industrial_intake/templates/top_down_cad_strategy.md`
- Create: `docs/industrial_intake/templates/dfm_dfa_checklist.md`
- Create: `docs/industrial_intake/templates/verification_plan.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the template set whose H2 headings are the spec §8 "Required sections" — Task 6's workflow.md and Task 7's tree test reference these exact filenames. Each template's first line is an H1; each contains the line `> Copy this file to \`<project>/intake/\` and fill it in. Delete guidance lines as you go.`

Every value the user writes must carry one of the five statuses: `required`, `assumed`, `measured`, `vendor_provided`, `derived` (Global Constraints). The templates below say so where numbers appear.

- [ ] **Step 1: Write `idea_brief.md`**

```markdown
# Idea Brief

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

Captures the raw idea before any engineering language touches it. Preserve the
user's own words — later documents refine, this one records.

## Raw idea

*(The idea exactly as first stated, quoted verbatim.)*

## Intended job-to-be-done

*(What outcome does the user actually want? One paragraph.)*

## Target user/operator

*(Who runs this? Skill level, environment, how often.)*

## Target object/material/workpiece

*(What does the machine act on? Size range, material, weight, condition.)*

## Desired output

*(What does "done" look like per cycle? Sorted bins, a finished part, a report?)*

## Known constraints

*(Budget, space, power, noise, existing equipment it must fit — anything already fixed.)*

## Unknowns blocking engineering decisions

*(List every open question that stops a requirement from being written. These
become the interview questions.)*
```

- [ ] **Step 2: Write `requirements.md`**

```markdown
# Requirements

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

What the system must do — never how. Each requirement gets an ID (`REQ-001`…),
a priority (`must` / `should` / `could`), and a verification method
(`inspection` / `analysis` / `demonstration` / `test`).

## Functional requirements

*(REQ-xxx rows: what it does — sort, feed, cut, count…)*

## Performance requirements

*(Throughput, accuracy, cycle time — numeric and testable.)*

## Environmental requirements

*(Temperature, dust, humidity, indoor/outdoor, washdown?)*

## Physical constraints

*(Footprint, height, mass, doorway/bench limits.)*

## Production quantity, unit-cost target, and timeline

*(How many will be built, at what target cost, by when. Quantity is the primary
DFM driver — a one-off and a 10,000-unit run get different designs.)*

## Safety and compliance constraints

*(Machine-safety risk scan in the spirit of ISO 12100: pinch points, guarding,
e-stop, lockout/tagout, sharp edges, hot surfaces. List each hazard and the
intended control.)*

## Maintenance and serviceability requirements

*(What gets replaced/cleaned, how often, by whom, with what access.)*

## Acceptance criteria

*(The checks that mean "the machine is accepted" — each traceable to a REQ-xxx.)*
```

- [ ] **Step 3: Write `engineering_specs.md`**

```markdown
# Engineering Specs

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

Numeric, testable engineering assumptions. Estimates are allowed — but **every
number carries a status**: `required`, `assumed`, `measured`, `vendor_provided`,
or `derived`.

## Throughput, speed, accuracy, repeatability

*(Numbers with units and status, e.g. "belt speed 0.1 m/s (derived)".)*

## Payload, force, torque, power, duty cycle

*(Worst-case moving mass, peak forces, continuous vs intermittent duty.)*

## Dimensional envelope and mass

*(Overall machine envelope; per-module mass budget if lifting matters.)*

## Materials and surface constraints

*(Food-safe? ESD? Corrosion? Contact-surface hardness?)*

## Control and signal requirements

*(Sensors in, actuators out, buses, voltages — enough to size the electrical interfaces.)*

## Tolerance policy

*(The default tolerance class and where tighter fits are actually needed.)*

## Applicable standards

*(Drawing standard and projection angle — ISO or ASME, stated explicitly;
thread standard, e.g. ISO metric coarse; fit conventions, e.g. ISO 286 H7/g6.)*

## Units and reference coordinate conventions

*(Length/mass/angle units; which way X/Y/Z point; where the machine origin sits.)*
```

- [ ] **Step 4: Write `system_architecture.md`**

```markdown
# System Architecture

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

The high-level decomposition, before CAD. Name subsystems by role, not by part.

## Subsystems

*(One line each: name + single responsibility.)*

## Interfaces

*(IF-xxx list: from → to, type — spatial / mechanical / electrical / data /
thermal — and one sentence of contract.)*

## Data flow

*(What information moves between subsystems, in what direction?)*

## Material flow

*(The workpiece's path through the machine, station by station.)*

## Energy and force flow

*(Where power enters, how it becomes motion/force, where loads react to ground.)*

## Sensor/actuator/control boundaries

*(Which subsystem owns each sensor and actuator; where control decisions live.)*

## Failure modes and safe states

*(For each subsystem: how it fails, what the machine does when it does.)*
```

- [ ] **Step 5: Write `module_breakdown.md`**

```markdown
# Module Breakdown

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

The bridge between architecture and CAD: every module here may become a part,
an assembly, a fixture, or a purchased component (`cad_intent`).

## Module list

*(MOD-xxx table: id, snake_case name, cad_intent — part / assembly / fixture /
purchased.)*

## Module responsibility

*(One sentence per module: what it alone is accountable for.)*

## Inputs and outputs

*(Per module: what enters, what leaves — material, signal, force.)*

## Mechanical interfaces

*(Mounting patterns, mating faces, alignment features — reference IF-xxx ids.)*

## Electrical/control interfaces

*(Connectors, voltages, signal types — reference IF-xxx ids.)*

## Dependencies

*(Which module's geometry must exist before which — this drives build order.)*

## Build/buy decision

*(Per module: build / buy / mixed, with one line of why.)*
```

- [ ] **Step 6: Write `calculations.md`**

```markdown
# Calculations

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

First-order sizing between the specs and any component selection. Selecting a
motor without a torque calculation is guesswork — this file holds the numbers
that justify COTS choices. Every input is traceable to `engineering_specs.md`;
every result carries the `derived` status.

## Sizing calculations

*(One block per calc: purpose, formula, inputs (with their statuses), result
(derived), safety factor. Torque, speed, force, inertia, power.)*

## Structural checks

*(Deflection, load paths, bolted-joint sanity — where relevant.)*

## Tolerance stack-up

*(For critical fits, where relevant: chain of dimensions, worst-case sum,
verdict against the fit requirement.)*

## Power and duty-cycle budget

*(Sum of actuator loads vs supply; continuous vs peak.)*

## Open calculations that block COTS selection

*(Anything not yet computed that gates a component choice. Empty when ready.)*
```

- [ ] **Step 7: Write `cots_selection.md`**

```markdown
# COTS Selection

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

Standard parts before custom geometry: industrial CAD depends on real (or
candidate) purchased-component geometry before brackets are designed around it.

## Candidate components

*(COTS-xxx table: motors, actuators, sensors, rails, bearings, belts,
fasteners, controllers.)*

## Vendor/model or generic standard

*(Per item: a specific vendor part number, or the generic standard it must meet.)*

## Key dimensions

*(The dimensions custom parts will reference — with status: `vendor_provided`
once from a datasheet, `assumed` until then.)*

## CAD asset availability

*(Per item: `available` (STEP/IGES on hand or in SW Toolbox) or `missing`.)*

## Selection rationale

*(Per item: one line tying it to a calculation or requirement.)*

## Open questions and substitutions

*(Unconfirmed specs, acceptable substitutes, lead-time risks.)*
```

- [ ] **Step 8: Write `top_down_cad_strategy.md`**

```markdown
# Top-down CAD Strategy

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

How the CAD model is structured — decided before any backend-specific spec is
written.

## Global coordinate system

*(Where the machine origin sits; which way X/Y/Z point. Must match
`engineering_specs.md`.)*

## Master origin and datum planes

*(The named planes everything references — base plane, belt-top plane,
centerline plane.)*

## Skeleton/layout sketch strategy

*(Which layout sketches drive which modules. NOTE: skeleton parts and
in-context references are **manual-in-GUI** — the bridge cannot create them;
mark them as such.)*

## Global variables and parameter names

*(Bound through per-part `*_locals.txt` equation files. Module-owned parameters
carry the module prefix (e.g. `S1B_BELT_T`); machine-global parameters (e.g.
`CONVEYOR_WIDTH`) may omit it. List every parameter, its owner, and its status.)*

## Executable-by-bridge vs manual-in-GUI split

*(Executable today: per-part `*_locals.txt` parameters, part builds, component
placement, and mates. Manual-in-GUI: skeleton parts, in-context references.
Every manual step must be listed here so nobody waits on the bridge for it.)*

## Assembly structure

*(The assembly tree: which parts under which sub-assemblies, and why.)*

## Naming conventions

*(Features, sketches, parts, mates — e.g. `SK_<purpose>`, `EX_<purpose>`,
`<MODULE>_<part>.SLDPRT`, `MATE_<a>_<b>`.)*

## Rebuild and variant strategy

*(What changes when a parameter changes; which variants are expected and how
they materialize — e.g. multi-file variants via `ai-sw-configurations`.)*
```

- [ ] **Step 9: Write `dfm_dfa_checklist.md`**

```markdown
# DFM/DFA Checklist

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

Manufacturing and assembly thinking before modeling details harden.

## Manufacturing process candidates

*(Per custom part family: 3D print, laser-cut plate, CNC, sheet-metal fold…)*

## Process fit at the target production quantity

*(Check each candidate process against the quantity in `requirements.md` —
what is right at qty 1 is wrong at qty 1000.)*

## Material/process fit

*(Does the chosen material suit the process — printable, laser-cuttable,
machinable?)*

## Tolerance and fit strategy

*(Which fits are clearance-by-default; where the tolerance stack-up from
`calculations.md` demands tighter.)*

## Tool access and minimum feature limits

*(Minimum wall, minimum hole, internal corners, tool reach.)*

## 3D print or CNC constraints

*(Overhang angles, support strategy, workholding — where applicable.)*

## Assembly order

*(The sequence a human (or fixture) assembles the machine in; flag any
impossible-to-reach fastener now.)*

## Service access

*(What must be replaceable without tearing the machine down.)*

## Inspection method

*(How each critical dimension gets checked — calipers, gauge, CMM, or a bridge
observe check.)*
```

- [ ] **Step 10: Write `verification_plan.md`**

```markdown
# Verification Plan

> Copy this file to `<project>/intake/` and fill it in. Delete guidance lines as you go.

How the model — and eventually the machine — is judged. Every check traces to a
requirement.

## Requirements traceability

*(Table: REQ-xxx → verification method (inspection / analysis / demonstration /
test) → the concrete check below that covers it.)*

## CAD checks

*(Model-level gates: zero interference, minimum clearances, minimum wall on
printed parts, equations matching the declared parameters.)*

## Simulation or motion checks

*(Mate-travel/motion studies, load cases — where relevant.)*

## Physical prototype checks

*(The tests run on the built prototype, with pass thresholds.)*

## Operator acceptance checks

*(What the operator confirms before accepting: e-stop works, guards in place,
noise acceptable.)*

## Risks requiring manual engineering review

*(Anything an automated check cannot judge — safety guarding always lands here.)*
```

- [ ] **Step 11: Verify headings match the spec**

Run:

```powershell
python -c "from pathlib import Path; import sys; t=Path('docs/industrial_intake/templates'); files=[p.name for p in sorted(t.glob('*.md'))]; print(files); sys.exit(0 if len(files)==10 else 1)"
```

Expected: a list of the 10 template names, exit 0. Then open spec §8.1–§8.10 side-by-side and confirm every "Required sections" bullet has a matching H2 in its template (the wording above already matches; this is a read-through, not an edit).

- [ ] **Step 12: Commit**

```powershell
git add docs/industrial_intake/templates
git commit -m "docs(intake): add the ten intake artifact templates"
```

---

### Task 3: Example project — definition documents

**Files:**
- Create: `docs/industrial_intake/examples/automated_sorting_machine/idea_brief.md`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/requirements.md`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/engineering_specs.md`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/system_architecture.md`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/module_breakdown.md`

**Interfaces:**
- Consumes: template headings from Task 2 (same H2 set, filled in).
- Produces: the REQ/MOD/IF ids and the parameter names that Tasks 4 and 5 reuse **verbatim**: requirements `REQ-001`–`REQ-006`; modules `MOD-001 infeed_conveyor`, `MOD-002 vision_module`, `MOD-003 diverter_unit`, `MOD-004 bin_array`, `MOD-005 frame`, `MOD-006 controls`; interfaces `IF-001`–`IF-006`; parameters `CONVEYOR_WIDTH` (120 mm), `INF_BELT_L` (600 mm), `INF_ROLLER_D` (40 mm), `INF_FRAME_H` (150 mm), `INF_BELT_SPEED` (0.1 m/s, derived). First build slice = the infeed conveyor (spec §17).

- [ ] **Step 1: Write `idea_brief.md`**

```markdown
# Idea Brief — Automated Sorting Machine

## Raw idea

> "I want to build an automated sorting machine."

## Intended job-to-be-done

Take a mixed stream of small objects, identify each one visually, and drop it
into the right bin — so a person no longer sorts by hand.

## Target user/operator

A single hobbyist/small-workshop operator; no PLC experience; comfortable with
a PC and basic hand tools. Runs the machine attended, a few hours at a time.

## Target object/material/workpiece

Rigid objects up to 100 × 100 × 100 mm and 0.5 kg (e.g. plastic parts, small
boxed goods). Dry, non-fragile, one object at a time on the belt.

## Desired output

Objects land in one of at least three bins by visual class; a sort log is nice
to have (could).

## Known constraints

- Fits on a workbench: about 1200 × 800 mm footprint.
- Mains 230 V AC available; low-voltage DC preferred inside the machine.
- Prototype budget-sensitive: prefer COTS and laser-cut/printed parts.

## Unknowns blocking engineering decisions

- Exact object mix and the visual classes to separate. **(assumed 3 classes
  for v1 — drives bin count)**
- Required throughput. **(assumed 30 objects/min for v1 — drives belt speed)**
- Whether bins must be operator-swappable during a run. (deferred, not
  blocking the first slice)
```

- [ ] **Step 2: Write `requirements.md`**

```markdown
# Requirements — Automated Sorting Machine

## Functional requirements

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| REQ-001 | Convey objects one at a time through a sensing zone at ≥ 30 objects/min | must | test |
| REQ-002 | Classify each object into one of ≥ 3 visual classes with ≥ 95 % accuracy on the target set | must | test |
| REQ-004 | Divert each classified object into its matching bin (≥ 3 bins) | must | demonstration |

## Performance requirements

- REQ-001 sets the pace: 30 objects/min at 200 mm object pitch (pitch assumed).
- REQ-002 sets sensing dwell: the camera needs ≥ 100 ms unobstructed view per
  object (assumed until the vision stack is chosen).

## Environmental requirements

Indoor workshop, 10–35 °C, dust typical of a workshop; no washdown.

## Physical constraints

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| REQ-003 | Handle objects up to 100 × 100 × 100 mm and 0.5 kg | must | analysis |
| REQ-005 | Whole machine fits 1200 × 800 mm bench footprint | should | inspection |

## Production quantity, unit-cost target, and timeline

- Quantity: **1 prototype now, up to 5 pilot units later** — DFM targets
  laser-cut plate + FDM printing, not tooling.
- Unit-cost target: prototype bill of materials ≤ the cost of a mid-range
  hobby 3D printer (assumed ceiling; refine after COTS quotes).
- Timeline: first buildable slice (infeed conveyor) modeled first; whole
  machine follows slice by slice.

## Safety and compliance constraints

Machine-safety risk scan (in the spirit of ISO 12100):

| ID | Requirement | Priority | Verification |
|---|---|---|---|
| REQ-006 | An e-stop cuts all motion; belt nip points and the diverter sweep are guarded | must | demonstration |

- Hazards identified: belt/roller nip points (guard strips), diverter sweep
  (side guards), mains wiring (enclosed in the controls module).
- Guarding design is flagged `safety_guarding` for manual engineering review —
  no automated check signs this off.

## Maintenance and serviceability requirements

- Belt replaceable without disassembling the frame (slotted tensioner).
- Bins removable without tools.

## Acceptance criteria

- 100-object mixed run sorts ≥ 95 % correctly (covers REQ-001, REQ-002, REQ-004).
- Bench check confirms footprint and object-envelope limits (REQ-003, REQ-005).
- E-stop and guard inspection passes (REQ-006).
```

- [ ] **Step 3: Write `engineering_specs.md`**

```markdown
# Engineering Specs — Automated Sorting Machine

Every number carries a status: `required`, `assumed`, `measured`,
`vendor_provided`, or `derived`.

## Throughput, speed, accuracy, repeatability

| Quantity | Value | Status | Source |
|---|---|---|---|
| Throughput | 30 objects/min | required | REQ-001 |
| Object pitch on belt | 200 mm | assumed | one object length + gap |
| Belt speed `INF_BELT_SPEED` | 0.1 m/s | derived | calculations.md §1 |
| Classification accuracy | ≥ 95 % | required | REQ-002 |

## Payload, force, torque, power, duty cycle

| Quantity | Value | Status | Source |
|---|---|---|---|
| Max object mass | 0.5 kg | required | REQ-003 |
| Objects on belt simultaneously | 3 | derived | INF_BELT_L / pitch |
| Belt mass | 0.3 kg | assumed | typical PU flat belt this size |
| Belt-on-bed friction coefficient | 0.35 | assumed | slider bed, conservative |
| Drive torque required | 0.25 N·m (incl. SF 2.0) | derived | calculations.md §2 |
| Duty | continuous while running | required | operating pattern |

## Dimensional envelope and mass

| Quantity | Value | Status | Source |
|---|---|---|---|
| `CONVEYOR_WIDTH` | 120 mm | assumed | 100 mm object + 2 × 10 mm clearance |
| `INF_BELT_L` (roller-center to roller-center) | 600 mm | assumed | sensing zone + a pitch either side |
| `INF_ROLLER_D` | 40 mm | assumed | candidate crowned roller |
| `INF_FRAME_H` (belt top above baseplate) | 150 mm | assumed | bin clearance under discharge |
| Machine envelope | ≤ 1200 × 800 mm | required | REQ-005 |

## Materials and surface constraints

Frame plates 5052 aluminium 3 mm (laser-cut); printed brackets PETG; belt
food-grade PU not required (dry rigid goods).

## Control and signal requirements

One stepper (belt drive), one diverter actuator (later slice), one USB camera,
one e-stop circuit; controller is a single-board computer + stepper driver
(candidate). 24 V DC internal bus (assumed).

## Tolerance policy

`prototype_clearance`: default ±0.2 mm on laser-cut plate; clearance fits
everywhere except roller bearing seats (see calculations.md tolerance
stack-up).

## Applicable standards

- Drawing standard: **ISO 128, third-angle projection, stated on every sheet**
  (assumed — flip to first-angle only if a supplier demands it).
- Threads: ISO metric coarse (M3/M5).
- Fits: ISO 286; bearing seats H7 (deferred to the roller slice detail).

## Units and reference coordinate conventions

mm / kg / deg. X = belt travel direction, Y = across the belt, Z = up.
Machine origin: frame center, front face, bottom
(`machine_origin_at_frame_center_front_bottom`).
```

- [ ] **Step 4: Write `system_architecture.md`**

```markdown
# System Architecture — Automated Sorting Machine

## Subsystems

- **infeed_conveyor** — moves objects through the sensing zone at constant speed.
- **vision_module** — camera + lighting over the belt; classifies each object.
- **diverter_unit** — sweeps a classified object off the belt into its bin lane.
- **bin_array** — three (or more) bins receiving diverted objects.
- **frame** — the structure everything mounts to; carries loads to the bench.
- **controls** — SBC + stepper driver + PSU + e-stop; runs the classify-divert loop.

## Interfaces

| ID | From | To | Type | Contract |
|---|---|---|---|---|
| IF-001 | vision_module | infeed_conveyor | spatial | camera FOV covers the belt sensing zone, unobstructed |
| IF-002 | infeed_conveyor | frame | mechanical | slotted bolt pattern; belt-top height = `INF_FRAME_H` |
| IF-003 | diverter_unit | infeed_conveyor | spatial | paddle sweep envelope clears belt + object by ≥ 2 mm |
| IF-004 | infeed_conveyor | controls | electrical | stepper 4-wire to driver; e-stop in series |
| IF-005 | vision_module | controls | data | USB camera stream |
| IF-006 | diverter_unit | bin_array | spatial | diverted-object trajectory lands inside the bin mouth |

## Data flow

camera frame → controls (classify) → diverter command; belt stepper speed is
open-loop from controls.

## Material flow

operator places object → infeed_conveyor → sensing zone → diverter point →
bin_array (one of ≥ 3 bins).

## Energy and force flow

mains → controls PSU (24 V) → stepper → drive roller → belt → object friction.
Object weight → belt → slider bed → side plates → frame → bench.

## Sensor/actuator/control boundaries

vision_module owns the camera; infeed_conveyor owns the stepper; diverter_unit
owns its actuator; controls owns all decisions and the e-stop circuit.

## Failure modes and safe states

- Stepper stall → objects stop moving; safe (no stored energy). Detect by
  vision (object not advancing).
- Misclassification → wrong bin; tolerated to 5 % (REQ-002).
- E-stop → all motion stops; belt has no overrun mass worth braking.
```

- [ ] **Step 5: Write `module_breakdown.md`**

```markdown
# Module Breakdown — Automated Sorting Machine

## Module list

| ID | Name | cad_intent | build_buy |
|---|---|---|---|
| MOD-001 | infeed_conveyor | assembly | mixed |
| MOD-002 | vision_module | assembly | mixed |
| MOD-003 | diverter_unit | assembly | mixed |
| MOD-004 | bin_array | part | build |
| MOD-005 | frame | assembly | mixed |
| MOD-006 | controls | purchased | buy |

## Module responsibility

- MOD-001 moves objects at `INF_BELT_SPEED` through the sensing zone.
- MOD-002 delivers a class decision per object to controls.
- MOD-003 physically redirects one object per decision.
- MOD-004 receives and holds sorted objects.
- MOD-005 positions every module and carries loads to the bench.
- MOD-006 powers and sequences everything; hosts the e-stop.

## Inputs and outputs

infeed_conveyor: objects in (by hand) / objects out (at diverter point);
step pulses in. vision_module: light + object in view / class decision out.
diverter_unit: actuation command in / lateral push out. bin_array: falling
objects in. frame: static loads. controls: mains in / 24 V + signals out.

## Mechanical interfaces

- MOD-001 ↔ MOD-005 via IF-002 (slotted bolt pattern, M5).
- MOD-002 and MOD-003 mount to MOD-005 rails above/at belt level.
- MOD-004 sits on the bench under the diverter discharge (locates by gravity,
  tool-free per serviceability requirement).

## Electrical/control interfaces

- IF-004 stepper wiring; IF-005 USB camera; e-stop loop through MOD-006.

## Dependencies

frame geometry ← infeed_conveyor envelope ← COTS roller/motor dimensions.
Model order: COTS placeholders → conveyor parts → conveyor assembly → frame.

## Build/buy decision

Buy: motor, rollers, belt, camera, controller, fasteners. Build: side plates,
slider bed, motor bracket, bins. Mixed modules combine both.
```

- [ ] **Step 6: Commit**

```powershell
git add docs/industrial_intake/examples/automated_sorting_machine
git commit -m "docs(intake): sorting-machine example - definition docs (idea to modules)"
```

---

### Task 4: Example project — engineering documents

**Files:**
- Create: `docs/industrial_intake/examples/automated_sorting_machine/calculations.md`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/cots_selection.md`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/top_down_cad_strategy.md`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/dfm_dfa_checklist.md`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/verification_plan.md`

**Interfaces:**
- Consumes: REQ/MOD/IF ids and parameter names from Task 3 (exact values in its Interfaces block).
- Produces: COTS ids `COTS-001`–`COTS-006` and the derived numbers (`0.1 m/s`, `0.25 N·m`, `48 rpm`) that Task 5's JSON and handoff reuse verbatim.

- [ ] **Step 1: Write `calculations.md`**

```markdown
# Calculations — Automated Sorting Machine

Inputs trace to `engineering_specs.md`; every result is `derived`.

## Sizing calculations

### 1. Belt speed

- Purpose: meet REQ-001 (30 objects/min) at 200 mm pitch (assumed).
- Formula: v = rate × pitch = (30/60) obj/s × 0.200 m
- Result: **`INF_BELT_SPEED` = 0.10 m/s (derived)**

### 2. Drive torque

- Purpose: size the belt-drive motor (justifies COTS-001).
- Moving load: 3 objects on belt (`INF_BELT_L` 600 mm / 200 mm pitch) × 0.5 kg
  + belt 0.3 kg (assumed) = **1.8 kg**
- Drag force: F = μ·m·g = 0.35 (assumed) × 1.8 kg × 9.81 m/s² = **6.2 N**
- Torque at drive roller (r = `INF_ROLLER_D`/2 = 0.020 m):
  τ = F·r = 6.2 × 0.020 = **0.124 N·m**
- With safety factor 2.0: **τ_required = 0.25 N·m (derived)**

### 3. Drive-shaft speed

- n = v / (π·D) = 0.10 / (π × 0.040) = 0.80 rev/s ≈ **48 rpm (derived)**

### 4. Candidate motor check (COTS-001, NEMA 17)

- Generic NEMA 17: 0.40 N·m holding; usable torque at 48 rpm typically
  ≥ 0.28 N·m (vendor curve required — `vendor_provided`, open below).
- Margin vs load torque: 0.28 / 0.124 ≈ 2.3×. **PASS as candidate.**

## Structural checks

Side plates are 3 mm 5052 spanning 600 mm with < 20 N distributed load —
deflection is negligible at prototype scale (engineering judgment; revisit if
`INF_BELT_L` grows past 1 m).

## Tolerance stack-up

Roller-center to roller-center sets belt tension: slotted tensioner absorbs
±0.2 mm × 2 plate cuts + roller length tolerance, so no tight fit is required
on `INF_BELT_L`. Bearing seats (H7) are deferred to the roller-detail slice.

## Power and duty-cycle budget

P = F·v = 6.2 N × 0.10 m/s ≈ **0.62 W** mechanical — trivial for any NEMA 17
at continuous duty; PSU sizing is dominated by the controller + camera, not
the drive.

## Open calculations that block COTS selection

- None blocking. Open (non-blocking): confirm the selected motor's torque
  curve at 48 rpm from the vendor datasheet (`vendor_provided`).
```

- [ ] **Step 2: Write `cots_selection.md`**

```markdown
# COTS Selection — Automated Sorting Machine

## Candidate components

| ID | Category | Model / standard | Status | CAD asset |
|---|---|---|---|---|
| COTS-001 | motor | Generic NEMA 17 stepper (0.4 N·m holding) | candidate | missing |
| COTS-002 | belt | PU flat belt, 120 mm wide, endless | candidate | missing |
| COTS-003 | roller | Crowned conveyor roller, Ø40 × 130 mm | candidate | missing |
| COTS-004 | camera | USB 1080p module w/ fixed-focus lens | candidate | missing |
| COTS-005 | controller | SBC (Raspberry-Pi-class) + stepper driver | candidate | missing |
| COTS-006 | fasteners | ISO 4762 M5 socket-head screws | selected | available |

## Vendor/model or generic standard

All candidates are generic classes for the prototype; pin vendor part numbers
before the `cad_ready` state (slice COTS must be confirmed with CAD assets).
COTS-006 is standard hardware (SW Toolbox provides geometry — `available`).

## Key dimensions

| ID | Dimension | Value | Status |
|---|---|---|---|
| COTS-001 | faceplate_square | 42.3 mm | vendor_provided (NEMA 17 standard) |
| COTS-001 | shaft_diameter | 5 mm | vendor_provided (NEMA 17 standard) |
| COTS-003 | outer_diameter | 40 mm | assumed (drives `INF_ROLLER_D`) |

## CAD asset availability

Vendor STEP files: none downloaded yet (`missing`). The handoff builds
placeholder geometry from the key dimensions above until assets arrive, then
swaps via `ai-sw-import`.

## Selection rationale

- COTS-001: passes the torque check (calculations.md §4) with ≈ 2.3× margin.
- COTS-002/003: match `CONVEYOR_WIDTH` 120 mm and `INF_ROLLER_D` 40 mm.
- COTS-004/005: one-camera, one-SBC control fits the data/electrical interfaces.

## Open questions and substitutions

- Motor: any NEMA 17 with ≥ 0.28 N·m at 48 rpm substitutes freely.
- Roller: a printed roller over a steel shaft is an acceptable prototype
  substitute if the COTS roller lead time is long.
```

- [ ] **Step 3: Write `top_down_cad_strategy.md`**

```markdown
# Top-down CAD Strategy — Automated Sorting Machine

## Global coordinate system

Origin at frame center, front face, bottom
(`machine_origin_at_frame_center_front_bottom`); X = belt travel, Y = across
belt, Z = up. Matches `engineering_specs.md`.

## Master origin and datum planes

- `PLN_BASE` — bench contact plane (Z = 0).
- `PLN_BELT_TOP` — Z = `INF_FRAME_H` (150 mm): belt working surface.
- `PLN_BELT_CL` — Y = 0 centerline of the belt.

## Skeleton/layout sketch strategy

One machine-layout sketch positioning the six module envelopes is desirable —
**manual-in-GUI** (skeleton parts and in-context references are not executable
by the bridge). For the first slice it is skipped: module positions come from
explicit placement coordinates in the assembly spec instead.

## Global variables and parameter names

| Parameter | Value | Scope | Status |
|---|---|---|---|
| `CONVEYOR_WIDTH` | 120 mm | machine-global | assumed |
| `INF_BELT_L` | 600 mm | module (infeed) | assumed |
| `INF_ROLLER_D` | 40 mm | module (infeed) | assumed |
| `INF_FRAME_H` | 150 mm | module (infeed) | assumed |

Module-owned parameters carry the `INF_` prefix; `CONVEYOR_WIDTH` is
machine-global. Each custom part binds its values through its own
`<part>_locals.txt` equation file; `cad_ready_summary.json` is the source of
truth when files disagree. (`INF_BELT_SPEED` is derived and non-geometric —
it lives in the summary and calculations, not in any `*_locals.txt`.)

## Executable-by-bridge vs manual-in-GUI split

| Work | Path |
|---|---|
| Part builds from specs (`*_locals.txt` parametric) | executable (`ai-sw-build`) |
| Component placement + mates | executable (`ai-sw-assembly`) |
| Drawings, custom properties | executable (`ai-sw-drawing`, `ai-sw-properties`) |
| Skeleton part / in-context references | **manual-in-GUI** |
| Belt as a flexible body | **not modeled in v1** (represented by roller pitch + clearance) |

## Assembly structure

`sorting_machine.SLDASM` → `infeed_conveyor.SLDASM` (side plates ×2, slider
bed, rollers ×2, motor, motor bracket) + later `frame`, `vision_module`,
`diverter_unit`. First slice builds only `infeed_conveyor.SLDASM`.

## Naming conventions

Sketches `SK_<purpose>`, extrudes `EX_<purpose>` (repo convention); parts
`INF_<name>.SLDPRT`; mates `MATE_<partA>_<partB>_<n>`.

## Rebuild and variant strategy

Width variants (e.g. 160 mm belt) materialize as separate part files via
`ai-sw-configurations` variants over `CONVEYOR_WIDTH`; no in-file
configurations (platform constraint).
```

- [ ] **Step 4: Write `dfm_dfa_checklist.md`**

```markdown
# DFM/DFA Checklist — Automated Sorting Machine

## Manufacturing process candidates

Side plates + slider bed: laser-cut 3 mm 5052. Motor bracket + camera mount:
FDM PETG. Bins: FDM or folded sheet. Rollers/motor/belt: purchased.

## Process fit at the target production quantity

Quantity from `requirements.md` = 1 prototype + ≤ 5 pilots: laser-cut plate
and FDM are right; no tooling, no castings. Revisit only if pilots become a
production run.

## Material/process fit

5052 laser-cuts cleanly; PETG prints the bracket's 3 mm walls without
supports if the overhang rule below holds.

## Tolerance and fit strategy

`prototype_clearance` policy: ±0.2 mm laser parts, clearance holes Ø5.5 for
M5. Only the roller bearing seats need a fit class (H7) — deferred to the
roller-detail slice.

## Tool access and minimum feature limits

Minimum printed wall 3 mm (verified by observe `min_wall` in the verification
plan); laser internal corners get R1 relief; all fasteners reachable with a
straight hex key.

## 3D print or CNC constraints

PETG bracket: ≤ 45° overhangs, no supports in the bore, print flat side down.

## Assembly order

frame → slider bed → side plates → rollers → belt (manual stretch over
rollers) → motor + bracket → tension via slots → guards → camera → bins.

## Service access

Belt swap: loosen tensioner slots, no frame disassembly (requirements.md).
Bins lift out tool-free.

## Inspection method

Roller-center distance ±0.2 mm by calipers; printed-bracket walls by the
`min_wall` observe check; assembly clearances by the bridge clearance check
(see verification_plan.md).
```

- [ ] **Step 5: Write `verification_plan.md`**

```markdown
# Verification Plan — Automated Sorting Machine

## Requirements traceability

| REQ | Method | Concrete check |
|---|---|---|
| REQ-001 | test | 100-object timed run ≥ 30 obj/min |
| REQ-002 | test | same run: ≥ 95 % correct bins |
| REQ-003 | analysis | envelope/mass covered by calculations.md load case |
| REQ-004 | demonstration | one object of each class lands in its bin |
| REQ-005 | inspection | bench tape-measure of footprint |
| REQ-006 | demonstration | e-stop halts motion; guard walk-around |

## CAD checks

- Zero component interference (`ai-sw-observe interference` on the slice
  assembly).
- ≥ 2 mm static clearance belt-path to guards (`ai-sw-observe clearance`).
- Printed-bracket minimum wall ≥ 3 mm (`ai-sw-observe min_wall`).
- Equations in each part match the declared parameters
  (`ai-sw-observe equations` diffed against `cad_ready_summary.json`).
- No feature errors, no mate errors (`feature_errors` / `mate_errors`).

## Simulation or motion checks

Diverter sweep-vs-object clearance in motion — deferred to the diverter slice
(`ai-sw-motion` drives the mate through its travel).

## Physical prototype checks

Timed 100-object run (REQ-001/002/004); belt-tracking observation over 30 min.

## Operator acceptance checks

E-stop function, guards fitted, bins removable tool-free, noise subjectively
acceptable at bench distance.

## Risks requiring manual engineering review

- `safety_guarding` — nip-point and sweep guarding must be reviewed by a
  human before first powered run. No automated check signs this off.
```

- [ ] **Step 6: Commit**

```powershell
git add docs/industrial_intake/examples/automated_sorting_machine
git commit -m "docs(intake): sorting-machine example - calculations, COTS, CAD strategy, DFM, verification"
```

---

### Task 5: Example project — CAD-ready summary + SolidWorks handoff

**Files:**
- Create: `docs/industrial_intake/examples/automated_sorting_machine/cad_ready_summary.json`
- Create: `docs/industrial_intake/examples/automated_sorting_machine/solidworks_handoff.md`

**Interfaces:**
- Consumes: the schema (Task 1), the ids/parameters/numbers (Tasks 3–4). CLI verbs available (all real, from `pyproject.toml`): `ai-sw-import`, `ai-sw-build`, `ai-sw-batch`, `ai-sw-assembly`, `ai-sw-drawing`, `ai-sw-properties`, `ai-sw-configurations`, `ai-sw-observe`, `ai-sw-motion`, `ai-sw-history`. Observe subcommands (real, from `cli/observe.py`): `volume`, `bounding_box`, `assembly_bbox`, `interference`, `clearance`, `equations`, `feature_errors`, `mate_errors`, `min_wall`. **Note:** there is no import-diagnostics observe subcommand — `ai-sw-import` reports its own diagnostics; `ai-sw-checkpoint` manages encryption keys only — step-boundary query/rollback is `ai-sw-history`.
- Produces: the example summary JSON that Task 7's test validates; the handoff doc Task 6's spine links to.

- [ ] **Step 1: Write `cad_ready_summary.json`**

```json
{
  "schema_version": 1,
  "project": {
    "name": "automated_sorting_machine",
    "intent": "Sort mixed rigid objects into at least three bins by visual classification."
  },
  "units": {
    "length": "mm",
    "mass": "kg",
    "angle": "deg"
  },
  "requirements": [
    {
      "id": "REQ-001",
      "text": "Convey objects one at a time through a sensing zone at >= 30 objects/min.",
      "priority": "must",
      "verification": "test"
    },
    {
      "id": "REQ-002",
      "text": "Classify each object into one of >= 3 visual classes with >= 95 % accuracy.",
      "priority": "must",
      "verification": "test"
    },
    {
      "id": "REQ-003",
      "text": "Handle objects up to 100 x 100 x 100 mm and 0.5 kg.",
      "priority": "must",
      "verification": "analysis"
    },
    {
      "id": "REQ-004",
      "text": "Divert each classified object into its matching bin (>= 3 bins).",
      "priority": "must",
      "verification": "demonstration"
    },
    {
      "id": "REQ-005",
      "text": "Whole machine fits a 1200 x 800 mm bench footprint.",
      "priority": "should",
      "verification": "inspection"
    },
    {
      "id": "REQ-006",
      "text": "An e-stop cuts all motion; nip points and the diverter sweep are guarded.",
      "priority": "must",
      "verification": "demonstration"
    }
  ],
  "parameters": [
    {
      "name": "CONVEYOR_WIDTH",
      "value": 120.0,
      "unit": "mm",
      "status": "assumed",
      "rationale": "Largest object 100 mm plus 2 x 10 mm side clearance."
    },
    {
      "name": "INF_BELT_L",
      "value": 600.0,
      "unit": "mm",
      "status": "assumed",
      "rationale": "Sensing zone plus one object pitch either side."
    },
    {
      "name": "INF_ROLLER_D",
      "value": 40.0,
      "unit": "mm",
      "status": "assumed",
      "rationale": "Candidate crowned roller size; input to the drive-torque calculation."
    },
    {
      "name": "INF_FRAME_H",
      "value": 150.0,
      "unit": "mm",
      "status": "assumed",
      "rationale": "Belt-top height above baseplate for bin clearance under the discharge."
    },
    {
      "name": "INF_BELT_SPEED",
      "value": 0.1,
      "unit": "m/s",
      "status": "derived",
      "rationale": "REQ-001 throughput (30 obj/min) at 200 mm assumed pitch; calculations.md section 1."
    }
  ],
  "modules": [
    {
      "id": "MOD-001",
      "name": "infeed_conveyor",
      "role": "Move objects through the sensing zone at constant speed.",
      "cad_intent": "assembly",
      "interfaces": ["IF-001", "IF-002", "IF-003", "IF-004"],
      "build_buy": "mixed"
    },
    {
      "id": "MOD-002",
      "name": "vision_module",
      "role": "Classify each object passing the sensing zone.",
      "cad_intent": "assembly",
      "interfaces": ["IF-001", "IF-005"],
      "build_buy": "mixed"
    },
    {
      "id": "MOD-003",
      "name": "diverter_unit",
      "role": "Redirect each classified object into its bin lane.",
      "cad_intent": "assembly",
      "interfaces": ["IF-003", "IF-006"],
      "build_buy": "mixed"
    },
    {
      "id": "MOD-004",
      "name": "bin_array",
      "role": "Receive and hold sorted objects.",
      "cad_intent": "part",
      "interfaces": ["IF-006"],
      "build_buy": "build"
    },
    {
      "id": "MOD-005",
      "name": "frame",
      "role": "Position all modules and carry loads to the bench.",
      "cad_intent": "assembly",
      "interfaces": ["IF-002"],
      "build_buy": "mixed"
    },
    {
      "id": "MOD-006",
      "name": "controls",
      "role": "Power and sequence the machine; host the e-stop.",
      "cad_intent": "purchased",
      "interfaces": ["IF-004", "IF-005"],
      "build_buy": "buy"
    }
  ],
  "interfaces": [
    {
      "id": "IF-001",
      "from": "vision_module",
      "to": "infeed_conveyor",
      "type": "spatial",
      "description": "Camera field of view covers the belt sensing zone unobstructed."
    },
    {
      "id": "IF-002",
      "from": "infeed_conveyor",
      "to": "frame",
      "type": "mechanical",
      "description": "Slotted M5 bolt pattern; belt-top height equals INF_FRAME_H."
    },
    {
      "id": "IF-003",
      "from": "diverter_unit",
      "to": "infeed_conveyor",
      "type": "spatial",
      "description": "Paddle sweep envelope clears belt and object by at least 2 mm."
    },
    {
      "id": "IF-004",
      "from": "infeed_conveyor",
      "to": "controls",
      "type": "electrical",
      "description": "Stepper 4-wire to driver with the e-stop loop in series."
    },
    {
      "id": "IF-005",
      "from": "vision_module",
      "to": "controls",
      "type": "data",
      "description": "USB camera stream to the classifier."
    },
    {
      "id": "IF-006",
      "from": "diverter_unit",
      "to": "bin_array",
      "type": "spatial",
      "description": "Diverted-object trajectory lands inside the bin mouth."
    }
  ],
  "cots": [
    {
      "id": "COTS-001",
      "category": "motor",
      "selection_status": "candidate",
      "model": "Generic NEMA 17 stepper, 0.4 N.m holding",
      "critical_dimensions": {
        "faceplate_square": { "value": 42.3, "unit": "mm" },
        "shaft_diameter": { "value": 5.0, "unit": "mm" }
      },
      "cad_asset": "missing"
    },
    {
      "id": "COTS-002",
      "category": "belt",
      "selection_status": "candidate",
      "model": "PU flat belt, 120 mm wide, endless",
      "critical_dimensions": {
        "width": { "value": 120.0, "unit": "mm" }
      },
      "cad_asset": "missing"
    },
    {
      "id": "COTS-003",
      "category": "roller",
      "selection_status": "candidate",
      "model": "Crowned conveyor roller",
      "critical_dimensions": {
        "outer_diameter": { "value": 40.0, "unit": "mm" },
        "face_length": { "value": 130.0, "unit": "mm" }
      },
      "cad_asset": "missing"
    },
    {
      "id": "COTS-004",
      "category": "camera",
      "selection_status": "candidate",
      "model": "USB 1080p module with fixed-focus lens",
      "critical_dimensions": {},
      "cad_asset": "missing"
    },
    {
      "id": "COTS-005",
      "category": "controller",
      "selection_status": "candidate",
      "model": "SBC (Raspberry-Pi-class) plus stepper driver",
      "critical_dimensions": {},
      "cad_asset": "missing"
    },
    {
      "id": "COTS-006",
      "category": "fasteners",
      "selection_status": "selected",
      "model": "ISO 4762 M5 socket-head screws",
      "critical_dimensions": {
        "thread_major_diameter": { "value": 5.0, "unit": "mm" }
      },
      "cad_asset": "available"
    }
  ],
  "manufacturing": {
    "candidate_processes": ["laser_cut_plate", "3d_printing"],
    "tolerance_policy": "prototype_clearance",
    "notes": [
      "Quantity 1 prototype + up to 5 pilots: no tooling, no castings.",
      "Belt is not modeled as a flexible body in v1 CAD."
    ]
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

- [ ] **Step 2: Validate it against the schema**

```powershell
python -c "import json, jsonschema; s=json.load(open('docs/industrial_intake/templates/cad_ready_summary.schema.json', encoding='utf-8')); d=json.load(open('docs/industrial_intake/examples/automated_sorting_machine/cad_ready_summary.json', encoding='utf-8')); jsonschema.validate(d, s); print('VALID')"
```

Expected output: `VALID`.

- [ ] **Step 3: Write `solidworks_handoff.md`**

````markdown
# SolidWorks Handoff — Automated Sorting Machine (first slice: infeed conveyor)

This maps the design package onto the existing bridge surfaces and gives the
**ordered build sequence** with a verify point per step. The package readiness
is `cad_ready_with_assumptions` — every `assumed` parameter above is fair game
to change; rebuild from specs, do not hand-edit models.

## What becomes what

| Package item | CAD artifact | Bridge surface |
|---|---|---|
| MOD-001 custom parts (side plates ×2, slider bed, motor bracket) | `INF_*.SLDPRT` | `ai-sw-build` (one spec per part; `ai-sw-batch` for multi-feature slices) |
| COTS-001/002/003 (motor, belt, rollers) | imported or placeholder parts | `ai-sw-import` (STEP/IGES) or placeholder `ai-sw-build` specs |
| MOD-001 assembly | `infeed_conveyor.SLDASM` | `ai-sw-assembly` (placement + mates) |
| Manufacturing drawings (side plate first) | drawing + PDF | `ai-sw-drawing` |
| Part metadata (number, material) | custom properties | `ai-sw-properties` |
| Width variants (future) | separate part files | `ai-sw-configurations` |
| Parameters table | per-part `<part>_locals.txt` | bound in each build spec |

Parameters map to per-part `*_locals.txt` variables: `INF_*` are module-owned;
`CONVEYOR_WIDTH` is machine-global. `cad_ready_summary.json` is the source of
truth if files disagree.

## Ordered build sequence (verify point per step)

1. **COTS assets.** Vendor STEP files are `missing`: build placeholder parts
   from the critical dimensions (roller = Ø40 × 130 cylinder; motor = 42.3 mm
   square block with a Ø5 shaft) via `ai-sw-build`. When vendor STEP arrives,
   swap in via `ai-sw-import` and review the diagnostics it reports (a
   surface-body count > 0 means unstitched geometry).
   **Verify:** `ai-sw-observe volume` > 0 and `ai-sw-observe bounding_box`
   matches the critical dimensions.
2. **Custom parts.** One spec per part, parametric against its
   `<part>_locals.txt` (e.g. `INF_side_plate_locals.txt` carrying
   `INF_BELT_L`, `INF_FRAME_H`, `INF_ROLLER_D`).
   **Verify per part:** `ai-sw-observe volume` and `bounding_box` within the
   expected envelope; `ai-sw-observe feature_errors` empty.
3. **Assemble the slice.** `ai-sw-assembly`: place side plates, slider bed,
   rollers (concentric + distance mates to plate bores), motor on bracket
   (coincident + concentric to the drive roller shaft).
   **Verify:** `ai-sw-observe interference` reports zero interferences;
   `ai-sw-observe clearance` belt-path-to-guard ≥ 2 mm;
   `ai-sw-observe mate_errors` empty.
4. **Drawings + metadata.** `ai-sw-drawing` for the side plate (third-angle,
   ISO, title block per `engineering_specs.md`); `ai-sw-properties` sets part
   number and material (5052).
   **Verify:** the drawing lifecycle commit succeeds and the sheet contains
   the driving dimensions.
5. **Close the loop against the package.** Diff
   `ai-sw-observe equations` output for each part against the `parameters`
   array in `cad_ready_summary.json` — names and values must match. Then run
   the CAD checks in [`verification_plan.md`](verification_plan.md)
   (`min_wall` ≥ 3 mm on the printed bracket).

Checkpoints are recorded automatically during builds; at each step boundary,
`ai-sw-history part <part>` confirms the checkpoint exists, and
`ai-sw-history diff` / rollback is the recovery path if a step regresses.

## Manual-in-GUI items (not bridge-executable)

- Skeleton/layout sketch and any in-context references.
- Physically fitting the belt (and its flexible-body CAD, omitted in v1).
- The `safety_guarding` review flagged in `readiness.manual_review_required`.

## When to return to the build docs

Spec authoring rules, feature-type choice, and worked spec examples live in
[`docs/AGENTS.md`](../../../AGENTS.md) and
[`docs/spec_reference.md`](../../../spec_reference.md). Return there once this
package's readiness is `cad_ready_with_assumptions` or better — that is the
pre-CAD gate.
````

- [ ] **Step 4: Verify the two relative links in the handoff resolve**

```powershell
python -c "from pathlib import Path; b=Path('docs/industrial_intake/examples/automated_sorting_machine'); import sys; sys.exit(0 if (b/'../../../AGENTS.md').resolve().exists() and (b/'../../../spec_reference.md').resolve().exists() and (b/'verification_plan.md').exists() else 1)"
```

Expected: exit code 0 (no output).

- [ ] **Step 5: Commit**

```powershell
git add docs/industrial_intake/examples/automated_sorting_machine/cad_ready_summary.json docs/industrial_intake/examples/automated_sorting_machine/solidworks_handoff.md
git commit -m "docs(intake): sorting-machine example - CAD-ready summary + SolidWorks handoff"
```

---

### Task 6: Intake spine — README, AGENTS contract, workflow

**Files:**
- Create: `docs/industrial_intake/README.md`
- Create: `docs/industrial_intake/AGENTS.md`
- Create: `docs/industrial_intake/workflow.md`

**Interfaces:**
- Consumes: every file from Tasks 1–5 (all links below resolve because those files exist).
- Produces: `docs/industrial_intake/README.md` and `docs/industrial_intake/AGENTS.md` — the two paths that Task 8's and Task 9's routing edits point at. The 11 agent rules (spec §10) and the readiness-state table (spec §9) live here.

- [ ] **Step 1: Write `README.md`**

````markdown
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
````

- [ ] **Step 2: Write `AGENTS.md`**

```markdown
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
```

- [ ] **Step 3: Write `workflow.md`**

```markdown
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
```

- [ ] **Step 4: Verify every link in the three spine files resolves**

```powershell
python -c "
import re, sys
from pathlib import Path
base = Path('docs/industrial_intake')
dead = []
for name in ('README.md', 'AGENTS.md', 'workflow.md'):
    p = base / name
    for t in re.findall(r'\]\(([^)]+)\)', p.read_text(encoding='utf-8')):
        t = t.split(' ', 1)[0].split('#', 1)[0].strip()
        if not t or t.startswith(('http://', 'https://', 'mailto:')):
            continue
        if not (p.parent / t).resolve().exists():
            dead.append(f'{name}: {t}')
print(dead)
sys.exit(1 if dead else 0)
"
```

Expected output: `[]`, exit 0.

- [ ] **Step 5: Commit**

```powershell
git add docs/industrial_intake/README.md docs/industrial_intake/AGENTS.md docs/industrial_intake/workflow.md
git commit -m "docs(intake): intake spine - README, AGENTS contract, workflow (both lanes)"
```

---

### Task 7: The committed docs gate

**Files:**
- Create: `tests/test_industrial_intake_docs.py`

**Interfaces:**
- Consumes: the tree from Tasks 1–6 (exact paths in the `_EXPECTED_FILES` literal below).
- Produces: the permanent gate. Later tasks (8–11) must keep it green.

- [ ] **Step 1: Write the test file**

Create `tests/test_industrial_intake_docs.py` with exactly:

```python
"""Documentation gate for the Industrial Design Intake tree.

Committed guarantees (spec 2026-07-07-industrial-design-intake-design.md,
section 13):

1. The tree contains every file the spec's section 7 promises (frozen to
   literals -- derive nothing from the tree being tested).
2. Every shipped CAD-ready summary validates against
   ``cad_ready_summary.schema.json`` -- and the schema demonstrably rejects
   invalid documents, so this gate cannot rot into always-green.
3. Every relative link in every intake Markdown file resolves on disk (the
   dead-link pattern from ``tests/test_i18n_staleness.py``).

Pure filesystem: no git, no SOLIDWORKS seat, safe on shallow checkouts.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import jsonschema
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_INTAKE = _ROOT / "docs" / "industrial_intake"
_TEMPLATES = _INTAKE / "templates"
_EXAMPLE = _INTAKE / "examples" / "automated_sorting_machine"

_SCHEMA_PATH = _TEMPLATES / "cad_ready_summary.schema.json"
_SUMMARY_PATHS = [
    _TEMPLATES / "cad_ready_summary.example.json",
    _EXAMPLE / "cad_ready_summary.json",
]

# The repository shape promised by spec section 7, frozen to literals
# (snapshot-mirror rule: derive nothing from the tree being tested).
_EXPECTED_FILES = [
    "README.md",
    "AGENTS.md",
    "workflow.md",
    "templates/idea_brief.md",
    "templates/requirements.md",
    "templates/engineering_specs.md",
    "templates/system_architecture.md",
    "templates/module_breakdown.md",
    "templates/calculations.md",
    "templates/cots_selection.md",
    "templates/top_down_cad_strategy.md",
    "templates/dfm_dfa_checklist.md",
    "templates/verification_plan.md",
    "templates/cad_ready_summary.schema.json",
    "templates/cad_ready_summary.example.json",
    "examples/automated_sorting_machine/idea_brief.md",
    "examples/automated_sorting_machine/requirements.md",
    "examples/automated_sorting_machine/engineering_specs.md",
    "examples/automated_sorting_machine/system_architecture.md",
    "examples/automated_sorting_machine/module_breakdown.md",
    "examples/automated_sorting_machine/calculations.md",
    "examples/automated_sorting_machine/cots_selection.md",
    "examples/automated_sorting_machine/top_down_cad_strategy.md",
    "examples/automated_sorting_machine/dfm_dfa_checklist.md",
    "examples/automated_sorting_machine/verification_plan.md",
    "examples/automated_sorting_machine/cad_ready_summary.json",
    "examples/automated_sorting_machine/solidworks_handoff.md",
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_intake_tree_matches_spec_shape() -> None:
    missing = [rel for rel in _EXPECTED_FILES if not (_INTAKE / rel).is_file()]
    msg = f"intake files promised by spec section 7 are missing: {missing}"
    assert not missing, msg


@pytest.mark.parametrize("summary_path", _SUMMARY_PATHS, ids=lambda p: p.parent.name)
def test_summary_validates_against_schema(summary_path: Path) -> None:
    jsonschema.validate(_load(summary_path), _load(_SCHEMA_PATH))


def test_schema_rejects_unknown_readiness_state() -> None:
    doc = copy.deepcopy(_load(_SUMMARY_PATHS[0]))
    doc["readiness"]["state"] = "totally_ready"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _load(_SCHEMA_PATH))


def test_schema_rejects_unknown_top_level_key() -> None:
    doc = copy.deepcopy(_load(_SUMMARY_PATHS[0]))
    doc["solidworks_specifics"] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _load(_SCHEMA_PATH))


def _relative_links(text: str) -> list[str]:
    # ](target) where target is not http(s), not an in-page #anchor, not a
    # mailto -- the same extraction as tests/test_i18n_staleness.py.
    links = re.findall(r"\]\(([^)]+)\)", text)
    out = []
    for t in links:
        t = t.split(" ", 1)[0].split("#", 1)[0].strip()
        if not t or t.startswith(("http://", "https://", "mailto:")):
            continue
        out.append(t)
    return out


def _dead_links(md_file: Path) -> list[str]:
    return [
        t
        for t in _relative_links(md_file.read_text(encoding="utf-8"))
        if not (md_file.parent / t).resolve().exists()
    ]


def test_no_dead_relative_links_in_intake_tree() -> None:
    dead = {
        str(p.relative_to(_ROOT)).replace("\\", "/"): links
        for p in sorted(_INTAKE.rglob("*.md"))
        if (links := _dead_links(p))
    }
    assert not dead, f"intake docs have dead relative links: {dead}"


def test_dead_link_detector_actually_detects(tmp_path: Path) -> None:
    bad = tmp_path / "doc.md"
    bad.write_text("see [missing](does_not_exist.md)", encoding="utf-8")
    assert _dead_links(bad) == ["does_not_exist.md"]
```

- [ ] **Step 2: Run the new gate**

```powershell
pytest tests/test_industrial_intake_docs.py -v
```

Expected: **7 passed** (tree-shape, 2× schema-validates, 2× schema-rejects, dead-links, detector-detects). If the tree-shape test fails, a Task 1–6 file is missing or misnamed — fix the file, not the test.

- [ ] **Step 3: Lint the new file**

```powershell
black --check tests/test_industrial_intake_docs.py
flake8 tests/test_industrial_intake_docs.py
```

Expected: black "would leave 1 file unchanged"; flake8 silent, exit 0. If black wants changes, run `black tests/test_industrial_intake_docs.py` and re-check.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_industrial_intake_docs.py
git commit -m "test(intake): schema-validation + dead-link gate for the intake tree"
```

---

### Task 8: Non-mirrored routing surfaces

**Files:**
- Modify: `docs/AGENTS.md` (after rule 5, ~line 40)
- Modify: `docs/operator_guide.md` (after the "Pairing with an AI assistant?" blockquote, ~line 14)
- Modify: `docs/README.md` (Getting started list, ~line 10)
- Modify: `docs/CAPABILITIES.md` (Surfaces bullet ~line 18; new section after Surfaces)

**Interfaces:**
- Consumes: `docs/industrial_intake/README.md` and `docs/industrial_intake/AGENTS.md` (Task 6).
- Produces: nothing downstream; these four files are NOT i18n-mirrored (manifest: only `README.md`, `USAGE.md`, `docs/PUBLIC_API.md`), so no mirror work here.

- [ ] **Step 1: Add rule 6 to `docs/AGENTS.md`**

Edit `docs/AGENTS.md` — old string:

```text
5. **Start from a known-good shape.** Prefer adapting a working spec over writing from scratch. Run `ai-sw-build --demo --dry-run` to print a complete, valid reference spec; the [`examples/` folder on GitHub](https://github.com/Thomas-Tai/ai-sw-bridge/tree/master/examples) has 20 more covering every shipped feature type — browsable online (an installer / pipx setup won't have them on disk).
```

New string (the same line, plus a new rule 6):

```text
5. **Start from a known-good shape.** Prefer adapting a working spec over writing from scratch. Run `ai-sw-build --demo --dry-run` to print a complete, valid reference spec; the [`examples/` folder on GitHub](https://github.com/Thomas-Tai/ai-sw-bridge/tree/master/examples) has 20 more covering every shipped feature type — browsable online (an installer / pipx setup won't have them on disk).
6. **Vague idea? Intake first.** If the goal is a vague product or machine idea ("build me a sorting machine") rather than a concrete part, assembly, or spec, do not draft any spec yet: run the Industrial Design Intake process ([`industrial_intake/AGENTS.md`](industrial_intake/AGENTS.md)) until the package reaches a CAD-ready state, then come back here.
```

- [ ] **Step 2: Add the intake paragraph to `docs/operator_guide.md`**

Edit `docs/operator_guide.md` — old string:

```text
> **Pairing with an AI assistant?** Hand it [`docs/AGENTS.md`](AGENTS.md) — that
> file is written *for the AI*: it spells out the rules, the spec format, which
> example to copy, and exactly what needs your confirmation before anything runs.
> You stay in the loop; the AI drafts, you approve.
```

New string:

```text
> **Pairing with an AI assistant?** Hand it [`docs/AGENTS.md`](AGENTS.md) — that
> file is written *for the AI*: it spells out the rules, the spec format, which
> example to copy, and exactly what needs your confirmation before anything runs.
> You stay in the loop; the AI drafts, you approve.

> **Starting from just an idea?** If you have a product or machine idea but no
> design yet, have your AI run the [Industrial Design
> Intake](industrial_intake/README.md) first — it turns one idea into a
> reviewable engineering package (requirements → architecture → calculations →
> CAD plan) before any SolidWorks work begins.
```

- [ ] **Step 3: Add the nav row to `docs/README.md`**

Edit `docs/README.md` — old string:

```text
- [AGENTS.md](AGENTS.md) — how an AI agent drives the bridge (the contract agents read).
```

New string:

```text
- [AGENTS.md](AGENTS.md) — how an AI agent drives the bridge (the contract agents read).
- [industrial_intake/](industrial_intake/README.md) — pre-CAD intake: from one idea (or a complete professional design) to a CAD-ready package the bridge can build.
```

- [ ] **Step 4: Fix the stale surfaces line and add the intake section to `docs/CAPABILITIES.md`**

Edit 4a — old string:

```text
- **21 command-line tools** (`ai-sw-build`, `ai-sw-mutate`, `ai-sw-assembly`,
  `ai-sw-drawing`, `ai-sw-properties`, `ai-sw-configurations`, `ai-sw-sketch-edit`,
  `ai-sw-sketch-relations`, `ai-sw-observe`, `ai-sw-import`, `ai-sw-export-dxf-flat`,
  `ai-sw-motion`, `ai-sw-solver`, `ai-sw-urdf`, `ai-sw-checkpoint`, `ai-sw-history`,
  `ai-sw-memory`, `ai-sw-apidoc`, `ai-sw-codegen`, `ai-sw-probe`) — see
  [`PUBLIC_API.md`](PUBLIC_API.md) for stability tiers.
```

New string (22 is the real count from `pyproject.toml [project.scripts]` minus `ai-sw-mcp`; the list adds the missing `ai-sw-batch` and `ai-sw-doctor`):

```text
- **22 command-line tools** (`ai-sw-build`, `ai-sw-mutate`, `ai-sw-batch`, `ai-sw-assembly`,
  `ai-sw-drawing`, `ai-sw-properties`, `ai-sw-configurations`, `ai-sw-sketch-edit`,
  `ai-sw-sketch-relations`, `ai-sw-observe`, `ai-sw-import`, `ai-sw-export-dxf-flat`,
  `ai-sw-motion`, `ai-sw-solver`, `ai-sw-urdf`, `ai-sw-checkpoint`, `ai-sw-history`,
  `ai-sw-memory`, `ai-sw-apidoc`, `ai-sw-codegen`, `ai-sw-probe`, `ai-sw-doctor`) — see
  [`PUBLIC_API.md`](PUBLIC_API.md) for stability tiers.
```

Edit 4b — old string:

```text
- **One MCP server** (`ai-sw-mcp`) exposing 37 tools to MCP-capable AI clients.

---

## Build — part features
```

New string:

```text
- **One MCP server** (`ai-sw-mcp`) exposing 37 tools to MCP-capable AI clients.

---

## Industrial Design Intake — pre-CAD planning (docs layer)

Upstream of every build surface sits a documentation-and-templates layer that
turns a raw product idea (or a professional's complete design) into a CAD-ready
package: requirements → architecture → calculations → COTS selection → top-down
CAD strategy → DFM/DFA → verification plan, ending in a CAD-neutral
`cad_ready_summary.json` handoff. It adds no CLI or MCP tool — see
[`industrial_intake/README.md`](industrial_intake/README.md).

---

## Build — part features
```

- [ ] **Step 5: Run the doc gates**

```powershell
python tools/doc_coverage_gate.py
pytest tests/test_doc_truth.py tests/test_doc_coverage.py tests/test_industrial_intake_docs.py -v
```

Expected: gate exits 0; all tests pass. (`docs/CAPABILITIES.md` pins only the `v{version}` string in doc-truth — the count fix is safe; the intake adds no feature types, so doc-coverage is untouched.)

- [ ] **Step 6: Commit**

```powershell
git add docs/AGENTS.md docs/operator_guide.md docs/README.md docs/CAPABILITIES.md
git commit -m "docs: route vague-idea users to industrial intake (agents, operator guide, nav, capabilities)"
```

---

### Task 9: README persona row + zh-CN/zh-TW mirror retranslation

**Files:**
- Modify: `README.md` (persona-router table, ~line 21) — **commit A**
- Modify: `docs/i18n/zh-CN/README.md` (frontmatter line 2 + table ~line 24) — **commit B**
- Modify: `docs/i18n/zh-TW/README.md` (frontmatter line 2 + table ~line 22) — **commit B**

**Interfaces:**
- Consumes: `docs/industrial_intake/README.md` (Task 6). i18n mechanics: each mirror declares `translated-from: <sha>`; the gate fails if `README.md` has commits after that sha and no staleness banner. The sha must already exist (`git cat-file -e`), so the mirrors can only reference the README commit **after** it exists → two commits, same push.
- Produces: nothing downstream.

**CRITICAL SEQUENCE:** commit A (README only) first; read its hash; then commit B (both mirrors, `translated-from` = commit A's full hash). Never squash A and B into one commit, and never amend/rebase A afterward — either orphans the sha the mirrors point at. (Amending B alone is safe; nothing references B's hash.)

- [ ] **Step 1: Add the persona row to `README.md`**

Edit `README.md` — old string:

```text
| **An operator** — a SOLIDWORKS user, not a coder | Install the bridge and drive it from your AI assistant | [**For operators — 5-minute quickstart**](#for-operators--5-minute-quickstart) · then hand [`docs/operator_guide.md`](docs/operator_guide.md) to your AI |
```

New string (the operator row, then the new Maker row):

```text
| **An operator** — a SOLIDWORKS user, not a coder | Install the bridge and drive it from your AI assistant | [**For operators — 5-minute quickstart**](#for-operators--5-minute-quickstart) · then hand [`docs/operator_guide.md`](docs/operator_guide.md) to your AI |
| **A Maker / system designer** — an idea, not a CAD design yet | Turn the idea into a CAD-ready engineering package before modeling | [**Industrial Design Intake**](docs/industrial_intake/README.md) — guided intake (or direct entry for complete designs), ending in a SolidWorks handoff |
```

- [ ] **Step 2: Commit A (README only) and capture its hash**

```powershell
git add README.md
git commit -m "docs(readme): add Maker / system designer persona row routing to industrial intake"
git rev-parse HEAD
```

Expected: a 40-hex hash printed. Copy it — call it `<SHA-A>` below.

- [ ] **Step 3: Retranslate the zh-CN mirror section and bump its sentinel**

Edit `docs/i18n/zh-CN/README.md` — TWO edits:

Edit 3a (frontmatter) — old string:

```text
translated-from: 2ea6f13a0fb79d310d59eb8e3c74e836c982850f
```

New string (substitute the real hash from Step 2):

```text
translated-from: <SHA-A>
```

Edit 3b (table row) — old string:

```text
| **操作者** — SOLIDWORKS 用户，不是程序员 | 安装桥接器，并从你的 AI 助手驱动它 | [**面向操作者 — 5 分钟快速入门**](#面向操作者--5-分钟快速入门) · 然后把 [`docs/operator_guide.md`](../../operator_guide.md) 交给你的 AI |
```

New string:

```text
| **操作者** — SOLIDWORKS 用户，不是程序员 | 安装桥接器，并从你的 AI 助手驱动它 | [**面向操作者 — 5 分钟快速入门**](#面向操作者--5-分钟快速入门) · 然后把 [`docs/operator_guide.md`](../../operator_guide.md) 交给你的 AI |
| **创客 / 系统设计者** — 只有想法，还没有 CAD 设计 | 在建模之前，先把想法变成可进入 CAD 的工程设计包 | [**Industrial Design Intake（工业设计前期导入）**](../../industrial_intake/README.md) — 引导式导入（已有完整设计可直接填写），最终产出 SolidWorks 交接文档 |
```

- [ ] **Step 4: Retranslate the zh-TW mirror section and bump its sentinel**

Edit `docs/i18n/zh-TW/README.md` — TWO edits:

Edit 4a (frontmatter) — old string:

```text
translated-from: 2ea6f13a0fb79d310d59eb8e3c74e836c982850f
```

New string (same `<SHA-A>`):

```text
translated-from: <SHA-A>
```

Edit 4b (table row) — old string:

```text
| **操作者 (operator)** — SOLIDWORKS 使用者，不是工程師 | 安裝橋接器並從你的 AI 助理驅動它 | [**給操作者 — 5 分鐘快速入門**](#給操作者--5-分鐘快速入門) · 接著把 [`docs/operator_guide.md`](../../operator_guide.md) 交給你的 AI |
```

New string:

```text
| **操作者 (operator)** — SOLIDWORKS 使用者，不是工程師 | 安裝橋接器並從你的 AI 助理驅動它 | [**給操作者 — 5 分鐘快速入門**](#給操作者--5-分鐘快速入門) · 接著把 [`docs/operator_guide.md`](../../operator_guide.md) 交給你的 AI |
| **創客／系統設計者** — 只有想法，還沒有 CAD 設計 | 在建模之前，先把想法變成可進入 CAD 的工程設計包 | [**Industrial Design Intake（工業設計前期導入）**](../../industrial_intake/README.md) — 引導式導入（已有完整設計可直接填寫），最終產出 SolidWorks 交接文件 |
```

- [ ] **Step 5: Commit B (both mirrors)**

```powershell
git add docs/i18n/zh-CN/README.md docs/i18n/zh-TW/README.md
git commit -m "docs(i18n): retranslate README persona router for the intake row (zh-CN, zh-TW)"
```

- [ ] **Step 6: Run the i18n gate**

```powershell
pytest tests/test_i18n_staleness.py -v
```

Expected: **all 25 tests pass** (4 parametrized checks × 6 mirrors + the manifest check). The two README mirrors are fresh (their `translated-from` is the last commit that touched `README.md`, so `rev-list` is empty → no banner required). The USAGE/PUBLIC_API mirrors were untouched and stay fresh. If `test_mirror_exists_and_declares_translated_from` fails with "not in git history", the pasted hash is wrong — re-run `git log --oneline -3`, take the hash of commit A, fix both frontmatters, `git commit --amend --no-edit` commit B.

---

### Task 10: MCP server routing sentence

**Files:**
- Modify: `src/ai_sw_bridge/mcp/server.py:144-156` (`_SERVER_INSTRUCTIONS`)

**Interfaces:**
- Consumes: nothing (the sentence references the repo path `docs/industrial_intake/`, which exists since Task 6).
- Produces: nothing downstream. No contract test pins this string (verified by grep across `tests/`); do NOT add one — spec §10.1 keeps it churn-free informational text.

- [ ] **Step 1: Append the routing sentence**

Edit `src/ai_sw_bridge/mcp/server.py` — old string:

```python
    "(ComExecutor.is_sw_dead=True). The two write tools (`sw_build`, "
    "`sw_batch_execute`) never persist without your in-chat approval — COM "
    "writes are irreversible within a single SW session, so review the plan "
    "before approving."
)
```

New string:

```python
    "(ComExecutor.is_sw_dead=True). The two write tools (`sw_build`, "
    "`sw_batch_execute`) never persist without your in-chat approval — COM "
    "writes are irreversible within a single SW session, so review the plan "
    "before approving. If the user starts from a vague product or machine "
    "idea rather than a concrete part or spec, run the Industrial Design "
    "Intake process first (docs/industrial_intake/ in the repo, or ask the "
    "user for their intake package) before proposing any build."
)
```

- [ ] **Step 2: Verify formatting and content**

```powershell
black --check src/ai_sw_bridge/mcp/server.py
flake8 src/ai_sw_bridge/mcp/server.py
python -c "import re; t=open('src/ai_sw_bridge/mcp/server.py', encoding='utf-8').read(); assert 'Industrial Design ' in t and 'intake package' in t; print('SENTENCE-PRESENT')"
```

Expected: black unchanged, flake8 silent, then `SENTENCE-PRESENT`. (String-literal concatenation keeps every line under 88 columns; do not join the lines.)

- [ ] **Step 3: Commit**

```powershell
git add src/ai_sw_bridge/mcp/server.py
git commit -m "docs(mcp): route vague product ideas to industrial intake in server instructions"
```

---

### Task 11: Full gate sweep + acceptance checklist

**Files:**
- No new files. Read-only verification of the whole branch.

**Interfaces:**
- Consumes: everything above.
- Produces: the green light for the user to review and push.

- [ ] **Step 1: Doc gates**

```powershell
python tools/doc_coverage_gate.py
pytest tests/test_doc_truth.py tests/test_doc_coverage.py tests/test_i18n_staleness.py tests/test_industrial_intake_docs.py -v
```

Expected: gate exit 0; every test passes.

- [ ] **Step 2: Lint the two touched Python files**

```powershell
black --check tests/test_industrial_intake_docs.py src/ai_sw_bridge/mcp/server.py
flake8 tests/test_industrial_intake_docs.py src/ai_sw_bridge/mcp/server.py
```

Expected: both clean.

- [ ] **Step 3: Full offline suite (the per-PR CI cut)**

```powershell
pytest -n auto -m "not solidworks_only and not destructive_sw and not fault_injection and not mcp_lane_live"
```

Expected: **all pass, none of the new work skipped**. This is the same marker cut CI runs per PR. If anything unrelated fails, STOP and report — do not fix drive-by failures inside this plan.

- [ ] **Step 4: Acceptance checklist (spec §16 — check each, fix in the owning task if one fails)**

- A vague-idea user landing on `README.md`, `docs/AGENTS.md`, `docs/operator_guide.md`, `docs/README.md`, or `docs/CAPABILITIES.md` is routed to `docs/industrial_intake/` (Tasks 8–9).
- The package location `<project>/intake/` is stated in the intake README, AGENTS, and workflow (Task 6).
- The pre-CAD gate exists on both surfaces: repo docs (Tasks 6, 8) and `_SERVER_INSTRUCTIONS` (Task 10).
- The professional direct-entry lane is in `workflow.md` Lane 2 and intake AGENTS rule 11 (Task 6).
- Every template has required sections + placeholder guidance (Task 2).
- The summary has a formal schema + two validating examples (Tasks 1, 5) with the exact spec §9 enums.
- The sorting-machine example runs idea → CAD-ready summary, first slice = infeed conveyor (Tasks 3–5).
- No build/mutate/assembly/drawing behavior changed: `git diff master --stat -- src/` shows only `src/ai_sw_bridge/mcp/server.py` with a string-only diff.
- The handoff gives an ordered build sequence with a named verify command per step and `ai-sw-history` at boundaries (Task 5).

- [ ] **Step 5: Final review**

```powershell
git log --oneline master..HEAD
git status --short
```

Expected: the 11 commits from Tasks 1–10 (Task 9 lands two: README, then mirrors), plus any pre-existing branch commits, and a working tree showing only the user's uncommitted ` M .gitignore`. Report completion to the user — the user decides when to push.
