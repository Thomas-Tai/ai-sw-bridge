# Unsupported & Deferred Features

This page lists CAD operations the bridge does **not** currently support, the
technical reason, and whether that is likely to change. The bridge drives
SOLIDWORKS from a separate process through the COM API; a number of operations the
desktop application supports interactively cannot be reproduced faithfully through
that interface.

If a feature you need is here, the **Why** column tells you whether to wait for it
(deferred), design around it (workaround), or treat it as a hard boundary (platform
constraint).

## How to read this

- **Unsupported — platform constraint** — cannot be produced through this
  architecture. Grouped by root cause (out-of-process API / no public API /
  modeling-kernel). These will not change without a change in SOLIDWORKS or a new
  bridge component.
- **Deferred** — technically feasible, planned, not yet implemented.
- **Out of scope** — intentionally excluded by design.

---

## Unsupported — out-of-process API limitations

The COM API accepts the call, but the geometry kernel only completes these
operations with interactive context. Driven from an external process the call
returns with **no effect** (no geometry change). The common thread: the kernel must
*synthesize or traverse geometry mid-call* (a boolean shell, a coordinate frame, an
arbitrary path) rather than replicate an explicitly specified input.

| Feature | What it does | Why unsupported | Workaround |
|---|---|---|---|
| **Indent** | Deform one body to conform to another | Requires an in-process boolean-shell computation between bodies | None — author interactively |
| **Flex** | Bend / twist / taper a body | Needs an interactively-defined deformation frame (axes + pivot) | None |
| **Table-driven pattern** | Replicate a feature at coordinates from a table | Requires a file-backed pattern table the headless path cannot supply | Use a linear/circular/sketch-driven pattern |
| **Dimension-driven pattern** | Pattern parameterized by named dimensions | Resolves symbolic dimension names interactively | Use an explicit pattern |
| **Derived pattern** | Inherit a parent pattern's layout | Depends on interactive parent–child context | Re-author the pattern explicitly |
| **Chain / curve-driven pattern** | Space instances along a path | Kernel must walk the path and solve arc-length spacing mid-call | Use linear/circular/sketch-driven |
| **Fill pattern** | Fill a bounded region with instances | Kernel must solve the boundary and internal grid mid-call | Use an explicit pattern |
| **Split line** | Project a sketch/curve to divide a face | Projection resolves against a rendered viewport | Author faces directly where possible |
| **Move / copy body** | Translate or copy a solid body after creation | The post-hoc body-transform call is dropped out-of-process | **Author the geometry at its target location** in the spec |
| **Per-configuration geometry** | Different geometry per configuration in one file | Per-configuration scope is not honored out-of-process | **Use multi-file variants** (the `variants` spec) |
| **Assembly component pattern** | Pattern a placed component | No programmable assembly-pattern API exists | Place instances explicitly |
| **Ordinate / baseline dimensions** | Datum-referenced drawing dimensions | The creation calls produce zero dimensions headless | Use standard dimensions |
| **MBD / DimXpert auto-dimensioning** | Auto-apply 3D PMI tolerances | Feature recognition must traverse the B-rep mid-call | Author PMI interactively (read-only MBD *observation* is supported) |
| **Control-point variable fillet** | Per-control-point fillet radii | The control-point interface is unreachable out-of-process | Use a per-edge variable-radius fillet (supported) |
| **Sketch trim (closest)** | Trim by picking a point | Resolves a cursor pick against a viewport | Author the final sketch geometry directly |

---

## Unsupported — no public API

These capabilities exist only as interactive GUI / PropertyManager workflows with
no programmable entry point in the SOLIDWORKS API.

| Feature | What it does | Why unsupported |
|---|---|---|
| **Path mate** | Constrain a component to follow a path | The only mate type with no programmable feature-data interface; its options are PropertyManager-only |
| **Equation-driven curve** | Sketch a curve from an equation | No create/insert method exists in the SOLIDWORKS API |
| **Free degree-of-freedom drag** | Drag an under-constrained component | Interactive-drag only; no programmable equivalent |

---

## Unsupported — modeling-kernel constraints

For these, a direct **in-process** connection was tested (no COM marshalling
involved) and the Parasolid kernel still refused the operation. There is therefore
no software fix at the bridge layer — the constraint is in the modeling kernel's
out-of-context behavior.

| Feature | What it does | Why unsupported |
|---|---|---|
| **Thicken** | Convert a surface body to a solid | Kernel refuses the surface→solid bridge without interactive context |
| **Edge flange** | Sheet-metal flange off an edge | Kernel refuses the profile↔face relation |
| **Miter flange** | Mitered sheet-metal flange along edges | No feature-data path; kernel refuses the profile relation |
| **Jog** | Offset bend in a sheet-metal face | Fold solver requires a fixed-face designation unavailable headless |
| **Wrap** | Emboss/deboss/scribe a sketch onto a face | Kernel refuses the sketch→face projection |
| **Rib** | Thin support web from an open profile | Profile must terminate precisely on existing walls; no programmable path |
| **Loft** | Blend between profiles | No reachable creation path; legacy and feature-data routes both refuse |
| **Boundary boss** | Bidirectional boundary surface/solid | No creation API exists for the feature |

---

## Deferred — planned, not yet implemented

Technically feasible; awaiting implementation priority.

| Feature | Notes |
|---|---|
| **Combine / split bodies** (boolean) | A feature-data implementation path is characterized; not yet built |
| **Sketch relations** — collinear, coincident, symmetric | Need endpoint/multi-entity selection and verified constraint tokens |
| **Advanced hole** | High-configuration feature; needs a full near/far element-data spec |
| **Sheet-metal tables** — bend / flat-pattern / gauge | Backlog |
| **Multi-profile configurations** | Build one spec against multiple config profiles, diff the results |
| **Additional exports** — 3D PDF, eDrawings, export quality options (DPI / layers / units) | Beyond the shipped STEP / IGES / STL / 3MF / Parasolid / PDF / DXF / DWG / flat-pattern DXF |
| **Drawing enhancements** — GD&T frames, cross-sheet section/detail, additional dimension types | Beyond the shipped views / dimensions / tolerances / BOM |
| **Interference detail** — body-level, clearance/min-distance, ignored-clash sets | Beyond the shipped assembly-level interference detection |

---

## Out of scope — by design

| Item | Reason |
|---|---|
| **In-process macro injection / VBA emit-and-run** | Would require executing generated code, which violates the bridge's guarantee of **zero arbitrary code execution**. Several kernel-bound features above could in principle be unlocked this way; that path is intentionally rejected. |

---

## What could change this

- A future SOLIDWORKS release that exposes one of the unsupported operations
  through a programmable API.
- An optional, supported in-process add-in component (a sandboxed extension — *not*
  arbitrary macro execution) could unlock part of the modeling-kernel set.
- For deferred items: implementation priority, typically driven by user demand.
