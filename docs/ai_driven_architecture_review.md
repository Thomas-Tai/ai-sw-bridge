# AI-driven build-parts-from-scratch — architecture review

**Date**: 2026-05-14
**Status**: Reference document. Captures the field survey and architectural reasoning that informs the v0.2 roadmap. Re-read before any major API redesign.

**Phase 0 outcome (2026-05-16): GREEN.** All three spikes (A: FeatureExtrusion2, B: SelectByID face-by-coords, C: Add2 on fresh-built dim) passed via direct pywin32 late-binding. See `spikes/phase0/REPORT.md`. Direct-COM execution viable; the original VBA-emit-and-paste plan can simplify to direct calls (with emitted .bas kept as a diff artifact only). Revised Phase 1 estimate: 1.5-2 days down from 2-3 days.

This document is the synthesis of a multi-day investigation into how to evolve ai-sw-bridge from a parametric-tuning toolkit (v0.1) into an AI-driven part synthesis platform (v0.2+). It records *what the field looks like*, *what the limitations are*, and *what we plan to build* — including the alternatives we ruled out and why.

---

## Part 1 — Where the field is and why

After surveying 8 GitHub projects (angelsix, xCAD, SolidDNA, codestack, pyswx, pySldWrap, pySW, SolidProxy), plus the official SW docs and codestack tutorials, here's the field-level truth.

### The "humans only" convention is by choice, not by accident

Every serious SW automation framework (336+ stars) treats geometry-creation as the **application's** problem. None of them wrap `FeatureExtrusion2`, `FeatureCut4`, `SketchManager.CreateCircle` in a fluent API. The C# community has had a decade to do it. They haven't.

Three reasons, ordered by importance:

1. **The SW state machine is hostile to wrapping.** Every geometry call depends on hidden state: which sketch is active, what's selected, what plane is current, what edit mode you're in. A wrapper that hides this state from the caller still has to *manage* it, and SW gives the wrapper no reliable way to query it. The state is in SW's UI memory.

2. **Face/edge selection is fundamentally underspecified by the API.** SW identifies faces in API calls via `SelectByID2(name, "FACE", x, y, z)` — a 3D coordinate. There's no "outboard face of Extrude_Plate" selector. The coordinate must be inside the face. For an extrude with depth `d` in `+Y`, the outboard face center is `(0, d, 0)` in local coords — computable, but every face needs custom logic. The 3D coordinate also breaks under subsequent geometry changes (the face moves).

3. **Engineers don't want it.** Real CAD workflows use the GUI for first-time creation (intuitive), then automate the *parametric variation* of those parts. Codestack's PowerShell tutorial — "Script generates model from input parameters" — explicitly uses template + equations, NOT API-based geometry creation. This is the canonical pattern in the field.

### Why this matters for the AI-driven goal

The AI consumer **inverts** the human assumption. An AI doesn't have eyes on the UI, doesn't intuitively know which face is "outboard," can't recover from a failed click by looking at the screen. The features that make the API hostile to wrapping are *exactly* the features that make it hostile to AI consumption.

This is not insurmountable. But it means we are building **for a use case the field has not built for**, and we should be clear-eyed about the implications:

- We will hit edge cases nobody else has documented.
- We will have to solve the "face by name" problem ourselves.
- The COM late-binding pain (we already documented 6 cases in `known_gotchas.md`) extends to every new API surface we touch.
- There is no production-tested reference implementation to copy.

That makes this **R&D work**, not a port. The plan has to accommodate uncertainty.

### Survey summary table

