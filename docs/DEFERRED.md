# Deferred Items

Single source of truth for items scoped, evaluated, and intentionally
held for a later release. Items here have been considered and either
need data we don't have yet, are out-of-scope for their cohort
release, or are too large to justify the cost today.

When something here ships, **remove the row** (preserve history via
git log) and reference the implementing commit in `CHANGELOG.md`.

---

## Open strategic decisions

| Item | First raised | Decision rationale |
|---|---|---|
| **L5 collapse via VBA emit-and-run** | 2026-05-23 | `SolidworksMCP-python/vba_adapter.py` pattern may make the C# in-process adapter obsolete. Re-evaluate after v0.13 produces stability telemetry. |
| **L3 corpus boundary** — `sldworksapiprogguide.chm` ingestion strategy | 2026-05-23 | Whether the programmer's guide goes into the main corpus (dedup) or stays as a separate `examples` sub-corpus. Decide after gathering precision@k data from real RAG usage. |
| **L4 multi-part storage** — per-part `.sqlite` vs shared per-project DB | 2026-05-23 | **RESOLVED 2026-06-05 (W14):** neither — extended the per-assembly JSON manifest (`<asm>.sldasm.manifest.json`, schema v2: verbatim spec + runtime overlay) instead of SQLite. Consistent with the per-part `brep.manifest` pattern, git-friendly, zero new deps. SQLite-per-project stays deferred until a cross-assembly query/scale need actually exists. Retained for decision history. |

## Open technical questions

| Item | Source | Resolution path |
|---|---|---|
| **L1 face-fingerprinting tolerance** (6-decimal quantization) | `spec.md` §9.1 (legacy) | Measure actual rebuild noise on a canonical MMP build across SW SP levels before committing. |
| **L2 hint catalog completeness** | `spec.md` §9.2 (legacy) | Append-only; new hints accumulate from telemetry. Not a one-time deferral. |
| **L5 trigger telemetry definition** — what does "pywin32 stability issues" mean concretely? | `spec.md` §9.6 (legacy) | Define memory-leak growth-rate or failure-rate thresholds against a benchmark spec. Needs production baseline data. |

## v0.14 (deferred from v0.13 closure)

| Item | Rationale |
|---|---|
| **`observe.*` route through `runtime.adapter`** | Pre-existing W5.2 coupling. observe.* calls `sw_com.get_sw_app()` directly instead of the adapter. The W5.5 fixtures use union markers (`["$str", "$none"]`) to tolerate both, and the v0.13 `GetActiveObject` fix solves the cross-process attachment problem at a deeper layer — but cleanly routing observe through the adapter remains the right architectural fix. ~4-8h refactor across 10+ observe functions. |
| **CI snapshot tests SW-state-dependent** | Resolves automatically when observe.* uses the adapter. Until then, union markers tolerate both empty- and live-SW shapes. |
| **`docs/central_idea/todolist.md` doc rot** | Local scratch file (gitignored) where checkboxes remained `[ ]` even after items shipped. Cleaned up as part of v0.13 release prep (entire `docs/central_idea/` removed since gitignored). |
| **CI test job skips ~31 mcp_lane + keyring tests** | The `test` job installs `[dev]` only; `mcp` and `keyring` are not in `[dev]`, so `tests/mcp_lane/*` (test_server_contract.py × 4 + test_payload_snapshots × 21 + test_wire_e2e × 3 + test_checkpoint_info × 3) and `TestKeyringKeySource::test_reads_keyring` all `pytest.importorskip` to clean skips on CI. Locally with `[mcp]` installed every test runs and passes (947+ count in PR body is local). Two fix options: (A) one-line CI change `pip install -e ".[dev,mcp,crypto]" keyring`, or (B) add `mcp`/`cryptography`/`keyring` to the `[dev]` extra in `pyproject.toml`. (B) matches the principle that `[dev]` should exercise the full suite. First raised 2026-05-28 during the v0.13 PR CI greening. |
| **Release workflow has no skip-when-empty branch for GPG signing** | `.github/workflows/release.yml` step `Sign checksums with GPG` unconditionally imports `$GPG_SIGNING_KEY` and signs with key id `ai-sw-bridge-release`. When the repo has no `GPG_SIGNING_KEY` / `GPG_PASSPHRASE` secret configured (current state), the import is a no-op and `gpg --default-key` aborts the step, which skips the `Create GitHub Release` step entirely — so the tag push produces no Release at all. v0.13.0 hit this on 2026-05-29: tag pushed, workflow failed at GPG, the Release was created manually via the GitHub API with sdist + wheel + unsigned `checksums.txt` (no `checksums.txt.asc`). Two fix options: (A) configure the two repo secrets and re-run, or (B) make the GPG step conditional (`if: env.GPG_SIGNING_KEY != ''`) and drop `checksums.txt.asc` from the `files:` list when absent, so unsigned releases still publish. (B) keeps releases unblocked on contributors without signing keys; (A) is the right answer for the project's threat model. Until resolved, every future `v*.*.*` tag push will fail the same way. |

## v0.15 (deferred from v0.14 closure)

| Item | Rationale |
|---|---|
| **D-v0.14-01: classify the 11 non-sketch `_build_*` handlers** | Mirror, pattern, revolve, hole, fillet, chamfer. The `FEATURE_REGISTRY` dict in `spec/builder.py` already provides polymorphism; class ceremony adds no value until a new feature group lands that benefits from shared base behavior. |
| **D-v0.14-02: decompose `sw_types.py`** | 762-line constants module. Split into per-family modules (selection types, sketch types, mate types, etc.) once a refactor anchor (e.g. import-linter sub-lane) needs it. |
| **D-v0.14-03: remove `SW_PREF_INPUT_DIM_VAL_ON_CREATE`** | Toggle marked "harmless, may help on other SW builds." Remove once a verifiable build is found where it has no effect on a control corpus. |
| **D-v0.14-04: pywin32 → `comtypes` migration** | Already in this list since v0.10. v0.14 did not unblock. |
| **D-v0.14-05: CI doc-coverage gate** | Diff `cli/*.py` argparse flag inventory against `README.md` flag-reference table; fail on drift. Manual upkeep until then. |
| **D-v0.14-06: deeper `SolidWorksObserver` + `ProposalStore` migration** | v0.14 ships thin-facade classes that delegate to the legacy `sw_*` free functions. The deeper migration — move logic into methods, extract a `_with_active_doc` template method to remove `get_sw_app/get_active_doc/try-except` ceremony, parameterize app/doc providers via constructor for cleaner mocking, eventually delete the free-function shims — was bundled into the v0.14 plan and deferred mid-execution: every free function has unique error messages and edge cases that tests assert on; doing the full migration safely is ~5h of focused work that is worth its own PR. Class API surface is stable; only the internals move. |

## v0.16 / Wave-4 (deferred)

| Item | Rationale |
|---|---|
| **Edge Flange — ⛔ QUARANTINED 2026-06-09 (W42 ghost; the Wave-7 "SHIPPED" claim was FALSIFIED — see Wave-44 below)** | The out-of-process COM boundary is **fully cracked and characterized** (`spikes/v0_16/spike_edgeflange.py`, seat-run SW2024 SP1); only a geometric sub-task remains. **(1) COM marshaling solution:** the legacy `IFeatureManager.InsertSheetMetalEdgeFlange2` (13 args) rejects bare Python `None`/`pythoncom.Missing` on its trailing `IDispatch` args (`SketchFeats` arg 2, `CustomBendAllowance` arg 13) with "Type mismatch"; passing **`win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)`** for each clears every mismatch and the call executes cleanly (reusable pattern for any pedantic legacy SW signature out-of-process). The modern `CreateDefinition(37)→typed_qi(IEdgeFlangeFeatureData)→AddEdges` path is a **dead end** out-of-process: `AddEdges` accepts the edge array/dispatch but `GetEdgeCount` stays 0 (the IDispatch pointer is not unwrapped server-side). **(2) Valid `BooleanOptions` mask = `129`** (`swInsertEdgeFlangeUseDefaultRadius=1 | swInsertEdgeFlangeUseDefaultRelief=128`) — forces document defaults so the manual bend/relief args are ignored. **(3) Edge filtering:** pass the **longest linear boundary edge** (typed `IEdge→ICurve`, `IsLine()` + `GetLength`); the 2mm thickness edges are a guaranteed topological rejection. **Remaining blocker (deferred):** with `SketchFeats` nulled, the solver has no profile to define the flange wall length/shape (there is no flange-length scalar in the signature), so it correctly returns a silent `None`. Materializing requires constructing a profile sketch on a plane normal to the chosen edge and passing the `ISketch` — a dedicated geometry-automation epic (normal-to-edge ref plane → sketch the flange-height line → pair edge↔sketch 1:1 per `swEdgeFlangeError_NumberOfEdgesAndSketchesNotEqual`), not a tacked-on script. First raised 2026-05-31, Wave-4 closure. **Wave-6 update (2026-06-04):** the **auto-profile (null `SketchFeats`) path was exhaustively re-tested and WALLED** (`spikes/v0_16/spike_edgeflange_autoprofile.py`, 36 attempts across mark/options/angle/edge/route, all delta=0, silent `None`; base-flange precondition clean) — re-confirming the method needs a real profile. **BUT the predicted blocker is now RESOLVED:** the normal-to-edge ref plane + profile sketch shipped this wave as the `ref_plane` `edge_ref` variant (PAE GREEN, `d25f73e`). **Edge-flange custom-profile is the tractable Wave-7 LEAD task** — distinct from the rib/wrap/E4 no-API-path walls; the only remaining work is (a) **typelib-verify the `InsertSheetMetalEdgeFlange2` 13-arg signature** (the Wave-6 sweep used a guessed positional vector — guessed enums silently no-op, the standing T6 lesson) and (b) pass the normal-edge profile sketch as `SketchFeats`, paired 1:1 with the edge. **Wave-7 resolution — SHIPPED 2026-06-04 (gate `3c652df`):** both unknowns cleared. (a) The 13-arg signature was typelib-dumped (`FlangeEdges`/`SketchFeats`=VARIANT, then `BooleanOptions`/`FlangeAngle`/`FlangeRadius`/`BendPosition`/`FlangeOffsetDist`/`ReliefType`/`FlangeReliefRatio`/`FlangeReliefWidth`/`FlangeReliefDepth`/`FlangeSharpType`/`CustomBendAllowance`). (b) **THE breakthrough = SAFEARRAY marshaling:** `FlangeEdges` and `SketchFeats` MUST be `VARIANT(VT_ARRAY \| VT_DISPATCH, (obj,))` — a bare object or VARIANT-wrapped single is silently ignored. **This was the real root cause behind the "AddEdges dead end" (GetEdgeCount=0) AND the Wave-6 auto-profile no-op all along** — not a missing profile per se, but un-arrayed dispatch args. `_create_edge_flange` ships (handler `c806782`, production PAE `644edf6` = GREEN: `Edge-Flange1`/`EdgeFlange` materialized on a `base_flange` body via durable edge_ref). Authoring: `{"type":"edge_flange","height_mm":N[,"angle_deg":90,"radius_mm":2]}` + `target:{edge_ref}`; the handler auto-builds the normal-edge plane + profile line internally. ~~No longer deferred.~~ **⛔ FALSIFIED 2026-06-09 (W42):** the `644edf6` "GREEN / Edge-Flange1 materialized / delta-verified" claim was a **NODE-PRESENCE false positive** — the W7 PAE asserted feature-node + plane + sketch PRESENCE and **never measured the B-rep**. On the live seat (3× reproduced, `spikes/v0_2x/edgeflange_brep_probe.py`) `_create_edge_flange` returns `ok=True` and creates an `Edge-Flange1` node that is NOT suppressed with `GetErrorCode2=(0,False)` — yet adds **ZERO geometry** (ΔVol=0, ΔFaces=0). The SAFEARRAY/profile construction almost certainly collapses to a degenerate flange the kernel silently accepts. De-advertised from `_SUPPORTED_FEATURE_TYPES` (propose fails-closed); handler retained as characterized code. Re-advertise ONLY after a ΔVol>0 seat proof. See Wave-44. |
| **Miter Flange** | No `IMiterFlangeFeatureData` in the SW2024 typelib (no `CreateDefinition` path); legacy `InsertSheetMetalMiterFlange` walls. Deferred during W2-seat (2026-05-31). |
| **Hem — ✅ UN-WALLED 2026-06-16 (W59; the W55-C "CreateDefinition WALLED" record was only HALF the picture)** | **Hem is a GENERATIVE capability out-of-process.** The modern path does wall exactly as W55-C found — `CreateDefinition(<swFm hem id>)→typed_qi(IHemFeatureData)` returns `E_NOINTERFACE` (no `swFmHem` id resolves). **BUT the legacy `IFeatureManager.InsertSheetMetalHem` (9 args, memid 91) WORKS — if and only if BOTH locks are cleared** (`spikes/v0_2x/spike_hem_v5.py`, seat-run SW2024 SP1, `hem_v5_results.json`, exit 0): **(1) Marshaling lock —** the 9th arg `PCBA` is a `VT_PTR` (raw_vt 26) the makepy proxy rejects as bare `None` (`DISP_E_TYPEMISMATCH`, fire3); coerce it with **`win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)`** (the identical edge_flange null-coercion recipe, line 54). **(2) Topological lock —** the target must be a **valid linear sheet-metal BOUNDARY contour** — a major-face perimeter edge. Selecting `GetEdges()[0]` (a 2mm thickness edge) makes the kernel silently NO_OP; deterministically pick the **longest edge (~60mm major-face perimeter)** — measured via the `IEdge.GetCurveParams2` **property** (11-tuple `[sx,sy,sz,ex,ey,ez,...]`; note: a *property* on dynamic dispatch, a *method* on the typed proxy — `GetStartVertex`/`GetEndVertex`/`GetCurve` are `DISP_E_MEMBERNOTFOUND` on dynamic dispatch). **Result:** faces 6→14 (+8), vol 4800→5903.84 mm³ (+1103.84), node `Hem1`/type `Hem`, **surviving save→reopen** (typed `ISldWorks`+`OpenDoc6(path,1,1,"",0,0)`, Type=1). A real B-rep delta, not a W42-class ghost. **Overturns the `bc5c849` walled verdict.** Production-wired as the sheet-metal `hem` `feature_add` kind via the W56 `features/HANDLER_REGISTRY` seam (durable `edge_ref` target; `feat/w59-hem` `63c513d`, merged here). `InsertSheetMetalHem2` (16 args, memid 201) extends with relief options; same PCBA recipe at idx 8. **Sibling lanes jog/sketched_bend/corners remain CreateDefinition-walled and unproven on the legacy route — separate spikes.** |

## v0.16 / Wave-5 (deferred)

