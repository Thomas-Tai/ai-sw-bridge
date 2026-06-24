# Pending Live-Seat Gates

Lanes that are **offline-green** but carry a verification step that requires a
live SOLIDWORKS seat (and, in some cases, a human-authored fixture the COM API
cannot produce out-of-process). Each entry is shippable as-is; this log records
the one assertion that is *not yet* proven against the kernel.

---

## `observe.mbd` — DimXpert / MBD PMI extraction (opened 2026-06-24)

**Status:** offline dual-branch suite green (`tests/test_observe_mbd.py`, 12
tests). The read graph and the JSON schema are proven against mocks.

**Pending gate — the asymmetric deviation bridge.** The DimXpert-native API
exposes no independent upper/lower (+/-) deviation getters — only
`GetNominalValue()`, a single symmetric `Tolerance()`, and `LimitsAndFitsCode()`
(measure-first finding, `spikes/v0_2x/spike_mbd_read_extract.py`, 50 interfaces
enumerated). Asymmetric bounds (e.g. `+0.2 / -0.05`) are recovered via a
best-effort bridge:

```
IDimXpertAnnotation.GetDisplayEntity()
  -> IDisplayDimension.GetDimension2(0)
  -> IDimension.Tolerance
  -> ITolerance.{GetMaxValue, GetMinValue}
```

This bridge is implemented defensively: on success the payload sets
`asymmetric_extracted=True` with the bounds; on any fault it falls back to the
symmetric base fields with `asymmetric_extracted=False`. **The success path is
unproven live** because authoring DimXpert PMI walls out-of-process
(`AutoDimensionScheme` / `InsertSizeDimension` ghost — `spike_mbd_probe.py`,
verdict `READABLE_WALL_ON_WRITE`), so no PMI-bearing fixture can be generated
programmatically.

**To close the gate:**
1. A human authors `tests/fixtures/mbd_block.sldprt` at the live seat — a
   `100 × 50 × 25 mm` block with Datum A (bottom face), a symmetric `±0.1` size
   dimension (width), and a **bilateral `+0.2 / -0.05`** size dimension (length).
2. Run the armed probe:
   `MBD_FIXTURE=tests/fixtures/mbd_block.sldprt python spikes/v0_2x/spike_mbd_read_extract.py`
3. Confirm `ITolerance.GetMaxValue/GetMinValue` yields `+0.2 / -0.05` (verifying
   the deviation-vs-absolute semantics) and that `observe.mbd(<fixture>)` returns
   `asymmetric_extracted=True` with the expected bounds + datum `A` + nominals
   `100`/`50`.

Until then the lane ships read-only with the symmetric fallback as the
guaranteed contract and the asymmetric bounds as a documented enhancement.

---

## `weld-bead table` — `IDrawingDoc.InsertWeldTable` (deferred 2026-06-24)

**Status:** unimplemented; deliberately deferred. The drawing TABLE family is
otherwise complete and shipped (W71): hole (`InsertHoleTable2`), revision
(`InsertRevisionTable2`), weldment cut-list (`InsertWeldmentTable`), general
(`InsertGeneralTableAnnotation`), plus BOM (`InsertBomTable4`, W23). The weld-bead
*summary* table is the lone remaining table type.

**Why deferred (not built):** `IDrawingDoc.InsertWeldTable(UseAnchorPoint,
IncludeAnnotations, CombineSameType, X, Y, AnchorType, Configuration,
TableTemplate) -> Boolean` summarizes **weld beads**, so it needs a model that
already carries weld-bead features (fillet/groove welds). Authoring weld beads
out-of-process (`IFeatureManager.InsertFilletWeldBead`-class calls) is **unprobed
and of uncertain feasibility** — manufacturing-annotation geometry has repeatedly
hit the OOP authoring wall (cf. the MBD PMI Catch-22 above: `AutoDimensionScheme`
/ `InsertSizeDimension` ghost). The ROI on a weld-bead *summary* table does not
justify a bash against a probable `InsertFilletWeldBead` OOP wall.

**To close the gate (if ever pursued):**
1. A human authors a `.sldprt` weldment containing weld beads at the seat (do NOT
   attempt to author beads programmatically — assume the OOP wall until a probe
   says otherwise).
2. Drop the part into a drawing and probe `IDrawingDoc.InsertWeldTable(...)` —
   classify materialize-vs-ghost against the returned Boolean + a visible table.
3. If it materializes, add a `weld_table` spec flag mirroring the W71 table family
   wiring in `drawing/lifecycle.py`.
