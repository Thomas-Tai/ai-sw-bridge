# Quickstart: get running in 5 minutes

This page is the fast path. It splits cleanly into two tiers, and the split
is honest: **Tier A never touches SOLIDWORKS** — you can author and validate
specs with nothing but Python installed. **Tier B is where the payoff
happens** — it needs a running SOLIDWORKS seat to actually build geometry.

Run the whole thing yourself at any time with:

```bash
python tools/demo_full_system.py --quickstart
```

(add `--with-sw` once you're ready to run the Tier B commands live).

## Tier A — Ready to develop, no license needed

No SOLIDWORKS required for any of this. Install the package, run a
read-only health check, see what the bridge can build, and validate a real
spec offline.

```bash
pip install -e .[dev]
```

```bash
python -m ai_sw_bridge.cli.doctor --no-seat
```

`--no-seat` runs environment checks only (Python bitness, pywin32, PATH,
MCP registration) and never touches SOLIDWORKS. Without that flag, `doctor`
also probes for a live SOLIDWORKS seat, which falls back to auto-launching
SOLIDWORKS if none is running -- so quickstart always passes `--no-seat`.

```bash
python -m ai_sw_bridge.cli.build --list-kinds
```

```bash
python -m ai_sw_bridge.cli.build examples/demo_widget/demo_baseplate/spec.json --dry-run --lint
```

That last command is the real headline of Tier A: it validates and lints
an actual committed part spec — schema, references, locals resolution, DFM
lint — with zero SOLIDWORKS involvement. If you're only authoring and
reviewing specs (for example, from an AI assistant that has no SW seat),
Tier A alone is a complete workflow.

## Tier B — Your first real part, needs a SOLIDWORKS seat

This is the live payoff: an actual part built in an actual SOLIDWORKS
document, and geometry read back to prove it. Open SOLIDWORKS first.

```bash
python -m ai_sw_bridge.cli.build --demo --no-dim --yes
```

```bash
python -m ai_sw_bridge.cli.observe bounding_box
```

`--demo` builds the bundled 20×20×10 mm filleted box (the same spec shown
in the main [README](README.md)) so there's nothing to author before your
first build. `ai-sw-observe bounding_box` reads real geometry back from the
model that command just created.

## Author specs with editor autocomplete

Point your editor at the published JSON Schema and every `spec.json` gets
autocomplete, enum hints, and inline validation as you type — no build required.
In VS Code, add to `.vscode/settings.json`:

```json
{
  "json.schemas": [
    { "fileMatch": ["**/spec.json"], "url": "./schema/ai-sw-bridge.spec.schema.json" }
  ]
}
```

Working outside a repo clone (a `pip`/`pipx` install)? The schema ships inside
the wheel — resolve its path with:

```python
from ai_sw_bridge.spec import published_schema_path
print(published_schema_path())
```

Full wiring (JetBrains, the raw-URL option, and why an inline `$schema` key is
rejected) is in
[docs/spec_reference.md](docs/spec_reference.md#editor-autocomplete-json-schema).

## Where next

Edit any `examples/demo_widget/*/spec.json` and re-run the Tier-A dry-run
to see your change validated.

```bash
python tools/demo_full_system.py --chapter all
```

That runs the full chaptered tour — part build, assembly, DFM observe,
drawing, and export — end to end against a live seat.

Read `docs/demo_full_system.md` for how to record each chapter.
