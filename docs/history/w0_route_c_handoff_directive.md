# W0 Architectural Hand-off Directive — Route-C (W67 Track-2) In-Process Thicken

**Status:** READ-ONLY ruling from the overwatch session.
**Date:** 2026-06-20
**Author:** W0 (architectural overwatch)
**Audience:** the concurrent session owning Route-C / in-process `FeatureBossThicken`

> No edits were made to any `spikes/v0_2x/route_c/*` file or `spike_route_c_thicken.py`.
> Those are your live, **untracked** WIP and were left untouched to preserve worktree
> isolation. This note is analysis only.

---

## 1. Diagnosis — you are not going crazy; the *vehicle* is walled

Your last fired result (`spikes/v0_2x/_results/route_c_thicken.json`) reads:

- `RunMacro2(dll, "SolidWorksMacro", "Main", 0)` -> `ran=true, error_code=0 (NoError)`
- `sentinel: {}` (empty)
- `verdict: MAIN_NOT_RUN`

`Main()` writes `%TEMP%\route_c_sentinel.txt` as its **first** statement, before it ever
touches `swApp`. An empty sentinel therefore proves `Main()` never entered — even though
RunMacro2 reported NoError.

**Ruling:** the SOLIDWORKS VSTA macro host is silently swallowing your
`csc /target:library`-compiled class library. It accepts the path, returns NoError, but
never instantiates the `SolidWorksMacro` type nor invokes `Main()`. A hand-rolled `csc`
DLL lacks the VSTA hosting scaffold and assembly/COM attributes the macro engine binds
against. This is a documented-class **accept-then-no-op** wall — the same silent-refusal
signature we mapped on the out-of-process ghost features in W65/W66. It is not a bug in
your code, and rebuilding the bare DLL with fresh timestamps will keep returning the same
NoError / empty-sentinel pair.

**Corollary:** the W66 thicken feasibility question — *does in-process execution break the
surface->solid wall?* — is **STILL UNANSWERED.** You never reached in-process. Do **not**
read `MAIN_NOT_RUN` as `GHOST_IN_PROCESS`; the kernel was never exercised.

## 2. Directive — abandon the `RunMacro2` + hand-compiled-DLL vehicle

Stop iterating the `csc` + `RunMacro2` loop. The loader contract cannot be satisfied by an
arbitrary assembly. Switch the **in-process delivery vehicle**.

## 3. Allowed paths (priority order)

### Primary — minimal `ISwAddin` COM add-in  **[RECOMMENDED]**
- Implement `SolidWorks.Interop.swpublished.ISwAddin`. `ConnectToSW(object ThisSW, int Cookie)`
  hands you the **live, in-process `ISldWorks`** directly — there is no out-of-process
  marshaling boundary at all. This is the canonical guaranteed-in-process path.
- Register via `regasm` (admin) + the add-in registry keys (`HKLM\SOFTWARE\SolidWorks\Addins\{GUID}`
  plus the per-user `AddInsStartup` enable flag). **Exact keys are already filed** —
  reference `docs/addins_research.md` and `docs/why_no_addim2.md`.
- Trade-off: admin + COM registration ceremony. Worth it — it removes the marshaling
  boundary entirely, which is the entire point of Route-C.

### Secondary — a GENUINE VSTA macro (UI-generated)
- If you must stay on the macro vehicle: generate the VSTA project from **within** the
  SOLIDWORKS UI (Tools -> Macro -> New -> VSTA C#). SW emits the correct hidden assembly
  attributes and the partial `SolidWorksMacro` hosting scaffold the macro engine knows how
  to instantiate.
- Build **that generated project's** DLL (do not hand-roll `csc`), then fire it via
  `RunMacro2`. Strictly inferior to the add-in (still macro-host-mediated), but it will at
  least get `Main()` to run in-process.

## 4. What you KEEP (do not rewrite — the vehicle is the *only* walled piece)

- **Feedback channel** (`route_c_sentinel.txt`): vehicle-agnostic, survives a null-app
  early bail. Correct design — keep it.
- **The 7-way verdict ladder** in `spike_route_c_thicken.py`
  (`ROUTE_C_PROVEN` / `GHOST_IN_PROCESS` / `MACRO_EXCEPTION` / `NO_APP_IN_PROC` /
  `MAIN_NOT_RUN` / `VEHICLE_FAILED` / `ERROR`): it already separates vehicle failure from
  kernel verdict. Keep it; just point it at the new vehicle.
- **The thicken payload**: `fm.FeatureBossThicken(0.002, 0, 0, false, false, false, true)`
  — the verbatim W66 OOP-ghosting 7-arg shape (Thickness=2mm, Dir=side1, FaceIdx=0,
  FillVolume=false, Merge=false, UseFeatScope=false, UseAutoSelect=true). That is exactly
  what must be re-fired in-process.

## 5. Vehicle-first validation gate (cheap — do this before re-judging thicken)

Prove the vehicle delivers a live in-process app **before** trusting any thicken verdict:

1. Confirm the sentinel appears **non-empty** with `MAIN_ENTERED=1`.
2. Confirm `SWAPP_NULL=False` (a live in-process `ISldWorks`).
3. **Only then** is the thicken verdict (`ROUTE_C_PROVEN` vs `GHOST_IN_PROCESS`) meaningful.

If the sentinel is non-empty but `SWAPP_NULL=True`, the vehicle ran but injection failed
(`NO_APP_IN_PROC`) — fix injection before reading the thicken result.

---

**Overwatch session scope ends here.** No Route-C files were modified. Track-2 in-process
execution is yours.
