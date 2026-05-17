# Why `--no-dim` exists: the AddDimension2 popup post-mortem

> Audience: future engineers (human or AI) tempted to "fix" the
> AddDimension2 popup blocker. This doc captures what we tried, what
> failed, and why so you don't re-walk the same dead ends.

## TL;DR

`IModelDoc2.AddDimension2` opens a Modify-Dimension popup that **cannot
be suppressed via pywin32 on SW 2024 SP1**. We shipped `ai-sw-build
--no-dim`, which resolves `{"rhs": "..."}` references against
`spec['locals']` in Python upfront and skips every `AddDimension2` call.
Trade-off: the resulting SLDPRT has no live equation link to
`locals.txt` (re-run `ai-sw-build` to propagate edits).

**If you're here because someone told you "just set
`swInputDimValOnCreate` to False" — read on. We've tried. Three times.
It doesn't work from external COM clients on this build.**

## The problem

`AddDimension2(x, y, z)` is how SW binds a numeric value to a sketch
dimension that `EquationMgr.Add2` can later target by name (e.g.
`"D1@SK_Body"`). On SW 2024 SP1, every call opens **two** dialogs:

1. A small floating **Modify Dimension popup** (numeric value + green/red ticks)
2. The **left-side Dimension PropertyManager (PM) pane** (green/red ticks)

Both must be dismissed before `AddDimension2` returns. The call blocks
synchronously — the COM thread parks until the user clicks. Empirically
about **~12s per dim** of human attention. For MMP (~15 dims) that's
~30 ticks per build.

## What we tried and why each failed

| Approach | Spike | Result | Why it failed |
|---|---|---|---|
| Toggle 8 (`swInputDimValOnCreate`) `SetUserPreferenceToggle(8, False)` | [spike_i_verify_toggle.py](../spikes/phase0/spike_i_verify_toggle.py) | FAIL | `GetUserPreferenceToggle(8)` reads back False both before and after the Set call, but `AddDimension2` still blocks ~12s. Either ID 8 isn't `swInputDimValOnCreate` on this build, or the preference simply doesn't gate `AddDimension2` from external COM contexts. |
| Toggle 78 (`swSketchEnableOnScreenNumericInput`-class, forum-suggested as the "real" toggle) | [spike_m_toggle_78.py](../spikes/phase0/spike_m_toggle_78.py) | FAIL | Same outcome as toggle 8. Pywin32 + SW 2024 SP1 ignores both. |
| `keybd_event(VK_RETURN)` blind injection | [spike_h_sendkeys.py](../spikes/phase0/spike_h_sendkeys.py) | PARTIAL | Blind keybd_event DOES dismiss the Modify popup, but leaves the PM pane focused. Double-ENTER (200ms apart) is unreliable — after the first ENTER closes the popup, focus returns to the launching terminal and the second ENTER doesn't land in SW. `sw.SendKeys("{ENTER}")` and keybd_event + `SetForegroundWindow` both fail outright (focus stolen from modal to main window). |
| `doc.Extension.RunCommand(1, "")` to close PM pane | [spike_f_close_pm.py](../spikes/phase0/spike_f_close_pm.py) | FAIL | Returns True but the pane stays open. `doc.ClosePropertyManager()` and `doc.Extension.CloseAndDestroyPropertyManagers()` both raise AttributeError (not members on this build). |
| `AddSpecificDimension` (typed alternative to AddDimension2) | [spike_j_specific_dim.py](../spikes/phase0/spike_j_specific_dim.py) | FAIL | All 9 `DimType` values (1-9) return `com_error('Type mismatch.', ..., 5)` at ~0.1s each. The OUT `Error` parameter can't bind via pywin32 late-binding — same class of failure as `SelectByID2`'s `Callout` arg (see [known_gotchas.md](known_gotchas.md)). Method is unusable from this client. |
| Query internal `D1`/`D2`/`Diameter@...` dim params **without** calling AddDimension2 | [spike_o_param_without_dim.py](../spikes/phase0/spike_o_param_without_dim.py) | FAIL | Probed 9 candidate names against a `--no-dim` cylinder. All 9 returned None. SW does NOT auto-create queryable dim params on sketches/features; linkability via `EquationMgr.Add2` REQUIRES a named dim, which requires AddDimension2. |

Side note: the SW 2024 SP1 main-window class is NOT `"SldWorks"` —
it's an `Afx:*` class. The title prefix `"SOLIDWORKS"` works for
`FindWindow`. Recorded here in case the next attempt at a focus-based
workaround needs it.

