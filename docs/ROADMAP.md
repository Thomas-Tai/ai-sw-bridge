# Roadmap

Public commitment to where `ai-sw-bridge` is going. For shipped-state
history see [`CHANGELOG.md`](../CHANGELOG.md); for v0.14+ backlog and
deferred items see [`DEFERRED.md`](DEFERRED.md).

---

## v0.14 — Shipped (2026-05-29)

Commercial-hardening release. Full-codebase audit, four shipped
correctness bugs fixed, one broken-by-design legacy function
removed, doc parity across README / USAGE / AGENTS, and class-based
facades (`SolidWorksObserver`, `ProposalStore`) over the observe
and mutate modules.

- **Correctness:** parametric / `--deferred-dim` builds no longer
  apply each equation binding twice; `ai_sw_bridge.__version__`
  now reads from installed metadata; MCP contract test asserts the
  four real mutate names (not the fictional `sw_mutate_apply`).
- **Doc parity:** primitive count (16, not 12), example count (15,
  not 12), full `ai-sw-build` flag inventory, env-var matrix.
- **Class API:** `SolidWorksObserver` and `ProposalStore` ship as
  the recommended entry points; the legacy `sw_*` free functions
  remain as backward-compatible shims through v0.14 and are slated
  for removal in v0.15 (D-v0.14-06 in DEFERRED.md).
- **Removed (BREAKING):** `ai-sw-mutate run_macro` subcommand +
  `mutate.sw_run_macro` Python function. Migration: see the v0.14 entry in
  [`CHANGELOG.md`](../CHANGELOG.md).

Full details: [`CHANGELOG.md`](../CHANGELOG.md) v0.14.0.

---

## v0.11 — Shipped (2026-05-27)

Reliability, observability, and supply-chain hardening. Fifteen parallel
lanes merged after a six-phase audit.

- **L1 foundation:** feature-flag module, fault-injection harness, late-bound
  pywin32 reconnect-on-stale-handle.
- **L2 foundation:** circuit breaker (ported from SolidworksMCP-python),
  anti-loop retry guard with canonical spec hashing.
- **Observability:** SLI instrumentation with p50/p95/p99 regression gate,
  local SQLite telemetry (seven counters, one histogram, trace-id propagation).
- **Supply chain:** license-compliance lint, upstream drift monitor,
  privacy review, supply-chain security policy.

Full details: [`CHANGELOG.md`](../CHANGELOG.md) v0.11.0.

---

## v0.12 — In progress

Four capability lanes plus carryover fixes. Target: close the load-bearing
gaps an LLM hits when operating the bridge in closed-loop refinement.

### L1 — B-rep interrogation

After each feature handler returns, interrogate the resulting `IFace2` set
to produce a topological fingerprint (per-face bounding box, surface normal,
centroid) the LLM can reason about. Gated by `--enable-flag brep_interrogation`.

- Live-SW marshal spike (E2.1) — confirm SAFEARRAY shapes for `GetBox`,
  `Normal`, `GetSelectByIDString`.
- `brep/interrogator.py` — per-face extraction with multi-body and
  surface-body support.
- `brep/fingerprint.py` — quantized normal + centroid hash, calibrated
  against rebuild noise.
- `brep/manifest.py` — per-feature B-rep block serialization.
- `brep/resolver.py` — symbolic `face_role` resolution at validate time.
- Builder integration — `build_brep.json` sidecar alongside `build_metrics.json`.

### L2 — Envelope closure

Ship the structured error envelope the LLM retries against. Without this,
the auto-retry is brakes-without-steering-wheel.

- `errors/build_error.py` — `BuildError` dataclass with Tier A/B/C
  classification, HRESULT, hint key, trace ID.
- `errors/wrapper.py` — `@com_error_boundary` decorator at every COM call
  site in `spec/builder.py`.
- `errors/hints.py` — 9-item hint catalog (face-not-found, sketch-under-constrained,
  end-condition-mismatch, etc.) with multi-key resolution.
- `errors/auto_retry.py` — hint-aware retry guard: allow retry only when
  the spec materially differs or the hint key changed.

### L3 — API RAG (deferred until L1 + L2 land)

Retrieval-augmented generation over the CHM corpus. Matters most when the
LLM is *adding* a new primitive; deferred until the hallucination data is
empirical rather than preemptive.

