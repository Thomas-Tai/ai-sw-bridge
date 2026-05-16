"""
Generate docs/api_reference.md from docs/api_reference.json.

Run after chm_extract.py batch to refresh the human-readable reference.

Output structure:
  ## Methods
    ### IFeatureManager.FeatureCut4
       (summary)
       Signature, args table, return type, availability
  ## Enums
    ### swEndConditions_e
       (summary)
       Values table
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def render_method(fq: str, m: dict) -> list[str]:
    lines: list[str] = []
    lines.append(f"### `{fq}`")
    lines.append("")
    if m.get("summary"):
        lines.append(m["summary"])
        lines.append("")
    lines.append(f"**Args ({m['args_count']}):**")
    lines.append("")
    lines.append("| # | Name | Type | Description |")
    lines.append("|---|------|------|-------------|")
    for i, a in enumerate(m["args"], 1):
        doc = (a.get("doc") or "").replace("|", "\\|").replace("\n", " ")
        # Trim very long docs
        if len(doc) > 200:
            doc = doc[:197] + "..."
        lines.append(f"| {i} | `{a['name']}` | `{a['type']}` | {doc} |")
    lines.append("")
    if m.get("return_type"):
        lines.append(f"**Returns:** `{m['return_type']}`")
        lines.append("")
    if m.get("availability"):
        lines.append(f"**Availability:** {m['availability']}")
        lines.append("")
    return lines


def render_enum(name: str, e: dict) -> list[str]:
    lines: list[str] = []
    lines.append(f"### `{name}`")
    lines.append("")
    if e.get("summary"):
        lines.append(e["summary"])
        lines.append("")
    lines.append("| Name | Value | Doc |")
    lines.append("|------|-------|-----|")
    # Sort by numeric value for readability
    for v in sorted(e["values"], key=lambda x: x["value"]):
        doc = (v.get("doc") or "").replace("|", "\\|")
        lines.append(f"| `{v['name']}` | `{v['value']}` | {doc} |")
    lines.append("")
    return lines


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: gen_api_markdown.py <api_reference.json> <out.md>")
        return 1
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    data = json.loads(src.read_text(encoding="utf-8"))

    lines: list[str] = [
        "# SOLIDWORKS API Reference (verified)",
        "",
        "Auto-generated from decompiled `sldworksapi.chm` + `swconst.chm`. ",
        f"Regenerate with `tools/chm_extract.py batch tools/_api_extract_input.json {src.name}` ",
        f"then `tools/gen_api_markdown.py {src.name} {out.name}`.",
        "",
        "**Authoritative for arg counts and types on this SW build.** When an SW API",
        "call fails `PARAMNOTOPTIONAL` or `Invalid number of parameters`, the first check",
        "is whether the arg count here matches what's being passed. ([builder.py FeatureCut4 was 27 args, not 24](src/ai_sw_bridge/spec/builder.py))",
        "",
        "## Methods",
        "",
    ]
    for fq, m in sorted(data["methods"].items()):
        lines.extend(render_method(fq, m))

    lines.append("## Enums")
    lines.append("")
    for name, e in sorted(data["enums"].items()):
        lines.extend(render_enum(name, e))

    if data.get("missing"):
        lines.append("## Not found in CHM")
        lines.append("")
        for miss in data["missing"]:
            lines.append(f"- `{miss}`")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(lines)} lines, {len(data['methods'])} methods, {len(data['enums'])} enums)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
