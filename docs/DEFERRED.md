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
| **L5 — C# in-process adapter via PythonNET** | Decisions.md ratified the indefinite deferral 2026-05-23. The VBA-emit-and-run alternative (`SolidworksMCP-python/vba_adapter.py`) likely collapses L5 entirely. Re-evaluate only if pywin32 stability degrades meaningfully against the (still-undefined) trigger telemetry above. |
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
