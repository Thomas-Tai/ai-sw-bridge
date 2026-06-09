"""ai-sw-configurations: Multifile variant materialization CLI.

The §6.5-consistent surface for configuration variant management —
CLI-only, never MCP, mirroring ``ai-sw-properties``.

Subcommands:
  propose --spec <path>
      Validate a configurations spec offline; no SW touch.  Checks the
      base spec and variants block structure.
  materialize --spec <path> --output-dir <dir>
      Build one .sldprt per variant.  Deep-merges each variant's
      overrides into the base spec, builds with no_dim=True, saves
      to output_dir, and measures volume via COM.

Each subcommand prints a single JSON object to stdout and exits 0 if ok.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet


def _run_propose(args: argparse.Namespace) -> dict[str, Any]:
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        return {"ok": False, "error": f"spec file not found: {args.spec}"}
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON: {exc}"}

    from ..config import parse_variants
    from ..spec import validate

    result: dict[str, Any] = {"ok": False}

    # Pop variants before base spec validation (variants is a W36 extension)
    variants_block = spec.pop("variants", [])
    if not variants_block:
        result["error"] = "no 'variants' block in spec"
        return result

    # Validate base spec (without variants)
    try:
        validate(spec, spec_path=spec_path)
    except Exception as exc:
        result["error"] = f"base spec validation failed: {exc}"
        return result

    # Parse variants
    try:
        variants = parse_variants(variants_block)
    except ValueError as exc:
        result["error"] = f"variants parse failed: {exc}"
        return result

    result["ok"] = True
    result["variant_count"] = len(variants)
    result["variant_names"] = [v.name for v in variants]
    result["base_spec_name"] = spec.get("name", "")
    return result


def _run_materialize(args: argparse.Namespace) -> dict[str, Any]:
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        return {"ok": False, "error": f"spec file not found: {args.spec}"}
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON: {exc}"}

    from ..config import materialize_all, parse_variants

    # Pop variants before passing spec to builder
    variants_block = spec.pop("variants", [])
    if not variants_block:
        return {"ok": False, "error": "no 'variants' block in spec"}

    try:
        variants = parse_variants(variants_block)
    except ValueError as exc:
        return {"ok": False, "error": f"variants parse failed: {exc}"}

    output_dir = Path(args.output_dir)
    results = materialize_all(spec, output_dir, variants)

    ok_count = sum(1 for r in results if r.ok)
    all_vols = {
        r.variant: r.volume_mm3
        for r in results
        if r.ok and r.volume_mm3 is not None
    }
    distinct = sorted(set(round(v, 1) for v in all_vols.values()))

    return {
        "ok": ok_count == len(variants) and len(distinct) >= 2,
        "variant_count": len(variants),
        "ok_count": ok_count,
        "results": [r.to_dict() for r in results],
        "distinct_volumes_mm3": distinct,
        "output_dir": str(output_dir.resolve()),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-configurations",
        description=(
            "Multifile variant materialization for SOLIDWORKS. "
            "Workflow: propose -> materialize. Each variant becomes a "
            "distinct .sldprt file with independently-proven geometry."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")

    p = subs.add_parser(
        "propose",
        help="Validate a configurations spec offline; no SW touch.",
    )
    p.add_argument("--spec", required=True, help="Path to spec JSON with variants block.")
    p.set_defaults(func=_run_propose)

    p = subs.add_parser(
        "materialize",
        help="Build one .sldprt per variant with volume verification.",
    )
    p.add_argument("--spec", required=True, help="Path to spec JSON with variants block.")
    p.add_argument(
        "--output-dir",
        dest="output_dir",
        required=True,
        help="Directory for output .sldprt files.",
    )
    p.set_defaults(func=_run_materialize)

    return parser


@cli_stability("stable")
def main() -> int:
    parser = _build_parser()
    add_tier(parser, "stable")
    add_quiet_flag(parser)
    args = parser.parse_args()
    apply_quiet(args)
    result = args.func(args)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
