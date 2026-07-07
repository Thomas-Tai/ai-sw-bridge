# COTS Selection — Automated Sorting Machine

## Candidate components

| ID | Category | Model / standard | Status | CAD asset |
|---|---|---|---|---|
| COTS-001 | motor | Generic NEMA 17 stepper (0.4 N·m holding) | candidate | missing |
| COTS-002 | belt | PU flat belt, 120 mm wide, endless | candidate | missing |
| COTS-003 | roller | Crowned conveyor roller, Ø40 × 130 mm | candidate | missing |
| COTS-004 | camera | USB 1080p module w/ fixed-focus lens | candidate | missing |
| COTS-005 | controller | SBC (Raspberry-Pi-class) + stepper driver | candidate | missing |
| COTS-006 | fasteners | ISO 4762 M5 socket-head screws | selected | available |

## Vendor/model or generic standard

All candidates are generic classes for the prototype; pin vendor part numbers
before the `cad_ready` state (slice COTS must be confirmed with CAD assets).
COTS-006 is standard hardware (SW Toolbox provides geometry — `available`).

## Key dimensions

| ID | Dimension | Value | Status |
|---|---|---|---|
| COTS-001 | faceplate_square | 42.3 mm | vendor_provided (NEMA 17 standard) |
| COTS-001 | shaft_diameter | 5 mm | vendor_provided (NEMA 17 standard) |
| COTS-003 | outer_diameter | 40 mm | assumed (drives `INF_ROLLER_D`) |

## CAD asset availability

Vendor STEP files: none downloaded yet (`missing`). The handoff builds
placeholder geometry from the key dimensions above until assets arrive, then
swaps via `ai-sw-import`.

## Selection rationale

- COTS-001: passes the torque check (calculations.md §4) with ≈ 2.3× margin.
- COTS-002/003: match `CONVEYOR_WIDTH` 120 mm and `INF_ROLLER_D` 40 mm.
- COTS-004/005: one-camera, one-SBC control fits the data/electrical interfaces.

## Open questions and substitutions

- Motor: any NEMA 17 with ≥ 0.28 N·m at 48 rpm substitutes freely.
- Roller: a printed roller over a steel shaft is an acceptable prototype
  substitute if the COTS roller lead time is long.
