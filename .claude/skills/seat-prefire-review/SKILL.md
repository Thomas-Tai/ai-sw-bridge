---
name: seat-prefire-review
description: >
  W0 pre-seat diligence review. Run BEFORE firing the singleton SOLIDWORKS seat
  on any handback spike or feature_add handler (W55-style lanes), or before
  merging any COM-touching change. Five project-specific adversarial reviewers
  gate the code against this codebase's known failure modes — invariants,
  COM footguns, verify-the-EFFECT, O1 introspection, and architecture/layers.
  A cheaper UPSTREAM filter; it does NOT replace the live seat fire.
---

# Seat Pre-Fire Review (W0 diligence gate)

## The one hard rule

**This review is a cheap upstream filter, NOT seat-validation.** The deepest
lesson of this codebase is that *code review cannot catch a COM ghost* —
`ok=True`, a clean `GetErrorCode2`, and a feature-count delta all **lie**
(edge_flange W42, draft W44). Only the live seat, asserting a geometric effect
that survives save→reopen, proves a feature. This gate exists to stop you
**wasting a seat fire** on code that a grep could have shown was doomed
(a `CloseDoc` channel-corruptor, a guessed signature, a missing effect
assertion). It earns its keep by being run *before* the irreplaceable fire.

When in doubt, a reviewer **defaults to RED** (block). A false BLOCK costs a
re-review; a false PASS costs a seat fire on the singleton seat.

## How to run it

