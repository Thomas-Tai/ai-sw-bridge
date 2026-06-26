# Codebase Audit — Commercial-Standard Review

> **Date:** 2026-06-26 · **Release under review:** v1.6.0 · **Branch:** `feat/w67-phase3`
> **Scope:** duplication / class consolidation · feature-handler mode selection ·
> redundancy & dead code · README completeness · commercial-standard posture.
> **Method:** static read of `src/ai_sw_bridge` (214 modules), the registry, the
> import-linter contract, the test layout, and the published surface. No behavior
> was changed except the one README completeness fix noted in §5.

---

## Verdict at a glance

| Dimension | Verdict | Note |
|---|---|---|
| Architecture / class design | **Strong** | One stateful client + 5 facades + registry; a *completed* strangler-fig refactor |
| Duplicate functions | **Already consolidated** | `verify.py` is the single source; lane "copies" are intentional test-seam shims |
| Mode selection (A/B) | **Correct** | Per-lane, seat-proven, fail-loud `_register_lane` gate |
| Redundancy / dead code | **Low** | Dormant handlers are intentional provenance, not dead code |
| README completeness | **Strong (one gap closed)** | Added the 36 feature-kind enumeration this pass |
| Commercial standard | **Meets bar** | SemVer contract, tiers, CI gates, telemetry-privacy; gaps are legal (Gate 4), not code |

**Bottom line:** the codebase already embodies the consolidation the request asks
for. The "merge duplicates into classes" work was largely done across the v1.0
strangler-fig cuts and the W67 verify-substrate unification. The remaining apparent
duplication is *load-bearing* (test seams) and must **not** be naively merged.

---

## 1. Duplication & class consolidation

### What I found
- **`features/verify.py` is the unified verify substrate** (W67). Its own docstring
  records the history: "Before W67, every feature handler hand-copied its own
  `_solid_bodies` / `_metrics` / `_sheet_bodies` / `_count_feature_nodes` …
  (28 defs across 13 modules). This module is the single source."
- A cross-module scan for repeated function names surfaced two distinct classes:
  - **Convention, not duplication:** `main`/`_build_parser` (one per CLI, ×17–22),
    `register` (one per MCP tool, ×10), `_apply`/`_validate`/`_verify`/`_try_mode_a`/
    `_try_mode_b` (the per-lane handler contract). These *should* repeat.
  - **Thin delegating shims:** `_curve_length_mm` (×5), `_count_feature_nodes` (×6),
    `_solid_body_count`/`_sheet_body_count`/`_total_sheet_area_mm2` (×3 each). Every
    one is a 1–3 line wrapper whose body is `return verify.<fn>(…)`, with a docstring
    that literally says "Delegates to the W67 verify substrate."

### Why the shims exist (and must stay)
The `features/__init__.py` lane protocol mandates that **each lane's offline tests
monkeypatch COM seams on the lane module's own namespace** (e.g.
`monkeypatch.setattr(features.helix, "typed_qi", …)`). A lane-local shim is the
patch point. Collapsing them into direct `verify.*` calls would break that test
contract for the whole feature suite — the exact trap the strangler-fig work
documented. **Recommendation: leave them.** This is correct engineering, not debt.

### The `_impl`-cores question
The free-function `_sw_*_impl` cores in `observe*.py` / `mutate.py` are also
module-level by design (same monkeypatch contract). They are already *exposed
through* classes (the facades). Bodily merging them **into** facade classes would
break the tests and re-introduce the v0.18 god-object the architecture deliberately
avoided. The class-ification the request asks for is the facade layer, and it
already exists.

### Genuine (minor, optional) micro-duplication
- `SolidWorksObserverFacade` repeats the doc-resolution guard 14× (`doc = doc if
  doc is not None else self._client.active_doc(); if doc is None: return _NO_DOC`).
  Idiomatic and explicit; a helper/decorator would add indirection. **Optional**,
  low value — recommend leaving unless it grows.
- `SolidWorksMutatorFacade.batch()` repeats the bare-engine fallback call 3×. A
  one-line local closure would DRY it. **Safe** but cosmetic. Recommend as an
  opt-in cleanup, not a release blocker.

> These align with the **ratified consolidation policy** (`project_consolidation_policy`):
> friction-triggered seams, not big-bang reconstruction. Neither rises to a friction seam yet.

---

## 2. Feature-handler mode selection (Mode-A / Mode-B)

**Verdict: correct, and not a thing that can drift silently.**

- Mode is chosen **per lane, empirically, from a live seat-proof**, and documented
  inline in `features/__init__.py` against the **OOP boundary law**
  (`reference_oop_boundary_law`): Mode-A (`CreateDefinition → typed_qi → CreateFeature`)
  when the kernel is handed positions directly; Mode-B (legacy `Insert*`) when no
  creation enum exists or Mode-A is quarantined on this SW build.
