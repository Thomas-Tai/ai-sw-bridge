"""
Generate src/ai_sw_bridge/sw_types.py from docs/api_reference.json.

Output: Python module exposing
  - Constants for every enum value (e.g. SW_END_COND_THROUGH_ALL = 1)
  - Per-API call helper docstrings (so the AI sees arg names + types via IDE)
  - Sentinel calling conventions (which we *don't* generate as wrappers because
    pywin32 late-binding type marshalling is per-arg-position and a wrapper
    layer would obscure the call site).

Hand-edits should NEVER go in sw_types.py. Add new enums/methods to
tools/_api_extract_input.json and regenerate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


HEADER = '''"""
Auto-generated SOLIDWORKS API constants from decompiled CHM.

DO NOT HAND-EDIT. Regenerate by running:
  tools/chm_extract.py batch tools/_api_extract_input.json docs/api_reference.json
  tools/gen_sw_types.py docs/api_reference.json src/ai_sw_bridge/sw_types.py

This file contains:
  - Enum constants (one per enum value, name-prefixed for easy access)
  - A METHOD_SIGNATURES dict mapping fully-qualified method names to their
    arg-name lists + arg-count. Used by builder.py for runtime arg-count
    assertion (catches CHM-mismatched calls early).
"""
'''


def _enum_const_name(enum_name: str, value_name: str) -> str:
    """Turn (swEndConditions_e, swEndCondThroughAll) -> SW_END_COND_THROUGH_ALL.

    Handles three styles:
      camelCase:    swEndCondThroughAll -> SW_END_COND_THROUGH_ALL
      ALL_CAPS:     swDocPART           -> SW_DOC_PART
      mixed-runs:   swDocIMPORTED_PART  -> SW_DOC_IMPORTED_PART
    """
    n = value_name
    if n.startswith("sw"):
        n = n[2:]

    # Insert underscore between lowercase->uppercase transitions: "EndCond" -> "End_Cond"
    # but DO NOT split between consecutive uppercase letters (acronyms / ALL_CAPS).
    out: list[str] = []
    for i, ch in enumerate(n):
        prev = n[i - 1] if i > 0 else ""
        if i > 0 and ch.isupper() and prev.islower():
            out.append("_")
        out.append(ch)
    s = "".join(out)
    # Collapse double underscores
    while "__" in s:
        s = s.replace("__", "_")
    return "SW_" + s.upper()


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: gen_sw_types.py <api_reference.json> <sw_types.py>")
        return 1
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    data = json.loads(src.read_text(encoding="utf-8"))

    lines: list[str] = [HEADER, ""]

    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("")
    lines.append("# -----------------------------------------------------------------------------")
    lines.append("# Enum constants")
    lines.append("# -----------------------------------------------------------------------------")
    lines.append("")
    for ename, e in sorted(data["enums"].items()):
        lines.append(f"# {ename}: {e.get('summary', '')}")
        for v in sorted(e["values"], key=lambda x: x["value"]):
            const_name = _enum_const_name(ename, v["name"])
            doc = v.get("doc")
            if doc:
                lines.append(f"{const_name} = {v['value']}  # {v['name']} -- {doc}")
            else:
                lines.append(f"{const_name} = {v['value']}  # {v['name']}")
        lines.append("")

    lines.append("# -----------------------------------------------------------------------------")
    lines.append("# Method signatures (for arg-count validation)")
    lines.append("# -----------------------------------------------------------------------------")
    lines.append("")
    lines.append("METHOD_SIGNATURES: dict[str, dict[str, object]] = {")
    for fq, m in sorted(data["methods"].items()):
        arg_names = [a["name"] for a in m["args"]]
        arg_types = [a["type"] for a in m["args"]]
        lines.append(f'    "{fq}": {{')
        lines.append(f'        "args_count": {m["args_count"]},')
        lines.append(f'        "arg_names": {arg_names!r},')
        lines.append(f'        "arg_types": {arg_types!r},')
        lines.append(f'        "return_type": {m.get("return_type")!r},')
        if m.get("summary"):
            lines.append(f'        "summary": {m["summary"]!r},')
        lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("def assert_args(fq_method: str, args: tuple) -> None:")
    lines.append('    """Sanity-check that a call has the documented arg count. Raise')
    lines.append('    ValueError on mismatch to catch CHM-vs-call drift at runtime."""')
    lines.append('    sig = METHOD_SIGNATURES.get(fq_method)')
    lines.append('    if sig is None:')
    lines.append("        return  # uncatalogued -- trust the caller")
    lines.append('    expected = sig["args_count"]')
    lines.append('    if len(args) != expected:')
    lines.append('        names = sig["arg_names"]')
    lines.append('        raise ValueError(')
    lines.append('            f"{fq_method} expects {expected} args, got {len(args)}. "')
    lines.append('            f"Per CHM signature: {names}"')
    lines.append('        )')
    lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
