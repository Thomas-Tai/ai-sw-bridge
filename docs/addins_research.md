# `--disable-addins` — Research note (W7.1)

**Status:** Research complete; implementation deferred to W7.1-code
(Sonnet/GLM).
**Authors:** v0.13 closure track.
**Empirical claims:** every load-bearing claim below carries a
**VERIFY** tag and a one-line spike script that confirms it on a live
SW session. The reader **must not** treat unmarked claims as
verified — many are drawn from API documentation and prior automation
knowledge, not from this codebase's spike record.

## 1. Why this matters

The bridge's deterministic-execution promise (`CODESTYLE.md` §2.4,
`spec.md` §3.1) is undermined by SW add-ins that subscribe to model
events. An add-in that hooks `AfterSaveNotify` can rewrite custom
properties post-save; one that hooks `FileNewNotify` can modify the
template; SOLIDWORKS Toolbox modifies dimension chains as a feature
of its purpose. None of these are bugs in the add-ins — they are
the contract those add-ins ship.

When a build that worked yesterday fails today, and the only thing
that changed is "I enabled Routing add-in to lay out wiring," we
need a flag that either:

1. Disables the interfering add-ins for the bridge's invocation, **or**
2. Warns clearly when interfering add-ins are loaded so the user
   knows which knob to turn.

This document concludes that **(2) is the achievable goal**, and that
"disable add-ins at runtime via COM API" is largely a myth.

## 2. SW add-in lifecycle (background)

SW add-ins are out-of-process COM servers (or in-process for some
older `.dll` add-ins) registered under Windows registry keys:

```
HKEY_LOCAL_MACHINE\SOFTWARE\SolidWorks\AddIns\{CLSID}\
   → metadata: name, path, default load state
HKEY_CURRENT_USER\Software\SolidWorks\AddinsStartup\{CLSID}\
   → DWORD: 0 = don't load at startup, 1 = load at startup
```

At SW startup, the host enumerates HKCU `AddinsStartup`, and for each
entry with value `1`, calls `IDispatch::Invoke` on the add-in's
`ConnectToSW` method. The add-in registers event handlers, command
managers, and exposes objects via `ISldWorks::SetAddInObject`.

**Key consequence:** add-ins register event subscriptions when they
load. There is **no documented API to remove an arbitrary add-in's
event subscriptions from a running SW session.** Even if the bridge
"unloads" an add-in (which itself has caveats — see §3), already-
registered event handlers may persist until SW restart.

## 3. API surface for add-in management

### 3.1 What is documented

The SW API surface for add-in introspection (from the SW API help,
not verified against this build):

