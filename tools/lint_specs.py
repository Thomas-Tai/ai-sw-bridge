#!/usr/bin/env python3
"""Lint one or more spec.json files with the semantic linter.

Backs the pre-commit `ai-sw-build-lint` hook, which passes the staged spec
paths as arguments. Exits non-zero if any file has lint findings so the
commit is blocked.

    python tools/lint_specs.py examples/drive_roller/spec.json [...]

Exit codes: 0 = clean, 1 = lint findings, 2 = a file could not be read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_sw_bridge.spec.lint import lint as spec_lint  # noqa: E402


def main(argv: list[str]) -> int:
    findings_total = 0
    for arg in argv:
        path = Path(arg)
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path}: cannot read spec ({exc})", file=sys.stderr)
            return 2
        for finding in spec_lint(spec):
            print(f"{path}: {finding}")
            findings_total += 1
    if findings_total:
        print(f"\n{findings_total} lint finding(s) -- commit blocked")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
