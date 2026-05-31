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
| **L4 multi-part storage** — per-part `.sqlite` vs shared per-project DB | 2026-05-23 | Premature without assembly support. Decide when multi-part assemblies actually ship. |

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
| **Edge Flange — pending profile-sketch automation** | The out-of-process COM boundary is **fully cracked and characterized** (`spikes/v0_16/spike_edgeflange.py`, seat-run SW2024 SP1); only a geometric sub-task remains. **(1) COM marshaling solution:** the legacy `IFeatureManager.InsertSheetMetalEdgeFlange2` (13 args) rejects bare Python `None`/`pythoncom.Missing` on its trailing `IDispatch` args (`SketchFeats` arg 2, `CustomBendAllowance` arg 13) with "Type mismatch"; passing **`win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)`** for each clears every mismatch and the call executes cleanly (reusable pattern for any pedantic legacy SW signature out-of-process). The modern `CreateDefinition(37)→typed_qi(IEdgeFlangeFeatureData)→AddEdges` path is a **dead end** out-of-process: `AddEdges` accepts the edge array/dispatch but `GetEdgeCount` stays 0 (the IDispatch pointer is not unwrapped server-side). **(2) Valid `BooleanOptions` mask = `129`** (`swInsertEdgeFlangeUseDefaultRadius=1 | swInsertEdgeFlangeUseDefaultRelief=128`) — forces document defaults so the manual bend/relief args are ignored. **(3) Edge filtering:** pass the **longest linear boundary edge** (typed `IEdge→ICurve`, `IsLine()` + `GetLength`); the 2mm thickness edges are a guaranteed topological rejection. **Remaining blocker (deferred):** with `SketchFeats` nulled, the solver has no profile to define the flange wall length/shape (there is no flange-length scalar in the signature), so it correctly returns a silent `None`. Materializing requires constructing a profile sketch on a plane normal to the chosen edge and passing the `ISketch` — a dedicated geometry-automation epic (normal-to-edge ref plane → sketch the flange-height line → pair edge↔sketch 1:1 per `swEdgeFlangeError_NumberOfEdgesAndSketchesNotEqual`), not a tacked-on script. First raised 2026-05-31, Wave-4 closure. |
| **Miter Flange** | No `IMiterFlangeFeatureData` in the SW2024 typelib (no `CreateDefinition` path); legacy `InsertSheetMetalMiterFlange` walls. Deferred during W2-seat (2026-05-31). |

## v0.13+ backlog (no committed dates)

Future capability lanes — each is a multi-week project with its own
design phase, NOT a "we forgot to do this" item.

| Item | Status |
|---|---|
| **Configuration support** — build same spec against multiple `.ai-sw-bridge.toml` profiles, diff resulting B-rep manifests | Backlog |
| **Assembly + mate primitives** — extend declarative JSON contract to multi-part assemblies | Backlog |
| **Drawing generation** — 2D drawing sheets from 3D part/assembly specs | Backlog |
| **Sheet metal primitives** — bend tables, flat patterns, gauge tables | Backlog |

## Indefinitely deferred (by design)

| Item | Reason |
|---|---|
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
