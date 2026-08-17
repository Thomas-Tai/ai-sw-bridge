#!/usr/bin/env python3
"""Lint gate for the Project B landing page + launch kit.

Mechanizes the checkable parts of the honesty guardrails (spec §3, L6):

  * no placeholders (TODO / TBD / FIXME / `<...>` angle-bracket stubs);
  * no phantom CLI claims (bare ``ai-sw-export`` — real export is the spec
    export block or ``ai-sw-export-dxf-flat``);
  * internal links / image assets resolve on disk.

UTM correctness lives upstream in tools/launch_links.py (the generated
manifest is the source of truth); nuanced honesty (tone, framing, "wedge
not swipe") stays a human checklist.

Run from repo root::

    python tools/check_launch_kit.py

Exit 0 clean, 1 if any violation. Missing site/ or launch-kit/ is not an
error (nothing to lint yet).
"""
from __future__ import annotations

import sys
from pathlib import Path

from _honesty_checks import (
    find_placeholders,
    find_banned_claims,
    check_internal_links,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("site", "launch-kit")

__all__ = [
    "find_placeholders",
    "find_banned_claims",
    "check_internal_links",
    "lint_paths",
    "main",
    "SCAN_DIRS",
    "REPO_ROOT",
]


def lint_paths(paths: list[Path], repo_root: Path) -> list[str]:
    """Run all checks over each doc in *paths*; return flattened errors."""
    errors: list[str] = []
    for path in paths:
        rel = path.relative_to(repo_root)
        text = path.read_text(encoding="utf-8")
        errors += [f"{rel}: placeholder '{h}'" for h in find_placeholders(text)]
        errors += [f"{rel}: phantom CLI '{h}'" for h in find_banned_claims(text)]
        errors += check_internal_links(path, repo_root)
    return errors


def main() -> int:
    docs: list[Path] = []
    for name in SCAN_DIRS:
        base = REPO_ROOT / name
        if base.is_dir():
            docs += sorted(base.rglob("*.md"))
            docs += sorted(base.rglob("*.html"))
    if not docs:
        print("OK: nothing to lint yet (no site/ or launch-kit/ docs)")
        return 0
    errors = lint_paths(docs, REPO_ROOT)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"\n{len(errors)} violation(s) found.", file=sys.stderr)
        return 1
    print(f"OK: {len(docs)} doc(s) pass the launch-kit lint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
