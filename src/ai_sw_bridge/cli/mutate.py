"""ai-sw-mutate: Propose-Approve-Execute mutation CLI.

Subcommands:
  propose --var <NAME> --new-value <expr>
      Stage a change; no SW touch. Returns a proposal_id.
  dry_run --proposal-id <id>
      Apply in SW, force-rebuild, capture before/after, roll back.
  commit --proposal-id <id>
      Re-apply (only allowed after dry_run_ok), save the doc.
  undo_last_commit
      Revert the most-recently committed proposal.
  run_macro --macro-path <path.swp> [--module <name>] [--sub <name>]
      Execute a SW VBA macro (binary .swp only).

Each subcommand prints a single JSON object to stdout and exits 0 if the
tool returned ok=True, else 1. Both --key=value and --key value syntax
are accepted.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..mutate import (
    sw_commit,
    sw_dry_run,
    sw_propose_local_change,
    sw_run_macro,
    sw_undo_last_commit,
)
from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet


def _run_propose(args: argparse.Namespace) -> dict[str, Any]:
    return sw_propose_local_change(var=args.var, new_value=args.new_value)


def _run_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    return sw_dry_run(proposal_id=args.proposal_id)


def _run_commit(args: argparse.Namespace) -> dict[str, Any]:
    return sw_commit(proposal_id=args.proposal_id)


def _run_undo_last_commit(_args: argparse.Namespace) -> dict[str, Any]:
    return sw_undo_last_commit()


def _run_macro(args: argparse.Namespace) -> dict[str, Any]:
    return sw_run_macro(
        macro_path=args.macro_path,
        module=args.module,
        sub=args.sub,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-mutate",
        description=(
            "Propose-Approve-Execute mutation tools for SOLIDWORKS. "
            "Workflow: propose -> dry_run -> commit. All mutations route "
            "through the SW-linked *_locals.txt file."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")

    p = subs.add_parser(
        "propose",
        help="Stage a change to a single variable in the linked locals file.",
    )
    p.add_argument("--var", required=True, help="Variable name (without quotes).")
    p.add_argument(
        "--new-value",
        dest="new_value",
        required=True,
        help="New RHS expression for the variable.",
    )
    p.set_defaults(func=_run_propose)

    p = subs.add_parser(
        "dry_run",
        help="Apply a proposal in SW, capture state, then roll back.",
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
        help="Re-apply a proposal that passed dry-run and save the SW doc.",
    )
    p.add_argument(
        "--proposal-id",
        dest="proposal_id",
        required=True,
        help="Proposal id (must be in state dry_run_ok).",
    )
    p.set_defaults(func=_run_commit)

    p = subs.add_parser(
        "undo_last_commit",
        help="Revert the most-recently committed proposal.",
    )
    p.set_defaults(func=_run_undo_last_commit)

    p = subs.add_parser(
        "run_macro",
        help="Execute a SW VBA macro (binary .swp only).",
    )
    p.add_argument(
        "--macro-path",
        dest="macro_path",
        required=True,
        help="Path to the .swp macro file.",
    )
    p.add_argument(
        "--module",
        default="Module1",
        help="Module name inside the macro (default Module1).",
    )
    p.add_argument(
        "--sub",
        default="main",
        help="Sub name to invoke (default main).",
    )
    p.set_defaults(func=_run_macro)

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
