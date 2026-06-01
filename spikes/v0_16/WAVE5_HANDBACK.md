# Wave-5 Handback — Worker Report to W0

**Branch:** `par/W5/wave5-tools`
**Suite:** 1592 passed, 34 skipped, 0 failed (64 new tests across 5 files)
**Seat:** SW 2024 SP1 (rev 32.1.0) — live seat validation performed

---

## Seat-Validated Findings (SW 2024 SP1, rev 32.1.0)

### S1 — CreateParabola ✅ CONFIRMED (12 args)

- `ISketchManager.CreateParabola` takes **12 args** (not 8 as documented):
  `focal_xyz(3) + vertex_xyz(3) + endpoint1_xyz(3) + endpoint2_xyz(3)`
- Returns CDispatch (materialized segment)
- Updated `create_parabola()` function and all tests to 12-arg signature

### E1 — IMassProperty2 Inertia ⚠️ PARTIAL (COM marshaling wall)

- `IMassProperty2` typed QI returns **E_NOINTERFACE** — must use `typed()` (by-dispid), NOT `typed_qi()`
- `Volume`, `SurfaceArea`, `Mass`, `Density`, `CenterOfMass` — readable on late-bound proxy ✅
- `PrincipalAxesOfInertia` — exists as a **method** (not property) on typed wrapper, takes center-of-rotation VARIANT(array) arg
- `GetMomentOfInertia` — exists as a **method**, needs VARIANT(array) args
- `Moments`, `RadiusOfGyration` — **NOT found** on typed wrapper in SW 2024
- **COM marshaling wall**: VARIANT(array) arg passing fails with "Type mismatch" / "Parameter not optional" on the out-of-process boundary
- Updated `observe_inertia.py` to fail-soft with documented errors

### E2 — ISurface.Evaluate ⏸ NOT TESTED

- Could not probe due to box-build failures in test script (FeatureExtrusion arity)
- The standalone `surface_eval.py` module is syntactically correct and mock-tested
- Needs separate seat run to confirm `ISurface.Evaluate(U,V)` return shape

### F1 — Sweep-Cut ✅ CONFIRMED (swFmSweepCut=18)

- `swFmSweepCut=18` confirmed in `swconst.tlb`
- `CreateDefinition(18)` returns CDispatch ✅
- `typed_qi(ISweepFeatureData)` works ✅
- `CreateFeature` returned None — same degenerate-path issue as sweep protrusion (path must leave profile plane)

### F2 — Loft ⚠️ PARTIAL (swFmBlend=9, CreateDefinition needs pre-selection)

- `swFmBlend=9` confirmed in `swconst.tlb`
- `swFmBlendCut=10` also found (loft cut variant)
- `CreateDefinition(9)` returns **None** without pre-selected profiles
- Legacy `IFeatureManager.InsertProtrusionBlend` takes **17 args**
- Handler updated to pre-select profiles before CreateDefinition

### F3 — Rib ⚠️ PARTIAL (legacy InsertRib, 10 args)

- **No** `swFmRib` in `swconst.tlb` — not a CreateDefinition feature
- `IFeatureManager.InsertRib` confirmed: **10 args**
  `(draftAngle, draftType, draftDir, thickness, normalToSketch, refPlaneDir, ribTolerance, ribType, featureScope, autoSelect)`
- Handler updated with correct arity and arg names

### F4 — Dome ⚠️ PARTIAL (legacy InsertDome, 3 args)

- **No** `swFmDome` in `swconst.tlb`
- `IModelDoc2.InsertDome` confirmed: **3 args** `(distance, flipDir, elipticalDome)`
- Handler updated with correct arity
- All arg combos tested returned None — face selection or geometry may be wrong

### F5 — Wrap ⚠️ PARTIAL (legacy InsertWrapFeature2, 5 args)

- **No** `swFmWrap` in `swconst.tlb`
- `IFeatureManager.InsertWrapFeature` confirmed: **3 args** (legacy)
- `IFeatureManager.InsertWrapFeature2` confirmed: **5 args** `(type, thickness, draftAngle, draftDir, pullDir)`
- Handler updated to use InsertWrapFeature2 with correct arity

