# Example: minimal cylinder

End-to-end Path C demonstration. You'll record a Ø25 × 80 mm cylinder once, parameterize it against `locals.txt`, then replay to verify the parametric binding works.

If this example runs cleanly on your machine, the full ai-sw-bridge install is healthy.

## Files in this folder

| File | Purpose |
|---|---|
| `locals.txt` | Tiny standalone locals file with two vars: `PART_DIAMETER` (25) and `PART_LENGTH` (80) |
| `spec.json` | Parameterization spec mapping recorded sketch/extrude dims to those vars |
| `recorded.swp` | **YOU CREATE THIS** in step 1 below |

## Step 1 — Record the cylinder in SOLIDWORKS

1. Start SOLIDWORKS.
2. `File → New → Part` (use your default template — must be a FRESH empty doc).
3. `Tools → Macro → Record`. (If a save dialog appears, save anywhere — the recording captures from here.)
4. Build a cylinder:
   - Click **Front Plane** in the FeatureManager tree
   - Click **Sketch**
   - Use the **Circle tool** to draw a circle centered on the origin
   - Use **Smart Dimension** on the circle → type `25` → Enter (click through the modify popup if it appears)
   - Exit sketch (green check)
   - **Boss-Extrude** → set depth to `80` → green check
   - (Optional) Rename `Boss-Extrude1` to `Extrude_Body` in the feature tree (right-click → Feature Properties, or F2). This makes the spec stable.
5. `Tools → Macro → Stop`. Save the macro as `recorded.swp` in **this folder** (`examples/minimal_cylinder/`).

> **Why must the doc be fresh?** SW names features incrementally — if your doc already had `Sketch1`, your new sketch will be `Sketch2`, and the recording will reference the wrong name on replay. See [docs/known_gotchas.md](../../docs/known_gotchas.md#path-c-gotchas).

## Step 2 — Check the spec

[`spec.json`](spec.json) expects these recording-time names:

```json
{
  "locals_path": "<absolute path to locals.txt>",
  "bindings": [
    { "dim": "D1@Sketch1",      "var": "PART_DIAMETER" },
    { "dim": "D1@Extrude_Body", "var": "PART_LENGTH"   }
  ]
}
```

- If you DID rename `Boss-Extrude1` to `Extrude_Body`, the spec works as-is.
- If you DIDN'T rename, change `D1@Extrude_Body` to `D1@Boss-Extrude1` in the spec.
- `D1@Sketch1` assumes the first sketch in a fresh doc — should match.

You'll also need to set `locals_path` to the absolute path of [`locals.txt`](locals.txt) in this folder. Use the command in step 3 to figure out the right path.

## Step 3 — Parameterize

From the repo root:

```powershell
# Replace <REPO_PATH> with where you cloned ai-sw-bridge
$repo = "C:\path\to\ai-sw-bridge"

ai-sw-codegen parameterize `
  "$repo\examples\minimal_cylinder\recorded.swp" `
  "$repo\examples\minimal_cylinder\spec.json"
```

Output:
```json
{
  "ok": true,
  "swp_input": ".../recorded.swp",
  "bas_output": ".../recorded_parameterized.bas",
  "bytes": 4730,
  "next_steps": [...]
}
```

## Step 4 — Replay in SOLIDWORKS

1. `File → New → Part` (fresh empty doc — same starting state as recording).
2. Make the new part the active window.
3. `Alt+F11` to open VBE.
4. Delete any stub code in the default module.
5. Paste **all** of `recorded_parameterized.bas` (open in any text editor, Ctrl+A, Ctrl+C, then Ctrl+V into VBE).
6. Press **F5**.
7. If a "modify dimension" popup appears, press Enter to dismiss it.

If everything went right, a Ø25 × 80 mm cylinder appears in SW.

## Step 5 — Verify the parametric binding

```powershell
ai-sw-observe equations
```

Look for these entries near the end:
```
"expression": "\"D1@Sketch1\" = \"PART_DIAMETER\"",
"value": 25.0,
...
"expression": "\"D1@Extrude_Body\" = \"PART_LENGTH\"",
"value": 80.0,
```

If you see them, the parametric binding worked. To prove it's truly parametric:

1. Open `locals.txt` in a text editor
2. Change `PART_DIAMETER` from `25.0` to `30.0`, save
3. In SW: `Ctrl+B` (force rebuild)
4. The cylinder grows to Ø30. Done.
