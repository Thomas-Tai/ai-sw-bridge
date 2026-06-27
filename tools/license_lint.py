#!/usr/bin/env python3
"""License-compliance lint for ai-sw-bridge ported code.

Walks ``src/`` for files whose docstring contains a port marker
(``Ported from`` or ``Adapted from``), then verifies three attribution
surfaces:

  (a) Docstring: SPDX-style license name + source repo + commit hash.
  (b) CONTRIBUTING.md: a row in the "Third-party derivations" table
      referencing the same file and upstream.
  (c) README.md: an Acknowledgments line for the upstream repo.

Cross-references the upstream repo against the license matrix below
(mirrored from the CONTRIBUTING.md "Third-party derivations" table).
Fails on GPL or no-LICENSE upstreams — those are study-only.

Also checks that the top-level LICENSE file and pyproject.toml declared
license agree (both MIT; see docs/SECURITY.md §5).

Exit 0 if clean, 1 if violations found. Run from repo root::

    python tools/license_lint.py src/

Ref: docs/SECURITY.md §5, CONTRIBUTING.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Repos classified as GPL or no-license (see docs/SECURITY.md §5).
# Ports from these are forbidden; the lint rejects them outright.
FORBIDDEN_REPOS: dict[str, str] = {
    "pySolidWorks-main": "GPL-3.0",
    "swapi-pilot-solidworks-mcp-main": "NO LICENSE",
    "AI-SolidWorks-main": "NO LICENSE",
}

# Allowed upstream repos with their license classification (see CONTRIBUTING.md).
ALLOWED_REPOS: dict[str, str] = {
    "SolidworksMCP-python-main": "MIT",
    "mcp-server-solidworks-main": "MIT",
    "Solidworks-MCP-main": "MIT",
    "CAD-MCP-main": "MIT",
    "SolidworksMCP-TS-main": "MIT",
    "AI_CAD_Solidworks-main": "MIT",
    "pyswx-main": "MIT",
    "solidworks-api-develop": "MIT",
    "codestack-master": "MIT",
}

# Merge: any repo not in ALLOWED is unknown; any repo in FORBIDDEN is
# rejected regardless of whether it also appears in ALLOWED.
REPO_LICENSE: dict[str, str] = {**ALLOWED_REPOS, **FORBIDDEN_REPOS}

_PORT_MARKER_RE = re.compile(r"^(?:Ported|Adapted)\s+from\s+([^\s,.:;]+)", re.MULTILINE)
_LICENSE_RE = re.compile(r"\b(MIT|BSD-\d-Clause|Apache-2\.0|GPL-\d[\d.]*\+?|ISC)\b")
_COMMIT_RE = re.compile(r"\b[0-9a-f]{40}\b")

# CONTRIBUTING.md table-row pattern: | src/... | repo-name | license | commit | ...
_CONTRIB_ROW_RE = re.compile(
    r"^\|\s*`?((?:src/)?[^\s|`]+)`?\s*\|\s*([^|]+)\s*\|", re.MULTILINE
)

# README.md Acknowledgments section: look for repo names after "Acknowledgments"
_ACKNOWLEDGMENTS_HEADING_RE = re.compile(r"^##\s+Acknowledgments", re.MULTILINE)


def _find_ported_files(src_dir: Path) -> list[tuple[Path, str, str]]:
    """Walk *src_dir* for Python files with port markers.

    Returns list of (file_path, upstream_repo, full_marker_line).
    """
    results: list[tuple[Path, str, str]] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        m = _PORT_MARKER_RE.search(text)
        if m:
            results.append((py_file, m.group(1), m.group(0)))
    return results


def _check_docstring(file_path: Path, text: str) -> list[str]:
    """Verify surface (a): docstring contains license name and commit hash."""
    errors: list[str] = []
    has_license = _LICENSE_RE.search(text) is not None
    has_commit = _COMMIT_RE.search(text) is not None
    if not has_license:
        errors.append(f"{file_path}: docstring missing license name (e.g. MIT)")
    if not has_commit:
        errors.append(f"{file_path}: docstring missing 40-char commit hash")
    return errors


def _parse_contributing_table(contributing: Path) -> dict[str, str]:
    """Parse CONTRIBUTING.md "Third-party derivations" table rows.

    Returns mapping of ``relative_path → upstream_repo_name``.
    """
    if not contributing.exists():
        return {}
    text = contributing.read_text(encoding="utf-8")
    rows: dict[str, str] = {}
    for m in _CONTRIB_ROW_RE.finditer(text):
        file_ref = m.group(1).strip()
        repo_name = m.group(2).strip()
        if file_ref.startswith("src/"):
            rows[file_ref] = repo_name
    return rows


def _normalize_repo(name: str) -> str:
    """Normalize repo names for license-matrix comparison.

    The license matrix uses local-archive naming (`-main` / `-develop` /
    `-master` suffixes from GitHub ZIP downloads); docstrings and the README
    use the canonical upstream name. Strip the trailing suffix so both
    forms compare equal.
    """
    for suffix in ("-main", "-master", "-develop"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


_NORMALIZED_ALLOWED = {_normalize_repo(r): r for r in ALLOWED_REPOS}
_NORMALIZED_FORBIDDEN = {_normalize_repo(r): r for r in FORBIDDEN_REPOS}


def _parse_readme_acknowledgments(readme: Path) -> set[str]:
    """Extract upstream repo names mentioned in README Acknowledgments section.

    Returns matrix-form names (with `-main`/`-master`/`-develop` suffixes
    as they appear in the license matrix). The canonical form (without
    suffix) is also recognized in the README text but normalized back to
    the matrix-form name on return so downstream callers can compare to
    the matrix without ambiguity.
    """
    if not readme.exists():
        return set()
    text = readme.read_text(encoding="utf-8")
    m = _ACKNOWLEDGMENTS_HEADING_RE.search(text)
    if m is None:
        return set()
    ack_section = text[m.end() :]
    found: set[str] = set()
    for repo_name in REPO_LICENSE:
        canonical = _normalize_repo(repo_name)
        if repo_name in ack_section or canonical in ack_section:
            found.add(repo_name)
    return found


def _check_license_classification(upstream_repo: str, file_path: Path) -> list[str]:
    """Cross-reference the upstream repo against the license matrix.

    Comparison normalizes the local-archive `-main` / `-master` / `-develop`
    suffix so canonical names from docstrings match license-matrix entries.
    """
    errors: list[str] = []
    canonical = _normalize_repo(upstream_repo)
    if canonical in _NORMALIZED_FORBIDDEN:
        lic = FORBIDDEN_REPOS[_NORMALIZED_FORBIDDEN[canonical]]
        errors.append(
            f"{file_path}: upstream {upstream_repo} is {lic} — "
            f"study-only, porting is forbidden (see docs/SECURITY.md §5)"
        )
    elif canonical not in _NORMALIZED_ALLOWED:
        errors.append(
            f"{file_path}: upstream {upstream_repo} not found in "
            f"license matrix (see CONTRIBUTING.md) — classify before porting"
        )
    return errors


def _check_top_level_license(root_dir: Path) -> list[str]:
    """Verify the proprietary commercial license is in place and consistent.

    The project went proprietary at v1.5.0 (the commercial LICENSE template);
    pyproject must declare it, and the bundled MIT upstream (SolidworksMCP-python)
    must keep its attribution in THIRD-PARTY-NOTICES.md.
    """
    errors: list[str] = []
    license_file = root_dir / "LICENSE"
    pyproject = root_dir / "pyproject.toml"
    notices = root_dir / "THIRD-PARTY-NOTICES.md"

    if license_file.exists():
        if "Commercial Software License" not in license_file.read_text(
            encoding="utf-8"
        ):
            errors.append("LICENSE is not the proprietary commercial license")
    else:
        errors.append("LICENSE file missing")

    if pyproject.exists():
        if "Proprietary" not in pyproject.read_text(encoding="utf-8"):
            errors.append("pyproject.toml does not declare a Proprietary license")

    if notices.exists():
        ntext = notices.read_text(encoding="utf-8")
        if "SolidworksMCP-python" not in ntext or "MIT" not in ntext:
            errors.append(
                "THIRD-PARTY-NOTICES.md missing the SolidworksMCP-python MIT notice"
            )
    else:
        errors.append("THIRD-PARTY-NOTICES.md missing (bundled MIT attribution)")

    return errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="License-compliance lint for ported code."
    )
    parser.add_argument(
        "src_dir",
        nargs="?",
        default="src",
        help="Directory to scan (default: src).",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root directory (default: inferred from script location).",
    )
    args = parser.parse_args()

    root_dir = Path(args.root) if args.root else REPO_ROOT
    src_dir = root_dir / args.src_dir
    if not src_dir.is_dir():
        print(f"FAIL: {src_dir} is not a directory", file=sys.stderr)
        return 1

    contributing = root_dir / "CONTRIBUTING.md"
    readme = root_dir / "README.md"

    all_errors: list[str] = []

    ported_files = _find_ported_files(src_dir)

    if not ported_files:
        print("OK: no ported files found in src/")
        all_errors.extend(_check_top_level_license(root_dir))
        if all_errors:
            for e in all_errors:
                print(f"FAIL: {e}", file=sys.stderr)
            return 1
        return 0

    contrib_rows = _parse_contributing_table(contributing)
    ack_repos = _parse_readme_acknowledgments(readme)

    for file_path, upstream_repo, marker_line in ported_files:
        rel = str(file_path.relative_to(root_dir)).replace("\\", "/")
        text = file_path.read_text(encoding="utf-8")

        # Surface (a): docstring SPDX + source + commit
        all_errors.extend(_check_docstring(file_path, text))

        # Surface (b): CONTRIBUTING.md row
        if rel not in contrib_rows:
            all_errors.append(f"{rel}: no CONTRIBUTING.md row for this ported file")

        # Surface (c): README.md Acknowledgments line
        canonical = _normalize_repo(upstream_repo)
        ack_canonicals = {_normalize_repo(r) for r in ack_repos}
        if canonical not in ack_canonicals:
            all_errors.append(
                f"{rel}: upstream {upstream_repo} not mentioned in "
                f"README.md Acknowledgments"
            )

        # License matrix cross-reference
        all_errors.extend(_check_license_classification(upstream_repo, file_path))

    # Check for CONTRIBUTING.md rows that reference files not in src/
    ported_paths = {
        str(fp.relative_to(root_dir)).replace("\\", "/") for fp, _, _ in ported_files
    }
    for row_path in contrib_rows:
        if row_path not in ported_paths:
            all_errors.append(
                f"CONTRIBUTING.md references {row_path} but no port marker "
                f"found in that file"
            )

    # Top-level license consistency
    all_errors.extend(_check_top_level_license(root_dir))

    if all_errors:
        for e in all_errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"\n{len(all_errors)} violation(s) found.", file=sys.stderr)
        return 1

    print(f"OK: {len(ported_files)} ported file(s) pass license lint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
