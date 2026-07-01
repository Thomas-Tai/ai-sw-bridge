#!/usr/bin/env python3
"""Module-size budget gate.

New hand-written ``src/`` modules must stay <= CEILING (800) lines. Modules
already over budget are grandfathered in ``module_size_baseline.json`` and may
only SHRINK (a ratchet). Generated files (header ``DO NOT HAND-EDIT``) are
exempt.

Warn mode (default): prints violations, exits 0. --strict: exits 1 on any
violation. --update-baseline: rewrites the baseline from the current tree.

Run from repo root: python tools/module_size_gate.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
BASELINE_PATH = REPO_ROOT / "tools" / "module_size_baseline.json"
CEILING = 800
_GENERATED_MARKER = "DO NOT HAND-EDIT"


def count_loc(path: Path) -> int:
    """Physical line count of a file (matches ``wc -l`` semantics closely)."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def _is_generated(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return False
    return _GENERATED_MARKER in head


def scan(root: Path = SRC) -> dict[str, int]:
    """Map repo-relative path -> LOC for every non-generated ``*.py`` under root."""
    result: dict[str, int] = {}
    for py in sorted(root.rglob("*.py")):
        if "__pycache__" in py.parts or _is_generated(py):
            continue
        result[py.relative_to(REPO_ROOT).as_posix()] = count_loc(py)
    return result


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def check(
    scan_result: dict[str, int],
    baseline: dict[str, int],
    *,
    ceiling: int = CEILING,
) -> list[str]:
    """Return a list of violation strings (empty == pass)."""
    violations: list[str] = []
    for path, loc in sorted(scan_result.items()):
        base = baseline.get(path)
        if base is None:
            if loc > ceiling:
                violations.append(
                    f"{path}: NEW module is {loc} LOC (> {ceiling} ceiling). "
                    f"Split it, or add an explicit waiver via --update-baseline "
                    f"with a rationale in the PR."
                )
        elif loc > base:
            violations.append(
                f"{path}: grew {base} -> {loc} LOC. Grandfathered modules are "
                f"shrink-only; move new code into a focused module."
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Module-size budget gate")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    current = scan()
    if args.update_baseline:
        over = {p: n for p, n in current.items() if n > CEILING}
        BASELINE_PATH.write_text(
            json.dumps(over, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"baseline updated: {len(over)} grandfathered modules", file=sys.stderr)
        return 0

    violations = check(current, load_baseline())
    if not violations:
        print("module-size gate: OK", file=sys.stderr)
        return 0
    print("module-size gate violations:", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