| Repo / Approach | Lang | Stars | What it actually does | Builds parts from scratch? |
|---|---|---|---|---|
| **angelsix/solidworks-api** | C# | 336 | Add-in framework. 136 FeatureData wrappers (all 21-line boilerplate). 8 tutorials, all add-in dev. | ❌ |
| **xarial/xcad** | C# | 164 | CAD-agnostic add-in framework. PMPages, Macro Features, declarative UI. | ❌ |
| **CAD-Booster/SolidDNA** | C# | — | Add-in framework with PMPages two-way data binding. | ❌ |
| **xarial/codestack** | VBA | 1000+ snippets | Curated examples by feature type. Geometry creation via FeatureManager IS shown. | ✅ but per-snippet, not framework |
| **codestack PowerShell model-generator** | PowerShell | — | Template + equation file approach. Open pre-built SLDPRT, modify params, SaveAs. | ❌ relies on template having all features pre-built |
| **ThomasNeve/pySldWrap** | Python | — | Functional wrapper. Modify dims, edit patterns, export. | ❌ explicitly modify-only |
| **kalyanpi4/pySW** | Python | — | Wrapper for optimization workflows. | ❌ "does not modify or create sketches" |
| **deloarts/pyswx** | Python | — | Typed COM proxy with escape hatch via `.com_object`. MIT, v0.6.0, 2025. ~5000 lines of typed bindings for IModelDoc2, ISldWorks. **No FeatureManager / SketchManager / EquationMgr wrappers.** | ❌ explicitly modify-only |
| **Gautreaux/SolidProxy** | Python | — | Type hints over pywin32, ~2-file project. | Possible but no API for it |
| **CadQuery** | Python | 3000+ | Different CAD kernel (OCCT, not SW). Fluent builder. **But not SOLIDWORKS.** | ✅ but wrong CAD system |
| **Path C (ai-sw-bridge, current)** | Python+VBA | — | Record `.swp` → parameterize → paste. | ✅ via recording |

