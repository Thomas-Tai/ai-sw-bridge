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

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("site", "launch-kit")

_PLACEHOLDER_RE = re.compile(
    r"\b(?:TODO|TBD|FIXME|XXX)\b"  # bare dev markers (case-sensitive)
    r"|<[A-Za-z0-9]*_[A-Za-z0-9_]*>"  # <UPPER_UNDERSCORE> stubs (HTML tags have no '_')
    r"|(?i:<[a-z0-9 _-]*\b(?:here|placeholder)\b[a-z0-9 _-]*>)"  # <name here> / <placeholder>
)
# Bare `ai-sw-export` as a whole token: real word ends here, is not the
# real `ai-sw-export-dxf-flat` CLI, and is not a longer word like `ai-sw-exporter`.
_BANNED_RE = re.compile(r"ai-sw-export\b(?!-)")
# Markdown ![alt](path) and [text](path); HTML src="path" / href="path".
_MD_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_HTML_ASSET_RE = re.compile(r'(?:src|href)="([^"]+)"')


def find_placeholders(text: str) -> list[str]:
    """Return placeholder tokens found in *text* (one per match)."""
    return [m.group(0) for m in _PLACEHOLDER_RE.finditer(text)]


def find_banned_claims(text: str) -> list[str]:
    """Return phantom-CLI claims found in *text*."""
    return [m.group(0) for m in _BANNED_RE.finditer(text)]


def _is_internal(target: str) -> bool:
    """True if *target* is a repo-local path (not http, mailto, or anchor)."""
    return not target.startswith(("http://", "https://", "mailto:", "#"))


def check_internal_links(doc_path: Path, repo_root: Path) -> list[str]:
    """Verify every internal link/asset in *doc_path* resolves on disk."""
    text = doc_path.read_text(encoding="utf-8")
    targets = _MD_LINK_RE.findall(text) + _HTML_ASSET_RE.findall(text)
    errors: list[str] = []
    for raw in targets:
        target = raw.split("#", 1)[0].split("?", 1)[0].strip()
        if not target or not _is_internal(target):
            continue
        if target.startswith("/"):
            resolved = (repo_root / target.lstrip("/")).resolve()
        else:
            resolved = (doc_path.parent / target).resolve()
        if not resolved.exists():
            errors.append(f"{doc_path.name}: broken internal link -> {target}")
    return errors


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
