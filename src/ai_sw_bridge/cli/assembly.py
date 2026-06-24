"""ai-sw-assembly: Propose-Approve-Execute assembly CLI.

The §6.5-consistent surface for the (approval-gated) assembly write
lifecycle — CLI-only, never MCP, mirroring ``ai-sw-mutate``.

Subcommands:
  propose --spec <path>
      Validate an assembly spec offline; no SW touch. Returns a proposal_id.
  dry_run --proposal-id <id>
      Resolve component part files / part_specs and bind mate faces without
      mutating SW.
  commit --proposal-id <id> --out <path> [--part-paths <json>]
      Build the assembly — place components, create mates, SaveAs3 the
      ``.sldasm`` to ``--out``, and write the assembly manifest. Only allowed
      after dry_run_ok. ``--part-paths`` is an optional JSON object mapping
      ``component_id -> prebuilt .sldprt path`` (overrides; the lifecycle builds
      ``part_spec`` components itself when omitted).

Each subcommand prints a single JSON object to stdout and exits 0 if the tool
returned ok=True, else 1.
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
    return SolidWorksClient().mutate.propose_assembly(spec)


def _run_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    return SolidWorksClient().mutate.dry_run_assembly(args.proposal_id)


def _run_commit(args: argparse.Namespace) -> dict[str, Any]:
    part_paths: dict[str, str] | None = None
    if args.part_paths:
        try:
            part_paths = json.loads(args.part_paths)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"invalid --part-paths JSON: {exc}"}
        if not isinstance(part_paths, dict):
            return {"ok": False, "error": "--part-paths must be a JSON object"}
    return SolidWorksClient().mutate.commit_assembly(
        args.proposal_id, args.out, part_paths=part_paths
    )


def _load_op(raw: str) -> dict[str, Any] | None:
    """Parse --op as inline JSON or @file path. Returns None on error."""
    if raw.startswith("@"):
        p = Path(raw[1:])
        if not p.is_file():
            return None
        raw = p.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _run_edit(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest
    if not Path(manifest_path).is_file():
        return {"ok": False, "error": f"manifest not found: {manifest_path}"}
    op = _load_op(args.op)
    if op is None:
        return {"ok": False, "error": f"invalid --op JSON: {args.op}"}
    return SolidWorksClient().mutate.edit_assembly(manifest_path, op)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-assembly",
        description=(
            "Propose-Approve-Execute assembly tools for SOLIDWORKS. "
            "Workflow: propose -> dry_run -> commit. Places components and "
            "creates mates from a declarative assembly spec."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")

    p = subs.add_parser(
        "propose",
        help="Validate an assembly spec offline; returns a proposal_id.",
    )
    p.add_argument(
        "--spec",
        required=True,
        help="Path to a declarative assembly spec JSON file.",
    )
    p.set_defaults(func=_run_propose)

    p = subs.add_parser(
        "dry_run",
        help="Resolve parts and bind mate faces without mutating SW.",
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
        help="Build + save the assembly (only after dry_run_ok).",
    )
    p.add_argument(
        "--proposal-id",
        dest="proposal_id",
        required=True,
        help="Proposal id (must be in state dry_run_ok).",
    )
    p.add_argument(
        "--out",
        required=True,
        help="Absolute path to save the built .sldasm.",
    )
    p.add_argument(
        "--part-paths",
        dest="part_paths",
        default=None,
        help=(
            "Optional JSON object mapping component_id -> prebuilt .sldprt "
            "path (overrides; part_spec components build automatically)."
        ),
    )
    p.set_defaults(func=_run_commit)

    p = subs.add_parser(
        "edit",
        help=(
            "Apply a declarative edit op to a manifest, validate, and propose. "
            "Returns a proposal_id for dry_run/commit."
        ),
    )
    p.add_argument(
        "--manifest",
        required=True,
        help="Path to the .manifest.json sidecar.",
    )
    p.add_argument(
        "--op",
        required=True,
        help=(
            "Edit op as inline JSON or @file path. "
            "Ops: add_component, remove_component, add_mate, remove_mate."
        ),
    )
    p.set_defaults(func=_run_edit)

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