| Method | Returns | Use case |
|---|---|---|
| `ISldWorks::GetAddInObject(name)` | `IDispatch` (the add-in's exposed object) or `Nothing` | Inter-add-in dispatch — find a peer add-in's object to call its methods |
| `ISldWorks::SetAddInObject(name, obj)` | `bool` | An add-in registers its own exposed object — NOT typically called from outside the add-in |
| `ISldWorks::GetEnabledAddIns()` | `Variant` (array of names) | Enumerate currently-loaded add-ins | **VERIFY** |
| `ISldWorks::EnableAddIn(name, enable)` | `bool` | Enable/disable an add-in by name (documented in some sources, unverified) | **VERIFY** |
| `ISldWorks::LoadAddIn(name)` | `int` | Load a specific add-in by registry name | **VERIFY** |
| `ISldWorks::UnloadAddIn(name)` | `int` | Unload an already-loaded add-in | **VERIFY** |

**The `SetAddInObject` reference in the W7.1 task name appears to be
based on a misnaming.** `SetAddInObject` is the add-in self-
registration API; it cannot be used by an outside caller to register
a `null` object as a way to "unhook" an add-in (calling it from
outside the add-in's COM context is undefined behavior).

The relevant APIs for the W7.1 goal are `GetEnabledAddIns` and
(if it works) `EnableAddIn` / `UnloadAddIn`.

### 3.2 Spike to verify the API surface

`spikes/v0_13/spike_addin_enumeration.py` — minimal probe (does NOT
ship in W7.1; this is the empirical-test spec the user can run when
they have a live SW session):

```python
"""Probe ISldWorks for add-in management methods (W7.1-research).

Run with SW open. Prints which of GetEnabledAddIns / EnableAddIn /
LoadAddIn / UnloadAddIn are reachable via late-binding, and what
each returns. NO writes — observation only.
"""
import win32com.client

sw = win32com.client.Dispatch("SldWorks.Application")

for method in ("GetEnabledAddIns", "EnableAddIn", "LoadAddIn", "UnloadAddIn"):
    try:
        m = getattr(sw, method, None)
        if m is None:
            print(f"  {method}: ABSENT")
            continue
        if method == "GetEnabledAddIns":
            result = m()
            print(f"  {method}: {type(result).__name__} {result!r}")
        else:
            print(f"  {method}: present (signature unknown without arg probe)")
    except Exception as exc:
        print(f"  {method}: REACHED -> {exc!r}")
```

Run with a known mix of add-ins enabled (Toolbox + one third-party)
and record:

- Does `GetEnabledAddIns()` return the same names as Tools → Add-Ins?
- Does `UnloadAddIn(name)` actually remove the add-in's event hooks,
  or does it return success while subscriptions persist?
- After `UnloadAddIn`, does a subsequent `SaveAs3` exhibit the
  add-in's known interference pattern? (The behavioral test, not
  the API return-code test.)

The behavioral test matters because of the `CODESTYLE.md` §2.4
principle: **verify the postcondition, not the return code.**

## 4. What "disable" means in practice

Three approximations, in increasing order of effectiveness and
invasiveness:

### 4.1 Enumerate + warn (RECOMMENDED for v0.13)

- Call `GetEnabledAddIns()` at build start.
- Cross-reference against a curated known-problematic list (§5 below).
- Emit a stderr warning naming the add-ins that may interfere.
- Optionally: exit early with rc=4 when `--strict-addins` is set
  AND any known-problematic add-in is loaded.

**Why this is the recommended default:**
- Works with the API surface we can reasonably trust.
- Doesn't require a working `UnloadAddIn` — falls back to "tell the
  user to disable manually."
- Aligns with the bridge's "fail loud, fail informative" philosophy.

**What this does NOT do:** actually disable add-ins. The user is
responsible for the manual disable step (Tools → Add-Ins, or
registry edit).

### 4.2 Best-effort runtime unload (OPTIONAL extension)

- If `UnloadAddIn(name)` is verified to actually remove event hooks
  (the behavioral test above), the bridge can attempt to unload the
  problematic add-ins for the build duration.
- Re-load after build completes (or don't — the user can restart SW).

**Risks:**
- Unloading an add-in mid-session can crash SW for some add-ins (PDM,
  3DEXPERIENCE — these own background threads and process state).
- Event subscriptions may not actually be removed.
- Re-loading after build adds complexity and another failure surface.

**Recommendation:** ship this behind a `--unload-addins` flag (NOT
default). The warning path is the v0.13 deliverable; runtime unload
is a v0.14+ consideration after we have spike evidence.

### 4.3 Restart SW without add-ins (NOT for v0.13)

- Kill the running `SLDWORKS.exe`.
- Edit HKCU `AddinsStartup` to set all problem add-ins to `0`.
- Relaunch SW.
- Run the build.
- Restore HKCU keys.
- Tell the user to restart SW one more time (or do it for them).

**Why we don't ship this:** it touches the user's persistent
configuration. The bridge's "no side effects outside the working
directory" promise (privacy_review §3.1) forbids registry mutation.
A `--clean-sw-relaunch` would be a separate tool with its own
contract, not a build-time flag.

## 5. Known-problematic add-ins (curated list)

Compiled from public SW automation knowledge + the bridge's existing
failure-mode taxonomy (`docs/com_failure_modes.md`). The exact
behavior is documented per add-in; the LIST is the contribution of
this research note.

| Add-in | Why it interferes | Bridge symptom |
|---|---|---|
| **SOLIDWORKS Toolbox** | Auto-resizes inserted hardware; rewrites mate references; can edit feature names | Dimension chain changes between build and re-build; `_apply_bindings` finds renamed features |
| **SOLIDWORKS PDM (Standard or Professional)** | Intercepts `Save` / `SaveAs` via `FilePreSaveNotify`; vault-bound files require check-out | `SaveAs3` returns 0 but file is unchanged (vault refused write); the S-01 verifier catches it but reports a misleading cause |
| **3DEXPERIENCE PLM Connector** | Captures save events; modifies custom properties | `custom_props` (W2.1) returns properties the spec didn't set |
| **SOLIDWORKS Routing** | Adds Route features when assembly contains connector parts; modifies feature tree | Unexpected features in the tree post-build; `feature_tree_diff` shows additions |
| **SOLIDWORKS Electrical** | Same as Routing but for electrical wiring | Same |
| **SOLIDWORKS Simulation** | Adds Simulation study features; modifies units when activated | `IUnitMgr` values shift; mass-property checks may fail |
| **SOLIDWORKS Inspection** | Tags features with inspection metadata | Custom properties grow unexpectedly |
| **SOLIDWORKS Composer (formerly 3DVIA)** | Subscribes to assembly events | Rare in part-only builds; assembly builds risk it |
| **Any third-party MBD/CAM/CAE add-in** | Unpredictable per vendor | Build failures with unfamiliar HRESULTs |

**What the bridge ships:** the W7.1-code task includes this list as a
constant in `src/ai_sw_bridge/com/addins.py` (or wherever the W5
factor lands; see §7). The list is conservative — it lists add-ins
**known to interfere**, not all add-ins. Users with a custom add-in
not on the list still get the enumeration in the warning, just
without the "known problematic" badge.

## 6. Interaction with Lane M / W5

The W5 (Lane M) port introduces `com/executor.py` with an `ISldWorks`
adapter abstraction. The add-in enumeration logic should live in
that lane, not in `cli/build.py` or `spec/builder.py`:

```
src/ai_sw_bridge/com/
    executor.py     (W5.1 — STA-threaded COM executor)
    adapters/
        sw_app.py   (the ISldWorks wrapper)
        addins.py   (NEW — add-in enumeration + warn + optional unload)
```

This keeps the `com/` lane as the single chokepoint for "things we
touch via COM that aren't direct geometric writes," and means the
W7.1 work doesn't have to be re-homed when W5 lands.

**If W7.1-code ships before W5.1** (timeline-wise, W7.1 is sequenced
before W5 in the v0.13 closure plan), the add-in module lives at
`src/ai_sw_bridge/observe.py` (alongside `sw_get_*` read functions)
temporarily and migrates into `com/` when Lane M opens. The W7.1-code
task chooses the location; W5.1 inherits whatever was chosen.

## 7. Implementation sketch for W7.1-code (Sonnet/GLM)

```python
# observe.py (or com/addins.py post-W5.1)

KNOWN_PROBLEMATIC_ADDINS: frozenset[str] = frozenset({
    "SOLIDWORKS Toolbox",
    "SOLIDWORKS Routing",
    "SOLIDWORKS Electrical",
    "SOLIDWORKS Simulation",
    "SOLIDWORKS Inspection",
    "SOLIDWORKS Composer",
    "SOLIDWORKS PDM Standard",
    "SOLIDWORKS PDM Professional",
    "3DEXPERIENCE PLM Connector",
    # Names match what GetEnabledAddIns returns; VERIFY by running
    # spikes/v0_13/spike_addin_enumeration.py with each enabled.
})


def sw_get_enabled_addins() -> dict[str, Any]:
    """Enumerate currently-loaded add-ins (W7.1).

    Returns {ok, addins: [...], known_problematic: [...], error}.
    The addins list contains every name reported by
    ISldWorks::GetEnabledAddIns. known_problematic is the subset
    that intersects KNOWN_PROBLEMATIC_ADDINS.

    Fail-soft: if GetEnabledAddIns is not present on this SW build,
    returns ok=True with addins=[] and a warning string. The build
    does not fail on the absence of the API — many SW builds may
    expose the API only when at least one add-in is enabled.
    """


# cli/build.py — extended

parser.add_argument(
    "--disable-addins",
    action="store_true",
    default=False,
    help=(
        "Pre-build add-in check (W7.1). Enumerates loaded add-ins "
        "via ISldWorks::GetEnabledAddIns. Emits a stderr warning if "
        "any known-problematic add-in is active. Does NOT unload "
        "add-ins — see docs/addins_research.md §4 for why. The user "
        "must disable interfering add-ins manually (Tools → Add-Ins) "
        "for the build duration."
    ),
)
parser.add_argument(
    "--strict-addins",
    action="store_true",
    default=False,
    help=(
        "Hardens --disable-addins: exit rc=4 BEFORE the build starts "
        "when any known-problematic add-in is loaded. Use in CI."
    ),
)


# In build flow, before the first COM write:
if args.disable_addins or args.strict_addins:
    result = sw_get_enabled_addins()
    if result["known_problematic"]:
        msg = (
            f"Known-problematic add-ins loaded: {result['known_problematic']!r}. "
            f"See docs/addins_research.md §5 for behavior. To disable: "
            f"Tools → Add-Ins → uncheck → restart SW."
        )
        _emit_stderr(msg)
        if args.strict_addins:
            return 4
```

**Wire format:** the enumeration is exposed as `ai-sw-observe addins`
(new subcommand) for AI agents to query before invoking
`ai-sw-build`. Two-stream contract: stdout JSON, stderr warning.

## 8. Empirical test plan (for live SW session)

When the user has SW open with a known set of add-ins enabled:

1. Run `spikes/v0_13/spike_addin_enumeration.py` (§3.2). Record:
   - Which methods (`GetEnabledAddIns`, `EnableAddIn`, `LoadAddIn`,
     `UnloadAddIn`) are reachable.
   - What `GetEnabledAddIns()` returns (type, format, name shapes).

2. With Toolbox enabled, run a build that inserts a Toolbox part.
   Verify: does `ai-sw-build` see the Toolbox interference? Does
   `sw_get_enabled_addins` correctly identify Toolbox in the
   `known_problematic` list?

3. (Optional, if `UnloadAddIn` is reachable) Call
   `sw.UnloadAddIn("SOLIDWORKS Toolbox")`. Verify:
   - Return value (0 = success, non-zero = failure code).
   - Whether the add-in's event handlers are actually unhooked
     (insert a Toolbox part; if it still auto-resizes, hooks remain).
   - Whether SW becomes unstable.

4. With PDM Pro enabled (if available), attempt `SaveAs3` to a
   non-vault folder. Verify the bridge's S-01 verifier catches the
   refusal correctly.

**Recording format:** add a row to `docs/com_failure_modes.md` under
a new "Add-in interference" section per finding. The W7.1-code task
references the row IDs for the warning messages.

## 9. Open questions

- **Is `GetEnabledAddIns` reliably present on SW 2020+?** Spike
  result resolves this. Fallback: if absent, `sw_get_enabled_addins`
  returns `ok=True, addins=[], note="api_not_present"`.
- **Are add-in names stable across SW versions?** (Toolbox might be
  "SOLIDWORKS Toolbox" on 2024 and "SolidWorks Toolbox" on older
  builds.) The KNOWN_PROBLEMATIC_ADDINS list should match
  case-insensitively until verified.
- **Should the warning be on stderr always, or behind a flag?**
  Recommendation: always emit on stderr when add-ins are loaded
  (informational); `--strict-addins` upgrades to rc=4. The user can
  silence with `--quiet` per the two-stream contract.
- **PDM-bound files specifically:** should the bridge refuse to
  build against a file checked into PDM? Out of scope for W7.1 —
  this is a separate file-validation concern. The warning suffices.

## 10. Recommendation summary

**For W7.1-code (Sonnet/GLM):**

1. Implement `sw_get_enabled_addins()` in `observe.py` (migrates to
   `com/addins.py` when W5.1 lands).
2. Add the curated KNOWN_PROBLEMATIC_ADDINS list (§5).
3. Wire `--disable-addins` and `--strict-addins` into
   `ai-sw-build`.
4. Add `addins` subcommand to `ai-sw-observe`.
5. Ship the spike at `spikes/v0_13/spike_addin_enumeration.py` for
   the user to run when they have a live session.
6. **Do NOT** implement runtime `UnloadAddIn` calls. Defer to v0.14+
   after spike results.
7. Update `docs/com_failure_modes.md` with placeholder rows for
   add-in interference (A-XX prefix); populate when spikes return.

**Honest summary:** `--disable-addins` is a misnomer for what the
bridge can responsibly ship. The flag name is preserved for clarity
(users will search for "disable add-ins") but the semantic is
"detect and warn about add-ins that may interfere." Actually
disabling add-ins requires user action; the bridge tells them
*which* user action.
