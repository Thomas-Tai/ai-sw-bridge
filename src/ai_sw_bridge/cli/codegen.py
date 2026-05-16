"""ai-sw-codegen: Path C parameterizer CLI.

Usage:
  ai-sw-codegen parameterize <recorded.swp> <spec.json>

Reads a SW-recorded .swp (binary OLE compound), parameterizes it per the
spec JSON, and writes a .bas file next to the .swp. You then paste the
.bas into a SW VBE module and press F5 to create the parametric part.

spec.json schema:
  {
    "locals_path": "absolute path to *_locals.txt to link",
    "bindings": [
      { "dim": "D1@Sketch1",      "var": "PART_DIAMETER" },
      { "dim": "D1@Boss-Extrude1","var": "PART_LENGTH"   }
    ]
  }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..parameterize import parameterize


def cmd_parameterize(swp_path: Path, spec_path: Path) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out_bas = swp_path.with_name(swp_path.stem + "_parameterized.bas")
    result_text = parameterize(swp_path, spec)
    out_bas.write_text(result_text, encoding="utf-8")
    return {
        "ok": True,
        "swp_input": str(swp_path),
        "spec": str(spec_path),
        "bas_output": str(out_bas),
        "bytes": out_bas.stat().st_size,
        "next_steps": [
            "Open the recorded part's source state in SOLIDWORKS (File > New > Part).",
            f"Open VBE (Alt+F11), paste the contents of {out_bas.name} into a new module.",
            "Press F5 to run.",
            "Click through any 'modify dimension' popups (a future release will suppress these).",
        ],
    }


def main() -> int:
    argv = sys.argv
    if len(argv) < 2:
        print(json.dumps({
            "ok": False,
            "error": "usage: ai-sw-codegen parameterize <recorded.swp> <spec.json>",
        }, indent=2))
        return 2

    cmd = argv[1]

    if cmd == "parameterize":
        if len(argv) < 4:
            print(json.dumps({
                "ok": False,
                "error": "usage: ai-sw-codegen parameterize <recorded.swp> <spec.json>",
            }, indent=2))
            return 2
        swp_path = Path(argv[2]).resolve()
        spec_path = Path(argv[3]).resolve()
        if not swp_path.exists():
            print(json.dumps({"ok": False, "error": f"swp not found: {swp_path}"}, indent=2))
            return 2
        if not spec_path.exists():
            print(json.dumps({"ok": False, "error": f"spec not found: {spec_path}"}, indent=2))
            return 2
        try:
            result = cmd_parameterize(swp_path, spec_path)
        except Exception as exc:
            result = {"ok": False, "error": f"parameterize failed: {exc!r}"}
    else:
        result = {"ok": False, "error": f"unknown command: {cmd}", "commands": ["parameterize"]}

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