| Item | Rationale |
|---|---|
| **Boundary Boss (F6) — no reachable creation API** | Characterized on a live seat (SW2024 SP1, `spikes/v0_16/spike_boundary.py`). There is **no `swFmBoundaryBoss` constant** in `swconst.tlb` (`swFeatureNameID_e`), so the `CreateDefinition(swFm*)→typed_qi→CreateFeature` recipe has no entry point; and **no `InsertBoundaryBoss*` method** is exposed on `IFeatureManager` or `IModelDoc2` (probed via `GetIDsOfNames`). Only `swBoundaryBoss*` *sub-parameter* enums (tangency/direction/curve-influence) exist — they configure a feature that cannot be created out-of-process via the known API surface. The kind is **not advertised** (absent from `mutate.py:_SUPPORTED_FEATURE_TYPES`; propose fails closed). Materializing would require a Route-C (in-process) or VBA-emit-and-run path, i.e. a separate epic. First raised 2026-06-01, Wave-5 Task-0 closure. |
| **Ref Point (F0, Wave-5) -- SHIPS via durable `face_ref` (face-centroid); only legacy vertex-coord fallback walls** | **ADVERTISED 2026-06-01 (W5.3 Epic B).** Entity-select wall cracked (`spikes/v0_16/spike_entity_select.py`, `880486a`): the durable persist round-trip (`body.GetFaces() → GetPersistReference3 → GetObjectByPersistReference3 → typed(IEntity).Select2`) selects faces/edges/vertices live out-of-process — the same `resolve_manifest_face`/`select_entity` infra `wizard_hole`/`draft` ship. **Production-handler PAE GREEN** (`spikes/v0_16/_run_ref_point_pae.py`, `40ea050`): `_create_ref_point` with `{"face_ref": <manifest-face dict>}` resolves the face and `fm.InsertReferencePoint(4, 0, 0.0, 1)` (type 4 = `swRefPointTypeInCentreOfFace`) **materializes a centroid ref-point** (2 of 3 probed faces; the 3rd miss was a test-harness artifact — a hand-built face_ref with a corner-instead-of-centroid, which correctly fail-softed). `ref_point` is now in `_SUPPORTED_FEATURE_TYPES`. **Still walls (non-advertised fallback only):** the legacy `target.point` vertex-coordinate path (`SelectByID("","VERTEX",x,y,z)` + type 5) returns `False` out-of-process; production should always author `ref_point` with a durable `face_ref`. First raised 2026-06-01, Wave-5 seat session; cracked + shipped 2026-06-01, Epic B. |
| **Loft (F2, Wave-5) -- both `CreateDefinition(9)` and `InsertProtrusionBlend*` wall** | Characterized on a live seat (SW2024 SP1, `spikes/v0_16/spike_loft.py` + ad-hoc arity probes). **Route A** (`fm.CreateDefinition(swFmBlend=9) -> typed_qi(ILoftFeatureData) -> CreateFeature`): the constant `swFmBlend=9` is confirmed in `swconst.tlb`, and both profile sketches are mark-selected (`SelectByID2("Sketch1", "SKETCH", ..., Mark=1)` returns True for both), but `CreateDefinition(9)` returns `None` regardless of Mark value (0 or 1) or selection order. **Route B** (legacy `fm.InsertProtrusionBlend` / `fm.InsertProtrusionBlend2`): arity sweep finds `InsertProtrusionBlend` accepts 17 args and `InsertProtrusionBlend2` accepts 18 args, but every combination of bool/int/float at each position returns `None` and no loft feature materializes (feature count unchanged). The per-argument semantic shape (direction flags, option flags, tangency weights, guide-curve array) is not exposed by the typelib walker, so reverse-engineering the correct recipe is an O(2^18) blind search. Materializing likely needs a dedicated typelib-signature dump of `InsertProtrusionBlend2` (arg VT types) + guide-curve pre-selection, which is a separate epic. The kind is **not advertised** (propose fails closed). **W20 re-test (2026-06-06, `spikes/v0_2x/spike_loft.py`, `loft.json`):** re-probed with the CORRECT production order (select profiles BEFORE `CreateDefinition(9)`, matching the `_create_loft` handler sequence at mutate.py:874) and with ISelectionMgr verification (`GetSelectedObjectCount2(-1)=2`, both objects are live CDispatch). **Selection-order hypothesis from v0_16 is DISPROVED** — `CreateDefinition(9)` returns `None` regardless of whether profiles are pre-selected or not; the wall is intrinsic, not a sequencing artifact. Legacy `InsertProtrusionBlend` (17 args) and `InsertProtrusionBlend2` (18 args) also return `None` with simple defaults (feature count delta=0). Mark=1 confirmed correct for all loft profiles. Success-signal contract is UNRESOLVED (CreateDefinition returns None before CreateFeature is reached, so the return-value-vs-count-delta question is moot). Composition seam UNTESTED (ref_plane + sketch composition works for geometry setup, but the loft step walls before the seam can be evaluated). First raised 2026-06-01, Wave-5 seat session; W20 hard-reconfirmed 2026-06-06. |
| **Wrap (F5, Wave-6) -- legacy `InsertWrapFeature*` silently no-ops; no API path; Route-C/VBA territory** | Exhaustively characterized on a live seat (SW2024 SP1, `spikes/v0_16/spike_wrap_recipe.py`, `8b231e3`; `wrap_recipe_T3.json`), with **delta-based detection** (so not a None-return false-negative): `feature_count 20→20`, **all 18 sel/arg combos delta=0** across geometry variants — box + sketch-on-face (emboss/deboss/scribe × fwd/rev × sketch-only/sketch+face/face+sketch), **cylinder + sketch on a tangent ref plane** (the canonical wrap scenario), box + sketch on a 1 mm offset plane, box + sketch on Top Plane iterated over all 6 faces. Both legacy APIs wall: **`fm.InsertWrapFeature2(Long, Double, Bool, Long, Long)` (5 args)** and **`fm.InsertWrapFeature` (3 args)** both return `None` with status OK, no feature. **No `swFmWrap` constant**; `CreateDefinition(0..200)→typed_qi(IWrapSketchFeatureData)` = 0 hits (no modern feature-data path). Same signature as rib / F6 boundary boss → Route-C/in-process or VBA-emit territory, not a seat task. The kind is **not advertised** (propose fails closed). (NB: the entity-select root cause was solved in W5.3 Epic B; this is a feature-recipe wall, not a selection wall. Dome — the third of the old F3/F4/F5 trio — SHIPPED at W6 T2; rib has its own entry below.) First raised 2026-06-01, Wave-5; exhaustively characterized 2026-06-01, Wave-6 T3. |
| **E1 Inertia -- SHIPS (tensor GREEN via `GetMomentOfInertia(0)` + `eigh`); only `PrincipalAxesOfInertia` walls** | **RESOLVED 2026-06-01 (W5.3 Epic A, `46e6294`/`05774dc`).** The earlier "VARIANT(array) marshaling wall" was a **MISDIAGNOSIS**: `IMassProperty2.GetMomentOfInertia` is `([in] long WhereTaken) -> VT_VARIANT` (dispid=12, METHOD) — it takes a **plain Python int frame-selector**, NOT a center-of-rotation `VARIANT(VT_ARRAY|VT_R8)` array. `GetMomentOfInertia(0)` (0 = centre of mass) returns a **9-tuple = row-major 3×3 inertia tensor in SI kg·m²**, physics-validated. `observe_inertia.py` now reads the tensor and derives principal moments/axes via `numpy.linalg.eigh` (exact: axes = eigenvectors, moments = eigenvalues of the symmetric tensor). **The one genuine wall is `PrincipalAxesOfInertia`** (dispid=7, PROPGET): COM `DISP_E_BADPARAMCOUNT` for every probed arity/invkind (gen_py wrapper arity ≠ live server) — but it's **fully worked around** by the eigendecomposition, so E1 inertia **ships** (not deferred). Retained here only to record the `PrincipalAxesOfInertia` API defect. First raised 2026-06-01, Wave-5 seat session; resolved 2026-06-01, Epic A. |
| **Rib (F3, Wave-6) -- legacy `InsertRib` silently no-ops; no API path; Route-C/VBA territory** | Exhaustively characterized on a live seat (SW2024 SP1, `spikes/v0_16/spike_rib_recipe.py`, `0d00797`; 1183-line `rib_recipe_T1.json`). The entity-select root cause is NOT the blocker (Epic B solved it). Probes, all negative: **legacy `fm.InsertRib(Bool,Bool,Double,Long,Bool,Bool,Bool,Double,Bool,Bool)` (10 args)** with a correct **L-bracket + open profile sketch** precondition — 60 combos on a box (5 sel × 12 arg-tuples) + 48 on an L-bracket (4 sel × 12) = **108 calls, all `None`** with status OK (solver silently rejects); **`CreateDefinition(0..200)` → `typed_qi(IRibFeatureData)` scan = 0/201 hits** (no modern feature-data path exists); **alternate names `InsertRib2`/`AddRib`/`CreateRib`/`InsertWeb` = none exist**; line-entity `SelectByID` = False; active-sketch (`EditSketch`) InsertRib = None. The call marshals without exception but no feature materializes — same signature as F6 boundary boss. The kind is **not advertised** (propose fails closed). **One residual unknown** (kept honestly ajar): a rib's open profile must precisely terminate on / bridge the existing walls for the solver to accept it, and that positioning is the one variable a blind sweep can't nail — so the precise claim is "walls for all blind-constructed profile geometries," not "provably impossible." Practical conclusion: Route-C/in-process or VBA-recorded-geometry, not a seat task. First raised + characterized 2026-06-01, Wave-6 T1. |
| **E4 Interference Detection (Assembly) -- ✅ SHIPPED (W27, 2026-06-06)** | **RESOLVED 2026-06-06 (W27).** The W8-falsified premise was confirmed dead end-to-end: place overlapping components via the W8 `OpenDoc6`-pre-open pipeline → `IAssemblyDoc.InterferenceDetectionManager` (dispid 126 property-get) → `IInterferenceDetectionMgr.GetInterferenceCount()`/`GetInterferences()` → enumerate `IInterference` (components + `Volume`). **Discrimination proven on a live seat** (`spikes/v0_2x/spike_interference_v2.py`, `interference.json`): two 20mm cubes @10mm offset → count=1, volume=4000 mm³, components=["block_20mm-1","block_20mm-2"]; negative control @50mm → count=0. Shipped as the **read-only `observe_interference.py`** (mirrors `observe_inertia.py`), exposed BOTH as `ai-sw-observe interference` CLI AND the `sw_interference` MCP observe tool (§6.5 gates only *mutations*; read-only interrogation may be MCP). Report: `{interference_count, interferences:[{components:[A,B], interference_volume_mm3}]}` (m³→mm³ ×1e9), fail-closed on non-assembly / manager-acquisition failure. PAE 5/5 GREEN. **Seat lesson:** `Close()` on a doc mid-session corrupts the COM channel — leave docs open, clean up via `CloseAllDocuments` in `finally`. **DEFERRED sub-scope:** sub-component/body-level detail, coincidence-vs-interference distinction, ignored-clash sets, self-interference toggles, clearance/min-distance verification. _Historical characterization below retained._ |
| **E4 Interference -- historical characterization (pre-W27)** | Characterized on a live seat (SW2024 SP1, `spikes/v0_16/spike_interference.py`, `f036bc7`). **Proven:** assembly doc acquisition out-of-process (`sw.NewDocument(<Assembly.asmdot>, 0, 0, 0)` → assembly doc); the correct manager API is `typed(asm_doc, "IAssemblyDoc").InterferenceDetectionManager` (**property-get, dispid=126 — NOT `Get…`**) returning an `IInterferenceDetectionMgr` (interface is `…Mgr`, not `…Manager`); `GetInterferenceCount()` / `GetInterferences()` / `GetInterferenceComponents()` are callable. **NOT proven (why deferred):** no real interference was ever detected — `AddComponent5` returns status `OK` but a `None` dispatch (components are not physically placed), so `GetInterferenceCount()==0` and `GetInterferences()→None`. The meaningful *value path* — place overlapping components → detect a non-empty interference → enumerate `IInterference` (volume / bodies / components) → surface through `observe.py` — is unproven. (Note: the committed JSON's structured `interference_mgr` block records only the *failed* `GetInterferenceDetectionManager` attempt; the working dispid=126 name + count=0 are documented in the spike `interpretation` text, not captured as a structured success record.) **No tool is advertised; nothing wires into `observe.py`.** **W6 T5 exhaustively confirmed the wall (spike `5e3d60d`, `interference_T5_full.json`):** the blocker is **component placement, not detection** — `AddComponent5` / `AddComponent4` / `AddComponent2` all return `None` (no dispatch), `AddComponent` (raw, BOOL) returns `False`, `InsertImportedComponent` creates **bodyless Reference features** (no B-rep), `SetComponentsAndTransforms([c1,c2],[xf,xf])` returns status 2 but `GetInterferenceCount()` stays 0, `GetComponentsTransformInterferenceCount` hits VARIANT-array marshaling failure, and `GetBodies()` on imported comps raises Type mismatch (not real `IComponent2`). Out-of-process COM **cannot place components with overlapping solid bodies**, so the solver has nothing to interfere-check. **Root cause shared with rib/wrap/F6/loft:** the out-of-process boundary blocks solver-deep operations (here, B-rep component placement). → **Route-C/VBA-emit territory (Wave-7 strategic lane), not a seat task.** First raised + foundation-characterized 2026-06-01, Wave-5.3 Epic C; exhaustively confirmed 2026-06-01, Wave-6 T5. **⚠️ W8 update (2026-06-04): the core premise here — "out-of-process COM cannot place components with overlapping solid bodies" — is FALSIFIED.** W8 proved `AddComponent4` places real B-rep components once the part is `OpenDoc6`-pre-opened (E4 never pre-opened). So the interference *value path* (place overlapping components via offset transforms → `GetInterferences`) **may now be reachable out-of-process** and is no longer blocked by the placement wall. E4 interference detection remains formally out-of-scope per the 2026-06-04 VBA ruling, but that ruling rested on this now-false premise — **flagged for user reconsideration**, not unilaterally reopened. |

## Wave-22 (deferred)

| Item | Rationale |
|---|---|
| **Assembly Linear Component Pattern -- `IFeatureManager.FeatureLinearPattern5` returns None on assembly FeatureManager; no API path** | Characterized on a live seat (SW2024 SP1, `spikes/v0_2x/spike_asm_patterns.py`, `asm_patterns.json`). `IFeatureManager.FeatureLinearPattern5` (22 args, proven for PART-level linear patterns in W21) returns `None` with component-count delta=0 when called on an assembly's FeatureManager — regardless of selection method (edge or axis as direction, mark=1), component selection method (`IFeature.Select2(append, mark=4)` — seat-proven), or argument variants (also tested `FeatureLinearPattern4` 20 args, `FeatureLinearPattern3` 10 args, `FeatureDimensionPattern` 8 args — all None). **No assembly-specific linear pattern API exists** on `IAssemblyDoc` (typelib dump confirms only `DissolveComponentPattern` and `InsertDerivedPattern` — both selection-based with 0 args, not creation APIs). The kind is **not advertised** (propose fails closed). Unblocking would require a Route-C (in-process) or VBA-emit path. First raised + characterized 2026-06-06, Wave-22 S1. |
| **Assembly Circular Component Pattern -- same wall as linear; no API path** | Same characterization as linear pattern above. `IFeatureManager.FeatureCircularPattern5` (14 args, proven for PART-level in W21) returns `None` on assembly FeatureManager with axis selection (mark=1) + component selection (mark=4). `FeatureCircularPattern4/3/2` also return None. No assembly-specific circular pattern API on `IAssemblyDoc`. **Not advertised.** First raised + characterized 2026-06-06, Wave-22 S1. |

## Wave-31 (deferred)

| Item | Rationale |
|---|---|
| **Ordinate/Baseline Dimensions — selection succeeds, ALL creation APIs silently no-op** | **EARNED NO-GO (W31v2 Gate-2 exhaustive, 2026-06-06).** Characterized on a live seat (SW2024 SP1, `spikes/v0_2x/spike_ord_baseline_gate2.py`, `ord_baseline.json`). **Gate 1 SOLVED:** `IView.SelectEntity(entity, False)` selects an in-view datum — `SelectionManager.GetSelectedObjectCount2(-1)=1`, `GetSelectedObjectType2(1)=2` (swSelEDGES). **Key fix:** must use `dmdoc2.SelectionManager` (CDispatch, memid=65537, PROPGET); `ISelectionManager` (memid=65711) fails at runtime with "Unable to read write-only property" on BOTH typed IModelDoc2 and late-bound CDispatch. **Note on entity-type inversion:** `GetVisibleEntities(None, 2)` "edge entities" → `SelectEntity` reports `type=3` (vertex); `GetVisibleEntities(None, 3)` "vertex entities" → reports `type=2` (edge) — use vertex-entity for edge-datum (what ordinate/baseline need). **Gate 2 EXHAUSTED — all 6 methods create zero dims with confirmed datum selected:** (1) `InsertOrdinate()` → None, 0 dims; (2) `InsertHorizontalOrdinate()` → None, 0 dims; (3) `InsertVerticalOrdinate()` → None, 0 dims; (4) `AddOrdinateDimension2(type=0/1, X, Y, Z)` (memid 208) → 0 (I4, not BOOL), 0 dims; (5) `InsertBaseDim()` → None, 0 dims; (6) `InsertChainDim()` → None, 0 dims. All methods: dims_immediate=0, dims_on_reopen=0 (verified via SaveAs3 → CloseAllDocuments → OpenDoc6 → GetDisplayDimensions). The Insert* family returns void (None) — they are likely interactive-mode starters, not one-shot creators. `AddOrdinateDimension2` returns I4=0 (distinct from `AddOrdinateDimension`'s BOOL=True in W31v). **Both schemes (ordinate + baseline) are EARNED NO-GO** — every exposed API tested with confirmed datum selected, zero dims on reopen. This is an **API-creates-zero-effect wall** at the dimension-creation step, not a selection wall. Same family as W31v's finding for `AddOrdinateDimension`. Route-C/VBA territory. First raised W31, partially characterized W31v (AddOrdinateDimension only), exhaustively proven W31v2. |

## Wave-36 (deferred)

| Item | Rationale |
|---|---|
| **In-file per-configuration geometry distinction — all override routes silently no-op or leak globally** | **EARNED NO-GO (W36 S1/S2, 2026-06-09, SW2024 SP1).** Config *creation* is fully GREEN — `IConfigurationManager.AddConfiguration2(Name,Comment,AltName,Options,ParentConfigName,Description,Rebuild)` **7-arg** (NOT 3); `GetConfigurationNames`/`GetConfigurationByName`/`ShowConfiguration2`/`DeleteConfiguration2`/`GetConfigurationCount` all on **IModelDoc2** (not IConfigurationManager); create/persist(save+reopen)/activate/delete/name all proven. **What is WALLED:** making geometry actually DIFFER per config. Three routes, all dead out-of-process: **(A) per-config equations** — `IEquationMgr.Add3`/`SetEquationAndConfigurationOption` accept config-scope args and return 0/option=2, but `--no-dim` builds produce LITERAL geometry with no equation→dimension link, so changing equation values has zero geometric effect; parametric (`no_dim=False`) builds are blocked by the `AddDimension2` modal popup out-of-process. **(B) per-config dimension values** — every `--no-dim` dimension reports `IsAppliedToAllConfigurations()=True`; `IDimension.SetSystemValue2/3` + `SetValue2` return 0 (success) but volume never changes. **(C) per-config feature suppression** — `IFeature.SetSuppression2(state, Config_opt, Config_names)` **3-arg** (NOT 1): `opt=0` ("this config") = silent no-op (returns True, `IsSuppressed2`=False, no volume change); `opt=1/2` = LEAK to ALL configs (even with an explicit `("Config_A",)` array passed). `EditConfiguration2(SuppressByDefault=...)`=no change; `AddOrEditConfiguration`=error -24 "read-only property". Volumes identical (1,125,000 mm³) across all configs after every attempt. **Root cause:** the SW2024 SP1 COM layer does not honor per-configuration scope out-of-process — same solver-perimeter family as loft/rib/interference-placement. The UI supports it; the RPC boundary does not. **Falsified theories:** not a timing race (explicit-array `opt=2` still leaks — `EditRebuild3` between calls won't fix scope-not-honored); `swconst.tlb` has no suppression-by-default constant. **NOT pursued (by design):** design tables (`IDesignTable` → Excel OLE in-process = modal dialogs/orphaned procs/deadlocks); `.swp` macro (Invariant #3); `InsertDeleteBody2` (rides the same `SetSuppression2` scope machinery — expect the same leak). **RESOLUTION — reframe, not kill:** ship "configurations" as **MULTI-FILE variants** (`variants` spec → N distinct proven `.sldprt` files via `builder.build(no_dim=True, save_as=...)`, per-variant volume-discriminated), reusing the assembly epoch's build-then-place machinery + the already-measured distinct volumes (cylinder 39,270 vs two-block 1,062,500 mm³). See `WAVE36v_CONFIGURATIONS_MULTIFILE_REDISPATCH.md`. The offline scaffold (`config/` apply_overrides/validate_overrides/parse_variants, 24/24) is correct and carries forward. In-file native configurations stay deferred until a future SW version or an in-process bridge exposes per-config scope. |

## Wave-39 (deferred sub-scope)

| Item | Rationale |
|---|---|
| **Sketch relation: collinear** | Token unknown. Both `sgCOLLINEAR2D` and `sgCOLLINEAR` no-op on SW 2024 SP1 (`SketchAddConstraints` returns without error but geometry does not move — the W21 no-op trap). Effect-probe recipe: two parallel lines offset 5mm → apply token → assert the second line's Y collapses onto the first. Candidates to try: `sgCOLINEAR`, `sgSAMELINE`, `sgONLINE`, `sgALIGN`. Fail-closed: removed from `RELATION_TOKENS` until proven. First raised W39 seat session (2026-06-09). |
| **Sketch relation: coincident** | Needs endpoint (sketch point) selection, not whole-segment selection. `seg.GetStartPoint2` / vertex selection required. Token likely `sgCOINCIDENT` or `sgMERGE` — untested. Effect-probe recipe: two endpoints apart → select points → apply token → assert they coincide. Fail-closed: removed from `RELATION_TOKENS` until proven. First raised W39 seat session (2026-06-09). |
| **Sketch relation: symmetric** | 3-ref constraint (2 entities + centerline). Selection order and mark convention unproven (W12 width-mate precedent: the centerline may need a distinct mark). Token likely `sgSYMMETRIC2D` — untested. Effect-probe recipe: 2 lines + a construction centerline → select in order → apply token → assert mirror symmetry about the line. Fail-closed: removed from `RELATION_TOKENS` until proven. First raised W39 seat session (2026-06-09). |

## Wave-41 (body-ops sub-scope — `combine` / `split` deferred)

Wave-41 scoped three multi-body `feature_add` kinds ranked by wall-risk:
`delete_body` (low), `combine` (medium), `split` (high). **`delete_body`
SHIPPED** (S1 GREEN on SW 2024 SP1: 2 disjoint bodies 1800+4000 mm³ → delete
body[1] → 1 body 1800 mm³, the W21 volume-delta gate). The seat cracked four
binding bugs that masked viability — all W37-class: (1) `GetBodies2` is
`IPartDoc`-only (QI from the typed `IModelDoc2`); (2) per-body volume is
`IBody2.GetMassProperties(1.0)[3]`, NOT `IModelDocExtension.CreateMassProperty`
(which a body lacks → was silently 0.0); (3) body selection is
`Extension.SelectByID2(name, "SOLIDBODY", …)` (swSelType 76), NOT
`select_entity(body)` / face-select / `BODYFEATURE` (all leave
`InsertDeleteBody2` a no-op); (4) `InsertDeleteBody2(False)` is ONE arg (the
2-arg form raises "Invalid number of parameters"). `combine`/`split` handlers
remain as characterized dead code (dispatch + validator wired) but are held
OUT of `_SUPPORTED_FEATURE_TYPES` so propose fails-closed — the
edge-flange / loft precedent. First raised + deferred 2026-06-09 (W41 seat).

| Item | Rationale |
|---|---|
| **`combine` (boolean add/subtract/common)** | Two un-cleared blockers, each its own S1. **(1) Raw-`GetBodies2` binding:** `_create_combine` still calls `doc.GetBodies2` on the raw (un-QI'd) doc — needs the same typed-`IPartDoc` QI the `delete_body` path uses. **(2) `IBody2`-array marshaling (the real wall):** `InsertCombineFeature(type, mainBody, toolBodies)` requires the main body as an `IBody2` dispatch AND the tool bodies as an `IBody2` SAFEARRAY marshaled out-of-process — exactly the un-arrayed-dispatch class that walled edge-flange for two waves until the `VARIANT(VT_ARRAY \| VT_DISPATCH, (…))` breakthrough (Wave-7). The fix is likely the same SAFEARRAY-of-dispatch wrap, but it needs its own seat de-risk (build 2 overlapping bodies → subtract → assert single body, volume == A − overlap; a no-op that leaves 2 bodies = FAIL). Until proven, `combine` stays fail-closed. `_COMBINE_OP_MAP = {add:0, subtract:1, common:2}` already characterized. |
| **`split` (one body → N by a trim plane/surface)** | Solver-deep + needs a cutting entity, and the W41 S1 fixtures only ever built ONE body so the increase-to-N gate was never exercised (`PRECONDITION_FAILED`, not a COM verdict). Owns the highest wall-risk of the three (loft/rib solver-deep family). Needs a dedicated S1: build a single body + a ref plane through it → split → assert body count 1→N with volumes summing to the original. `_create_split` characterized (selects body[0], expects a `cutting_plane`/`cutting_surface` ref) but unproven end-to-end. |

### Wave-52 update (2026-06-11 seat) — the one-shot API is the wrong shape; both need FeatureData rewrites

W52 Lane A fired the combine/split handlers at the seat with corrected fixtures
(verify-the-effect gates). **Both are NO-GO on the one-shot `InsertXxxFeature`
API** — the out-of-process COM channel drops the implicit UI selection stack the
"Insert" macros rely on. The cycle produced the authoritative `FUNCDESC` map and
the real (FeatureData) paths, so the next worker starts from the answer, not a guess.

- **combine — `InsertCombineFeature` is a uniform no-op.** Five call variants all
  fail on a valid 2-body overlapping fixture (subtract): typed bodies, raw
  `_oleobj_`, `VARIANT(VT_DISPATCH)`-wrapped main, late-bound raw bodies, AND the
  separate `IPartDoc.InsertCombineFeature` overload. Ruled OUT by the seat: arg
  order (Leg-0 FUNCDESC = `InsertCombineFeature(OperationType:I4, MainBody:VT_PTR,
  ToolVar:VARIANT) -> VT_PTR`, matches the handler), enum (`add=0/subtract=1/common=2`
  = real `swBodyOperationType_e`), and marshaling. `IFeatureManager.InsertCombineFeature`
  → **None**; `IPartDoc.InsertCombineFeature` → **False**. **Real path =
  `ICombineBodiesFeatureData`:** `CreateDefinition(swFmCombineBodies)` → `typed_qi`
  → set `MainBody` + `BodiesToCombine` (strict `IBody2` SAFEARRAY; may need
  `_oleobj_.InvokeTypes` to force the VT_DISPATCH array if pythoncom strips types)
  + `OperationType` → `CreateFeature`. Same typed_qi FeatureData pattern as fillet/sweep.
- **split — the handler's `InsertSplitBody` does not exist.** A broad all-interface
  FUNCDESC sweep found **no `InsertSplitBody` on any interface** — it was a guessed
  name (O1 violation in the W41 handler), which is why the call would have died even
  past the plane-selection fix. **Real path = the two-step `IFeatureManager.PreSplitBody()`
  → `PostSplitBody(BodiesToMark, ConsumeCut, Origins, SavePaths)`:** PreSplitBody
  computes intersections from the active selection (so the cutting tool must be
  pre-selected); harvest the returned temp bodies, build parallel `BodiesToMark`
  (bool keep/consume), `Origins` (result coords), `SavePaths` (empty strings if not
  saving to new files) arrays, commit via PostSplitBody. This route is more reliable
  out-of-process than `ISplitBodyFeatureData` (which chokes on origin mapping). The
  cutting plane must select as **`"PLANE"`**, NOT `"REFPLANE"` (that handler bug is
  fixed on the branch but dormant).

**Artifacts on `feat/w52-bodyops` (author-only, UNMERGED):** the corrected de-risk
spike + `bodyops_combine_marshal_diag.py` (the 5-variant sweep + all-interface
combine/split FUNCDESC dump) + the `_create_split` `REFPLANE`→`PLANE` fix. Both
kinds STAY out of `_SUPPORTED_FEATURE_TYPES`. Re-scope as a dedicated FeatureData wave.

## Wave-58 / Wave-59 (two more out-of-process FeatureData walls + the doctrine)

Two characterization lanes this batch each hit the *same* runtime wall and, taken
with the W55-C hem/jog/miter finding, make the pattern systematic enough to write
down. **Neither ships a handler; both preserve a diagnostic baseline.**

| Item | Rationale |
|---|---|
| **`move_copy_body` (W58 Lane C, `feat/w58-move-copy-body`)** | **DEFERRED — both routes walled on SW 2024.** FUNCDESC-confirmed sig is the 12-**scalar** `IFeatureManager.InsertMoveCopyBody2(TransX,TransY,TransZ,TransDist, RotPtX/Y/Z, RotAngX/Y/Z:R8, BCopy:BOOL, NumCopies:I4) -> PTR` (invalidates the earlier assumed 4-arg `body:DISPATCH,transform:DISPATCH,…` form — R4 AMBER legitimately cleared). **(1) One-shot `InsertMoveCopyBody2` is an unroutable no-op** out-of-process (returns None, zero B-rep effect, across all selection paradigms / parameter matrices / dispatch layers — gen_py, CDispatch, raw `_oleobj_.Invoke`). **(2) `CreateDefinition(69)` + `IMoveCopyBodyFeatureData` also fails** — gen_py cannot marshal the property setters (Type-mismatch on all setters despite correct FUNCDESC VTs). Handler authored with a centroid-shift ΔVol-class verify-the-EFFECT gate that **fails LOUD** (`(False, "no body found at expected centroid…")`, never a ghost), but it is the registry seam's first customer and is a known wall: **when revisited, DROP the `HANDLER_REGISTRY["move_copy_body"]` advertisement line (walls are not advertised — the combine/split precedent) or gate it behind a DEFERRED flag, and reconcile the seam's "ships empty" docstring.** **W59 UPDATE — escape hatches resolved (2026-06-16):** **(b) `InsertMoveFace3` is now WALLED too** — the face-topology route (memid 247, 8-arg, `TranslationParams`=`VARIANT(VT_ARRAY\|VT_R8,[0.03,0,0])`) silently no-ops on a SINGLE valid +X face (box-discriminated, not a degenerate all-faces input): `call_ok=true`, returns `None`, ΔVol=0, zero `GetPartBox` shift — the third no-op of this class, so the o-o-p commit marshaler drops the operation whether the payload is a body-pointer SAFEARRAY or a face-topology move. **(a) sketch-level offset is PROVEN GREEN** — a fresh-seat run authored a 2nd cube whose sketch was centred at X+60 mm via the shipped `boss_extrude` → body count 1→2, combined-bbox xMax +60.0 mm exactly, volume ×2.0. **Net: move/copy is a TERMINAL o-o-p wall but the INTENT is covered by a validated spec-authoring workaround** (place the sketch at the target location; no post-hoc move). A genuine post-hoc body translate/copy needs the parked Route-D add-in. Provenance: `spikes/v0_2x/spike_move_face_translate.py` (+ `_results/move_face_translate.json`); the dormant handler `features/move_copy_body.py` fails loud and never advertises. |
| **Control-point variable fillet (W59 Lane K, `feat/w59-varfil-ctrlpts`, backlog #33)** | **WALL-ACQUIRE.** `sldworks.tlb` declares the full control-point API on `IVariableFilletFeatureData2` (`GetControlPointsCount`, `SetControlPointRadiusAtIndex(Index,Location,Radius)`, `Get…AtIndex`, conic/distance/transition variants) — but the interface is **runtime-unreachable out-of-process: `CreateDefinition(swFmFillet)` returns an object that QI-rejects `IVariableFilletFeatureData2` with `E_NOINTERFACE`, even after `Initialize(1)`** (MORPH-FALSE proven in prior spikes). NB the SHIPPED per-edge variable fillet (`mutate._create_variable_fillet`, `IsMultipleRadius=True` on the base fillet data) is unaffected — **only the intermediate control-point granularity is walled.** Unprobed escape hatches: legacy `InsertFeatureFillet`, or `GetDefinition` on a manually-created variable fillet (edit-existing rather than create-from-scratch). 20 mocked-COM recipe tests + parked ΔVol PAE on the branch. |

### Doctrine — the `CreateDefinition → E_NOINTERFACE` wall class (and its mirror)

Out-of-process, SOLIDWORKS feature creation has **two opposite, mutually
exclusive failure modes**, and which one applies is per-feature and empirical —
**probe BOTH; neither route is universally correct.** Reasoning from one to the
other is the trap.

- **Mode A — one-shot `Insert*` is a no-op → the FeatureData route is the fix.**
  The "Insert" macro relies on the implicit UI selection stack, which the OOP COM
  channel drops, so it silently returns None/False. Here `CreateDefinition(swFm…)`
  → `typed_qi` → set fields → `CreateFeature` is the WORKING path. Proven/working:
  **fillet, sweep**; the characterized real path for **combine**
  (`ICombineBodiesFeatureData`).
- **Mode B — `CreateDefinition` QI-rejects the specialized sub-interface
  (`E_NOINTERFACE`, even after `Initialize`) → fall back to legacy `Insert*`.**
  The factory hands back a bare/base `FeatureData` proxy whose specialized
  sub-interface won't resolve across the process boundary. Here the FeatureData
  route is walled and the legacy `Insert*` macro (which passes raw parameters
  straight to the geometric kernel, bypassing the specialized marshaling layer)
  is *often* — but not always — the escape. Three sub-cases, distinguished only
  by firing the legacy route:
  - **Mode-B escape PROVEN (legacy `Insert*` is generative):** **hem** (W59 —
    `InsertSheetMetalHem` works once the PCBA null-coercion + boundary-edge
    locks are cleared; see the Wave-4 Hem row above). The CreateDefinition wall
    was only half the picture.
  - **Mode-B, legacy escape untested/unfalsified:** **jog/miter** (W55-C —
    CreateDefinition rejected; legacy `Insert*` not yet probed at the seat),
    **control-point varfil** (`IVariableFilletFeatureData2`, W59 — legacy
    `InsertFeatureFillet` escape unprobed).
  - **Both-routes-dead → TERMINAL (the legacy `Insert*` ALSO no-ops, so Mode B
    offers no rescue):** **move_copy_body** (W58 — 12-scalar
    `InsertMoveCopyBody2` no-ops; W59 — the `InsertMoveFace3` face-topology
    escape ALSO silent-no-ops on a single valid face, ΔVol=0). Same shape as the
    W52/W53 `combine`/`split` o-o-p commit walls. Intent covered by the
    sketch-offset workaround (author geometry at target coords), not a new op.

**Rule of engagement for a new feature lane:** try the route the precedent class
suggests, but if it dead-ends, immediately probe the *other* mode rather than
declaring a terminal wall — a feature is only WALLED once BOTH the one-shot
`Insert*` and the `CreateDefinition`+QI routes are seat-proven to fail. Record the
FUNCDESC + the exact failure (no-op vs `E_NOINTERFACE`) so the next worker starts
from the answer.

## Wave-62 (`split_line` — operative path silent-no-op out-of-process)

**DEFERRED — Mode-A quarantined + Mode-B characterized walled.**

Per the W62 curves group plan, `split_line` was one of four lanes (composite,
helix, split_line, project_curve). Composite (`2a04542`) and helix
(`057789a`) shipped; split_line did not.

* **Mode-A** (CreateDefinition + ISplitLineFeatureData QI): QUARANTINED.
  The SW2024 swconst harvest (`docs/sw_api_full.json` @ 32.1.0.123) exposes
  NO `swFeatureNameID_e` for split-line — the worker probe id=65
  (`swFmReferenceCurve`) returned `None` from `CreateDefinition` on the
  live seat 2026-06-17. Same class as composite (`2a04542`) and helix
  (`057789a`). `ISplitLineFeatureData` is in the typelib but is edit-only
  via `IFeature.GetDefinition()` on an existing split-line node; no
  creation route exists.
* **Mode-B** (legacy `IModelDoc2.InsertSplitLineProject(Reverse, SingleDirection)`):
  characterized **silent no-op on the OOP IDispatch path**. Across four
  fire rounds with full per-step telemetry:
  - Selections route correctly (`IEntity.Select2(append, mark)` returns
    True for both sketch and face; tried `mark=0/0` and `mark=1/2`, both
    accepted).
  - Geometric reality validated (offset reference plane at z=+20mm
    parallel to top face, sketch line on that plane → projection -Z onto
    the 40x30 top face at z=+10mm — passes through the face boundary).
  - `InsertSplitLineProject` resolves callable=True, called with
    `(reverse=False, single=False)` AND `(False, True)`, returns `None`
    (void), no exception, dFace=0, dVol=0.
  - RefPlane creation in fixture works (`InsertRefPlane` with constraint
    flag `swRefPlaneReferenceConstraints_Distance=8`).
* **Class** likely matches the W60 trim wall (`swSketchTrimClosest`):
  legacy macro requires UI session / cursor context that the late-bound
  OOP dispatch path doesn't provide. Comparable to `move_copy_body` (W58
  + W59) where multiple Insert* routes were silent no-ops.

`spike_split_line.py` retains the offset-ref-plane fixture for the next
attempt; `features/split_line.py` ships Mode-A as a no-op stub and
Mode-B with full sub-step telemetry; SPIKE_STATUS = "UNRUN" so the
handler is dormant (registry never advertises). Tests preserve the
fail-closed contract.

**Unprobed escape hatches** (for a future re-attempt):
1. `Extension.SelectByID2(sketch_name, "SKETCH", ...)` instead of
   routing through `IEntity.Select2` — composite-class selection paths
   sometimes differ.
2. `ForceRebuild3` between fixture seed and Mode-B call (in case the
   sketch isn't fully baked when `InsertSplitLineProject` reads it).
3. Direct `_oleobj_.Invoke` with raw dispid for `InsertSplitLineProject`
   (the gen_py wrapper may be marshaling args wrong — composite-class
   trap we walked through for `InsertCompositeCurve`'s property-vs-method
   resolution).
4. The Route-D add-in route (already parked for `move_copy_body`).

## Wave-67 P5 (`boss_extrude_up_to_surface` — SHIPPED with a do-not-regress constant)

**`boss_extrude_up_to_surface` SHIPPED GREEN** (Tier 2) — but it carries an
**inverted-deprecation landmine** future engineers must not "fix". The handler
hardcodes `T1 = swEndCondUpToSurface = 4`. SOLIDWORKS' own API documentation
marks `4` as *deprecated* ("Do not use; superseded by
`swEndCondUpToSelection`") and steers callers to `swEndCondUpToSelection = 10`.

**Seat-proven out-of-process truth (the inversion):** the matrix sweep in
`spikes/v0_2x/spike_extrude_up_to_surface.py` (SW 2024 SP1, rev 32.1.0, committed
as forensic proof) fired every `[reference mark 0/1/2] × [T1 ∈ {10, 4}]` combo
against a Ø20 boss whose terminus is a ref plane at z=60mm, with `IBody2.GetBodyBox`
Zmax as the anti-ghost witness:

* **`T1 = 10` (UpToSelection) — NO_OP at every mark.** Feature never
  materialises (bbox unchanged at the base height). The "modern" constant the
  docs recommend silently ghosts across the COM boundary.
* **`T1 = 4` (UpToSurface) — PASS at every mark** (bbox 10mm → 60mm = the target
  surface). The formally-deprecated constant is the **only** functional OOP path.
* The reference selection **mark is irrelevant** (0/1/2 all passed). What gates
  is `T1=4` + the reference simply being present on the selection stack. The
  handler selects profile-sketch-then-target for hygiene, mark 0 both.

**Do not change `4` to `10`.** It will compile, validate, and silently produce
no geometry — the W42 ghost trap with extra steps. Same genre as the sheet-metal
profile-sketch ghost wall (Wave-65): the API the docs steer you toward is the one
that no-ops OOP. Recorded in `spec_reference.md`, the handler's inline comment,
`examples/up_to_surface_boss/README.md`, and the
`reference_extrude_up_to_surface_seat` memory.

## Wave-42 (`dxf_flat` — Developed Boundary Pass; inner bend lines deferred)

**`dxf_flat` SHIPPED 2026-06-09 as a Developed Boundary Pass** — it exports the
sheet-metal **developed (unrolled) OUTLINE** to DXF, proven by physical span
(L-bracket: vol=6902.655 mm³, 14 faces, one 90° bend → developed outline
**86.28 × 40.0 mm**, strictly > the 60 mm folded face and < the 90 mm naive
segment sum = an authentic topological unfold; the test pins that span directly,
not layer names / entity counts). **Deferred sub-scope: inner bend lines.**
`IModelDoc2.ExportFlatPatternView(path, options)` emits only the developed
boundary — across **every option 0–7** the DXF contains the outline LINEs on
layer `0` and **no bend-line layer** (`has_bend_layer=false`, reproduced on the
seat). The brake/bend annotation is therefore NOT available through the
flat-pattern-view export API.

**Architectural pathway for bend lines (when needed):** route through a
**drawing-space flat-pattern view** built on the established **W33 drawing
framework** — insert a Flat-Pattern drawing view of the sheet-metal part into a
`.SLDDRW`, where the bend lines render as first-class drawing entities, then
export that view. This is a `kind:"drawing"` composition, not an export-API flag,
and is its own S1 (view creation + bend-line entity extraction). First raised +
deferred 2026-06-09 (W42 seat).

**UPDATE 2026-06-10 (W46 seat) — bend-line drawing-view route PROVEN GREEN.**
The architectural pathway above is no longer hypothetical. Typelib dump pinned
the signature `IDrawingDoc.CreateFlatPatternViewFromModelView3(ModelName,
ConfigName, LocX, LocY, LocZ, HideBendLines, FlipView)`; calling it with
`HideBendLines=False` on the seat created a genuine flat-pattern drawing view
(`is_flat_pattern_view=True`, `view_type=7`) whose DXF export carries the bend
line as an interior LINE entity (L-bracket: 4 perimeter lines + 1 interior fold
line `(130,165)→(170,165)` at the 60/30 mm flange boundary, bbox span the exact
W42 developed 40.0 × 86.283 mm). **Caveat — the bend line is NOT layer-tagged:**
SW's drawing→DXF export collapses every entity to layer `0`, so the W42
layer-name parser can't see it (`matched_by_layer=0`). **Productionization (the
remaining deferred work) needs a GEOMETRIC classifier** (interior fold line vs.
bounding-rectangle perimeter), proven viable here — NOT a COM wall. Spike:
`spikes/v0_2x/dxf_flat_bendlines_drwview.py`.

**SHIPPED 2026-06-10 (W48) — `dxf_flat_bends` export format.** The deferred
sub-scope is closed. The drawing-view route + geometric classifier are
productionized in `export/dispatch.py::_flat_pattern_dxf_drawing` (new
`SaveMethod.FLAT_PATTERN_DXF_DRAWING`), with the classifier + a new in-place
layer rewriter (`rewrite_dxf_with_bend_layer`) in `export/dxf_bend_layers.py`.
The `dxf_flat_bends` format emits a CAM-ready DXF: developed-boundary perimeter on
layer `0` + interior fold lines re-assigned to a dedicated `BEND` layer. Seat
PAE GREEN (one-bend L-bracket → 1 BEND-layer LINE + 4 outline LINEs, bbox
40×86.28 mm). The part-space outline-only `dxf_flat` is retained unchanged.

## Wave-48 (Mechanical mates Tier-3 — hinge ANGLE LIMIT deferred)

**`slot` + `hinge` SHIPPED 2026-06-10** (merge `2dbe711`); the mechanical-mate
epoch is complete (5 kinematic mates). **Deferred sub-scope: the hinge ANGLE
LIMIT.** A hinge mate's optional min/max angular travel is set via
`IHingeMateFeatureData.AngleSelection` (enable) + `MaxVal` / `MinVal` (radians) —
all three are characterized and present on the typed interface. What's missing is
the **angle REFERENCE**: `swHingeMateEntityType_e` includes `Angle=2`, so the
angle is measured between two reference entities supplied as
`SetEntitiesToMate(2, <array>)`. Plain coaxial cylinders (the shipped hinge
fixture) have **no flat reference faces** that define an angular zero, so the
limit cannot be demonstrated on them. **This is a characterized sub-scope, NOT a
wall** — it needs a richer fixture (two flat-faced brackets with aligned holes)
to de-risk the angle-reference role + verify the limit round-trips through
save/reopen. Officially out of bounds for this wave; the basic 1-DOF hinge
(concentric+coincident, the load-bearing capability) ships fully. First raised +
deferred 2026-06-10 (W48 seat).

**W51 Lane B UPDATE — angle-reference role GREEN, but limit VALUES reparametrize
(re-deferred, branch `feat/w51-hinge-limit` left UNMERGED).** A richer fixture
(two 40×30×20 mm flat-faced blocks, dia-10 through-holes, coaxial) was authored +
fired at the seat (`spikes/v0_2x/mech_mate_hinge_anglelimit_derisk.py`). Findings:
1. **The angle-reference role marshaling is NOT a wall.** `SetEntitiesToMate(2,
   <VT_ARRAY|VT_DISPATCH>)` (the `swHingeMateEntityType_Angle=2` role) binds two
   planar +Y faces cleanly; `create_mate` (production handler with optional
   `angle_faces`+`angle_limit`) returns a `MateHinge`, `GetErrorCode2=(0,False)`,
   and **`AngleSelection=True` persists through save/reopen.**
2. **But the limit VALUES do not round-trip — SW reparametrizes the storage.**
   Requested `MinVal=−30°, MaxVal=+30°` → reads back `MinVal=0°, MaxVal=−60°,
   Angle=+30°`. The tell: the read-back `Angle` equals the **input `MaxVal`** to 13
   sig figs (0.5235987755983 vs 0.5235987755982988) — SW is **not** measuring
   geometry; it redefines the zero to the input max and stores the range running
   `[0, −span]`. The handler is a clean 1:1 setter (`MinVal=radians(min_deg)`, no
   transpose), so the transform is SW-internal, downstream of `CreateMate`.
3. **Alignment-independent.** Forcing `MateAlignment="aligned"` (0) vs the default
   `"closest"` (2) produced the **byte-identical** transform — so it is NOT a
   reference-normal flip; it is intrinsic angle-limit storage semantics.

Per the W51 contract this is the defer trigger (we do not reverse-engineer a moving
angular coordinate system out-of-process — quadrant-sensitive, would invert on a
different topology). The `angle_faces`/`angle_limit` schema+validator+handler code
remains on the unmerged branch for a future scoped wave; a viable v-next route is a
feature-tree equation driving the limit, or teaching the declarative layer to issue
limits **relative to the SW-reparametrized zero**. Re-deferred 2026-06-10 (W51-B
seat).

**W52-C UPDATE — the v-next correction is EPHEMERAL; the kernel overrides COM
values with geometry-derived datums on save (re-deferred again, branch
`feat/w51-hinge-limit` @ `3be4f42` UNMERGED).** The W51-B v-next was implemented and
seat-fired: read SW's reparametrized zero post-`CreateMate`, then re-issue the
desired limits. Two genuine bugs were fixed in the process — (a) the handler called
`IFeature.ModifyFeature`, which **does not exist** (an O1 slip; corrected to the
in-repo-proven early-bound `ModifyDefinition(defn, raw_doc, None)` — the
`variable_radius_fillet` pattern); (b) the shift formula was disproven —
`ModifyDefinition` stores `MinVal`/`MaxVal` **verbatim** on an existing mate
(diagnostic `H_direct`: set `[−30,+30]` → reads `[−30,+30]` in-process), so the
correction is a straight no-shift re-issue. **But it does not survive save.**
Instrumentation proved the in-process correction SUCCEEDS (`ModifyDefinition`
returns True, reads back `[−30,+30]`) yet the persisted state after reopen is the
kernel's geometry-derived `[0,−60]`: **SW re-solves the mate on save and re-derives
the angle limit from the reference-face geometry, blowing away the COM-issued
values.** This is an architectural boundary, NOT a marshaling wall. (The spike's
`H_direct` GREEN was a FALSE POSITIVE — it read in-process, never through
save+reopen; the leg-1 persisted gate is the honest arbiter.) **The only durable
route is reference-geometry: generate angle-reference faces whose NATURAL resting
state is the desired zero-datum (SW's zero = the swing midpoint)** — a
fixture/selection design problem, not a value correction. That is the future epic.
The `ModifyDefinition` fix hardens the baseline and stays on the branch; angle-limit
VALUES remain deferred. Re-deferred 2026-06-11 (W52-C seat).

**`gear` mate SHIPPED 2026-06-10** (`feature kind` on the assembly `mate` spec:
`{type:"gear", a, b, ratio:{numerator, denominator}}`). Created + solved + ratio
round-trips through save/reopen, proven end-to-end via the **production**
`create_mate` (`spikes/v0_2x/mech_mate_gear_pae.py` → `MateGearDim`, reopened
ratio == requested (2,1)). **Load-bearing finding — SW's `GearRatio*` COM setters
are TRANSPOSED** (`mech_mate_gear_transform.py`): assigning `.GearRatioNumerator`
writes the *denominator* slot and vice versa — deterministic, geometry-independent
(set(2,1)→persist(1,2); set(1,2)→(2,1); set(3,2)→(2,3); identical under both
EntitiesToMate orders, so it is NOT a selection-order effect). The handler
compensates by swapping the assignment. This is the `reference_makepy_wrong_argtype`
family at the property level.

**`screw` mate FROZEN 2026-06-10 — pitch not controllable out-of-process (COM
wall).** The screw mate creates and solves cleanly (`MateScrew`,
`GetErrorCode2=(0,False)`), but the pitch (`RevolutionVal` under
`RevolutionType=swDistancePerRevolution`) **clamps to the 1 mm kernel default**
regardless of the requested value. Three paths characterized + exhausted on the
seat:

| Path | Result |
|---|---|
| Pre-create setter on `IScrewMateFeatureData` | T₀ (post-set) holds the value, but `CreateMate` discards it → 1 mm. Matrix: set {0.002, 0.004, 0.010} all persist 0.001 (`mech_mate_screw_calibration.py`). Rules out a unit transform — it is a hard clamp, not a ×2 factor. |
| `GetDefinition` + `ModifyDefinition` post-create | `ModifyDefinition` returns True yet the value still reads 0.001 (same spike, inline probe). |
| Concentric-first precondition (establish the rotation axis) | The concentric mate solves clean, but the screw mate then **refuses to instantiate** — `CreateMate` → None, `ErrorStatus=1` (`mech_mate_screw_calibration_v2.py`). |

`screw` is removed from `MATE_TYPES` / `MATE_SCHEMA` / validator and from the
handler `MATE_TYPE_ENUMS` / `MATE_TYPE_INTERFACES` (propose fails-closed on an
unknown mate type). Re-evaluate only with a new route (e.g. a feature-tree
equation driving the pitch, or a SW-version with a working `RevolutionVal`
marshal). Enum truth retained: `swMateSCREW=17` (typelib-verified, NOT the
API-doc's 14=MAXMATES).

## Wave-50 (auto-pierce sweep — generalization deferred)

**Auto-pierce SHIPPED 2026-06-10** (merge `961f9e8`): `_create_sweep` establishes
a programmatic `sgATPIERCE` relation so an LLM names two independently-authored
profile+path sketches and the sweep self-anchors (cures the "dummy wrapper"). v1
covers the dominant generative profiles (circular/arc — tubing / O-ring / rod).
**Two deferred sub-scopes (characterized, NOT walls — Wave-51 Lane A):**

| Item | Status |
|---|---|
| **Arbitrary-profile anchor** | ✅ **SHIPPED (W51-A, merge `0c0a891`).** `_apply_auto_pierce` v2: arc-center fast path, else `_sketch_centroid_coords` (centroid of non-construction segment endpoints + arc centers). Rectangle/polygon/arbitrary profiles self-anchor. PAE GREEN (rectangle 240 mm³, triangle 850 mm³). **Seat bug fixed:** endpoint getters live on DERIVED `ISketchLine`/`ISketchArc`, not base `ISketchSegment` → `typed_qi` each segment to its derived interface. |
| **Non-Front-plane coord mapping** | ⏸ **STILL DEFERRED (v3).** `SelectByID2("SKETCHPOINT", x,y,z)` needs MODEL coords; profile sketch X/Y are sketch-local. v2 `_sketch_to_model_coords` is an IDENTITY stub (Front-plane only). PAE Leg 3 (circle on Top plane) WALLs here (`sel_pt=False`, anchor un-mapped). v3 = `IRefPlane.Transform2` / `ModelToSketchTransform` inverse so Top/Right/ref-plane profiles map. |

W51-A authored offline (Lane A), fired + bug-fixed + merged by W0. v3 coord-mapping
remains. Recipe + proxy-shape lessons in memory `project_pierce_autosweep`.

## Wave-51 Lane C2 (free-DOF drag via `GetDragOperator` — UI-only, deferred)

**`IDragOperator` free-DOF drag is REACHABLE but does NOT commit headless — EARNED
UI-ONLY WALL 2026-06-10** (branch `feat/w51-motion-ext`, characterization spike
`spikes/v0_2x/motion_dragop_derisk.py`; Lane C1 `choose_clearance_pair` already
SHIPPED to par/integration, merge `d9a829e`). The W49 motion audit drives a mate
through its DOF via `Parameter().SystemValue`; this lane probed the ALTERNATIVE —
free-DOF dragging of an under-constrained component (motion envelopes with no
driving mate). **Every marshaling layer was cracked and the full protocol
executes** (`AddComponent`→`BeginDrag`→`Drag(IMathTransform)`→`EndDrag`, all return
`True`):

| Layer | Finding |
|---|---|
| `GetDragOperator` | Reachable on `IAssemblyDoc`; returns a real `IDragOperator` (52 members, full dump in spike `_results`). |
| Fixed-component | The lone/first inserted component is auto-FIXED → `AddComponent` returns **False**. Must `UnfixComponent` (select + float) first → then returns True. |
| `GetMathUtility` | Must be captured **RAW + EARLY** (in `main`, pre-doc-ops). Calling it after build/place yields `DISP_E_MEMBERNOTFOUND` — intervening doc ops perturb the late-bound name-lookup. The typed proxy does NOT resolve it. |
| `IMathUtility.CreateTransform` | Resolves ONLY on the **typed** `IMathUtility` (raw CDispatch → member-not-found — the inverse of `GetMathUtility`). |
| `DragMode` | `swMouseDragMode_e.swTranslateAssemblyComponent = 1` (set before drag). |

**Yet the component never moves** — `Drag()` returns True but `Transform2` reads
identical before/after, even with `DragMode=1` + `EditRebuild3` + `GraphicsRedraw2`.
**Root cause: `IDragOperator` emulates interactive MOUSE dragging** — the enum is
literally `swMouseDragMode_e` and the operator has a `DragAsUI` sibling; it requires
a graphics/mouse context that does not exist out-of-process headless, so a
programmatic `Drag` computes-but-does-not-commit. **This is authoritative (every
layer introspected + driven), not guessed.** Free-DOF dragging is NOT a viable
headless motion route; the **W49 parametric sweep stays the only programmatic
motion driver**. Re-evaluate only with an in-process add-in (real UI context).

## Wave-53 (design tables — in-file config via parameter grid)

| Item | Rationale |
|---|---|
| **In-file design tables (IDesignTable / InsertFamilyTableNew) — S1 de-risk authored, PENDING seat fire** | **W53 S1 authored offline (2026-06-11, branch `feat/w53-designtables`).** Design tables are the Phase-4 remaining item and the *separate, viable path* to W36 native configs: instead of creating configs individually and trying to modify them post-hoc (SetSuppression2 / per-config equations / per-config dimensions — all walled at W36), design tables let SW generate N configs from a single parameter grid. Three routes probed: **(A) `IModelDoc2.InsertFamilyTableNew(FilePath)`** — CSV-based insertion that may bypass the Excel OLE dependency that W36 flagged; **(B) `IDesignTable.Attach3` + `EditTable2`** — the OLE path (expected to wall like W36 predicted); **(C) post-insertion config enumeration + volume discrimination** — the verification gate. **Offline deliverables:** (1) `config/design_table.py` — data model (`DesignTableSpec`/`Column`/`Row`, `parse_design_table`, `format_grid_csv`/`format_grid_tab_separated`); (2) `config/dt_dispatch.py` — SEAT-gated `insert_design_table` orchestrator (InsertFamilyTableNew → config enumeration → CreateMassProperty per config → discrimination check); (3) `spikes/v0_2x/designtable_typelib_probe.py` — O1 typelib FUNCDESC introspection for `IDesignTable`/`IDesignTableFeatureData`/`IFamilyTable` + IModelDoc2 DT-method sweep; (4) `spikes/v0_2x/spike_design_table.py` — the seat spike with GREEN gate (N configs, volume-discriminated, surviving save→reopen) and fail-closed NO-GO path (FUNCDESC + exact no-op/leak characterization). **GREEN gate:** design-table spec materializes N DISTINCT configurations, volume-discriminated via `CreateMassProperty` per config, surviving save→reopen. **NO-GO gate:** if InsertFamilyTableNew returns None or configs are not volume-discriminated, the wall is characterized precisely (FUNCDESC + the exact failure mode). **Test suite:** `tests/config/test_design_table.py` covers the SW-free layer (parse/format/validate/write_grid_file). First raised + authored 2026-06-11 (W53 offline); seat fire pending. |

## Wave-44 (the "ghost feature" finding — B-rep-effect verification gap)

**`edge_flange` is a GHOST — QUARANTINED 2026-06-09.** While building a bent
fixture for W42 (`dxf_flat`), the seat exposed that `_create_edge_flange`
returns `ok=True` and creates an `Edge-Flange1` feature node that is **not
suppressed** and reports **`GetErrorCode2=(0, False)` (no error)** — yet adds
**ZERO** geometry: ΔVol=0, ΔFaces=0, reproduced **3×** (S2-v1 @100mm edge, S2-v2
@60mm W7 edge, and the exact unmodified edgeflange_pae chain @height 10) via
`spikes/v0_2x/edgeflange_brep_probe.py`. The W7 "production PAE" (`644edf6`)
"passed" by asserting feature-node + plane + sketch **presence** and **never
measured the B-rep** — so it advertised a capability that materializes nothing.
The internal normal-plane/profile-line or `VARIANT(VT_ARRAY\|VT_DISPATCH)`
SAFEARRAY construction almost certainly collapses to a degenerate flange the
kernel silently accepts (error code 0). `edge_flange` is removed from
`_SUPPORTED_FEATURE_TYPES` (propose fails-closed); handler kept as characterized
code; re-advertise ONLY after a ΔVol>0 seat proof.

**The defect CLASS is the real deliverable — node-presence proof ≠ effect
proof.** A handler that creates a feature *node* with no geometric effect cannot
be caught by `GetFeatureCount`/`GetFeatures(True)` deltas or node-presence — only
a **B-rep topology delta** (ΔVol/ΔFaces via `IBody2.GetMassProperties(1.0)[3]`)
can. Triage flags ~6 other advertised kinds verified the same weak way:

| Kind | Risk | Re-verification standard |
|---|---|---|
| `base_flange` | AT-RISK (node-presence) | sheet-metal body materializes; ΔVol>0 + face delta |
| `shell` | AT-RISK (explicitly "GetFeatureCount delta, not GetBodies2") | ΔVol < 0 (removes material) + face delta |
| `draft` | AT-RISK (feature-count) | face-angle change on drafted faces (ΔVol small but faces re-angled) |
| `sweep` | AT-RISK ("GetFeatures(True) delta") | ΔVol>0 + face delta |
| `sweep_cut` | AT-RISK ("GetFeatures(True) delta") | ΔVol<0 + face delta |
| `dome` | AT-RISK ("GetFeatures(True) count delta") | ΔVol>0 + face delta |

EFFECT-PROVEN (sound, no re-verify needed): `fillet`, `chamfer` (face 6→7),
`linear`/`circular`/`mirror_pattern` (volume/face delta), `wizard_hole` (caught a
real no-op), `delete_body` (W41 ΔVol). Ref-geom kinds (`ref_plane`/`ref_axis`/
`coordinate_system`/`ref_point`) legitimately have no body delta (datum-only). The
**W44 verification-gap audit** (dispatched 2026-06-09) authored a ΔVol/ΔFace
re-verification harness (`spikes/v0_2x/brep_verify_w44.py`,
`_results/brep_verify_w44.json`) per at-risk kind; W0 drove it on the seat.

**RESULT — 6/6 GREEN, 0 GHOSTS (2026-06-09):** every at-risk kind is
effect-proven. `base_flange` ΔVol +3,200 / ΔFaces +6; `shell` ΔVol −27,436 /
ΔFaces +5; `draft` ΔVol +419 / ΔFaces 0 (re-angles faces without changing
count — ΔVol-only proof accepted); `sweep` ΔVol +2,356 / ΔFaces +3; `sweep_cut`
ΔVol −283 / ΔFaces +2; `dome` ΔVol +3,556 / ΔFaces 0 (modifies a face in place —
ΔVol-only). The edge_flange ghost was the **only** ghost in the advertised set;
all 18 kinds now stand on effect proof (or are legitimately datum-only).

**One handler defect surfaced (verification-method, NOT a ghost) — FIXED
2026-06-09 (`40842eb`):** `_create_draft` checked only `_materialized(feat)`,
but `InsertMultiFaceDraft` returns `None` even on success → the handler reported
`ok=False` when the draft in fact materialized (ΔVol +419 measured). Fixed with
the feature-count-delta gate that `_create_dome` / `_create_shell` already use.
Verification basis = no fresh PAE (W6/T4 sweep-cut precedent): the W44 harness
`test_draft` already ran this exact `GetFeatures(True)` delta live (lines
389-398, GREEN ΔVol+419); the fix ports that logic 1:1 into the handler, the
coordinate face-resolution path unchanged.

## v0.13+ backlog (no committed dates)

Future capability lanes — each is a multi-week project with its own
design phase, NOT a "we forgot to do this" item.

| Item | Status |
|---|---|
| **Configuration support** — build same spec against multiple `.ai-sw-bridge.toml` profiles, diff resulting B-rep manifests | Backlog |
| **Assembly + mate primitives** — extend declarative JSON contract to multi-part assemblies | **✅ SHIPPED — Phase-1 (W9) + Phase-2 (W10) + Phase-3 (W11) + Rotation (W13), 2026-06-05.** Advertised via the **`ai-sw-assembly` CLI** (propose→dry_run→commit; CLI-only per §6.5, never MCP). **Phase-1 (W9):** declarative assembly spec (`assembly/` module — schema/validator/storage/face_resolver/handlers/lifecycle); `place_components` via `OpenDoc6` pre-open (MANDATORY; its absence was the E4 "wall") → `NewDocument(asmdot)` → `IAssemblyDoc.AddComponent4(path,"",x,y,z)` → real B-rep `IComponent2`; components sourced from a prebuilt `.sldprt` OR built from a declarative `part_spec` by the lifecycle (build-then-place resolver, real PAE GREEN `b03104a`); coincident mate. **Phase-2 (W10):** **all five mate types ship** — coincident, distance, concentric, parallel, perpendicular. **Phase-3 (W11):** tangent, angle, limit mates. **Rotation (W13):** `rpy_deg` rotation un-fail-closed — `place_components` applies non-zero `rpy_deg` via `IMathUtility.CreateTransform(16-elem VT_R8)` → `IComponent2.Transform2` + `SetTransformAndSolve`. Convention: `R = Rz(yaw)·Ry(pitch)·Rx(roll)` (intrinsic ZYX). **8 mate types total.** **Persistence (W14):** manifest v2 sidecar (`<asm>.sldasm.manifest.json`) — verbatim spec (lossless `to_spec()`) + runtime overlay (live sw_names, resolved paths, part_spec provenance sha256); relative⇄absolute path handling; v1 back-compat. **Edit (W15):** interactive declarative edit — `assembly/edit.py::apply_edit_op` (add/remove component/mate, immutable, fail-closed) + `ai-sw-assembly edit` (CLI-only §6.5). **Drawing (W16):** `kind:"drawing"` — see the Drawing-generation row below. Assembly authoring surface complete (author→build→persist→edit→draw). |
| **Width mate (W12) — SHIPPED 2026-06-05** | Width (`swMateWIDTH=11`, `IWidthMateFeatureData`) is the **8th advertised mate type**. Production handler `_create_width_mate` takes a dedicated path before the shared `EntitiesToMate` block: resolves 4 face refs (2 `width_faces` → `WidthSelection`, 2 `tab_faces` → `TabSelection`), builds two `VARIANT(VT_ARRAY|VT_DISPATCH)` SAFEARRAYs, `CreateMate`. Declarative shape: `{"type":"width", "width_faces":[2 refs], "tab_faces":[2 refs]}`. PAE GREEN (`spikes/v0_2x/_results/width_mate_pae.json`): solo `MateWidth`, `solved:true`, `error_code:0`, `suppressed:false` — confirming W11 combined-PAE err-51 was over-constraint artifact. **Scope guard (still deferred):** non-centered `ConstraintType` modes (free/dimension/percent + `DistanceFromEnd`/`PercentDistanceFromEnd`/`FlipDimension`) and 1-face-per-side width mates; v1 = centered, exactly-2-per-set. |
| **Drawing generation** — 2D drawing sheets from 3D part/assembly specs | **✅ SHIPPED (W16 + W17 + W18 + W19 + W23 + W28, 2026-06-06)** — declarative `kind:"drawing"` via the **`ai-sw-drawing` CLI** (propose→dry_run→commit; CLI-only per §6.5, never MCP). `drawing/` module (spec_schema/validator/lifecycle). Spec: `{kind:"drawing", model:<.sldasm\|.sldprt>, views:[<string ortho/iso> \| {type:"section",name,parent,cut:"horizontal"\|"vertical"} \| {type:"detail",name,parent,center?:[fx,fy],radius?:frac}], dimensions?:bool, bom?:bool, sheet?}` **OR multi-sheet `sheets:[{name,template_size?,views[],dimensions?,bom?}]` (W23; `views` XOR `sheets`, mutually exclusive)**. **Multi-sheet (W23):** optional top-level `sheets[]`; back-compat = top-level `views` with no `sheets` is a single sheet, unchanged (legacy PAE 11/11 still GREEN). New sheet via **`IDrawingDoc.NewSheet3(Name, PaperSize:I4, TemplateIn:I4, Scale1, Scale2, FirstAngle:BOOL, TemplateName, Width, Height, PropertyViewName)→BOOL`** (10 args; **makepy-authoritative — CHM swaps PaperSize/TemplateIn, do NOT trust it**; PaperSize=`swDwgPaperSizes_e` A4=8/A3=11/…; TemplateIn=1=caller supplies Width/Height). Per-sheet routing = `NewSheet3(name)`→`ActivateSheet(name)`→`CreateDrawViewFromModelView3` (views land on active sheet). Per-sheet view count = `len(ISheet.GetViews())` (`ISheet.GetViewCount` does NOT exist). Validator fail-closed: views XOR sheets, ≥1 sheet, cross-sheet `parent` rejected, duplicate sheet-name rejected; commit normalises either mode + fail-closed abort before SaveAs3. PAE PASS (2 sheets, per-sheet view counts verified on reopen, each view on its intended sheet). **Cracked the W4 `IDrawingDoc` E_NOINTERFACE wall:** `NewDocument(Drawing.DRWDOT)` → **`typed_qi(doc,"IDrawingDoc")`** → per-view `CreateDrawViewFromModelView3`. **Dimensions (W17):** `dimensions:true` inserts model annotations via `IDrawingDoc.InsertModelAnnotations3(0,-1,True,False,True,0)`. Popup suppression: toggles `[9,10,22,23]` set to `False` enables clean parametric build (no_dim=False). PAE GREEN 9/9 (4 views, 6 dims, 33KB .SLDDRW). **BOM (W18):** `bom:true` inserts a top-level BOM via `IView.InsertBomTable4` (dispid 414, 10 args) → `IBomTableAnnotation`; anchored to the **sheet** (not a model view), `ActivateView` required before insert; liveness via `GetComponentsCount2` iterator (the `GetTableAnnotationCount`/`IGetBomTable`/`IBomTable`-QI paths are all dead). Cross-field fail-closed: `bom:true`+`.sldprt` → `ValueError` (parts have no BOM). PAE GREEN 11/11 (2-component .sldasm → 2 rows → 42KB, verified on reopen). **Section/detail views (W19):** `views[]` grows from strings-only to **string-or-object**; a derived entry carries `{type, name, parent}`. **Section:** `cut:"horizontal"\|"vertical"` → two-pass commit sketches a center cut line on the parent view (`IModelDoc2.SketchManager.CreateLine` after `ActivateView`) → `IDrawingDoc.CreateSectionViewAt5(X,Y,Z,label,opts,excl,depth)` (dispid 0xf8). **Detail:** `center?:[fx,fy]`+`radius?:frac` (bbox fractions) → `CreateCircleByRadius` → `CreateDetailViewAt4(...)` (dispid 0x111, returns CDispatch → `typed_qi(IView)`). Liveness: `GetViews` +1 **and** `IView.Type` (section=2, detail=3), non-degenerate outline. Validator fail-closed: `parent` must name an **earlier** string ortho/iso view (no section-of-section / forward-ref); section requires `cut`; detail center/radius type-checked. Note: `IDrawingDoc` does not inherit `IModelDoc2` in the typelib → separate `typed_qi(doc,"IModelDoc2")` for `SketchManager`. PAE GREEN 12/12 (front+section+detail, types `[1,7,2,3]` verified on reopen, 60KB). **Tolerances (W28):** `dimensions` grows from `bool` to **`bool | object`**; `{dimensions:{tolerance:{type, ...}}}` applies ONE general tolerance to all flowed dims on that sheet. Types: `symmetric` (`{type:"symmetric", value:≥0}`, ±value), `bilateral`/`limit` (`{type, max, min}`, max≥min). **CRITICAL — tolerances are MODEL-OWNED:** a drawing's `IDimension` *is* the part's `IDimension` (same COM object), so tolerance is set on the dim and persists in the **`.SLDPRT`/`.SLDASM`, NOT the `.SLDDRW`** → lifecycle saves the MODEL after applying (gated: only when `tolerance` is specified; plain `dimensions:true` never touches the part). Recipe: `IView.GetDisplayDimensions()`→`IDisplayDimension.GetDimension2(0)`→`IDimension.SetToleranceType(swTolType_e)`+`SetToleranceValues(min,max)` (metres); read-back `GetToleranceType()`/`GetToleranceValues()`. `swTolType_e`: symmetric=4, bilateral=2, limit=3. Validator fail-closed on any non-{symmetric,bilateral,limit} type (rejects GD&T). PAE GREEN (all 3 types set + read back on reopen). **Deferred:** shared/linked cross-sheet views, per-sheet title-block fields, sheet reorder/delete ops, cross-sheet section/detail parent, angled/offset/aligned/multi-segment section lines, section-of-section, detail shape/profile + explicit scale/label-style, broken-out & crop views, **ordinate/baseline dim types (W31v NO-GO: datum selectable via IView.SelectEntity, AddOrdinateDimension returns True but creates zero dims)**, per-dimension tolerance overrides / dual tolerances / fit-class (H7/g6) / GD&T feature-control-frames / surface-finish / datums / basic-reference dims, BOM type selection (parts-only/indented), BOM anchor/template/columns/multi-BOM/balloons. |
| **Export — PDF** (drawing → PDF, single + multi-sheet) | **✅ SHIPPED (W25, 2026-06-06)** — `export/` module via the export CLI. Recipe: `tsw.GetExportFileData(1)` (`swExportPdfData=1`) → `typed_qi(IExportPdfData)` → `SetSheets(mode, sheet_names)` (mode 1=all/2=current/3=specified) → `IModelDocExtension.SaveAs` via **`InvokeTypes` with 6 args** (early-bind `SaveAs` fails on the `[out] VARIANT*` Errors/Warnings params — pass placeholders via raw `_oleobj_.InvokeTypes(93, …, ((8,1),(3,1),(3,1),(9,1),(16387,3),(16387,3)), path, version, options, pdf_data._oleobj_, 0, 0)`). Declarative `sheets:"all" | [names]`. Doc-type fail-closed (PDF on a part rejected), unknown sheet-name rejected. S1 multi-sheet proof = size ratio 5.88 (2-sheet vs 1-sheet, differing content). PAE core gates GREEN (export + subset + rejections). **Deferred:** DXF export, PDF quality options (DPI/color/line-weight), 3D PDF, eDrawings, password/security. |
| **Export — DXF** (drawing → DXF, 2D vector) | **✅ SHIPPED (W33, 2026-06-06)** — `export/` module via the export CLI (format `"dxf"`). **Route: SaveAs3_DIRECT** — `IModelDoc2.SaveAs3(path.dxf, 0, 0)`; the extension in the path selects the DXF exporter (same pattern as STEP/IGES). **Liveness proven:** 4 LINE entities in ENTITIES section for a box front view (parsed via group-code scan `0\nLINE`); file size 20KB+. Doc-type fail-closed: DXF requires a Drawing doc; Part/Assembly → clear ValueError (`format:'dxf' requires a Drawing (.SLDDRW) document`). Seat-confirmed (`formats.py:seat_confirmed=True`). PAE GREEN (drawing→DXF = 4 entities; part→DXF = rejected). **Deferred (v1 scope guard):** `dxf_flat` (sheet-metal flat-pattern DXF needs S-SHEETMETAL + flat-pattern config activation; blocked on W16 sheet-metal walls), DWG (same API surface as DXF but requires different extension), 3D-DXF (3D geometry in DXF format), DXF version selection (AC1014/AC1015/AC1024/etc), DXF units mapping (mm/inch), layer mapping, polyline vs line export mode, hidden-line removal options, watermark/annotation injection. |
| **Observe — measure + bounding-box** (read-only perception) | **✅ SHIPPED (W30, 2026-06-06)** — `observe_bbox.py` + `observe_measure.py`, read-only, on BOTH `ai-sw-observe` CLI AND MCP (`sw_bounding_box`/`sw_measure_selection`; §6.5 gates only mutations). **bbox** = `IPartDoc.GetPartBox(True)` → 6-tuple metres (`IModelDocExtension.GetBox` is NOT exposed on the SW2024 typelib); PART-ONLY, fail-closed typed error on assemblies/drawings. **measure** = `IModelDocExtension.CreateMeasure()` → `IMeasure` → select entities → `Calculate(None)` → `Distance`+`DeltaX/Y/Z` (measures the CURRENT selection). Seat-proven on a 20×30×40mm box (bbox exact; diagonal 53.85mm). **Deferred:** assembly/multi-body bbox, tight-vs-system bbox option, measure-by-durable-ref-pair (vs current selection), min-distance/clearance between components, angle/area measures. |
| **Sheet metal primitives** — bend tables, flat patterns, gauge tables | Backlog |
| **Sketch editing — Trim (ray-cast `swSketchTrimClosest`)** | **WALLED (W60, 2026-06-17) — headless UI-state wall.** Sibling of Offset/Convert/Pattern (all 3 ✅ SHIPPED W60 on the `ai-sw-sketch-edit` CLI, §6.5). `ISketchManager.SketchTrim(0=swSketchTrimClosest, X, Y, Z)` resolves the trim target by **ray-casting a screen-space cursor point against a rendered viewport**; out-of-process there is no model-view / UI selection-state manager, so a **well-formed, unambiguous** call returns `False` with **zero segment delta**, every time. Proven exhaustively: the enum value (`0=swSketchTrimClosest`) and the method signature (`(Int32, Double, Double, Double)→Boolean`) were both confirmed against `SolidWorks.Interop.swconst.dll` / `…sldworks.dll`; two distinct picks were tried on a valid 3-segment cross fixture — dead-on the interior span, then shifted +5 mm clear of the origin and both intersections — both returned `False`/Δ0. Same UI-only class as free-DOF mate drag and the rib / move-copy-body o-o-p walls. **Mode-B doctrine ([[reference_createdefinition_qi_wall]]):** only the *ray-cast paradigm* is walled, NOT the trim feature. A future capability must evaluate **entity-preselection trim (`swSketchTrimEntities`=4 / `swSketchTrimTwoEntities`=2)** — these take pre-selected topological entities (a `DurableEdgeRef`-style interaction) instead of a spatial coordinate, so they may survive headless. That is a **different op schema = a new lane, not a hotfix**, hence deferred-not-dropped. |

| **Sheet-metal secondary features — `edge_flange`, `miter_flange`, `jog` (W65)** | **WALLED (W65, 2026-06-18) — out-of-process profile-sketch / fold-line GHOST trap.** Part of the W65 Sheet-Metal Completion epoch; the fourth lane **`sketched_bend` SHIPPED GREEN** (`InsertSheetMetal3dBend` → `'SM3dBend'`, ΔFaces+8, fold-class verified, merged to master). These three did NOT, and they fail as a **class**, not individually. **The systemic finding:** legacy `IFeatureManager.InsertSheetMetal*` features that require a **profile sketch or fold-line with topological relations** silently no-op/ghost out-of-process, while **parametric** ones (hem W59, 3dBend W65) materialize cleanly. Each was forced to the *correct geometric setup* in an isolated worktree seat fire and the kernel still refused to build: **`edge_flange`** — `InsertSheetMetalEdgeFlange` (13-arg) with a properly authored `SketchFeat` profile (ref-plane-normal-to-edge via the shipped two-reference `InsertRefPlane(4,0,2,0,0,0)` + length-driven line) creates an `Edge-Flange1` NODE but adds **zero geometry** (ΔFaces=0, ΔVol=0 — the W42 ghost; the handler's ΔVol gate correctly rejects it). The 13-arg single form has **no flange-length arg** at all — a null `SketchFeat` yields a zero-extent flange. **`miter_flange`** — `InsertSheetMetalMiterFlange` (14-arg Feature overload) with a stable two-reference profile plane (`Plane1`/`Sketch6` built) returns `None` and adds nothing (ΔFaces=0). **`jog`** — `InsertSheetMetalJog` (7-arg, Void) returns cleanly even with a **full-span** fold line (±0.035 m overshooting both face boundaries) but folds nothing (ΔFaces=0, bbox unchanged); the solver demands a fixed-face designation / selection granularity not reachable OOP. **Mode-B doctrine ([[reference_createdefinition_qi_wall]]):** the *API accepts the call and may even return a node*, but the topological solver silently refuses the profile↔face relation across the COM boundary. Same structural class as the Rib/Loft/Wrap walls below — **needs an in-process add-in (Route C), not more spike iteration.** Worker artifacts (a built-in `_create_edge_flange` rework + `_sm_metrics`/bbox math) preserved on branch `wip/w65-worker-mainrepo`. |

| **`thicken` — surface→solid bridge (W66)** | **WALLED (W66, 2026-06-18) — out-of-process surface→solid bridge no-op.** Part of the W66 Surfaces epoch; the other 3 lanes SHIPPED GREEN (`planar_surface`, `offset_surface`, `knit` — all merged to master). `IFeatureManager.FeatureBossThicken(Thickness, Direction, FaceIndex, FillVolume, Merge, UseFeatScope, UseAutoSelect)` (7-arg → Feature) runs clean but produces **ΔVol=0, ΔSolids=0** — no solid forms from a sheet body. Forensic chain (4 rounds): (1) selecting the sheet **body** failed (`IBody2` is not an `IEntity`) → must select a **face** (`GetFirstFace`); (2) face-select then succeeds but the call no-ops; (3) `UseAutoSelect` True/False — no change; (4) **decisive standalone probe** — built a sheet body in EMPTY space (no solid block → boolean-merge variable eliminated; sheets=1, solids=0 before) and `FeatureBossThicken` STILL produced nothing. This refutes the multi-body-merge hypothesis and proves a genuine OOP wall: **surface→solid bridging refuses across the COM boundary**, distinct from surface *creation* (planar/offset materialize fine) and surface *aggregation* (knit merges fine). Same Route-C-only class as the W65 sheet-metal profile↔face walls ([[reference_sheetmetal_oop_profile_sketch_wall]]). Handler kept UNFIRED/unregistered (the `__init__.py` block is dormant); authored shape retained as characterization. |

## Indefinitely deferred (by design)

| Item | Reason |
|---|---|
| **Solver-deep feature cluster — Rib (F3), Wrap (F5), Loft (F2), Boundary Boss (F6), Interference Detection (E4)** | **PERMANENTLY out-of-scope — architectural ruling 2026-06-04 (Wave-7 epoch).** Each was exhaustively characterized on a live seat (detailed entries in the Wave-5/Wave-6 sections above) and shown to have **no out-of-process creation API path**: the legacy `Insert*` methods silently no-op, no `swFm*`/`CreateDefinition` feature-data path exists, and (E4) overlapping B-rep component placement is unreachable across the COM boundary. The only known unlock was in-process macro injection / dynamic **VBA-emit-and-run**. **That path was formally REJECTED:** the VBA-emit strawman (`docs/central_idea/WAVE7_VBA_EMIT_STRAWMAN.md`) was declined because it would relax **Invariant #3 (zero arbitrary code execution)**, which is a defining, non-negotiable property of the declarative bridge. The out-of-process COM boundary is the architecture's defining constraint; features that require crossing it to compute topological projections are **structurally incompatible with the declarative paradigm**, not pending work. Recorded as a documented permanent limit, not a backlog item. (Earlier "Route-C/VBA-emit territory (Wave-7 strategic lane)" notes on the individual entries above are **superseded** by this ruling.) |
| **L5 — C# in-process adapter via PythonNET** | Decisions.md ratified the indefinite deferral 2026-05-23. The VBA-emit-and-run alternative (`SolidworksMCP-python/vba_adapter.py`) likely collapses L5 entirely. **Update 2026-05-30:** the last concrete *technical* driver for going in-process — OUT-param / Callout marshaling, specifically the durable-selection keystone `GetObjectByPersistReference3` — was cleared **out-of-process** by hybrid early binding (`spikes/v0_15/spike_earlybind_persist.py`, S-EARLYBIND = PASS; `com.earlybind`; decisions.md 2026-05-30). No feature lane now depends on L5. Re-evaluate only if pywin32 stability degrades meaningfully against the (still-undefined) trigger telemetry above. |
| **`ARCHITECTURE_STYLE.md`** as a separate doc | Decisions.md 2026-05-28 chose `CODESTYLE.md` over per-decision ADRs *and* over a parallel ARCHITECTURE_STYLE doc. Picking both was rejected as ceremony. |

## Re-evaluation triggers

Watch for these signals; they would unblock items above:

- **External demand for Lane M** alternatives — two or more independent integrators asking for HTTP transport, not stdio. (Lane M itself shipped in v0.13 over stdio.)
- **v0.13 B-rep fingerprint stability data** — informs the L1 quantization tolerance.
- **Adoption metrics from the API RAG index** — precision@1 trends inform the L3 corpus boundary.
- **First user report of pywin32 stability degradation** — defines the L5 trigger.
- **First multi-part assembly user** — unblocks L4 multi-part storage decision.
- **First non-English contributor** — pulls forward i18n catalog work beyond the scaffold.

## W68 Route-C Classification (kernel wall proofs, 2026-06-20)

Route-C in-process probe (`spikes/v0_2x/route_c/`) classifies four features
that ghosted out-of-process: does the feature ghost because of the **COM
marshaling boundary** (fixable), or because the **Parasolid kernel structurally
refuses** it (permanently deferred)?

| Feature | API call | In-process attempts | Result | Verdict |
|---|---|---|---|---|
| **edge_flange** | `InsertSheetMetalEdgeFlange2` (13-arg) | 8: `{edge_arg, preselect} × {opts:1,129} × {90°,45°}` | 8/8 ghost (ret:null, dVol:0, dFaces:0) | **KERNEL WALL** |
| **miter_flange** | `InsertSheetMetalMiterFlange` (14-arg) + Mode-A scan | 16: 4 FlangePos legacy + 12 CreateDefinition IDs scanned | 16/16 ghost (no IMiterFlangeFeatureData found) | **KERNEL WALL** |
| **jog** | `IModelDoc2.InsertSheetMetalJog` (7-arg, Void) | 6: `{30°,45°,90°} × {10mm,20mm}` offset | 6/6 ghost (dFaces:0, bbox:same, dVol:0) | **KERNEL WALL** |
| **wrap** | `InsertWrapFeature2` (5-arg) + Mode-A scan | 13: 3 types (emboss/deboss/scribe) + 10 CreateDefinition IDs | 13/13 ghost (no IWrapSketchFeatureData found) | **KERNEL WALL** |

**Structural finding:** all four features require a **profile↔face or
profile↔topology relation** that the Parasolid kernel structurally refuses,
even with a direct `ISldWorks` pointer (no COM marshaling boundary). This is
the same class as the W67 `FeatureBossThicken` kernel wall (12/12 ghost
in-process, `route_c_sweep_sentinel.txt`). The W65 diagnosis ("needs Route-C,
not more spike iteration") is now resolved: Route-C proves these are **not**
COM-boundary walls — no OOP fix (corrected selection, VARIANT coercion,
typed proxy) can materialize them.

**Implication for the production OOP path:** these four features are
**permanently deferred** alongside thicken, rib, loft, wrap (F5), and F6
boundary boss. The Route-C harness is retained in `spikes/v0_2x/route_c/` for
future classification tasks.

Artifacts: `spikes/v0_2x/_results/route_c_{edge_flange,miter_flange,jog,wrap}.{json,txt}`.

---

## W68 indent (out-of-process `InsertIndent` ghost — forensic kill, 2026-06-21)

`indent` (`IFeatureManager.InsertIndent(Thickness, Clearance, Exclude, ClrDir,
Cut, CutDir) -> Feature`) was seat-proven dead across the COM boundary by an
exhaustive forensic chain on the live seat. The lane first bounced on a
**selection** wall (the handler used `select_entity` for the tool body — a whole
solid body is not an `IEntity`); that wall was fixed (native
`IBody2.Select(Append, Mark)`, W0 patch, confirmed working — the handler reached
`InsertIndent`). With selection cleared, the feature still ghosted:

| Probe | Target entity | Marks swept | Bodies intersect? | Result |
|---|---|---|---|---|
| mark sweep | top **face** | (0,1)(1,2)(0,2)(1,1) | yes (10×10×10 mm) | 4/4 ghost (ret:None, dFaces:0, dVol:0) |
| body sweep | whole **body** | (0,1)(1,0)(1,1)(0,0) | yes (10×10×10 mm) | 4/4 ghost (ret:None, dFaces:0, dVol:0) |

**Key facts proven, not guessed:** (1) the two fixture bodies genuinely
intersect — an axis-aligned bbox preflight measured a 10×10×10 mm overlap every
variant, refuting the handler's own "must overlap" self-diagnosis; (2) both
entities select (`GetSelectedObjectCount2` == 2) under every configuration;
(3) `InsertIndent` returns `None` and produces zero topological change across all
8 topologically valid configurations (face-target and body-target × the full
mark matrix). The 6 `InsertIndent` args carry no target/tool role — roles come
only from marks — so marks were the live variable, and they are exhausted.

**Verdict: KERNEL/COM wall** — same OOP-ghost class as `InsertFlexFeature`
(all-Types ghost), `fill_pattern` `CreateFeature`, and the Route-C set (API
accepts, returns null, kernel refuses across marshaling). **Permanently
deferred**; do not re-attempt out-of-process. The durable extraction is the
`IBody2.Select` body-selection recipe (banked, reusable for every future
deform/boolean lane) and the reception-gate lint that now mechanically catches
the `"BODY"`→`"SOLIDBODY"` selection-type trap.

Artifacts (ephemeral, in the now-pruned `feat/w68-indent` worktree):
`spike_indent_marksweep.py` / `spike_indent_bodysweep.py` →
`_results/indent_{marksweep,bodysweep}.json`.

---

## W68 table_driven_pattern (out-of-process `InsertTableDrivenPattern` ghost, 2026-06-21)

`table_driven_pattern` (`IFeatureManager.InsertTableDrivenPattern(String
FileName, Object PointVar, Boolean UseCentroid, Boolean GeomPatt) -> Feature`)
was W0-authored (the offline worker's branch never reached origin) and
seat-proven dead across the COM boundary. The lane attempted the cleanest
pattern shape — a seed feature replicated at explicit (X,Y) points injected as
an in-memory array — and was the prime candidate for the W68 SAFEARRAY doctrine.
It ghosted (`ret=None`, ΔFaces 0, ΔVol 0) across **7 distinct configurations**:

| Axis | Variants | Result |
|---|---|---|
| marshalling (seed only, mark 4) | `VARIANT(VT_ARRAY\|VT_R8)` / bare list / `InsertTableDrivenPattern2` | 3/3 ghost (ret:None) |
| coordinate-system prerequisite | CS at origin (`CoordSys`) + seed(4), CS mark ∈ {1,2,0} | 3/3 ghost (ret:None) |
| seed-only baseline | seed(4) + SAFEARRAY | 1/1 ghost (ret:None) |

**Two decisive findings:** (1) the **SAFEARRAY doctrine did NOT extend** — a bare
list and `VARIANT(VT_ARRAY|VT_R8)` ghost *identically*, so marshalling is not the
differentiator; the wall sits upstream of the point array. (2) Supplying a valid
**coordinate system** (the table-driven frame of reference) and selecting it
alongside the seed at every plausible mark still produced a creation-level ghost
(`ret=None` — the feature never forms). Both genuine structural requirements
(array marshalling + reference frame) were satisfied and the kernel still
refused.

**Verdict: KERNEL/COM wall** — same OOP-ghost class as `indent`,
`InsertFlexFeature`, `fill_pattern`, and the Route-C set. The likely cause is
that the OOP path demands an internal context it cannot receive (e.g. a
file-backed `*.sldptab` pattern table rather than an in-memory array — the
`FileName` arg hints at a file-first design). **Permanently deferred**; do not
re-attempt the in-memory array path out-of-process. Lane branch+worktree pruned.

Artifacts (ephemeral, pruned worktree): `spike_table_driven_pattern.py` /
`spike_table_driven_csys.py` → `_results/table_driven_{pattern,csys}.json`.

---

## W68 flex (out-of-process `InsertFlexFeature` ghost — undefined flex frame, 2026-06-21)

`flex` (`IFeatureManager.InsertFlexFeature(RotX,RotY,RotZ, TanX,TanY,TanZ,
RadX,RadY,RadZ, Angle, PivotX,PivotY,PivotZ, Type, LeftTrim, RightTrim,
HardEdges) -> Feature`) was bounced once (selection wall), W0-fixed and
re-fired, and is now seat-proven dead OOP. The selection wall is CLEARED (native
`IBody2.Select` → "selected" every attempt — see [[reference_ibody2_select_not_ientity]]);
with the body correctly selected, the feature ghosts (`ret=None`) across:

| Axis | Variants | Result |
|---|---|---|
| Type Int32 (prior session) | 0/1/2/3, zeroed trim | 4/4 ghost |
| trim-plane convention (this session) | A(−L/4,+L/4) / B(+L/4,+3L/4) / C(+L/4,+L/4), L=100 mm | 3/3 ghost (ret:None, ΔFaces 0, bbox unchanged) |
| handler (variant A baked) | bbox-derived ∓L/4 | ghost |

**Decisive finding:** non-degenerate, well-separated trim planes (∓25 mm and
+25/+75 mm, all inside the 100 mm block) did NOT unstick it — so the original
all-zero-trim defect was real but not the whole story. The residual is the
**all-zero `Rot/Tan/Rad/Pivot` flex-frame triad**: `InsertFlexFeature` needs a
defined local coordinate system (tangent/rotation/radius vectors + pivot) to
orient the bend, and that is a 9-parameter continuous geometric space, not a
bounded discrete sweep. The OOP path cannot synthesize it reliably; `ret=None`
is a creation-level ghost.

**Verdict: KERNEL/COM wall** (same `ret=None` OOP-ghost class as `indent`,
`table_driven_pattern`, `fill_pattern`, Route-C). **Deferred**; an in-process
Route-C add-in with a UI-derived flex triad is the only plausible future path.
The durable wins extracted: the `IBody2.Select` recipe (re-confirmed) and the
bbox-derived `_trim_planes` math (correct, just insufficient alone). Lane
branch+worktree pruned.

Artifacts (ephemeral, pruned worktree): `spike_flex.py` (A/B/C trim sweep),
`spike_flex_typesweep.py` → `_results/flex{,_typesweep}.json`.

---

## W68 dimension_pattern + derived_pattern — KERNEL/COM WALL (PREDICTED, 2026-06-21)

Pre-emptively deferred WITHOUT a seat fire, by the **W68 OOP boundary law**
established empirically this session:

> **OOP gives Selection-and-Replication; abstract-spec geometry is Route-C.**
> Features that materialize out-of-process replicate a pre-SELECTED seed at
> pre-SELECTED locations (linear/circular/mirror/`sketch_driven`/`chain`). Features
> that require the kernel to synthesize geometry from an ABSTRACT spec — a boolean
> shell (`indent`), a coordinate matrix (`table_driven`), a deform frame (`flex`) —
> ghost `ret=None` at the COM boundary. (Empirical basis: `indent`,
> `table_driven_pattern`, `flex` all seat-killed `ret=None` this session;
> `sketch_driven`/`curve_through_xyz` shipped.)

- **`dimension_pattern`** (`FeatureDimensionPattern(Num1, Spacing1, Num2,
  Spacing2, DiagonalOnly, DName1, DName2, VaryInstance)`) is driven by live
  **dimension NAME strings** (`"D1@Sketch2"`) — an abstract symbolic spec the OOP
  caller must author and feed back; squarely on the wrong side of the boundary
  (no pre-selected geometry; the kernel resolves named parameters).
- **`derived_pattern`** (`InsertDerivedPattern2()`, zero-arg) derives a pattern
  from a parent pattern's instance layout via **UI-context parent-child
  relations** — pure abstract-context dependency, no pre-selectable seed-and-path.

Both violate the boundary law and are predicted `ret=None` ghosts. Deferred
without burning seat time; re-evaluate only via Route-C in-process. (If ever
seat-tested and one materializes, the boundary law needs revision — log it.)

---

## W68 chain_pattern (out-of-process `FeatureChainPattern` ghost — curve-traversal wall, 2026-06-21)

`chain_pattern` (`IFeatureManager.FeatureChainPattern(PitchMethod, Flip,
FillPath, Number, Spacing, G1Flip, G2Chain, G2Flip, Align, Options) ->
Feature`) was W0-authored and fired as the deliberate test of the OOP boundary
law (it looked like pure selection-and-replication). It ghosted `ret=None`
across **8 configurations**:

| Path type | seed×path marks | Result |
|---|---|---|
| model edge | (4,1)(4,2)(4,0)(0,1)(0,2)(0,0) | 6/6 ghost (ret:None, both selected, sel_count 2) |
| sketch-segment chain | (4,1)(4,2) | 2/2 ghost |

Neither the selection-mark role nor the path topology unstuck it. **This
SHARPENED the boundary law rather than breaking it:** `chain` and
`curve_driven` are the two *curve-traversal* patterns (the kernel must walk an
arbitrary path and solve arc-length spacing), and BOTH wall — while the three
*closed-form/explicit* patterns (linear / circular / `sketch_driven`) all ship.
The refined law: **OOP materializes replication at positions the caller
specifies directly (offset / rotation / explicit points); it walls when the
kernel must traverse or solve geometry mid-invocation to derive the positions.**
See `reference_oop_boundary_law` (memory).

**Verdict: KERNEL/COM wall** (curve-traversal subclass). Permanently deferred;
Route-C in-process only. Lane branch+worktree pruned. Artifacts (ephemeral):
`spike_chain_pattern.py` / `spike_chain_marksweep.py` →
`_results/chain_{pattern,marksweep}.json`.

---

## W68 wave-2 bounces — curve_driven_pattern + fill_pattern (epoch-close record, 2026-06-21)

Two W68 wave-2 lanes were bounced in earlier sessions and are now formally
deferred at epoch close (branches pruned; tips reflog-recoverable —
`curve_driven` @ `9d870a4`, `fill_pattern` @ `a2ba6e3`):

- **curve_driven_pattern** — `IFeatureManager.FeatureLocalCurveDrivenPattern`
  (the live method; `FeatureCurvePattern` on IModelDoc is a Void method that
  CRASHED the seat OOP, `RPC_E_DISCONNECTED`). Now cleanly classified by the
  **OOP boundary law** (see `reference_oop_boundary_law`) as a **curve-traversal
  wall** — the kernel must arc-length-march the seed along a path, the same
  subclass as `chain_pattern`. Permanently deferred OOP.
- **fill_pattern** — Mode-B marks ghost; Mode-A `CreateDefinition(105)` →
  `IFillPatternFeatureData` array setters BIND via the SAFEARRAY doctrine
  (readback 1/1) but `CreateFeature` still ghosts (the `full_round` "binds-but-
  ghosts" class — a missing scalar prop or fixture-geometry question, not a
  marshalling wall). Deferred pending a fresh-doc Mode-A scalar audit; low
  priority (boundary-law-adjacent: fill places instances inside a boundary the
  kernel must solve).

Both are documented in `project_w68_seat_fire_punchlist` (memory) with full
seat evidence.

### W69 equation_curve — NO-API WALL (2026-06-21)

The ribbon audit listed `CreateEquationCurve2` as the COM entry for an
equation-driven sketch curve.  **That method does not exist** — a full grep of
the SW2024 v32.1 DLL export (`docs/sw_api_full.md`, all 17 redist assemblies)
has NO `Create/InsertEquationCurve*` anywhere; the only `Equation` hits are the
read-only `Equation : String` data property, simulation load-case strings, and
event notifiers.  Same class as the audit's confirmed `SendKeys` /
`InsertSplitBody` no-API walls (absent from the DLL, not just the CHM).  There
is no out-of-process path to author an equation-driven curve; **DEFERRED — no
API**.  (Measure-don't-guess catch: the audit guessed a method name; the DLL is
the authority.)  Removed from the W69 materialize batch before any seat burn.

### W71 Part-Feature unknowns sweep — final classification (2026-06-21)

A throwaway classification probe (`spikes/v0_2x/spike_unknowns_probe.py`,
fixture = 40×40×10 block + Ø6 seed hole) fired the three lingering unknowns and
classified each materialize-vs-wall. Results:

- **`scale` — MATERIALIZE (NOT deferred; ready lane).** `IFeatureManager.
  InsertScale(Type, Uniform, X, Y, Z) -> Feature` returns a real `IFeature`;
  uniform 1.5× scaled the body volume 15717 → 53045 mm³ = **×3.375 = 1.5³
  exact**. A closed-form matrix transform — the boundary law predicts
  materialize and it does. Author a lane when the metadata/document axis is
  cleared; the Part-Feature axis is not 100% shipped until it lands.

- **`fill_pattern` — CONFIRMED KERNEL WALL (upgraded from W68 "low-priority").**
  The W68 note (above) deferred the `CreateDefinition(105)`→`IFillPatternFeature
  Data` route as "binds-but-ghosts." W71 fired the OTHER route — the direct
  `IFeatureManager.FeatureFillPattern(19 args) -> Feature` — with a VALID
  2-entity selection (boundary +z face at (15,15,10)mm + `CUT_Seed` feature,
  `GetSelectedObjectCount2 == 2`) and complete params: it returned **`None`,
  ΔVol 0**. BOTH routes wall. Boundary law confirmed: a fill pattern makes the
  kernel solve boundary intersections + internal grid spacing mid-invocation =
  a traversal/solve op = the `ret=None` kernel-deep class (same as curve-driven
  / table pattern / indent / flex). PERMANENTLY DEFERRED — do not re-attempt.

- **`advanced_hole` — DEFERRED (complexity wall, not a clean kernel proof).**
  There is NO `InsertAdvancedHole` (audit guessed; the real method is
  `IFeatureManager.AdvancedHole(near[], far[], UseBaseline, IsCustomCallout, out
  Result) -> Feature`). It needs fully-configured near/far `IAdvancedHole
  ElementData` arrays (13 props each); `CreateAdvancedHoleElementData(ElmType)`
  lives on **`IModelDocExtension`**, NOT `IFeatureManager`. Marshaling footgun:
  a bare Python list for `near` → `com_error -2147352563 DISP_E_ARRAYISLOCKED
  ("Memory is locked")` — the makepy SAFEARRAY doctrine fixes it
  (`VARIANT(VT_ARRAY|VT_DISPATCH, [elem])`). With marshaling fixed but the
  element minimally-configured, `AdvancedHole` returned `(None, None)`. NOT
  claimed a clean kernel wall (the inputs were incomplete) — a HIGH-COST lane
  deferred pending a full near/far element-data spec. Low priority.

Net: the Part-Feature geometric board is now classification-complete — one ready
materialize lane (`scale`) and two walls (`fill_pattern` kernel, `advanced_hole`
complexity). Boundary law corroborated on both sides (closed-form scale
materializes; traversal-solve fill walls).

---

## W72 MBD / DimXpert (Model-Based Definition) — READABLE-WALL-ON-WRITE (2026-06-22)

**DEFERRED — a NEW boundary-law subclass: out-of-process read/manager access is
GREEN, but headless write/auto-dimensioning GHOSTS.** Structural probe
`spikes/v0_2x/spike_mbd_probe.py` (telemetry `_results/mbd_probe.json`, verdict
`READABLE_WALL_ON_WRITE`) classified the entire DimXpert / 3D-annotation axis
against the live seat on a 10×10×10 block.

- **Accessible (GREEN):** `IModelDocExtension.DimXpertManager(Config, CreateSchema)`
  returns a VALID pointer out-of-process — **not** E_NOINTERFACE — and
  auto-creates a schema (`SchemaName` = 'Scheme2'). `IDimXpertManager.DimXpertPart`
  resolves; `GetFeatureCount` / `GetAnnotationCount` read cleanly (0 on a fresh
  schema). Selection model is standard: a raw `IFace2` selected via
  `IEntity.Select2(False, 0)` is accepted — DimXpert does NOT require its own
  `IDimXpertFeature` entity class for selection.
- **Write WALLS (GHOST):** `IDimXpertPart.AutoDimensionScheme(opt)` returns
  **`False`** with ΔFeatures / ΔAnnotations = 0 — **even with** the option fully
  configured (`FeatureFilters = 0xFFFF` = all 16 feature types, `ScopeAllFeature
  = True`, `PartType = Prismatic`, `ToleranceType = PlusMinus`). Manual
  `InsertSizeDimension(GetDimOption())` also returns **`False`** even with a valid
  face pre-selected — because the recognition engine found 0 DimXpert features to
  dimension. Nothing materializes; nothing to persist.
- **Why (boundary law):** DimXpert feature RECOGNITION requires the kernel to
  traverse/solve the B-rep mid-invocation to classify faces into DimXpert
  features. That traversal/solve ghosts headless/out-of-process — the same
  write-side wall class as `split_line`, `fill_pattern`, `indent`, `flex`. The
  signature differs from the classic creation-level `ret=None` ghost only in
  surface form (a clean Boolean `False` + zero delta instead of a null handle).
- **Not Route-C-rescuable:** per the W69 kernel-deep corollary, traversal/solve
  walls ghost identically in-process (zero COM marshaling). An MBD add-in driving
  recognition through the live UI session is the only known path; out of scope.
- **PERMANENTLY DEFERRED** — do not burn lane cycles on 3D annotations / DimXpert
  dimensioning out-of-process. Read/navigation of an existing schema (counts,
  names, annotation enumeration) IS viable OOP if a future read-only "observe MBD"
  need arises.

**Reusable technical artifacts banked from the dig (apply to ANY isolated SW
typelib):**
- `Extension.DimXpertManager` has TWO same-named makepy overloads; the 2-arg
  `(Configuration, CreateSchema)` form wins the generated class dict, so a single
  bool argument lands in the string `Configuration` slot → `Type mismatch`. Call
  it as `DimXpertManager("", True)`.
- `IDimXpertPart` and every `IDimXpert*` sub-object live in the **separate
  `swdimxpert.tlb`**, deliberately NOT makepy-gen'd (the protected SldWorks 32.0
  gen stays untouched). They arrive as late-bound `CDispatch` with
  `GetTypeInfoCount == 0` but a WORKING `GetIDsOfNames`. Drive them gen-free via
  `_oleobj_.InvokeTypes(GetIDsOfNames(name), 0, DISPATCH_METHOD, (ret_vt, 0),
  arg_vts, *args)` — the forced `DISPATCH_METHOD` invkind sidesteps the
  property/method auto-invoke ambiguity that otherwise throws a spurious
  `Member not found`. Do NOT `typed_qi` these objects (the interface isn't in the
  wrapper) and do NOT `()`-call no-arg getters on a `dynamic.Dispatch` (they
  resolve as property-gets returning the value directly).

---

## W75c path mate (swMatePATH) — WALLED out-of-process (GUI-PropertyManager-only, 2026-06-22)

**DEFERRED — no creation route from the COM bridge.** `spike_path_mate_probe.py`
(verdict `WALLED`, telemetry `_results/path_mate_probe.json`) classified the path
mate after the reflect-first sweep found it has **no `IPathMateFeatureData`
interface** in the 32.1 typelib — the only mate type (of 21) lacking a FeatureData
interface, so the declarative `CreateMateData → typed_qi → CreateMate` pipeline
that every shipped mate uses is structurally unavailable. The only legacy route is
selection-driven `IAssemblyDoc.AddMate3`. The probe pre-selected a slider VERTEX +
a base linear EDGE (a valid single-segment path) across 3 mark combinations
{(0,0),(0,1),(1,0)} — **every attempt: selections succeed (`sel_v`/`sel_e` True),
`ErrorStatus == 0`, but `AddMate3` returns NO mate** (silent ghost; `mate=None`,
nothing on reopen). The path mate's pitch/yaw + roll-control parametrization can
only be supplied through its PropertyManager dialog, which is headless-unreachable
— the same GUI-only class as the W36 ray-cast sketch-trim and motion free-DOF drag
walls. PERMANENTLY DEFERRED for the OOP bridge; a future Route-C in-process add-in
is the only conceivable vehicle (and even that must supply the PM-only options).
Sibling `linear_coupler` (swMateLINEARCOUPLER=18) SHIPPED the same wave — it HAS
`ILinearCouplerMateFeatureData` and fit the pipeline cleanly (faithful ratio
round-trip, no gear-style transpose).

---

## Process

Adding to this list:

1. Scope and evaluate the item.
2. Decide it's worth deferring (vs cutting entirely, or doing now).
3. Add a row to the appropriate section above with rationale.
4. If the deferral was triggered by an audit finding, reference the
   audit commit / PR.

Removing from this list:

1. When the item ships, **remove the row** here.
2. Reference the implementing commit in `CHANGELOG.md`.
3. The git history of this file is the audit trail.