- The single registration path `_register_lane(kind, handler, status)` enforces the
  invariant: **GREEN registers, dormant sentinels skip, a malformed status raises**.
  A forgotten flip or typo'd sentinel fails loud rather than advertising an unproven
  handler. Verified: `len(HANDLER_REGISTRY) == 36`.
- The verify substrate ties each mode's *effect* to a class gate, so a mode that
  silently no-ops (the classic OOP wall) fails its gate rather than reporting a ghost
  success. This is the strongest part of the design.

No defect found. The only "mode" risk is a future SW version changing which enums
`CreateDefinition` accepts — which the per-lane seat-proof + gate would catch on the
next fire.

---

## 3. Redundancy / dead code

**Verdict: low redundancy; the apparent dead code is intentional.**

- **Dormant handlers** (`combine`, `split`, `loft`, `rib`, `wrap`, `boundary_boss`,
  `edge_flange`, `move_body`, `copy_body`, `thicken`) are imported and routed through
  `_register_lane` but **not advertised**. They are kept deliberately for (a) wall
  provenance and (b) fail-loud propose behavior, mirroring the documented
  combine/split precedent. This is not dead code — removing it would let `propose`
  silently accept a kind that has no working path.
- **Legacy `sw_*` shims** are retained intentionally for back-compat with a
  `PendingDeprecationWarning`. Candidate for removal at the next major (v2.0), not now.
- No orphaned modules detected in the facade/registry/verify graph; every `features/*`
  lane is wired through `__init__.py`.

**Recommendation:** add a `vulture`/coverage-driven dead-code sweep to CI if you want
a continuous guarantee, but nothing actionable was found by inspection.

---

## 4. Commercial-standard posture

| Area | State |
|---|---|
| Versioning | SemVer; `PUBLIC_API.md` is the stability contract; MIT (≤v1.4.0) → commercial (v1.5.0+) boundary documented |
| API surface | One public class (`SolidWorksClient`); `sw_*` shims deprecated; 44 `sw_*` purge already done (v1.0.0-rc1) |
| Stability tiers | Per-command `stable`/`experimental`/`deprecated`, enforced by `tests/test_cli_stability.py` |
| CI gates | `black --check .`, `flake8 src/`, `mypy src/`, import-linter (0 broken), `pytest --cov-fail-under=60` (currently 65.28%, 3750 tests) |
| Safety model | Propose→Approve→Execute everywhere; no autonomous MCP write (both write tools elicitation-gated, Option 3); destructive ops PID-bind-checked |
| Resilience | Supervised-by-default batch (RES-1), **live-proven 2026-06-26**; durable transaction ledger |
| Telemetry privacy | Key never logged (sha256[:16] fingerprint only); aggregate bounded-enum labels |
| **Gaps** | **Legal, not code** — EULA/CLA are counsel-review templates (Gate 4); EULA lacks a telemetry/privacy clause despite the `telemetry/` module, liability carve-outs, and IP indemnification (see the human-gates Gate-4 self-review) |

The remaining commercial gaps are the **legal** ones tracked under Gate 4 — they are
not engineering defects.

---

## 5. README completeness for a fresh user

**Verdict: strong; one real gap, closed this pass.**

The README already gives a fresh user: a 5-minute quickstart, a 21-command table
with stability tiers + read-only flags, environment variables, full MCP server setup,
the 37-tool inventory grouped by category, an explicit "deliberately NOT exposed via
MCP" list, limitations, project status, and layout.

**Gap found:** nothing user-facing enumerated the **36 `feature_add` kinds** the
`ai-sw-build` / batch / `client.features` surface can actually create — a fresh user
had to call `client.features.list_kinds()` to discover them. **Fixed** by adding a
"Feature kinds you can build" subsection to the README (the 36 kinds, grouped), with
a pointer to `client.features.list_kinds()` as the runtime source of truth and
`docs/DEFERRED.md` for the walled kinds.

---

## 6. Recommendations (prioritized)

1. **Ship as-is on the code dimensions.** No duplication/mode/redundancy defect
   blocks commercial release. (Done: README kind-list gap closed.)
2. **Legal (Gate 4):** add a telemetry/privacy clause, liability carve-outs, and an
   IP-indemnification position to the EULA; add an employer/work-for-hire clause to
   the CLA. Counsel-owned.
3. **Optional cleanups (next friction seam, not now):** DRY the `batch()` bare-engine
   fallback (3×) into a local closure; consider a `_resolve_doc` helper if the
   observer facade's doc-guard grows. Both are cosmetic.
4. **Optional CI hardening:** add a `vulture` dead-code pass and keep the coverage
   floor climbing from 65%.
5. **At v2.0:** retire the `sw_*` `PendingDeprecationWarning` shims.

See [`CLASS_RELATION_MAP.md`](CLASS_RELATION_MAP.md) for the structural companion to
this audit.
