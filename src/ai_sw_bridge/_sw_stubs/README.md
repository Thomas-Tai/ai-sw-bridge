# `_sw_stubs/` — SOLIDWORKS COM type stubs

`sw_stubs.pyi` in this directory carries hand-written type signatures for the
~21 SOLIDWORKS COM interfaces this package drives (`ISldWorks`, `IModelDoc2`,
`IFeatureManager`, `ISketchManager`, …). The stubs exist for **mypy and IDE
autocompletion only** — they are never imported at runtime.

## Why the stubs are hand-written — and why late binding is the default

The obvious alternative is `win32com.client.gencache.EnsureDispatch`, which
generates a typed early-bound wrapper from the COM type library. **It is not
used here, and must not be "fixed" to use it:**

**`EnsureDispatch` cannot build the proxy.** On every tested SOLIDWORKS
install `SldWorks.Application` (and its objects) raise *"This COM object
cannot automate the makepy process"* — the SW objects refuse
`IDispatch::GetTypeInfo`, so `EnsureDispatch` / `Dispatch` / `CastTo` all
fail. (The sanctioned early-binding path below sidesteps this by loading the
type-library module with `gencache.EnsureModule` and constructing typed
interfaces directly from the raw `_oleobj_` — no `GetTypeInfo` round-trip.)

The project therefore uses `win32com.client.Dispatch` (late binding) as its
**default**, funnelled through `ai_sw_bridge.sw_com`. Late binding
auto-invokes zero-arg methods on attribute access, so a property and a
zero-arg method are reached the same way — behavior the builder relies on
throughout (see the `resolve()` docstring in `sw_com.py`, and the
`CreateMassProperty` note in `builder.py`).

### The one binding-specific nuance — it cuts both ways

The binding choice is not "late good, early bad." It is **per method**:

- Some calls only marshal *late*-bound — `SelectByID2`'s 8th arg
  (`Callout`, an OUT `IDispatch`) and `GetErrorCode2`'s OUT param are the
  documented cases (`docs/com_failure_modes.md` rows **X-01**/**X-03**);
  the bridge uses the legacy non-OUT counterparts for those.
- Some calls only marshal *early*-bound — the durable-selection keystone
  `IModelDocExtension.GetObjectByPersistReference3` returns its entity
  through an `[out] long` error param that late binding cannot deserialize
  but an early-bound typed wrapper handles natively (proven by
  `spikes/v0_15/spike_earlybind_persist.py`, S-EARLYBIND = PASS).

So the rule is **hybrid binding** (ratified `docs/decisions.md`
2026-05-30): late by default, with a narrow sanctioned escape hatch
(`ai_sw_bridge.com.earlybind.typed`) that typed-wraps *only* the specific
objects whose OUT-param/Callout methods need it. This stays out-of-process
and `pip`-installable — invariant #4 is "out-of-process Python, no agent COM
access," not "late binding." See `CODESTYLE.md §2.1`.

**Do not migrate to `EnsureDispatch`, and do not flip the codebase to early
binding** — both are wrong; the hybrid escape hatch is the sanctioned path.
If you want richer type hints, extend `sw_stubs.pyi`.
