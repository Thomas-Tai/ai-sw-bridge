# B-rep golden snapshots

Golden JSON files captured from a live SOLIDWORKS session with
`--enable-flag brep_interrogation`. Used by the
`pytest -m solidworks_only` regression gate.

## Capture procedure

Run against the MMP example (or the canonical example of your
choice) on SW 32.1.0:

```powershell
ai-sw-build examples/motor_mount_plate/spec.json `
    --no-dim `
    --enable-flag brep_interrogation `
    --save-as (Resolve-Path .).Path\mmp.sldprt
```

The build writes `build_brep.json` next to the saved `.sldprt`.
Copy it into this directory as `mmp.json`:

```powershell
Copy-Item build_brep.json tests/brep/golden/mmp.json
```

Commit the snapshot. The regression test in
`tests/brep/test_golden_mmp.py` (solidworks_only marker) rebuilds
the same spec and asserts the fresh brep manifest matches the
golden snapshot byte-for-byte, modulo `timestamp`-class fields.

## Current status (E2.6)

Golden snapshot not yet captured — requires a running SOLIDWORKS
session that isn't available in this CI environment. The
`test_golden_mmp.py` test will be added once the snapshot lands
(tracked in E2.6 follow-up / E3.5 live-SW regression).
