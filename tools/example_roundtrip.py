#!/usr/bin/env python3
"""Validate every example spec.json against the schema (W4.3).

Doc-as-test: reads every ``examples/*/spec.json``, runs schema +
reference validation, and exits non-zero naming any failures.

Usage::

    python tools/example_roundtrip.py
    python tools/example_roundtrip.py --examples-dir path/to/examples

Exit codes: 0 = all clean, 1 = validation failures, 2 = I/O error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_sw_bridge.spec import ValidationError, validate  # noqa: E402

_DEFAULT_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _validate_one(spec_path: Path) -> str | None:
    """Validate one spec. Returns an error string or None on success."""
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"invalid JSON: {exc}"
    except OSError as exc:
        return f"cannot read: {exc}"
    try:
        validate(spec, spec_path=spec_path)
    except ValidationError as exc:
        return f"validation_failed: {exc.path}: {exc.message}"
    return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="example_roundtrip",
        description=(
            "Validate every examples/*/spec.json against the schema "
            "and linked locals (W4.3 doc-as-test)."
        ),
    )
    parser.add_argument(
        "--examples-dir",
        default=str(_DEFAULT_EXAMPLES),
        help="Root examples directory (default: shipped examples).",
    )
    args = parser.parse_args(argv)

    examples_dir = Path(args.examples_dir)
    if not examples_dir.is_dir():
        print(f"error: examples dir not found: {examples_dir}", file=sys.stderr)
        return 2

    specs = sorted(examples_dir.glob("*/spec.json"))
    if not specs:
        print(f"error: no specs found under {examples_dir}", file=sys.stderr)
        return 2

    failures: list[tuple[str, str]] = []
    for spec_path in specs:
        example_name = spec_path.parent.name
        err = _validate_one(spec_path)
        if err:
            failures.append((example_name, err))
            print(f"FAIL  {example_name}: {err}", file=sys.stderr)
        else:
            print(f"ok    {example_name}", file=sys.stderr)

    print(
        f"\n{len(specs)} spec(s) checked, " f"{len(failures)} failure(s)",
        file=sys.stderr,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
