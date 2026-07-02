# Phase 3 — Contributor & Architecture Rigor — Design Spec

**Status:** DRAFT (awaiting user review gate)
**Date:** 2026-07-02
**Branch:** `docs/commercial-elevation`
**Governs:** Phase 3 of `docs/superpowers/specs/2026-07-01-commercial-google-standard-elevation-design.md` (§10)
**Predecessors:** Phase 0/1/2 SHIPPED to master (`ee8ada4..a4174695`).

---

## 1. Intent

`builder.py` (3335 LOC) becomes pure orchestration; a new engineer extends safely. Relocate the six `_build_*` handler families to `spec/handlers/*.py` via the existing `_wire_handlers`/`DESCRIPTORS` seam as **pure relocations** (dispatch key + resolution unchanged, no behavior change), behind an acyclic shared kernel. Then promote the module-size gate to blocking, strengthen the conformance test, expand mypy, and rewrite `CONTRIBUTING.md`.

**This is a refactor, not a feature.** The invariant across every task: `HANDLERS`/`DESCRIPTORS` dispatch is byte-for-byte identical; the seat-safe suite (3894) stays green at every commit; no walled/dormant kind is promoted.

---

## 2. Locked decisions (from the Phase 3 brainstorm)

Adjudicated this session; not reopened without new technical evidence (escalate if it appears).

### 2.1 Move 0 — the lean acyclic kernel `spec/handlers/_common.py`

Exactly **three** symbols, all genuinely cross-family COM/transport primitives:

