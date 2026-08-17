"""Shared honesty-check primitives (spec §3, L6).

Single source of truth for the checks mechanized across the launch-kit lint
and its siblings:

  * no placeholders (TODO / TBD / FIXME / `<...>` angle-bracket stubs);
  * no phantom CLI claims (bare ``ai-sw-export`` — real export is the spec
    export block or ``ai-sw-export-dxf-flat``);
  * internal links / image assets resolve on disk.

This module has no CLI of its own; it is imported by tools/check_launch_kit.py
(and other honesty-gate callers).
"""

from __future__ import annotations

import re
from pathlib import Path

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
