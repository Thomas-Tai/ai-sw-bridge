#!/usr/bin/env python3
"""Unified honesty-gate lint over the user-facing English surfaces.

Broadens `tools/check_launch_kit.py`'s launch-kit-only scan to every
user-facing surface that ships honesty claims (spec §3, L6), and
consolidates the standalone demo-caption guard into the same scanner:

  * no placeholders (TODO / TBD / FIXME / `<...>` angle-bracket stubs) --
    launch copy only (site/, launch-kit/); general docs may say "TODO".
  * no phantom CLI claims (bare ``ai-sw-export`` -- real export is the spec
    export block or ``ai-sw-export-dxf-flat``) -- the broad surface: top-level
    docs, site/, launch-kit/, and the tools/demo_*.py renderers whose burned-in
    captions have shipped this phantom before (2026-08-14).
  * internal links / image assets resolve on disk -- README.md, site/,
    launch-kit/.

`docs/superpowers/`, `docs/archive/`, and `docs/i18n/` are always excluded:
they legitimately contain the banned `ai-sw-export` example as documentation
of the mistake, and i18n honesty is covered by its own gate
(tests/test_i18n_staleness.py).

The scan core (`scan()`) is a pure function of `repo_root` (and an optional
manifest override) so it can run against a synthetic tmp_path repo in tests
without touching the real tree.

Run from repo root::

    python tools/honesty_gate.py

Exit 0 clean, 1 if any violation. Follows the two-stream contract
(tools/two_stream_lint.py): human-readable violations grouped by surface go
to stderr, a machine "OK: ..." summary goes to stdout on a clean run.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from _honesty_checks import (
    check_internal_links,
    find_banned_claims,
    find_placeholders,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories whose contents are exempt from every check: they legitimately
# document the banned phantom-CLI example, archived history, or are covered
# by their own dedicated gate (i18n staleness).
EXCLUDED_PREFIXES = ("docs/superpowers/", "docs/archive/", "docs/i18n/")

# Violation kind labels (surface_path, kind, detail).
KIND_BANNED_TOKEN = "banned-token"
KIND_PLACEHOLDER = "placeholder"
KIND_BROKEN_LINK = "broken-link"


@dataclass(frozen=True)
class CheckSpec:
    """One check's surface scoping: explicit files + glob patterns, both
    relative-to-repo-root POSIX strings."""

    explicit: tuple[str, ...]
    globs: tuple[str, ...]


# Per-check surface scoping (paths relative to repo root). See module
# docstring for the rationale behind each surface set.
DEFAULT_MANIFEST: dict[str, CheckSpec] = {
    KIND_BANNED_TOKEN: CheckSpec(
        explicit=(
            "README.md",
            "USAGE.md",
            "docs/PUBLIC_API.md",
            "docs/CAPABILITIES.md",
            "docs/ONBOARDING.md",
        ),
        globs=(
            "site/**/*.md",
            "site/**/*.html",
            "launch-kit/**/*.md",
            "tools/demo_*.py",
        ),
    ),
    KIND_PLACEHOLDER: CheckSpec(
        explicit=(),
        globs=(
            "site/**/*.md",
            "site/**/*.html",
            "launch-kit/**/*.md",
        ),
    ),
    KIND_BROKEN_LINK: CheckSpec(
        explicit=("README.md",),
        globs=(
            "site/**/*.md",
            "site/**/*.html",
            "launch-kit/**/*.md",
        ),
    ),
}

__all__ = [
    "CheckSpec",
    "DEFAULT_MANIFEST",
    "EXCLUDED_PREFIXES",
    "REPO_ROOT",
    "main",
    "scan",
]


def _is_excluded(rel_posix: str) -> bool:
    return rel_posix.startswith(EXCLUDED_PREFIXES)


def _resolve_surface_files(repo_root: Path, spec: CheckSpec) -> list[Path]:
    """Resolve *spec*'s explicit files + glob patterns to concrete files.

    Missing explicit files are skipped (not an error). Glob patterns whose
    top-level directory doesn't exist yet contribute nothing. Paths under
    an excluded prefix (see EXCLUDED_PREFIXES) are dropped.
    """
    found: set[Path] = set()

    for rel in spec.explicit:
        candidate = repo_root / rel
        if candidate.is_file():
            found.add(candidate)

    for pattern in spec.globs:
        top = pattern.split("/", 1)[0]
        if not (repo_root / top).is_dir():
            continue
        for path in repo_root.glob(pattern):
            if path.is_file():
                found.add(path)

    kept = [
        path
        for path in found
        if not _is_excluded(path.relative_to(repo_root).as_posix())
    ]
    return sorted(kept)


def scan(
    repo_root: Path,
    manifest: dict[str, CheckSpec] | None = None,
) -> list[tuple[str, str, str]]:
    """Run all honesty checks over *repo_root*.

    Pure function: no globals beyond the manifest are consulted, so tests
    can point *repo_root* at a synthetic tmp_path tree. *manifest* overrides
    (partially or fully) DEFAULT_MANIFEST's per-check surface scoping.

    Returns violations as `(surface_path, kind, detail)` tuples, sorted for
    deterministic output. `surface_path` is POSIX-relative to *repo_root*.
    """
    active = {**DEFAULT_MANIFEST, **(manifest or {})}
    violations: list[tuple[str, str, str]] = []

    for path in _resolve_surface_files(repo_root, active[KIND_BANNED_TOKEN]):
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8")
        for token in find_banned_claims(text):
            violations.append((rel, KIND_BANNED_TOKEN, f"phantom CLI claim: `{token}`"))

    for path in _resolve_surface_files(repo_root, active[KIND_PLACEHOLDER]):
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8")
        for token in find_placeholders(text):
            violations.append((rel, KIND_PLACEHOLDER, f"placeholder: `{token}`"))

    for path in _resolve_surface_files(repo_root, active[KIND_BROKEN_LINK]):
        rel = path.relative_to(repo_root).as_posix()
        for detail in check_internal_links(path, repo_root):
            violations.append((rel, KIND_BROKEN_LINK, detail))

    violations.sort()
    return violations


def _scanned_file_count(repo_root: Path, manifest: dict[str, CheckSpec]) -> int:
    files: set[Path] = set()
    for spec in manifest.values():
        files.update(_resolve_surface_files(repo_root, spec))
    return len(files)


def main() -> int:
    violations = scan(REPO_ROOT)
    if violations:
        by_surface: dict[str, list[tuple[str, str]]] = {}
        for surface, kind, detail in violations:
            by_surface.setdefault(surface, []).append((kind, detail))
        for surface in sorted(by_surface):
            print(f"FAIL: {surface}", file=sys.stderr)
            for kind, detail in by_surface[surface]:
                print(f"  [{kind}] {detail}", file=sys.stderr)
        print(f"\n{len(violations)} violation(s) found.", file=sys.stderr)
        return 1
    scanned = _scanned_file_count(REPO_ROOT, DEFAULT_MANIFEST)
    print(f"OK: {scanned} surface file(s) pass the honesty gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
