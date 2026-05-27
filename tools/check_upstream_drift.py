"""Check upstream repo drift against pinned commits.

Reads port-recipe metadata from ``harvest_plan.md`` §5 and/or
``CONTRIBUTING.md`` "Third-party derivations" table. For each pinned
upstream, queries the GitHub API for the commit count since the pin.
Flags repos with >50 commits of drift (exit 1).

Usage::

    python tools/check_upstream_drift.py [--threshold N] [--format table|json]

Refs: supply_chain_security.md §3, harvest_plan.md §7.1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
HARVEST_PLAN = REPO_ROOT / "docs" / "central_idea" / "harvest_plan.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"

GITHUB_API = "https://api.github.com"

DEFAULT_THRESHOLD = 50


@dataclass
class UpstreamPin:
    """One upstream repo + its pinned commit."""

    repo: str  # "owner/repo" form
    pinned_sha: str
    source_file: str  # which file we read this from
    target_file: str = ""  # the ported target in our tree


@dataclass
class DriftResult:
    """Drift status for one upstream."""

    repo: str
    pinned_sha: str
    commits_since_pin: int | None = None
    last_commit_date: str = ""
    latest_sha: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Pin extraction
# ---------------------------------------------------------------------------

_RECIPE_HEADER_RE = re.compile(r"### Recipe 5\.\d+ .*\n")
_SOURCE_RE = re.compile(r"\*\*Source:\*\*\s+`?([^`\n]+)`?")
_TARGET_RE = re.compile(r"\*\*Target:\*\*\s+`?([^`\n]+)`?")
_COMMIT_SHA_RE = re.compile(r"Commit:\s+([0-9a-f]{40})")

_CONTRIB_TABLE_ROW_RE = re.compile(
    r"\|\s*`?(src/[^`|\n]+)`?\s*\|"  # group 1: target file
    r"\s*([^|\n]+?)\s*\|"  # group 2: upstream repo
    r"\s*([^|\n]+?)\s*\|"  # group 3: license
    r"\s*([^|\n]+?)\s*\|"  # group 4: upstream commit
    r"\s*([^|\n]+?)\s*\|"  # group 5: ported date
    r"\s*([^|\n]+?)\s*\|"  # group 6: DRI
    r"\s*([^|\n]*?)\s*\|",  # group 7: notes
)

_UPSTREAM_REPO_MAP: dict[str, str] = {
    "SolidworksMCP-python": "andrewbartels1/SolidworksMCP-python",
    "mcp-server-solidworks": "eyfel/mcp-server-solidworks",
    "Solidworks-MCP": "Samsaam-Ali-Baig/Solidworks-MCP",
    "CAD-MCP": "ruicao/CAD-MCP",
    "SolidworksMCP-TS": "ESPO-Corporation/SolidworksMCP-TS",
    "AI_CAD_Solidworks": "mohamedhamed98/AI_CAD_Solidworks",
    "pyswx": "qdm12/pyswx",
    "solidworks-api-develop": "angelsix/solidworks-api-develop",
    "codestack": "Xarial/Xarial.CadPlus",
}

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://github\.com/([^/\s)]+/[^/\s)]+?)/?\)")


def _resolve_repo_name(raw: str) -> str:
    """Map a loose upstream name to 'owner/repo' for the GitHub API.

    Accepts:
      - "owner/repo"            → returned as-is
      - "[name](github URL)"    → owner/repo extracted from the URL
      - "name" (bare)           → looked up in _UPSTREAM_REPO_MAP
    """
    raw = raw.strip()
    md = _MD_LINK_RE.search(raw)
    if md:
        return md.group(2)
    if "/" in raw:
        return raw
    return _UPSTREAM_REPO_MAP.get(raw, raw)


def read_pins_from_harvest_plan(path: Path | None = None) -> list[UpstreamPin]:
    """Extract pinned commits from harvest_plan.md §5 recipes."""
    if path is None:
        path = HARVEST_PLAN
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    pins: list[UpstreamPin] = []
    for m in _RECIPE_HEADER_RE.finditer(text):
        # Scan from this header until the next header or end of file
        start = m.end()
        next_header = _RECIPE_HEADER_RE.search(text, start)
        end = next_header.start() if next_header else len(text)
        block = text[start:end]

        source_match = _SOURCE_RE.search(block)
        target_match = _TARGET_RE.search(block)
        sha_match = _COMMIT_SHA_RE.search(block)

        if not source_match:
            continue
        source_raw = source_match.group(1).strip()
        target_raw = target_match.group(1).strip() if target_match else ""
        if not sha_match:
            continue
        pinned_sha = sha_match.group(1)
        repo = _resolve_repo_name(source_raw.split("/")[0].replace("-main", ""))
        if repo and "/" in repo:
            pins.append(
                UpstreamPin(
                    repo=repo,
                    pinned_sha=pinned_sha,
                    source_file=str(path),
                    target_file=target_raw,
                )
            )
    return pins


def read_pins_from_contributing(path: Path | None = None) -> list[UpstreamPin]:
    """Extract pinned commits from CONTRIBUTING.md 'Third-party derivations' table."""
    if path is None:
        path = CONTRIBUTING
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    pins: list[UpstreamPin] = []
    for m in _CONTRIB_TABLE_ROW_RE.finditer(text):
        target_file = m.group(1).strip().strip("`")
        upstream_raw = m.group(2).strip()
        commit_sha = m.group(4).strip()
        repo = _resolve_repo_name(upstream_raw)
        if repo and "/" in repo and commit_sha:
            pins.append(
                UpstreamPin(
                    repo=repo,
                    pinned_sha=commit_sha,
                    source_file=str(path),
                    target_file=target_file,
                )
            )
    return pins


def collect_pins() -> list[UpstreamPin]:
    """Collect all pins from both sources, deduplicating by repo."""
    seen: set[str] = set()
    pins: list[UpstreamPin] = []
    for pin in read_pins_from_contributing():
        key = f"{pin.repo}:{pin.pinned_sha}"
        if key not in seen:
            seen.add(key)
            pins.append(pin)
    for pin in read_pins_from_harvest_plan():
        key = f"{pin.repo}:{pin.pinned_sha}"
        if key not in seen:
            seen.add(key)
            pins.append(pin)
    return pins


# ---------------------------------------------------------------------------
# GitHub API queries
# ---------------------------------------------------------------------------


def _github_get(url: str, etag: str = "") -> tuple[Any, str]:
    """GET *url* from the GitHub API. Returns (parsed_json, etag)."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if etag:
        req.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            new_etag = resp.headers.get("ETag", "")
            return body, new_etag
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, etag
        raise


