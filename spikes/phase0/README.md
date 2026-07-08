# Phase 0 — De-risking spikes

Gate for v0.2 (AI-driven build-parts-from-scratch). Each spike answers ONE
binary question. If all three pass, v0.2 architecture is viable.

| Spike | Question | Status |
|---|---|---|
| A | Can `FeatureManager.FeatureExtrusion2` be called via pywin32 late-binding? | pending |
| B | Does `SelectByID2("", "FACE", x, y, z, ...)` reliably select a face on a freshly-built feature? | pending |
| C | Does `EquationMgr.Add2(-1, formula, True)` bind a dim on a freshly-built feature? | pending |

## How to run

Each spike has two modes:

- `--mode=com` — call SW directly from Python via late-bound pywin32
- `--mode=vba` — emit a `.bas` file you paste into VBE and press F5

If `--mode=com` fails (late-binding wall), the `.bas` fallback proves the
underlying SW behavior is correct and isolates the failure to the COM marshalling.

## Prerequisites

- SOLIDWORKS running
- A blank Part document is the active doc (File → New → Part)
- venv with `ai-sw-bridge` installed: `C:\path\to\ai-sw-bridge\.venv-freshtest`

## Pass criteria

### Spike A — `FeatureExtrusion2` via late-binding

PASS: a 20×20×5 mm box appears in the FeatureManager tree as a feature named `Boss-Extrude1`
(or similar). `EditDimension` and `Feature.Name` are addressable afterward.

FAIL modes worth recording:
- `pywintypes.com_error` on the FeatureExtrusion2 call → marshalling failure
- Call returns `None` → SW silently rejected args
- Box appears but extrusion is in wrong direction / wrong depth → arg ordering wrong

### Spike B — `SelectByID2` face-by-coords

PASS: a sketch created after `SelectByID2(..."FACE"...)` lands on the outboard face of the
Spike A box. Sketch entities exist; the sketch plane is the box top.

FAIL modes:
- Selection succeeds but sketch lands on a different face → coord miss
- SelectByID2 returns False → coord outside any face

### Spike C — `Add2` binding on fresh-built feature

PASS: after binding `"D1@Sketch1"` to `"S1B_TEST_W"`, changing the value in `*_locals.txt`
and rebuilding shifts the box width.

FAIL modes:
- Add2 returns None / negative → COM late-binding issue
- Equation added but dim doesn't follow → variable name mismatch (boring) or equation
  not actually binding (interesting)
