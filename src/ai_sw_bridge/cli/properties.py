"""ai-sw-properties: Propose-Approve-Execute properties CLI.

The §6.5-consistent surface for the (approval-gated) properties write
lifecycle — CLI-only, never MCP, mirroring ``ai-sw-assembly`` and ``ai-sw-drawing``.

Subcommands:
  propose --spec <path>
      Validate a properties spec offline; no SW touch. Returns a proposal_id.
  dry_run --proposal-id <id>
      Confirm the model file exists.
  commit --proposal-id <id>
      Set the custom properties on the model, save, verify read-back.
      Only allowed after dry_run_ok.

Each subcommand prints a single JSON object to stdout and exits 0 if ok.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..client import SolidWorksClient
from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet


def _run_propose(args: argparse.Namespace) -> dict[str, Any]:
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        return {"ok": False, "error": f"spec file not found: {args.spec}"}
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON in {args.spec}: {exc}"}
    return SolidWorksClient().mutate.propose_properties(spec)


def _run_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksClient().mutate.dry_run_properties(args.proposal_id)


def _run_commit(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksClient().mutate.commit_properties(args.proposal_id)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-properties",
        description=(
            "Propose-Approve-Execute custom file properties for SOLIDWORKS. "
            "Workflow: propose -> dry_run -> commit. Sets custom properties "
            "on .sldprt/.sldasm files with read-back verification."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")

    p = subs.add_parser(
        "propose",
        help="Validate a properties spec offline; returns a proposal_id.",
    )
    p.add_argument(
        "--spec",
        required=True,
        help="Path to a declarative properties spec JSON file.",
    )
    p.set_defaults(func=_run_propose)

    p = subs.add_parser(
        "dry_run",
        help="Confirm model file exists without mutating SW.",
    )
    p.add_argument(
        "--proposal-id",
        dest="proposal_id",
        required=True,
        help="Proposal id returned by 'propose'.",
    )
    p.set_defaults(func=_run_dry_run)

    p = subs.add_parser(
        "commit",
        help="Set properties on the model (only after dry_run_ok).",
    )
    p.add_argument(
        "--proposal-id",
        dest="proposal_id",
        required=True,
        help="Proposal id (must be in state dry_run_ok).",
    )
    p.set_defaults(func=_run_commit)

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