- `tools/chm_extract.py` extension for `sldworksapiprogguide.chm`.
- `rag/corpus.py` + `rag/chunk.py` — normalized document model with
  paragraph-based chunking and table-boundary preservation.
- `rag/embed.py` + `rag/index.py` — sentence-transformers embeddings
  with sqlite-vec backend; model mirrored to repo-local storage.
- `tools/build_api_index.py` — canonical index committed as a determinism
  gate in CI.
- `cli/apidoc.py` — five subcommands (`search`, `detail`, `members`,
  `examples`, `enum`) behind `@cli_stability(Tier.EXPERIMENTAL)`.

### L4 — SQLite checkpoints

Per-feature snapshot and rollback. Gives the LLM "undo" — try-rollback-retry
compounds with L1 (rollback to before the topology you broke) and L2
(rollback when a hint says the prior feature poisoned a downstream face).
Gated by `--checkpoint`.

- `checkpoint/store.py` — SQLite schema with per-feature snapshot rows.
- `checkpoint/snapshot.py` + `rollback.py` + `history.py` — lifecycle,
  tree-hash rollback, query API.
- `checkpoint/gc.py` — configurable retention policy (count, age, size cap).
- `cli/history.py` — three subcommands (`part`, `locals`, `since`).

### Carryover (E4)

- **E4.1** — argparse migration for `tools/bundle_bug_report.py` and
  `tools/export_metrics.py` (v0.11 `--help` silently consumed as positional).
- **E4.2** — SolidworksMCP-python pin bump (51 commits of drift; threshold 50).

---

## Post-v0.12 — Forward look

No committed dates. These are directional signals; scope may shift based
on adoption data from v0.12.

### v0.13+ backlog

- **Lane M — MCP wrapper.** Adoption-driven. Re-evaluation triggers
  documented in `requirements.md` US-12. Useful for shell-less clients
  but not essential since the existing CLI surface already supports the
  full AI-SW loop. Framework choice (FastMCP / Anthropic SDK / custom
  stdio) deferred until the lane opens.
- **Configuration support — parametric variants.** Build the same spec
  against multiple `.ai-sw-bridge.toml` profiles; diff the resulting
  B-rep manifests.
- **Assembly + mate primitives.** Extend the declarative JSON contract to
  multi-part assemblies with mate constraints.
- **Drawing generation.** 2D drawing sheets from 3D part/assembly specs.
- **Sheet metal primitives.** Bend tables, flat patterns, gauge tables.
- **`_face_frame` side faces on flipped / non-rectangular parents.**
  *Standard orientations SHIPPED (v1.7+):* `spec/_face_geometry.py::_face_frame`
  resolves the `±x`/`±y` side faces of Front (`+z`), Top (`+y`), and Right
  (`+x`) parents for BOTH fillet/chamfer edge selection (`of_face` /
  `between_faces`) AND sketch-on-face (`sketch_*_on_face`, `simple_hole`) — the
  sketch frame is SW's own, read off `ISketch.ModelToSketchTransform` and
  seat-proven (`spike_face_frame_axes_pae.py`, `spike_sketch_on_side_face_pae.py`).
  *Remaining:* flipped (`-y`/`-x`) axis orientations keep `uv_calibrated=False`
  (edges work, sketch-on-face refused) until their frames are measured, and
  non-rectangular profile extents are still unaddressable. See
  `known_limitations.md` §2.
- **L5 — C# in-process adapter.** Stays deferred indefinitely. The
  VBA-emit-and-run alternative likely collapses it; re-evaluate after
  L1 produces stability telemetry.

### Re-evaluation triggers

- External demand for Lane M (two or more independent integrators).
- v0.12 B-rep fingerprint stability data informing L5 cost/benefit.
- Adoption metrics from the API RAG index (precision@1 trends).

---

## Principles

These do not change between versions:

1. **Propose, approve, execute** on every mutation.
2. **Declarative JSON specs** are the source of truth.
3. **Zero arbitrary code execution** — no eval, no exec, no
   `subprocess(shell=True)`, no dynamic import of user-supplied paths.
4. **Late-bound pywin32 only** — out-of-process marshaling is the
   load-bearing assumption.