Run the five reviewers as **independent instances** (separate agent contexts, so
blind spots don't correlate). For a thorough gate, spawn them in parallel and
collect verdicts; for a quick check, walk them inline in order. Each reviewer
emits `GREEN` / `AMBER` / `RED` per check, with file:line evidence.

**Gate logic — gate on checkable facts, never a holistic score:**
- **Any `RED` from any reviewer → BLOCK.** Do not fire the seat. Hand back with the evidence.
- **Any `AMBER` (reviewer can't prove it safe) → BLOCK pending W0 judgment.** Treat uncertainty as failure.
- **All `GREEN` → CLEARED to fire.** The seat fire is still the real verdict.

Do not average reviewers into a number. "8/10" is itself a self-report, and this
project distrusts self-reports. A single proven footgun sinks the handback.

---

## Reviewer 1 — Invariant Auditor

**Mandate:** the four load-bearing invariants are non-negotiable. Invariant #3
(zero arbitrary code execution) is the security model; a breach is an automatic
RED and an escalation, not a finding.

Checks (grep-backed):
- `grep -nE '\b(eval|exec)\s*\(|subprocess|shell\s*=\s*True|os\.system|run_macro|RunMacro2?\b'` → any hit in a new code path = **RED** (invariant #3). VBA emit-and-run / macro execution is REJECTED doctrine.
- Declarative-JSON-only: the spec is data, not code. No code strings interpreted as behaviour. **RED** if a spec field is `eval`'d or dispatched as code.
- Propose→approve→execute preserved: mutations still route through the PAE gate; no `--yolo` / auto-commit path added. **RED** if a mutation bypasses propose.
- Out-of-process: the agent/spec never touches COM directly; COM lives behind the executor. **AMBER** if a new module imports `win32com`/`pythoncom` outside the `com/` boundary without justification.

PASS = all four GREEN. This reviewer's RED also triggers `[[feedback_pause_on_errors]]`.

## Reviewer 2 — COM-Footgun Auditor

**Mandate:** the out-of-process pywin32 channel is fragile and makepy lies in
specific, catalogued ways. This reviewer carries the scar tissue.

Catalogue (each is a known, reproduced failure — grep for the anti-pattern):
- **Channel corruptor:** `grep -nE '\.CloseDoc(Doc)?\s*\('` → mid-session `CloseDoc`/`CloseDocSilent` = **RED**. Cleanup must be `CloseAllDocuments(True)` in a `finally`. (`[[reference_close_corrupts_com]]`; next `OpenDoc6` faults.) Also flag >10–12 doc-opens/session without a restart.
- **FUNCDESC on a live dispatch:** `grep -nE '\.GetTypeInfo\(|elemdescFunc|GetFuncDesc'` applied to a *live SW dispatch* = **RED**. SW `IDispatch` exposes no type-info (`GetTypeInfo`→`DISP_E_BADINDEX`); introspect by loading the `.tlb` directly (as `spike_rib.py` does for `swconst.tlb`).
- **makepy arg-mistype:** typed calls passing arrays/`[out]` params where makepy assigned the wrong VT → silent no-op or Type-mismatch. `[[reference_makepy_wrong_argtype]]`. Expect a raw `InvokeTypes` bypass with the correct VT; **AMBER** if a SAFEARRAY/[out] arg is passed through a typed proxy without one.
- **typed OpenDoc6 tuple-unpack:** a *typed* `ISldWorks.OpenDoc6` returns `(doc, *out)`; reading the doc directly drops it. Require `ret[0] if isinstance(ret, tuple) else ret`. A *dynamic* dispatch returns the doc directly (no unpack). **RED** if a typed OpenDoc6 result is used without the guard; **GREEN** if the dispatch is dynamic (`dynamic.Dispatch`).
- **GetSaveFlag typed-proxy:** `bool(typed.GetSaveFlag)` is always-True — it's a METHOD, call it. `[[reference_getsaveflag_typed_method]]`.
- **makepy method traps:** `Get6`/`Save3` raise; use `Add3`/`Get4`/`SaveAs3`. Method-vs-property surprises (`GetActiveSketch2` method, `GetSketchSegments` property; `SelectByID2` on `IModelDocExtension` not `IModelDoc2`). **AMBER** on any of these without a seat-proven precedent.
- **Result-dict COM leak:** a raw COM dispatch stored in a results dict then JSON-serialized after the doc closes → `str()`→Invoke→"Object is not connected to server". **RED** if a dispatch is stored for later serialization; extract a scalar/repr at capture time.

PASS = no RED, no unresolved AMBER.

## Reviewer 3 — Verify-the-EFFECT Auditor

**Mandate:** the W21 ghost trap. A feature is real only if it changes the B-rep
*and the change survives a save→reopen*.

Checks:
- The spike/handler asserts a **geometric effect** — ΔVolume, ΔFace count, ΔBody count, or Δannotation-count — measured before vs after. **RED** if the only success signal is `ok=True`, a non-None return, `GetErrorCode2==(0,False)`, or "no exception."
- **Feature-count delta alone is NOT sufficient** for in-place modifiers (draft, dome) — a node can exist with zero geometry (the edge_flange ghost). Prefer ΔVolume; if count is used, justify why a ghost node is impossible for this kind.
- **Save→reopen survival** is asserted (re-measure after `CloseAllDocuments(True)` + reopen). **AMBER** if persistence is unchecked (acceptable for ref-geometry which has no B-rep; **RED** for any solid feature).
- The effect magnitude is **discriminating** (e.g., a known cube's expected Δ), not just "nonzero by luck."

PASS = a real, discriminating, persistence-checked effect assertion exists.

## Reviewer 4 — O1 Auditor

**Mandate:** introspect FIRST, never guess. Guessed COM names silently no-op,
raise, or don't exist. The seat caught a guessed signature/enum/interface in
**5/5** non-wall lanes of W53 — this rule is load-bearing.

Checks:
- Every COM **method arg-count**, **enum value**, and **interface/IID** used traces to a typelib introspection source (a FUNCDESC dump from the `.tlb`, an enum dump from `swconst.tlb`, or a documented seat-proven precedent). **RED** for any magic arg-count or enum literal with no introspection trail.
- Enum tokens are the *real* ones, not plausible guesses (`sgSAMELENGTH` not `sgEQUAL`; gear=10 not 12; `swCustomInfoDouble=5` not 31/32/33). **RED** on an unverified token.
- Do **not** regenerate makepy as a "fix" — staleness was FALSIFIED; missing members are guessed names. **RED** on a `makepy`/`EnsureDispatch`-regen step.

PASS = no un-sourced signature/enum/interface.

## Reviewer 5 — Architecture / Layer Auditor

**Mandate:** containment baseline (the 2026-06-11 consolidation policy) and
hot-file parallel-safety.

Checks:
- A **new** feature_add kind uses the `features/HANDLER_REGISTRY` seam (own module + one registry line), NOT a new handler crammed into `mutate.py`. **AMBER** if it edits `mutate.py` for a new kind. (Fixes to *existing* handlers in `mutate.py` are fine — their tests monkeypatch its namespace.)
- import-linter **layers respected** (the CI `lint-imports` contract): `mutate>config>spec`, `brep>com`, COM stays behind `com/`. **RED** on a layer violation.
- **Hot-file discipline:** the lane's edits are disjoint from other in-flight lanes (no shared-file collision); parallel sessions use real per-session worktrees. `[[feedback_parallel_worktree_isolation]]`.
- **Attribution & commits:** ported code carries docstring + CONTRIBUTING attribution (`[[feedback_port_attribution]]`); **no `Co-Authored-By` trailers** (CONTRIBUTING.md:62, `[[feedback_no_co_author_trailers]]`).

PASS = registry seam used (or existing-handler fix), layers clean, hot-files disjoint.

---

## Output format

Emit one verdict block the orchestrator / W0 can act on:

```
SEAT PRE-FIRE REVIEW — <lane / file>
  R1 Invariant     : GREEN | AMBER | RED   <evidence file:line>
  R2 COM-Footgun    : GREEN | AMBER | RED   <evidence>
  R3 Verify-Effect  : GREEN | AMBER | RED   <evidence>
  R4 O1             : GREEN | AMBER | RED   <evidence>
  R5 Architecture   : GREEN | AMBER | RED   <evidence>
  GATE: CLEARED TO FIRE  |  BLOCKED (reasons)
```

A `BLOCKED` verdict hands back with the specific anti-pattern + the fix, exactly
as W0 did across the four W55 handbacks (CloseDoc→CloseAllDocuments, the
throwaway-dict, the FUNCDESC un-gate, the defensive serializer). `CLEARED TO
FIRE` means the cheap filter passed — now spend the seat and let the EFFECT
decide.

See `docs/central_idea/BACKLOG_BURNDOWN.md` for which reviewers each backlog
lane must pass before W0 fires.
