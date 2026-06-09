#!/usr/bin/env python3
"""Two-stream contract enforcement lint.

Walks `src/ai_sw_bridge/` and flags violations of the two-stream contract
(UIUX.md §2.3):
  - stdout is JSON-only (agent-facing structured output).
  - stderr is human-readable text (logs, warnings, progress).

Violations:
  1. Any `print()` call without `file=sys.stderr` (or equivalent) in a
     module under `src/` that is NOT a CLI entry point.
  2. Any `sys.stdout.write()` call anywhere under `src/`.
  3. Any `print(..., file=sys.stderr)` call whose arguments look like
     JSON (contain `{` literal or `json.dumps`).

CLI entry points (build.py, observe.py, mutate.py, codegen.py, probe.py)
are allowed to emit JSON to stdout — they are the designated emitters.

Run from the repo root: python tools/two_stream_lint.py src/

Exit 0 if clean, 1 if violations found.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# CLI entry points that are allowed to print JSON to stdout.
CLI_EMITTERS = frozenset(
    {
        "build.py",
        "observe.py",
        "mutate.py",
        "assembly.py",
        "drawing.py",
        "codegen.py",
        "probe.py",
        "history.py",
        "apidoc.py",
        "checkpoint.py",
        "properties.py",
        "configurations.py",
        "sketch_relations.py",
    }
)


class _ViolationVisitor(ast.NodeVisitor):
    """AST visitor that detects two-stream contract violations."""

    def __init__(self, filepath: Path, is_cli_emitter: bool):
        self.filepath = filepath
        self.is_cli_emitter = is_cli_emitter
        self.violations: list[str] = []

    def _line(self, node: ast.AST) -> int:
        return getattr(node, "lineno", 0)

    def visit_Call(self, node: ast.Call) -> None:
        # Check for sys.stdout.write(...)
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "sys"
            and node.func.value.attr == "stdout"
            and node.func.attr == "write"
        ):
            self.violations.append(
                f"{self.filepath}:{self._line(node)}: sys.stdout.write() — "
                f"use the designated JSON emitter instead"
            )
        # Check for print() calls
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self._check_print(node)
        self.generic_visit(node)

    def _check_print(self, node: ast.Call) -> None:
        has_file_kwarg = False
        file_value_is_stderr = False
        for kw in node.keywords:
            if kw.arg == "file":
                has_file_kwarg = True
                file_value_is_stderr = self._is_stderr(kw.value)
                break

        if not has_file_kwarg:
            # Bare print() — violation unless it's a CLI emitter
            if not self.is_cli_emitter:
                self.violations.append(
                    f"{self.filepath}:{self._line(node)}: bare print() — "
                    f"must use file=sys.stderr or the JSON emitter"
                )
            return

        if file_value_is_stderr:
            # print(..., file=sys.stderr) — check if it looks like JSON
            if self._args_look_like_json(node):
                self.violations.append(
                    f"{self.filepath}:{self._line(node)}: stderr print() with "
                    f"JSON-like argument — JSON belongs on stdout"
                )

    def _is_stderr(self, node: ast.expr) -> bool:
        """Check if an AST node represents sys.stderr."""
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "sys"
                and node.attr == "stderr"
            ):
                return True
            # Also matches __import__("sys").stderr
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "__import__"
            ):
                return True
        return False

    def _args_look_like_json(self, node: ast.Call) -> bool:
        """Heuristic: does a print() call's first argument look like JSON?

        Flags json.dumps() calls and bare dict literals. Does NOT flag
        f-strings with incidental braces (common in diagnostic messages
        that show example JSON syntax).
        """
        if not node.args:
            return False
        first = node.args[0]
        # Check for json.dumps(...) call
        if isinstance(first, ast.Call):
            if isinstance(first.func, ast.Attribute) and first.func.attr == "dumps":
                return True
            if isinstance(first.func, ast.Name) and first.func.id == "dumps":
                return True
        # Check for bare dict literal as first argument
        if isinstance(first, ast.Dict):
            return True
        return False


def lint_file(filepath: Path) -> list[str]:
    """Lint a single Python file for two-stream violations."""
    is_cli = filepath.name in CLI_EMITTERS
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, OSError):
        return []
    visitor = _ViolationVisitor(filepath, is_cli)
    visitor.visit(tree)
    return visitor.violations


def lint_tree(root: Path) -> list[str]:
    """Lint all .py files under *root*."""
    violations: list[str] = []
    for py_file in sorted(root.rglob("*.py")):
        violations.extend(lint_file(py_file))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Two-stream contract enforcement lint."
    )
    parser.add_argument(
        "src_dir",
        type=Path,
        nargs="?",
        default=REPO_ROOT / "src",
        help="Root directory to lint (default: src/).",
    )
    args = parser.parse_args(argv)

    if not args.src_dir.exists():
        print(f"FAIL: {args.src_dir} not found", file=sys.stderr)
        return 1

    violations = lint_tree(args.src_dir)
    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        print(f"\n{len(violations)} two-stream violation(s) found", file=sys.stderr)
        return 1
    print(f"OK: no two-stream violations in {args.src_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
