"""ai-sw-mutate: Propose-Approve-Execute mutation CLI.

Usage:
  ai-sw-mutate propose --var=<NAME> --new_value=<expr>
  ai-sw-mutate dry_run --proposal_id=<id>
  ai-sw-mutate commit  --proposal_id=<id>
  ai-sw-mutate undo_last_commit
  ai-sw-mutate run_macro --macro_path=<path.swp>

Workflow:
  1. propose: stages a change, no SW touch, returns proposal_id
  2. dry_run: applies in SW, force-rebuilds, captures before/after, rolls back
  3. commit:  re-applies (only allowed after dry_run_ok), saves the doc
  4. undo_last_commit: reverts the most-recently committed proposal

Prints a single JSON object to stdout. Non-zero exit on failure.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from ..mutate import (
    sw_commit,
    sw_dry_run,
    sw_propose_local_change,
    sw_run_macro,
    sw_undo_last_commit,
)


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "propose": sw_propose_local_change,
    "dry_run": sw_dry_run,
    "commit": sw_commit,
    "undo_last_commit": sw_undo_last_commit,
    "run_macro": sw_run_macro,
}


def parse_kwargs(args: list[str]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for raw in args:
        if not raw.startswith("--") or "=" not in raw:
            raise ValueError(f"bad arg (expected --key=value): {raw}")
        key, _, value = raw[2:].partition("=")
        try:
            kwargs[key] = json.loads(value)
        except json.JSONDecodeError:
            kwargs[key] = value
    return kwargs


def main() -> int:
    argv = sys.argv
    if len(argv) < 2:
        print(json.dumps({
            "ok": False,
            "error": "usage: ai-sw-mutate <tool> [--k=v ...]",
            "tools": list(TOOLS),
        }, indent=2))
        return 2

    name = argv[1]
    tool = TOOLS.get(name)
    if tool is None:
        print(json.dumps({
            "ok": False,
            "error": f"unknown tool: {name}",
            "tools": list(TOOLS),
        }, indent=2))
        return 2

    try:
        kwargs = parse_kwargs(argv[2:])
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    result = tool(**kwargs)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