| Symbol | Role | Test seams to carry |
|---|---|---|
| `_mm_to_m` | universal mm→m unit conversion | 4 |
| `_select_sketch` | profile selection by name — used by **extrude (#6) AND revolve (#2)**; revolve moves first, so it cannot ride with extrude (the forcing function) | 1 |
| `_r8_safearray` | SAFEARRAY-R8 COM marshalling primitive (COM-transport, not sketch-domain) | 1 |

`_common` imports only `BuildContext` from the already-leaf `_build_context.py` + `pythoncom`/`win32com` — **nothing** from `builder` or any handler module → acyclic leaf, passes import-linter on turn zero.

**Why lean:** prior strangler extractions already carry the shared infrastructure as leaves — types (`BuildContext`/`BuiltFeature`/`FeatureDescriptor` in `_build_context.py`, which is what kills the handler→builder type cycle), edge selection (`_edge_selectors.py`), face geometry (`_face_geometry.py`), sketch prims (`_sketch_primitives.py`), version resolution (`_version_resolver.py`), sketch handlers (`sketches`). A fat `_common` would be premature abstraction.

### 2.2 Migration sequence (risk-inverted, ascending coupling)

**Move 0 `_common` → 1. pattern → 2. revolve → 3. hole → 4. dress_up → 5. sketch → 6. extrude.**

Ordering rationale = measured monkeypatch-seam count + coupling, NOT the spec's stale "sketch is COM-free stubs" premise (falsified: `_build_sketch_line` calls `sm.CreateLine`). Seam counts: pattern/revolve/hole = **0** (proving ground); dress_up = **7** (`_select_edges`); sketch = **~28** (most-patched surface — high mechanical burden, late); extrude = **~15** + the `@versioned _cut4_args_2024/2025` version-resolver (the one *correctness* risk) → **truly last**, and the DoD live-seat re-fire candidate.

### 2.3 Module-size gate warn→block

Trigger: once `builder.py` is ≤ 800 LOC and removed from `tools/module_size_baseline.json`, flip the CI invocation of `tools/module_size_gate.py` to `--strict`. The other **8** grandfathered modules (`descriptors.py` 1513, `drawing/lifecycle.py` 2390, `observe.py` 2202, `mutate.py` 2181, `assembly/handlers.py` 1191, `export/dispatch.py` 1006, `brep/interrogator.py` 878, `cli/build.py` 811) **stay grandfathered** — accepted debt outside Phase 3 scope — and `--strict` then blocks their *growth* and any new >800 module.

---

## 3. Design — Move 0 and the per-family relocation

### 3.1 Move 0 — `spec/handlers/__init__.py` + `spec/handlers/_common.py`

- Create `spec/handlers/` package (`__init__.py`).
- Create `_common.py` holding the three §2.1 symbols, moved **byte-identical** (bodies unchanged; carry any module constant they reference).
- In `builder.py`: replace the three defs with `from .handlers._common import _mm_to_m, _select_sketch, _r8_safearray` **re-exported into builder's namespace** (so `builder._mm_to_m` etc. still resolve — the `client.py` `_impl` re-export precedent; keeps the 6 test seams biting without editing test files).
- Add an import-linter **forbidden** contract: `ai_sw_bridge.spec.handlers._common` may not import `ai_sw_bridge.spec.builder` (nor any `...spec.handlers.<family>`). Pins the leaf.
- **Seam re-point check:** the 6 tests patching `builder._mm_to_m`/`_r8_safearray` must still bite. Verify after the move (see §3.3).

### 3.2 Moves 1–6 — per-family relocation (uniform shape)

Each family is an independently shippable commit + review + green suite. For family **F** with handlers `H` and family-specific helpers `P`:

1. **Measure-first seam audit** (spec §10.2, mandatory): `grep` tests for every `builder.<sym>` this family owns; record the patch sites.
2. Create `spec/handlers/<F>.py`; move `H ∪ P` **byte-identical**, carrying each family constant with its handler (missing imports pass offline — mocks patch the seam — and fail only at the live seat, so port imports carefully).
3. `<F>.py` imports leaves only: `_common`, `_build_context`, `_face_geometry`, `_edge_selectors`, `_sketch_primitives`, `_version_resolver`, `sketches` — never `builder`.
4. In `builder.py`: `from .handlers.<F> import (H..., P...)` **re-exported into builder's namespace** so `DESCRIPTORS`/`_wire_handlers` still reference the same names and every `builder.<sym>` test seam still resolves.
5. **Verify the seam still bites** (§3.3) — the anti-mirror check for refactors.
6. `HANDLERS`/`DESCRIPTORS` dispatch unchanged — assert via the conformance test.

Per-family symbol assignments (from the locked ledger):

| Move | Module | Handlers | Family-specific helpers/constants moved with them |
|---|---|---|---|
| 1 | `pattern.py` | `_build_linear_pattern`, `_build_circular_pattern`, `_build_mirror_feature` | `_mark_first_selection` |
| 2 | `revolve.py` | `_build_revolve_boss`, `_build_revolve_cut` | `_call_feature_revolve` |
| 3 | `hole.py` | `_build_simple_hole` | (none — uses `_face_geometry` leaves + raw COM) |
| 4 | `dress_up.py` | `_build_fillet_constant_radius`, `_build_chamfer_edge` | `_edge_fingerprint`, `_all_solid_edges`, `_select_edges`, `_EDGE_FP_REFS`, `SW_FM_FILLET`, `SW_CONST_RADIUS_FILLET` |
| 5 | `sketch.py` | `_build_sketch_line/arc/spline/slot/polygon/ellipse/text/3d_sketch` | `_enter_plane_sketch`, `_close_plane_sketch_and_build`, `_apply_construction`, `_segments`, `_enter_3d_sketch`, `_close_3d_sketch_and_build`, `_as_sketch_text`, `_apply_text_format` |
| 6 | `extrude.py` | `_build_boss_extrude_{blind,midplane,through_all,two_direction,up_to_surface}`, `_build_cut_extrude_{through_all,blind,midplane,two_direction}` | `_call_feature_extrusion`, `_call_feature_cut`, `_cut4_args_2024`, `_cut4_args_2025`, `_boss_built_feature` |

**Stays in `builder.py` (orchestration spine, locked):** `build`, `run_feature_step`, `_health_gate`, `_build_one_feature`-equivalent loop, `_collect_bindings`/`_apply_bindings`/`_apply_deferred_dims`, RHS/locals cluster (`_load_locals_map`, `_safe_arith_eval`, `_eval_rhs`, `_resolve_rhs_in_spec`, `_ARITH_*`), `_default_rhs_walker`/`_circles_on_face_rhs_walker`, `create_blank_part`/`link_locals`, `_write_brep_sidecar`/`_save_as_with_verification`, the result `@dataclass`es, `DESCRIPTORS`/`_wire_handlers`/`HANDLERS`/`FEATURE_REGISTRY`/`DIM_FIELD_MAP`, `PLANE_NORMALS`, `SAVE_FORMAT_VERSIONS`, `SW_PREF_INPUT_DIM_VAL_ON_CREATE`. Target ~800 LOC.

### 3.3 The refactor anti-mirror check (per move)

A relocated seam that no longer bites is a silent regression (the Phase-2 snapshot-mirror lesson, applied to monkeypatch). After each move, for ≥1 patched symbol in the family: confirm the test that patches `builder.<sym>` still exercises the moved code (temporarily break the moved function, confirm the patching test FAILS, revert). If a seam no longer bites through the builder re-export (e.g. `DESCRIPTORS` captured the pre-patch reference at wire time), **re-point that test** to `handlers.<F>.<sym>` rather than leave a dead patch — and record it in the move's ledger.

### 3.4 `@versioned` import-order (extrude, Move 6)

`_cut4_args_2024/2025` self-register into the version-resolver registry at import. `spec/handlers/extrude.py` must be imported before first dispatch. `_wire_handlers()` already imports handler modules to populate `DESCRIPTORS`; confirm the extrude import runs at builder import time so the `@versioned` registry is populated. **Add an explicit test** that `resolve_op("FeatureCut4", <2024>)` and `<2025>` both resolve after a fresh `import builder` (guards the import-order regression the relocation risks).

### 3.5 WALL-NO-AMNESTY

A relocation never promotes a walled/dormant kind to GREEN. Verify each family's `DESCRIPTORS` entries keep their exact status; a dormant handler moves dormant.

---

## 4. Other Phase-3 work (§10.3)

### 4.1 Module-size gate warn→block
After Move 6, measure `builder.py`; if ≤ 800, remove its `module_size_baseline.json` entry and flip CI to `tools/module_size_gate.py --strict`. Add the new `spec/handlers/*.py` files (each must be < 800 — verify sketch.py/extrude.py, the largest, land under budget; if a family module itself exceeds 800, that's a signal to split it further, not to baseline it). The 8 other grandfathered modules stay baselined (documented as out-of-scope accepted debt).

### 4.2 Strengthen `tests/test_extension_conformance.py`
Grows in place (not replaced). After decomposition, assert the unified self-registration shape: every `spec/handlers/<family>.py` contributes to `DESCRIPTORS`; `HANDLERS` keys == the pre-refactor set (snapshot); dispatch resolves each kind to a callable in a `handlers.*` module. Reconciles the Phase-0 weak-form membership test to the now-landed contract.

### 4.3 mypy strictness
Extend the strict-typed set to the new `spec/handlers/*.py` modules (match the config mechanism already used for `features/`). Handlers are `(BuildContext, dict) -> BuiltFeature` — already typed; the move should keep them strict-clean.

### 4.4 `CONTRIBUTING.md` rewrite
Re-grep D3/D4/D5 at execution (some already fixed — CONTRIBUTING's version pin is doc-truth-green, so D3 likely done). Deliver:
- **D5 (substantive):** document the `features/` `HANDLER_REGISTRY` recipe (how to add a `feature_add` kind) **and** the new `spec/handlers/` recipe (how to add a spec-build handler) — the two distinct extension registries.
- Publish the **five-row Extension Contract** (the crown jewel, §6 of the governing spec).
- Promote `CLASS_RELATION_MAP.md` as the canonical architecture doc; mark `docs/architecture.md` superseded (D8).
- Any still-open D3/D4 wording.

---

## 5. Safety & invariants (non-negotiable)

1. **Seat-prefire-review before EVERY move** — all six families and `_common` are COM-adjacent (`builder.py` imports `get_sw_app`; handlers call live COM). Static grep + dynamic tripwire (monkeypatch Dispatch/DispatchEx/GetActiveObject/EnsureDispatch/CoCreateInstance, import target, assert `TRIPPED==[]` and SLDWORKS PID unchanged) before any subagent touches a handler file.
2. **Seat-safe suite only** — `pytest -m "not solidworks_only and not destructive_sw"`; never bare `pytest`; never `tests/e2e_sw/` or `tests/mcp_lane/` bodies. Green at **every** commit (baseline 3894).
3. **Spot live-seat re-fire** — DoD requires ≥1 relocated GREEN family re-proven on the live seat. Candidate: **extrude** (Move 6, the correctness-risk family). Run `seat-prefire-review` first; fire a spike against the seat; destructive-SW isolation.
4. **No behavior change** — byte-identical moves; `HANDLERS`/`DESCRIPTORS` dispatch identical; conformance snapshot unchanged. doc-truth pins preserved (esp. `feature_kinds`/`descriptors` counts derived from `HANDLER_REGISTRY`/`ALL_TYPES`).
5. **HELD push** — no push until the whole phase is green, then a single `isPrivate`-guarded fast-forward to master.
6. **Branch** `docs/commercial-elevation`; never `feat/w67-phase3`.
7. **Import-linter** — new leaf/forbidden contracts for `_common` and the handler layer; `2+ kept, 0 broken` at every commit.

---

## 6. Non-goals

- Do **not** touch the 8 other grandfathered modules (no splitting `descriptors.py`, `mutate.py`, etc.).
- Do **not** change `descriptors.py` (the schema layer) — Phase 3 moves *handlers*, not schema assembly.
- Do **not** refactor the `features/` `HANDLER_REGISTRY` — only *document* it (D5).
- No new feature kinds; no walled-kind promotion; no engine/COM behavior change.
- No i18n retranslation (Phase 4).

---

## 7. Definition of Done (§10.4)

- [ ] `spec/handlers/_common.py` + all six `spec/handlers/<family>.py` landed; each an independently-shipped, green commit.
- [ ] `builder.py` holds only orchestration (~800 LOC); handlers gone from it (re-exported for seams).
- [ ] `HANDLERS`/`DESCRIPTORS` dispatch byte-identical (conformance snapshot unchanged); no walled-kind promotion.
- [ ] Module-size gate `--strict` in CI; `builder.py` off the baseline; new handler modules under budget.
- [ ] `test_extension_conformance.py` strengthened to the self-registration contract, green.
- [ ] mypy strict across `spec/handlers/*.py`.
- [ ] `CONTRIBUTING.md` rewritten (D5 registry recipes + Extension Contract + CLASS_RELATION_MAP canonical; D3/D4 re-grep).
- [ ] Full seat-safe suite green (3894+); import-linter kept/0-broken; ≥1 live-seat re-fire (extrude) GREEN; single isPrivate-guarded FF push.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Relocated monkeypatch seam silently stops biting (mirror regression) | §3.3 anti-mirror check per move: break-the-moved-fn → confirm patching test fails → revert; re-point dead seams |
| `@versioned` extrude registry not populated after move → live-seat version dispatch fails | §3.4 explicit `resolve_op` post-import test; extrude last, after mechanic proven; live-seat re-fire |
| Missing import ports offline-green but fails only at the seat (mocks hide it) | §3.2 carry constants with handlers; the extrude live-seat re-fire is the backstop |
| Circular import builder↔handlers | Option-B acyclic kernel (`_common` leaf) + import-linter forbidden contract; handlers import leaves only |
| A handler module itself exceeds 800 LOC (sketch/extrude) | If so, split further (not baseline) — signals a sub-family seam; decide at measure time |
| doc-truth count drift (descriptors/feature_kinds) | Counts derive from `HANDLER_REGISTRY`/`ALL_TYPES`, unchanged by a pure relocation; re-run doc-truth per commit |

---

## 9. Self-review (pre-user-gate)

- **Grounded, not spec-verbatim?** Yes — falsified "sketch = COM-free stubs"; corrected "five offenders"→9 grandfathered; confirmed `_call_feature_revolve`→`_select_sketch` forcing function; confirmed hole self-contained via `_face_geometry`; verified gate already supports `--strict`.
- **Honors locked decisions?** Yes — lean 3-symbol `_common`, the sequence, extrude-last live-seat gate, warn→block trigger all transcribe the ratified adjudications.
- **Refactor safety explicit?** Yes — byte-identical moves, anti-mirror seam check, seat-prefire per move, dispatch-unchanged invariant, HELD push.
- **Scope disciplined?** Yes — other 8 grandfathered modules and `features/` registry refactor are explicit non-goals; only builder handlers move.
- **Open for the plan (not the design):** exact re-export vs re-point per seam (measured per family at implement time); whether sketch.py/extrude.py need sub-splitting to stay < 800 (measured after the move).

---

**NEXT:** user review gate on this design. On approval → writing-plans to cut the Phase 3 implementation plan (Move 0 + six family moves as SDD tasks with per-move seat-prefire, anti-mirror seam checks, checkpoints/telemetry; then the gate/conformance/mypy/CONTRIBUTING closers), then SDD execution with the HELD isPrivate-guarded FF push.