## Why community advice doesn't apply

At least three separate community-canonical recommendations
(angelsix/codestack/forums) point to `swInputDimValOnCreate` (toggle 8)
as the fix for the Modify-Dim popup. They work — but **only inside
SW's VBA editor**, where the toggle is honored at the same process /
COM context as the dim creation. From an **external pywin32 COM
client** on SW 2024 SP1, neither toggle 8 nor toggle 78 has any effect.
Spikes I and M independently confirm this.

This is a pathological case specific to our deployment context
(external Python process driving SW via late-binding COM), not a
misuse of the API.

## What we ship instead: `--no-dim`

When `ai-sw-build --no-dim` is set, every `{"rhs": "..."}` reference in
the spec is resolved against `spec['locals']` in Python **before any
SW call**. The literal mm value is substituted into the spec, geometry
is built at the literal target size, and every `AddDimension2` call
plus the entire `EquationMgr.Add2` binding pass is skipped.

Implementation:
- `_load_locals_map`, `_eval_rhs`, `_resolve_rhs_in_spec` in
  [src/ai_sw_bridge/spec/builder.py](../src/ai_sw_bridge/spec/builder.py)
  (lines 117-203). Handles quoted variable refs (`"VAR"`), arithmetic,
  and recursive locals (one var referencing another). Cycles raise;
  unknown refs raise KeyError.
- `BuildContext` gained a `no_dim: bool` field; every per-feature
  handler gates its `AddDimension2` block on `if not ctx.no_dim`.
  Geometry creation paths are unchanged.
- CLI flag wired in [src/ai_sw_bridge/cli/build.py](../src/ai_sw_bridge/cli/build.py).

Validation on SW 2024 SP1:
- Cylinder `--no-dim`: **1.72s, 0 ticks**, Ø25 × 80mm verified
- MMP `--no-dim`: **~3s, 0 ticks, 10/10 features**, screenshot-verified
  (was ~60s + ~16 ticks in parametric mode)

**Trade-off**: the resulting SLDPRT has NO equation link to `locals.txt`.
Editing `locals.txt` will NOT propagate to existing parts; the user
must re-run `ai-sw-build`. The locals file remains the single source
of truth — it's just resolved at build time instead of runtime.

## What's left unexplored

Paths a future engineer might walk:

- **VBA-macro fallback.** Emit a `.bas` per build and invoke it via
  `RunMacro2` from inside SW's VBA context, where toggle 8 may
  actually work. Estimated cost: ~1-2hr including `.swp` packaging
  investigation (`RunMacro2` cannot consume plain-text `.bas` directly
  — see v0.1 known limitations in [../CHANGELOG.md](../CHANGELOG.md)).
  This recovers full linkability. See [[project_sw_bridge_next]]
  Direction B' (referenced from project memory; not in this repo).

- **Toggle ID discovery sweep.** Written but not run as
  [spike_n_toggle_discovery.py](../spikes/phase0/spike_n_toggle_discovery.py).
  Would brute-force-probe 4 candidate toggle IDs (8, 78, 95, 167) with
  fresh-doc cycles. Skipped because spikes I + M together suggest the
  toggle approach is dead at the pywin32 layer **regardless of which
  ID is "correct"**. Likely outcome: more dead toggles.

- **Different SW build.** SW 2025+ may behave differently — Anthropic
  hasn't reproduced this on any other version. Untested.

## If you're tempted to try toggle 8 again

Don't.

We have **three** spike artifacts proving it doesn't work on this
build ([spike_i_verify_toggle.py](../spikes/phase0/spike_i_verify_toggle.py),
[spike_m_toggle_78.py](../spikes/phase0/spike_m_toggle_78.py),
[spike_o_param_without_dim.py](../spikes/phase0/spike_o_param_without_dim.py)).
The toggle reads back as the value you set, but `AddDimension2` still
blocks for ~12 seconds waiting for manual ticking.

The right path forward is:
- **`--no-dim`** for AI-driven builds (no live linkability needed)
- **VBA-macro fallback** for the rare case that genuinely needs live
  equation links to `locals.txt`

If you must re-investigate, start by reading
[../spikes/phase0/MMP_DEBUG_SESSION.md](../spikes/phase0/MMP_DEBUG_SESSION.md)
in full — every dead end above is reproducible from the spike scripts
in [../spikes/phase0/](../spikes/phase0/).