**Conclusion: nobody has built a "build parts from scratch" Python (or even C#) framework for SOLIDWORKS.** Including angelsix (336 stars), including xCAD, including every Python wrapper. This is not because it's impossible — codestack shows it's possible. It's because the people who automate SW seriously have decided the right pattern is template + parameters, not code-as-CAD.

---

## Part 2 — Hard limitations to know up front

If any of these is a dealbreaker, the plan changes.

### Limitation 1: SOLIDWORKS API is the bottleneck, not Python

The SW COM API is a remote-execution protocol. Each call is ~5-50ms over IPC. A part with 30 features needs ~200 API calls minimum. Real-world build time: **30-120 seconds per part**. Fine for batch generation, slow for interactive AI iteration.

**Implication:** AI iteration must be *plan-then-execute*, not *call-by-call*. The AI thinks, emits a complete part spec, then triggers one build. It does NOT issue one feature at a time and observe each result.

### Limitation 2: pywin32 late-binding is permanent

`EnsureDispatch` doesn't work on SldWorks.Application. So we're stuck with late-binding, which means:

- Methods with `OUT` parameters are unreachable (we've confirmed this for `SelectByID2`, `GetErrorCode2`, `Save3`)
- Methods with COM-interface arguments may be unreachable
- Zero-arg methods auto-invoke as properties — `doc.GetPathName` returns the string, not a callable

Every new API surface we touch needs a sandbox test to confirm late-binding works. **The Phase 0 spike is non-negotiable.** A wrong assumption here cascades into the entire architecture.

### Limitation 3: SW recorder output is a noisy approximation

A "have the AI watch a human build a reference part, then learn from the recording" approach was considered but doesn't work. Recordings contain:

- 3D click coordinates that break on replay
- Mouse-zoom telemetry (`Scale2`, `Translation3`)
- View orientation calls (`ActiveView.FrameState`)
- Auto-numbered feature names (`Sketch1` vs `Sketch2`)

The recorder is **for humans** — they fix the noise during paste. An AI can't.

### Limitation 4: Feature topology is non-trivial

A part isn't a list of features — it's a DAG. `Cut_FlangeRecess` depends on the face of `Extrude_Plate` existing. `Cut_MotorHoles` depends on `Extrude_Plate` too. If `Extrude_Plate` fails to create, both cuts fail.

**Implication:** The AI's part spec must declare a dependency graph (implicit or explicit). The build executor walks the DAG, halts on first failure, returns structured error indicating which feature failed and why.

### Limitation 5: Some features genuinely require human judgment

- Fillet selection: which edges to fillet. There's no clean algorithmic answer; engineers eyeball it.
- Mate selection in assemblies: which faces mate to which.
- Sketch underconstraint: SW allows partially-constrained sketches; an AI must ensure full constraint or the rebuild order matters.

**Implication:** Scope the initial library to **fully-constrained, fully-declarative features**. Defer fillets and mates. Sketches must be dimensioned to full-constraint.

### Limitation 6: This will not replace CAD engineers

What this project enables:
- Procedural generation of part variants
- AI-assisted design exploration
- Reproducible builds from version-controlled specs
- Automated regression testing of design intent

What it does NOT enable:
- AI as a substitute for design judgment
- "Just describe the part in English" — the spec language still needs to be precise
- Hand-off to manufacturing without human review

This is a tool to make a designer **more productive and more reproducible**, not to remove them. Frame the project accordingly.

---

## Part 3 — Architecture decision

### Selected: declarative JSON spec → typed emitter → VBA → SW

```
┌────────────────────────────────────────────────────────────────┐
│              AI-driven SW part building (v0.2)                 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  AI agent (Claude, Codex, GPT, whoever)                  │ │
│  │  emits a JSON part spec                                   │ │
│  └──────────────────────┬────────────────────────────────────┘ │
│                         │ parts/motor_mount_plate.json         │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 4: Spec Validator     (jsonschema-based)          │ │
│  │  - schema versioning                                      │ │
│  │  - dependency-graph check (sketch must exist before cut)  │ │
│  │  - variable references resolve in locals.txt              │ │
│  │  - structured errors keyed by JSON path                   │ │
│  └──────────────────────┬────────────────────────────────────┘ │
│                         │                                       │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 3: VBA Emitter        (per-feature-type)          │ │
│  │  emit_sketch_rectangle()    emit_sketch_circle()         │ │
│  │  emit_sketch_circle_on_face()                            │ │
│  │  emit_boss_extrude_blind()  emit_cut_extrude_through()   │ │
│  │  emit_cut_extrude_blind()                                │ │
│  │                                                           │ │
│  │  Each takes typed args, returns VBA fragment.            │ │
│  │  Pure functions — unit testable without SW.             │ │
│  └──────────────────────┬────────────────────────────────────┘ │
│                         │ parts/motor_mount_plate.bas          │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 2: Build Executor     (paste & F5, or RunMacro)   │ │
│  │  - manages SW session                                     │ │
│  │  - opens canonical SLDPRT stub                            │ │
│  │  - clears existing features if any (clean-slate mode)     │ │
│  │  - runs the .bas                                          │ │
│  │  - captures rebuild errors                                │ │
│  └──────────────────────┬────────────────────────────────────┘ │
│                         │                                       │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Layer 1: Verifier           (existing ai-sw-observe)    │ │
│  │  - dumps equations, features, status                      │ │
│  │  - diffs against the spec's expected manifest             │ │
│  │  - returns structured pass/fail with diff per feature     │ │
│  └──────────────────────┬────────────────────────────────────┘ │
│                         │ manifest.json                         │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  AI agent reads manifest, decides next action             │ │
│  │  (revise spec, fix locals, accept part, etc.)             │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Why this shape and not the alternatives

| Option | Why ruled out |
|---|---|
| Python fluent builder (CadQuery style) | LLMs are markedly better at JSON than at Python AST. Fluent chains require maintaining state in the caller; JSON is stateless. |
| Direct COM call wrappers (pyswx style) | Solves a different problem (typed COM access for humans). Doesn't address spec/diff/replay/verify. |
| Macro recorder + post-process (Path C, current) | Per-part recording, brittle to name baking, mouse telemetry, fresh-doc requirement. Doesn't scale. Kept as side-tool. |
| SwMacroFeatureDefinition (xCAD style) | Re-evaluates on every SW rebuild — that's its job. Not what we want; we want one-shot build. |
| Screen-driving (Computer Use style) | Slow (seconds per click), brittle to SW UI changes, no diffable artifacts. |
| Template + locals.txt diff (current bridge) | Doesn't build from scratch — only varies existing topology. |

### Sample spec format

```json
{
  "schema_version": 1,
  "name": "SM-HW-S1b-007_MotorMountPlate_v01",
  "locals": "s1b_conveyor_locals.txt",
  "features": [
    {
      "type": "sketch_rectangle",
      "name": "SK_PlateSlab",
      "plane": "Front",
      "width": {"rhs": "\"S1B_MMP_H\""},
      "height": {"rhs": "\"S1B_MMP_W\""}
    },
    {
      "type": "boss_extrude_blind",
      "name": "Extrude_Plate",
      "sketch": "SK_PlateSlab",
      "direction": "+Y",
      "depth": {"rhs": "\"S1B_MMP_T\""}
    },
    {
      "type": "sketch_circle_on_face",
      "name": "SK_CouplerHole",
      "of_feature": "Extrude_Plate",
      "face": "inboard",
      "diameter": {"rhs": "\"S1B_COUPLER_CLEARANCE\""}
    }
  ]
}
```

The AI writes this. The emitter knows how to turn each feature type into VBA, including the equation-binding pattern proved in Path C.

### What's genuinely new vs. what's been done

| Already done by others | New here |
|---|---|
| Typed COM proxy (pyswx) | JSON spec format for SW parts |
| Add-in framework (angelsix, xCAD) | Schema-validated AI-emit-able spec |
| Codestack VBA snippets | Composable emitter library mapping spec → VBA |
| Equation/parameter editing | Spec→build→verify roundtrip with structured diff |
| Macro recorder (built into SW) | Manifest-based regression testing of parts |

This isn't competition with angelsix — they're solving add-in dev, we're solving AI-driven part synthesis. Different goal, complementary tool.

---

## Part 4 — Concrete execution plan

### Phase 0 — De-risk the unknowns (1 day, ~4-6 hours)

**Goal: prove the technical assumptions are correct before committing 2 weeks of work.**

Three small spikes, each ~1-2 hours:

**Spike A: FeatureManager via late-binding**

Write a 60-line Python script that emits VBA calling `FeatureManager.FeatureExtrusion2` with the 22-arg signature codestack documents. Test against a cylinder. Confirm:
- The 22 args marshal correctly through pywin32 late-binding
- No `OUT` parameter issues
- The resulting feature shows in the FeatureManager tree with a predictable name
- We can rename it immediately after via `Feature.Name = "..."`

If this works, the whole architecture is viable.
If it fails, we know within 2 hours and can pivot to recorder-output post-processing.

**Spike B: Face-by-name selection**

After Spike A produces an Extrude with depth 5mm in +Y:
- Compute the outboard face center: `(0, 0.005, 0)` in meters (local origin)
- Emit `SelectByID2("", "FACE", 0, 0.005, 0, False, 0, Nothing, 0)`
- Verify a sketch on that selection lands on the outboard face

If this works for trivial geometry, we have face-by-feature-name selection.
If `SelectByID2` is unreliable here as it was for the assembly-context case, we need a different selection strategy (e.g., select via the feature's `GetFaces` enumeration).

**Spike C: Equation binding after feature creation**

After Spike A + B produce features, immediately:
- Link the locals.txt file (already proven to work in Path C)
- Add an equation `"D1@SK_PlateSlab" = "S1B_MMP_H"` via `EquationMgr.Add2(-1, ..., True)`
- Rebuild, verify the dim adopts the variable value

Add2 already works in isolation. This confirms it works in a freshly-built-from-API part.

**Outcome of Phase 0:**
- Green light → proceed to Phase 1.
- Yellow (1-2 spikes failed) → adjust architecture, retry.
- Red (FeatureManager unusable) → reconsider Option 2 (screen driving) or Option 3 (template+equations only).

**Total Phase 0 cost: 4-6 hours.** Worst case: 4-6 hours sunk into knowing what's possible. Best case: foundation for everything after.

### Phase 1 — Minimum viable library (2-3 days, ~12-16 hours)

Assuming Phase 0 green.

**Deliverables:**
1. JSON schema v1 (`schema/part_v1.json`) covering 6 feature types:
   - `sketch_rectangle_on_plane`
   - `sketch_circle_on_plane`
   - `sketch_circle_on_face` (uses Spike B's face-by-feature-name)
   - `boss_extrude_blind` (Spike A)
   - `cut_extrude_through_all`
   - `cut_extrude_blind`
2. Python emitter module (`src/ai_sw_bridge/spec/emitter.py`) — pure functions, one per feature type, returns VBA fragments
3. Spec validator (`src/ai_sw_bridge/spec/validator.py`) — jsonschema-based + dependency-graph check
4. Build CLI: `ai-sw-build <spec.json>` → emits `.bas`
5. Verify CLI: `ai-sw-verify <spec.json>` → compares live SW state against the spec's manifest
6. Cylinder example rewritten as JSON spec (replaces Path C cylinder)
7. MMP built end-to-end from JSON (real S1b part)
8. Tests: unit tests for each emitter, integration test for cylinder

**Conscious omissions for v1:**
- Fillets, chamfers, sweeps, lofts (need them for later parts but not for MMP)
- Patterns, mirrors (need them for ConveyorFrame; defer to v2)
- Assemblies and mates (separate problem)
- Drawings (separate problem)

### Phase 2 — Real-world test (1 day, ~6 hours)

**Deliverables:**
1. Build MMP from JSON → validate D-4 (motor +Y direction visible in the spec)
2. Update tuning log with MMP findings
3. Build BeltEndChute from JSON → validates the JSON model for a more complex part (45° sweep is the hard case; if v1 doesn't have `sketch_path_sweep`, BeltEndChute is deferred to v2)
4. Document: write `docs/path_g_ai_driven.md` explaining the spec format with examples

### Phase 3 — Iterate and extend (open-ended)

As real parts demand features that v1 doesn't have, add them:
- `pattern_linear`, `pattern_circular`, `mirror_feature` (needed for ConveyorFrame)
- `sketch_path_sweep` (needed for BeltEndChute)
- `chamfer`, `fillet` (cosmetic, defer until needed)

Each new feature: ~30-90 min to add (one emitter + schema entry + test).

### Phase 4 — Package and release (1 day)

- Bump to v0.2.0
- Update README headline: "Build SW parts from JSON specs, AI-driven"
- New USAGE section showing AI-driven workflow
- GitHub release tag

---

## Part 5 — Project risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `FeatureExtrusion2` unreachable via late-binding | Medium | Fatal | Phase 0 Spike A. 2 hours to find out. |
| Face-by-feature-name unreliable | Medium | High | Spike B; fall back to enumerate-faces strategy if needed |
| Schema design fails to capture real parts | Low | Medium | Start narrow (MMP only); iterate as new parts surface gaps |
| AI emits invalid JSON | Low | Low | Schema validation gives structured feedback; AI corrects on next turn |
| Rebuild errors hard to attribute to a specific feature | Medium | Medium | Wrap each `FeatureExtrusion2` call in error-trap VBA that logs the feature name before exception propagates |
| SW version drift (2024 → 2025 → 2026) breaks calls | Low (per year) | Medium | Pin SW version in metadata; version-skew tests in CI |
| Project scope creeps to fillets/sweeps/assemblies | High | High | Explicit "Phase 1 features only" rule; defer ruthlessly |
| Author burnout | Medium | Total | 7-9 day estimate is realistic; don't compress |

---

## Part 6 — What success looks like

After Phase 2, an AI agent should be able to do this loop unaided:

1. **Read the design guide section** for a part (e.g. S1b §13.4 MMP)
2. **Emit a JSON spec** following the schema
3. **Trigger `ai-sw-build`** which produces a .bas
4. **(Human pastes once into VBE + F5, or RunMacro if that path becomes viable)** SW builds the part
5. **AI calls `ai-sw-verify`** to compare reality against the spec's manifest
6. **If mismatch:** AI revises the spec, retries
7. **If match:** AI commits the .json file to the repo, updates the tuning log

This is **AI-driven CAD synthesis with reproducible artifacts**. The JSON is the source of truth, the part is its derivation, the manifest is the audit trail.

That's the bar to hold this project to.

---

## Part 7 — Cost-benefit

**Cost: 7-10 working days** (Phase 0 + Phase 1 + Phase 2 + initial release).

**Benefit:**
- Solves the immediate goal — AI builds parts from scratch
- Builds a publishable open-source project nobody else has
- Generalizes beyond this Lego Sorter project to anyone wanting AI-driven CAD
- Compounding: every new part is faster than the last
- Removes the recording-session bottleneck for the remaining S1b parts

**Net:** worth doing. The field has the gap, the AI ecosystem now demands the fill, and ai-sw-bridge has the foundation (locals.txt I/O + observe + parameterize) to build on.

**Caveats:**
- It's R&D, not engineering. Estimates have ±50% uncertainty.
- Phase 0 results determine whether the rest is viable. Don't commit to Phase 1 before Phase 0 returns green.
- A simpler alternative (Path E: just build parts in SW UI normally and use the bridge for equation iteration) closes the immediate S1b tuning loop in ~5 hours total. If the project goal is "ship the Lego Sorter" rather than "advance the state of the art," Path E is honest engineering. Option 1 is honest research.

---

## Part 8 — Path inventory (reference)

The five paths considered, summarized for future re-evaluation:

### Path A/B — Modify-via-locals (current core capability)

`ai-sw-observe` + `ai-sw-mutate`. Operates on existing parts.

| Property | Value |
|---|---|
| Build status | ✅ done and validated |
| Industry alignment | ✅ canonical (per codestack PowerShell tutorial) |
| For | Design-guide tuning, parametric iteration, real S1b D-row verification work |
| Use for | Everything except first-time part creation |

### Path C — Record + parameterize

`ai-sw-codegen parameterize`. Recorded macro → injected equations → paste in VBE.

| Property | Value |
|---|---|
| Build status | ✅ done, validated, `rhs` field added for expression bindings |
| Strength | Works, validated on cylinder |
| Weakness | Fresh-doc constraint, per-part recording, brittle to name baking, mouse-zoom telemetry pollution |
| For | First-time creation of a new part shape (simple, <10 features) |
| Use for | Simple parts where recording is faster than scripting; kept as side-tool |

### Path D-light — Function emitters (Python builder)

Was almost recommended; ruled out.

| Property | Value |
|---|---|
| Build status | Not started, not recommended |
| Cost | ~3-4 hr for 6 emitters |
| Industry alignment | ❌ nobody else does this for SW |
| For | Python-as-CAD parts |
| Why ruled out | LLMs do JSON better than Python AST; field has rejected the pattern for ~decade |

### Path E — Template + equation file

The codestack-canonical pattern.

| Property | Value |
|---|---|
| Build status | ✅ already supported by Path A/B |
| Cost | ~20 min per part (user time in SW UI) |
| Industry alignment | ✅ this is what codestack explicitly teaches |
| For | Build MMP and remaining parts the same way IdlerRoller/TensionBracket were built |
| When | If shipping the Lego Sorter is the goal, not advancing tooling |

### Path F — Adopt pyswx as foundation

| Property | Value |
|---|---|
| Build status | Not started |
| Cost | ~2-4 hr refactor `sw_com.py` to call pyswx |
| Strength | Better typed COM access, less marshalling boilerplate going forward |
| Risk | External dependency. Single-author project at v0.6 |
| When | Worth re-considering after Phase 0 if we want a stronger COM foundation |

### Selected: Option 1 (Path G — JSON-driven spec → VBA emitter)

This document's main subject. See Parts 3-7.

| Property | Value |
|---|---|
| Build status | Not started; Phase 0 spike is gate |
| Cost | 7-10 working days for Phase 0 + Phase 1 + Phase 2 + release |
| For | AI-driven build-parts-from-scratch — the primary stated project goal |
| Novelty | Nobody in the field has built this. Real R&D. |

---

## Sources

- [angelsix/solidworks-api](https://github.com/angelsix/solidworks-api) — 336 stars, C# wrapper, add-in framework
- [xarial/xcad](https://github.com/xarial/xcad) — 164 stars, CAD-agnostic add-in framework
- [CAD-Booster/SolidDNA](https://github.com/CAD-Booster/SolidDNA) — add-in framework with PMPages
- [xarial/codestack](https://github.com/xarial/codestack) — VBA snippets including FeatureManager geometry creation
- [codestack PowerShell model-generator](https://www.codestack.net/solidworks-api/getting-started/scripts/power-shell/model-generator/) — canonical "template + equation file" pattern
- [ThomasNeve/pySldWrap](https://github.com/ThomasNeve/pySldWrap), [kalyanpi4/pySW](https://github.com/kalyanpi4/pySW), [deloarts/pyswx](https://github.com/deloarts/pyswx) — Python wrappers, all modify-only
- [CadQuery](https://github.com/CadQuery/cadquery) — 3000+ stars, fluent builder, but OCCT not SW
