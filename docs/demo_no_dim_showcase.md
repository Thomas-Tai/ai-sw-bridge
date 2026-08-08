# No-Dim Showcase Recording

Use this when you want a short GIF that shows both the current ai-sw-bridge
capability surface and a live SOLIDWORKS build result.

## Full Recording

Open SOLIDWORKS, start your screen recorder with the terminal and SOLIDWORKS
window visible, then run this from the repo root:

```powershell
python tools/demo_no_dim_showcase.py
```

The script:

1. Prints the current supported build, observe, and CLI surfaces.
2. Dry-runs and lints the 10-feature motor-mount showcase spec.
3. Pauses so you can bring the SOLIDWORKS window into frame.
4. Runs `ai-sw-build ... --no-dim --yes` to create a fresh part.
5. Leaves the finished part visible for the final seconds of the GIF.

`--no-dim` is the real CLI flag. It resolves dimensions up front and avoids
SOLIDWORKS Modify Dimension popups during the recording.

For a shorter GIF-friendly capability intro, use compact mode:

```powershell
python tools/demo_no_dim_showcase.py --compact
```

## Safe Rehearsal

Run the terminal-only preflight without touching SOLIDWORKS:

```powershell
python tools/demo_no_dim_showcase.py --preflight-only --no-pause --sleep 0
```

Run only the capability tour:

```powershell
python tools/demo_no_dim_showcase.py --tour-only --no-pause --sleep 0
```

## Showcase Choices

The default showcase is `motor_mount`, a 10-feature plate with face sketches,
cuts, recesses, and hole groups.

Pick another showcase with:

```powershell
python tools/demo_no_dim_showcase.py --showcase drive_roller
python tools/demo_no_dim_showcase.py --showcase patterned_plate
python tools/demo_no_dim_showcase.py --showcase smoke
```

Use the smaller bundled filleted-box smoke demo with the shortcut:

```powershell
python tools/demo_no_dim_showcase.py --smoke
```

Use any custom spec with:

```powershell
python tools/demo_no_dim_showcase.py --spec path\to\spec.json
```
