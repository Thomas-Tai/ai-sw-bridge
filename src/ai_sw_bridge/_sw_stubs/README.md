# `_sw_stubs/` — SOLIDWORKS COM type stubs

`sw_stubs.pyi` in this directory carries hand-written type signatures for the
~21 SOLIDWORKS COM interfaces this package drives (`ISldWorks`, `IModelDoc2`,
`IFeatureManager`, `ISketchManager`, …). The stubs exist for **mypy and IDE
autocompletion only** — they are never imported at runtime.

## Why the stubs are hand-written — and why late binding is load-bearing

The obvious alternative is `win32com.client.gencache.EnsureDispatch`, which
generates a typed early-bound wrapper from the COM type library. **It is not
used here, and must not be "fixed" to use it.** Two hard reasons:

1. **`EnsureDispatch` cannot build the proxy.** On most SOLIDWORKS installs
   `SldWorks.Application` raises *"This COM object cannot automate the makepy
   process"* — the type library cannot be consumed by `gencache`.

2. **Early binding breaks real calls.** Where `EnsureDispatch` *does*
   succeed, early-bound marshalling rejects calls that late binding accepts.
   `SelectByID2`'s 8th argument (`Callout`, an OUT `IDispatch`) and
   `GetErrorCode2`'s OUT parameter both raise `Type mismatch` under early
   binding — see `docs/com_failure_modes.md` rows **X-01** and **X-03**.

The project therefore uses `win32com.client.Dispatch` (late binding)
exclusively, funnelled through `ai_sw_bridge.sw_com`. Late binding
auto-invokes zero-arg methods on attribute access, so a property and a
zero-arg method are reached the same way — behavior the builder relies on
throughout (see the `resolve()` docstring in `sw_com.py`, and the
`CreateMassProperty` note in `builder.py`).

**Do not migrate to `EnsureDispatch`.** If you want richer type hints,
extend `sw_stubs.pyi`.
