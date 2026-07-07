# Calculations — Automated Sorting Machine

Inputs trace to `engineering_specs.md`; every result is `derived`.

## Sizing calculations

### 1. Belt speed

- Purpose: meet REQ-001 (30 objects/min) at 200 mm pitch (assumed).
- Formula: v = rate × pitch = (30/60) obj/s × 0.200 m
- Result: **`INF_BELT_SPEED` = 0.10 m/s (derived)**

### 2. Drive torque

- Purpose: size the belt-drive motor (justifies COTS-001).
- Moving load: 3 objects on belt (`INF_BELT_L` 600 mm / 200 mm pitch) × 0.5 kg
  + belt 0.3 kg (assumed) = **1.8 kg**
- Drag force: F = μ·m·g = 0.35 (assumed) × 1.8 kg × 9.81 m/s² = **6.2 N**
- Torque at drive roller (r = `INF_ROLLER_D`/2 = 0.020 m):
  τ = F·r = 6.2 × 0.020 = **0.124 N·m**
- With safety factor 2.0: **τ_required = 0.25 N·m (derived)**

### 3. Drive-shaft speed

- n = v / (π·D) = 0.10 / (π × 0.040) = 0.80 rev/s ≈ **48 rpm (derived)**

### 4. Candidate motor check (COTS-001, NEMA 17)

- Generic NEMA 17: 0.40 N·m holding; usable torque at 48 rpm typically
  ≥ 0.28 N·m (vendor curve required — `vendor_provided`, open below).
- Margin vs load torque: 0.28 / 0.124 ≈ 2.3×. **PASS as candidate.**

## Structural checks

Side plates are 3 mm 5052 spanning 600 mm with < 20 N distributed load —
deflection is negligible at prototype scale (engineering judgment; revisit if
`INF_BELT_L` grows past 1 m).

## Tolerance stack-up

Roller-center to roller-center sets belt tension: slotted tensioner absorbs
±0.2 mm × 2 plate cuts + roller length tolerance, so no tight fit is required
on `INF_BELT_L`. Bearing seats (H7) are deferred to the roller-detail slice.

## Power and duty-cycle budget

P = F·v = 6.2 N × 0.10 m/s ≈ **0.62 W** mechanical — trivial for any NEMA 17
at continuous duty; PSU sizing is dominated by the controller + camera, not
the drive.

## Open calculations that block COTS selection

- None blocking. Open (non-blocking): confirm the selected motor's torque
  curve at 48 rpm from the vendor datasheet (`vendor_provided`).
