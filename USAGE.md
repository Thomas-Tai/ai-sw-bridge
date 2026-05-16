# USAGE

Detailed workflows for ai-sw-bridge. For installation and a 60-second quickstart, see [README.md](README.md).

## Workflow 1 — Design-guide verification (read-only)

Use case: You wrote a design guide that says "the post height is `D_Z_BELT − S1B_BELT_T − S1B_ROLLER_DIA/2 = 61.0 mm`." You want to verify SOLIDWORKS actually computes this.

```powershell
# 1. Open the part in SOLIDWORKS.
# 2. Check the equation evaluated as expected:
ai-sw-observe equations > equations.json

# 3. (optional) Capture a screenshot to compare against a visual reference:
ai-sw-observe screenshot --filename=verification.png
```

The output JSON has every equation with its current numeric value. Pipe it to `jq` or feed it directly to an AI agent that compares against the written guide.

This workflow has been used in practice on the Lego Sorter V2 S1b conveyor design guide to catch a parametric-enforcement gap (a literal `-32.5` mm offset that should have been bound to `-"S1B_CHUTE_OUTLET_LOCAL_X"`). The error wasn't visible from reading the guide alone — the AI agent only found it by diffing the live `equations` output against the documented invariants.

## Workflow 2 — Change a single variable (Propose-Approve-Execute)

Use case: The design guide says `S1B_FOOT_W` should be 16 mm but the model has 15 mm. You want to apply the change safely.

**Prerequisite**: The active SW part must have a `*_locals.txt` file linked via Tools → Equations → Link to file. The bridge reads `EquationMgr.FilePath` to discover the linked file.

```powershell
# 1. Propose (no SW state changed yet)
ai-sw-mutate propose --var=S1B_FOOT_W --new_value=16.0
# -> proposal_id: a1b2c3d4e5f6, state: proposed

# 2. Dry-run: apply, rebuild, capture, roll back
ai-sw-mutate dry_run --proposal_id=a1b2c3d4e5f6
# -> before: { manager_status: 0, var_value: 15.0 }
#    after:  { manager_status: 0, var_value: 16.0 }
#    rebuild_ok: true, rolled_back: true, state: dry_run_ok

# 3. Inspect the result. If happy, commit:
ai-sw-mutate commit --proposal_id=a1b2c3d4e5f6
# -> state: committed, doc_saved: true|false
```

`doc_saved: false` is NOT an error. It means the active part doesn't use the changed variable, so SW found nothing to write. The `*_locals.txt` file IS updated — that's the source of truth.

To rollback the last commit:
```powershell
ai-sw-mutate undo_last_commit
```

Proposal records persist in `./proposals/` (override via `AI_SW_BRIDGE_PROPOSALS` env var). You can inspect them with any JSON viewer.

## Workflow 3 — Path C: parametric part creation

Use case: You want to model `MyPart.SLDPRT` once in SOLIDWORKS, then regenerate variants by editing `*_locals.txt`.

### Step 1: Author the variables

In your `*_locals.txt` (the file your other parts already link), define the variables this part will consume. Example:
```
"PART_DIAMETER"  = 25.0
"PART_LENGTH"    = 80.0
```

### Step 2: Record the part in SOLIDWORKS

1. *File → New → Part* (FRESH empty part — important; see [known_gotchas.md](docs/known_gotchas.md))
2. *Tools → Macro → Record*
3. Build the part. Use **literal values** (e.g. type `25` for the circle diameter, not `="PART_DIAMETER"`). The parameterizer will swap them for you.
4. **Rename your sketches and features** to stable names you'll recognize (right-click → Feature Properties, or F2). E.g. `Sketch1` → keep it (or rename to `SK_Body`), `Boss-Extrude1` → rename to `Extrude_Body`.
5. *Tools → Macro → Stop*. Save as `recorded.swp`.

### Step 3: Write the spec JSON

```json
{
  "locals_path": "C:\\path\\to\\your_locals.txt",
  "bindings": [
    { "dim": "D1@Sketch1",      "var": "PART_DIAMETER" },
    { "dim": "D1@Extrude_Body", "var": "PART_LENGTH"   }
  ]
}
```

The `dim` paths use SW's internal dimension naming: `D<n>@<feature_name>`. You can see these in SW's equation manager. If the sketch was renamed during recording, use the FINAL name (after rename) — the binding runs after the rename, so the path reflects the new name.

### Step 4: Parameterize

```powershell
ai-sw-codegen parameterize recorded.swp spec.json
```

Output is a `.bas` file (plain-text VBA) next to the `.swp`.

### Step 5: Run in SW

1. *File → New → Part* (fresh empty doc — same starting state as your recording)
2. *Alt+F11* to open VBE
3. Paste the contents of `recorded_parameterized.bas` into a new module (or into the default `Module1` after deleting the stub)
4. Press F5
5. Click through any "modify dimension" popups (a future release will suppress these)

### Step 6: Verify

```powershell
ai-sw-observe equations | findstr "D1@"
```

Look for your two new entries:
```
"D1@Sketch1" = "PART_DIAMETER"     value=25.0
"D1@Extrude_Body" = "PART_LENGTH"  value=80.0
```

The part is now genuinely parametric. Edit `your_locals.txt`, save, rebuild in SW (`Ctrl+B`), and the part updates.

## Workflow 4 — Cross-session AI driving

Because every CLI prints one JSON object to stdout, an AI agent can drive the bridge with no special harness:

```python
import subprocess, json

def call_bridge(*args):
    result = subprocess.run(
        ["ai-sw-observe", *args],
        capture_output=True, text=True, check=False,
    )
    return json.loads(result.stdout), result.returncode

data, code = call_bridge("equations")
if data["manager_status_code"] != 0:
    print("Equation manager has errors:", data["manager_status"])
```

For Claude Code specifically, you can wrap each command in a slash-command or expose them via MCP. The package intentionally stays out of MCP transport details — point an MCP server at the CLIs and you're done.

## Output paths & environment

| Default location | Override via |
|---|---|
| `./captures/` (screenshots) | `AI_SW_BRIDGE_CAPTURES=...` env var |
| `./proposals/` (mutation proposals) | `AI_SW_BRIDGE_PROPOSALS=...` env var |

Both folders are created on first use. Add them to `.gitignore` if you don't want them committed.
