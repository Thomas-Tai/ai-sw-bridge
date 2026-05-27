"""``ai-sw-history`` — checkpoint query CLI (spec.md §5.7).

Three subcommands (plus a bonus ``diff``):

* ``ai-sw-history part <part_name>`` — list every checkpoint for the
  named part, most-recent-first.
* ``ai-sw-history locals <part_name> <locals_path>`` — list checkpoints
  whose locals snapshot matches the given locals file.
* ``ai-sw-history since <part_name> <iso_timestamp>`` — list
  checkpoints at-or-after the timestamp.
* ``ai-sw-history diff <part_name> <id_a> <id_b>`` — structural diff
  between two checkpoints (spec / locals / tree changed?).

Two-stream contract: stdout is JSON-only, stderr is human-readable
(errors, warnings, "0 rows" notices).

Stability tier: **experimental** — the subcommand set may grow as the
checkpoint surface expands. Marked with ``@cli_stability("experimental")``
(Task 1.9 decorator from v0.11).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ..checkpoint import (
    CheckpointStore,
    by_locals,
    by_part,
    feature_diff,
    since,
)
from .stability import add_subcommand_tier, add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet


_DEFAULT_ROOT = Path(".checkpoints")


def _checkpoint_to_dict(cp: Any) -> dict[str, Any]:
    """Serialize a Checkpoint dataclass to a JSON-safe dict."""
    d = dataclasses.asdict(cp)
    # Enum -> str so json.dumps is happy.
    status = d["status"]
    d["status"] = status.value if hasattr(status, "value") else str(status)
    return d


def _emit_json(payload: Any) -> None:
    """Emit one JSON object to stdout (two-stream contract)."""
    print(json.dumps(payload, sort_keys=False, indent=2))


def _emit_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _open_store(part_name: str, root: Path) -> CheckpointStore:
    if not root.exists():
        _emit_stderr(f"checkpoint root {root} does not exist; 0 rows")
        sys.exit(0)
    db_path = root / f"{part_name}.sqlite"
    if not db_path.exists():
        _emit_stderr(f"no checkpoints for part {part_name!r} (no {db_path})")
        sys.exit(0)
    return CheckpointStore(part_name=part_name, root=root)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _cmd_part(args: argparse.Namespace) -> int:
    store = _open_store(args.part_name, args.root)
    try:
        rows = by_part(store)
    finally:
        store.close()
    _emit_json(
        {
            "subcommand": "part",
            "part_name": args.part_name,
            "count": len(rows),
            "checkpoints": [_checkpoint_to_dict(r) for r in rows],
        }
    )
    return 0


def _cmd_locals(args: argparse.Namespace) -> int:
    locals_path = Path(args.locals_path)
    if not locals_path.exists():
        _emit_stderr(f"locals file not found: {locals_path}")
        return 2
    store = _open_store(args.part_name, args.root)
    try:
        rows = by_locals(store, locals_path)
    finally:
        store.close()
    _emit_json(
        {
            "subcommand": "locals",
            "part_name": args.part_name,
            "locals_path": str(locals_path),
            "count": len(rows),
            "checkpoints": [_checkpoint_to_dict(r) for r in rows],
        }
    )
    return 0


def _cmd_since(args: argparse.Namespace) -> int:
    try:
        ts = datetime.fromisoformat(args.timestamp)
    except ValueError as e:
        _emit_stderr(f"invalid ISO timestamp {args.timestamp!r}: {e}")
        return 2
    store = _open_store(args.part_name, args.root)
    try:
        rows = since(store, ts)
    finally:
        store.close()
    _emit_json(
        {
            "subcommand": "since",
            "part_name": args.part_name,
            "since": args.timestamp,
            "count": len(rows),
            "checkpoints": [_checkpoint_to_dict(r) for r in rows],
        }
    )
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    store = _open_store(args.part_name, args.root)
    try:
        a = store.get(args.id_a)
        b = store.get(args.id_b)
    finally:
        store.close()
    if a is None or b is None:
        missing = [i for i, cp in ((args.id_a, a), (args.id_b, b)) if cp is None]
        _emit_stderr(f"checkpoint id(s) not found: {missing}")
        return 2
    _emit_json(
        {
            "subcommand": "diff",
            "part_name": args.part_name,
            **feature_diff(a, b),
        }
    )
    return 0


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-history",
        description=(
            "Query checkpoint history for a part. "
            "Stdout is JSON; stderr is human-readable diagnostics."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_DEFAULT_ROOT,
        help=f"Checkpoint root directory (default: {_DEFAULT_ROOT}).",
    )
    add_tier(parser, "experimental")

    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_part = sub.add_parser(
        "part", help="List every checkpoint for a part (most recent first)."
    )
    p_part.add_argument("part_name", help="Part name (matches <part_name>.sqlite).")
    p_part.set_defaults(func=_cmd_part)
    add_subcommand_tier(p_part, "experimental")

    p_locals = sub.add_parser(
        "locals", help="List checkpoints whose locals snapshot matches a file."
    )
    p_locals.add_argument("part_name")
    p_locals.add_argument("locals_path", help="Path to a locals.txt equation file.")
    p_locals.set_defaults(func=_cmd_locals)
    add_subcommand_tier(p_locals, "experimental")

    p_since = sub.add_parser(
        "since", help="List checkpoints at-or-after an ISO timestamp."
    )
    p_since.add_argument("part_name")
    p_since.add_argument("timestamp", help="ISO-8601 timestamp.")
    p_since.set_defaults(func=_cmd_since)
    add_subcommand_tier(p_since, "experimental")

    p_diff = sub.add_parser("diff", help="Structural diff between two checkpoint ids.")
    p_diff.add_argument("part_name")
    p_diff.add_argument("id_a", type=int)
    p_diff.add_argument("id_b", type=int)
    p_diff.set_defaults(func=_cmd_diff)
    add_subcommand_tier(p_diff, "experimental")

    return parser


@cli_stability("experimental")
def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    add_quiet_flag(parser)
    args = parser.parse_args(argv)
    apply_quiet(args)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
