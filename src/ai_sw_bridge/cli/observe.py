"""ai-sw-observe: read-only inspection CLI.

Subcommands:
  active_doc          -> sw_get_active_doc()
  feature_errors      -> sw_get_feature_errors()
  equations           -> sw_get_equations()
  bbox                -> sw_get_bbox()             [part only]
  volume              -> sw_get_volume()           [part only]
  screenshot          -> sw_screenshot(width, height, fit_view, filename)
  measure             -> sw_measure(entity_a, entity_b)
  mate_errors         -> sw_get_mate_errors()  [assembly only]

Each subcommand prints a single JSON object to stdout and exits 0 if the
underlying tool returned ok=True, else 1. Both --key=value and --key value
syntax are accepted (argparse-standard).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..observe import (
    sw_get_active_doc,
    sw_get_bbox,
    sw_get_equations,
    sw_get_feature_errors,
    sw_get_mate_errors,
    sw_get_volume,
    sw_measure,
    sw_screenshot,
)
from .stability import add_tier, cli_stability


def _run_active_doc(_args: argparse.Namespace) -> dict[str, Any]:
    return sw_get_active_doc()


def _run_feature_errors(_args: argparse.Namespace) -> dict[str, Any]:
    return sw_get_feature_errors()


def _run_equations(_args: argparse.Namespace) -> dict[str, Any]:
    return sw_get_equations()


def _run_mate_errors(_args: argparse.Namespace) -> dict[str, Any]:
    return sw_get_mate_errors()


def _run_bbox(_args: argparse.Namespace) -> dict[str, Any]:
    return sw_get_bbox()


def _run_volume(_args: argparse.Namespace) -> dict[str, Any]:
    return sw_get_volume()


def _run_screenshot(args: argparse.Namespace) -> dict[str, Any]:
    return sw_screenshot(
        width=args.width,
        height=args.height,
        fit_view=args.fit_view,
        filename=args.filename,
    )


def _run_measure(args: argparse.Namespace) -> dict[str, Any]:
    return sw_measure(entity_a=args.entity_a, entity_b=args.entity_b)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-observe",
        description=(
            "Read-only inspection of the running SOLIDWORKS session. Each "
            "subcommand runs a single observation tool and prints a JSON "
            "object to stdout."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")

    p = subs.add_parser("active_doc", help="Report metadata on the active document.")
    p.set_defaults(func=_run_active_doc)

    p = subs.add_parser(
        "feature_errors",
        help="Walk the active doc's feature tree and report non-OK features.",
    )
    p.set_defaults(func=_run_feature_errors)

    p = subs.add_parser(
        "equations",
        help="Dump every equation in the active doc with value and status.",
    )
    p.set_defaults(func=_run_equations)

    p = subs.add_parser(
        "bbox",
        help="Report the active part's axis-aligned bounding box (part only).",
        description=(
            "Read the active part's bounding box via IPartDoc.GetPartBox. "
            "Reports min/max corners and spans in BOTH mm and m. Part docs "
            "only -- returns a typed error result for assemblies/drawings."
        ),
    )
    p.set_defaults(func=_run_bbox)

    p = subs.add_parser(
        "volume",
        help="Report the active part's volume, surface area, and mass (part only).",
        description=(
            "Read the active part's mass properties via "
            "IModelDocExtension.CreateMassProperty. Reports volume in mm^3 "
            "and m^3, surface area, mass (only meaningful with an assigned "
            "material; see density_kg_m3), and center of mass. The "
            "volume_mm3 field is the oracle compared against per-feature "
            "spec _expect.mass_delta_mm3 in the upcoming P0.5 verifier."
        ),
    )
    p.set_defaults(func=_run_volume)

    p = subs.add_parser(
        "screenshot",
        help="Capture the active SW viewport to a PNG file.",
        description=(
            "Capture the active SW viewport to a PNG on disk. Output goes to "
            "AI_SW_BRIDGE_CAPTURES env var if set, else ./captures relative "
            "to the current working directory."
        ),
    )
    p.add_argument("--width", type=int, default=640, help="Image width (default 640)")
    p.add_argument("--height", type=int, default=360, help="Image height (default 360)")
    p.add_argument(
        "--fit-view",
        dest="fit_view",
        action="store_true",
        help="Call ViewZoomtofit2 before capture.",
    )
    p.add_argument(
        "--filename",
        default=None,
        help="Output filename (auto-derived from doc title if omitted).",
    )
    p.set_defaults(func=_run_screenshot)

    p = subs.add_parser(
        "measure",
        help="Measure entities in the active document.",
        description=(
            "Measure entities in the active document. With no args, measures "
            "whatever is currently selected in the SW UI. With --entity-a, "
            "programmatically selects that entity and reports area/perimeter."
        ),
    )
    p.add_argument(
        "--entity-a",
        dest="entity_a",
        default=None,
        help="Name of the first entity to select.",
    )
    p.add_argument(
        "--entity-b",
        dest="entity_b",
        default=None,
        help="Name of the second entity (note: two-entity named selection is unsupported).",
    )
    p.set_defaults(func=_run_measure)

    p = subs.add_parser(
        "mate_errors",
        help="Walk an assembly's mate set and report per-mate status (assembly only).",
    )
    p.set_defaults(func=_run_mate_errors)

    return parser


@cli_stability("stable")
def main() -> int:
    parser = _build_parser()
    add_tier(parser, "stable")
    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
