"""ai-sw-observe: read-only inspection CLI.

Usage:
  ai-sw-observe <tool_name> [--key=value ...]

Values are parsed as JSON: --fit_view=true, --width=1920, --filename=\"x.png\"

Tools available:
  active_doc          -> sw_get_active_doc()
  feature_errors      -> sw_get_feature_errors()
  equations           -> sw_get_equations()
  screenshot          -> sw_screenshot(width, height, fit_view, filename)
  measure             -> sw_measure(entity_a, entity_b)
  mate_errors         -> sw_get_mate_errors()  [assembly only]

Prints a single JSON object to stdout. Non-zero exit if tool returns ok=False.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from ..observe import (
    sw_get_active_doc,
    sw_get_equations,
    sw_get_feature_errors,
    sw_get_mate_errors,
    sw_measure,
    sw_screenshot,
)


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "active_doc": sw_get_active_doc,
    "feature_errors": sw_get_feature_errors,
    "equations": sw_get_equations,
    "screenshot": sw_screenshot,
    "measure": sw_measure,
    "mate_errors": sw_get_mate_errors,
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
            "error": "usage: ai-sw-observe <tool> [--k=v ...]",
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