def check_drift(pin: UpstreamPin) -> DriftResult:
    """Query the GitHub compare API for commit count since *pinned_sha*."""
    if not pin.pinned_sha:
        return DriftResult(
            repo=pin.repo,
            pinned_sha="",
            error="no pinned commit SHA found",
        )
    owner_repo = pin.repo
    url = f"{GITHUB_API}/repos/{owner_repo}/compare/{pin.pinned_sha}...HEAD"
    try:
        data, _ = _github_get(url)
    except Exception as exc:
        return DriftResult(
            repo=pin.repo,
            pinned_sha=pin.pinned_sha,
            error=str(exc),
        )
    if data is None:
        return DriftResult(
            repo=pin.repo,
            pinned_sha=pin.pinned_sha,
            error="304 not modified (cached)",
        )
    if "status" in data and data["status"] == "identical":
        return DriftResult(
            repo=pin.repo,
            pinned_sha=pin.pinned_sha,
            commits_since_pin=0,
            latest_sha=pin.pinned_sha,
        )
    ahead_by = data.get("ahead_by", 0)
    commits = data.get("commits", [])
    last_date = ""
    latest_sha = pin.pinned_sha
    if commits:
        latest_sha = commits[-1].get("sha", pin.pinned_sha)
        commit_data = commits[-1].get("commit", {})
        last_date = commit_data.get("committer", {}).get("date", "")
    return DriftResult(
        repo=pin.repo,
        pinned_sha=pin.pinned_sha,
        commits_since_pin=ahead_by,
        last_commit_date=last_date,
        latest_sha=latest_sha,
    )


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def format_table(results: list[DriftResult]) -> str:
    """Format results as a markdown table."""
    lines = [
        "| Repo | Pinned SHA | Commits since pin | Last commit date | Latest SHA | Error |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        sha_short = r.pinned_sha[:12] if r.pinned_sha else "—"
        latest_short = r.latest_sha[:12] if r.latest_sha else "—"
        commits = str(r.commits_since_pin) if r.commits_since_pin is not None else "—"
        lines.append(
            f"| {r.repo} | {sha_short} | {commits} | {r.last_commit_date or '—'} "
            f"| {latest_short} | {r.error or ''} |"
        )
    return "\n".join(lines)


def format_json(results: list[DriftResult]) -> str:
    """Format results as JSON."""
    return json.dumps(
        [
            {
                "repo": r.repo,
                "pinned_sha": r.pinned_sha,
                "commits_since_pin": r.commits_since_pin,
                "last_commit_date": r.last_commit_date,
                "latest_sha": r.latest_sha,
                "error": r.error or None,
            }
            for r in results
        ],
        indent=2,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check upstream repo drift against pinned commits.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"Flag repos with more than N commits since the pin (default: {DEFAULT_THRESHOLD}).",
    )
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table).",
    )
    args = parser.parse_args(argv)

    pins = collect_pins()
    if not pins:
        print(
            "No upstream pins found in harvest_plan.md or CONTRIBUTING.md.",
            file=sys.stderr,
        )
        return 0

    results: list[DriftResult] = []
    for pin in pins:
        result = check_drift(pin)
        results.append(result)

    if args.fmt == "json":
        print(format_json(results))
    else:
        print(format_table(results))

    flagged = any(
        r.commits_since_pin is not None and r.commits_since_pin > args.threshold
        for r in results
    )
    if flagged:
        print(
            f"\nOne or more upstreams exceed the {args.threshold}-commit drift threshold.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
