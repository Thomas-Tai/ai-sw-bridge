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

import argparse
import json
import sys
from pathlib import Path

from ..parameterize import parameterize
from .stability import add_tier, cli_stability


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


def _handle_parameterize(args: argparse.Namespace) -> dict:
    swp_path = Path(args.swp).resolve()
    spec_path = Path(args.spec).resolve()
    if not swp_path.exists():
        return {"ok": False, "error": f"swp not found: {swp_path}"}
    if not spec_path.exists():
        return {"ok": False, "error": f"spec not found: {spec_path}"}
    try:
        return cmd_parameterize(swp_path, spec_path)
    except Exception as exc:
        return {"ok": False, "error": f"parameterize failed: {exc!r}"}


@cli_stability("experimental")
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ai-sw-codegen",
        description=(
            "Path C parameterizer: convert a SW-recorded macro into a "
            "parametric .bas file linked to a locals.txt."
        ),
    )
    add_tier(parser, "experimental")
    subs = parser.add_subparsers(dest="command", required=True, metavar="command")

    sub_param = subs.add_parser(
        "parameterize",
        help="Convert a recorded .swp into a parameterized .bas file.",
        description=(
            "Read a SW-recorded .swp (binary OLE compound), parameterize it "
            "per the spec JSON, and write a .bas file next to the .swp."
        ),
    )
    sub_param.add_argument("swp", help="Path to the recorded .swp file")
    sub_param.add_argument("spec", help="Path to the spec JSON file")
    sub_param.set_defaults(func=_handle_parameterize)

    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