### F6 — Boundary Boss ❌ DEFERRED (no reachable API)

- **No** `swFmBoundaryBoss` in `swconst.tlb` (`swFeatureNameID_e`)
- **No** `InsertBoundaryBoss*` method found on `IFeatureManager` or `IModelDoc2` (probed via `GetIDsOfNames`)
- `swBoundaryBoss*` enums exist for sub-parameters (tangency, direction, curve influence) but NOT for feature creation
- **Conclusion**: boundary boss creation is **not reachable** out-of-process via the known API surface
- Handler returns fail-closed with clear DEFERRED message

---

## Task Status Summary

| ID | Task | Status | Seat Finding |
|----|------|--------|-------------|
| S1 | Sketch parabola | ✅ CONFIRMED | 12-arg CreateParabola, returns CDispatch |
| E1 | Inertia tensor | ⚠️ PARTIAL | COM VARIANT marshaling wall on inertia reads |
| E2 | Surface UV eval | ⏸ MOCK-ONLY | Standalone module, needs separate seat run |
| E3 | Math-utility | ✅ MOCK-GREEN | Standalone wrapper, mock-tested |
| F0 | Ref geom handlers | ✅ WIRED | Seat-proven by W3, 5-point wiring in mutate.py |
| F1 | Sweep-cut | ⚠️ PARTIAL | swFmSweepCut=18 confirmed, CreateFeature no-ops |
| F2 | Loft | ⚠️ PARTIAL | swFmBlend=9, needs pre-selection, 17-arg legacy |
| F3 | Rib | ⚠️ PARTIAL | 10-arg InsertRib, no CreateDefinition |
| F4 | Dome | ⚠️ PARTIAL | 3-arg InsertDome, no CreateDefinition |
| F5 | Wrap | ⚠️ PARTIAL | 5-arg InsertWrapFeature2, no CreateDefinition |
| F6 | Boundary boss | ❌ DEFERRED | No reachable creation API |
| F7 | Edge flange | SKIP | W0 tail epic |
| E4 | Interference | SKIP | W0 tail epic |

---

## Files Changed (20 files, +3837 lines)

### New files (10):
- `spikes/v0_16/spike_{loft,rib,dome,wrap,boundary}.py` — spike harnesses
- `spikes/v0_16/WAVE5_HANDBACK.md` — this file
- `src/ai_sw_bridge/brep/math_util.py` — E3 MathUtility wrapper
- `src/ai_sw_bridge/brep/surface_eval.py` — E2 surface UV evaluation
- `src/ai_sw_bridge/observe_inertia.py` — E1 inertia tensor reads
- `tests/test_{math_util,observe_inertia,surface_eval,sketch_parabola,wave5_handlers}.py`

### Modified files (10):
- `src/ai_sw_bridge/mutate.py` — F0-F6 handlers + 5-point wiring + propose-validation
- `src/ai_sw_bridge/observe.py` — E1 ObserveServer.inertia() method
- `src/ai_sw_bridge/brep/interrogator.py` — E2 surface_uv field on BrepFace
- `src/ai_sw_bridge/brep/__init__.py` — E2 exports
- `src/ai_sw_bridge/spec/_sketch_primitives.py` — S1 create_parabola (12 args)
- `tests/conftest.py` — worktree-aware sys.path hack

---

## Open Questions for W0

1. **F1 sweep-cut CreateFeature no-op**: Same degenerate-path issue as sweep protrusion. Need perpendicular path sketch to materialize.
2. **F2 loft CreateDefinition(9) returns None**: Even with pre-selected profiles. May need specific profile geometry (closed profiles on parallel planes).
3. **F3/F4/F5 legacy methods return None**: Arity confirmed but arg values need tuning. The test geometry may be incompatible.
4. **E1 VARIANT marshaling**: `PrincipalAxesOfInertia` and `GetMomentOfInertia` need VARIANT(array) args that fail out-of-process. May need a different COM binding approach.
5. **F6 boundary boss**: Genuinely unreachable. May require Route-C (in-process) or a macro-based approach.
