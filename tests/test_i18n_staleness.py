"""Model-B i18n honesty gate: a mirror is stale IFF it declares itself stale.

stale(mirror) := the English source advanced past the mirror's translated-from
SHA (git rev-list <sha0>..HEAD -- <source> is non-empty). A stale mirror MUST
carry the sentinel <!-- i18n-staleness-banner -->; a fresh one must NOT. Also
enforces structural fidelity (frontmatter, DO-NOT-TRANSLATE tokens) and zero
dead relative links. English stays authoritative; honest lag is allowed,
silent rot is not.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "<!-- i18n-staleness-banner -->"

# manifest: mirror (repo-relative) -> English source (repo-relative)
I18N_MIRRORS = {
    "docs/i18n/zh-CN/README.md": "README.md",
    "docs/i18n/zh-CN/USAGE.md": "USAGE.md",
    "docs/i18n/zh-CN/PUBLIC_API.md": "docs/PUBLIC_API.md",
    "docs/i18n/zh-TW/README.md": "README.md",
    "docs/i18n/zh-TW/USAGE.md": "USAGE.md",
    "docs/i18n/zh-TW/PUBLIC_API.md": "docs/PUBLIC_API.md",
}

# high-signal DO-NOT-TRANSLATE tokens that must survive verbatim if the English
# source contains them.
DNT_TOKENS = ("ai-sw-build", "ai-sw-mcp", "SolidWorksClient", "spec.json", "--locale")

# The translated-from line lives inside the YAML frontmatter block (line 2,
# after the opening ---), so anchor to line-start with re.M, NOT \A (which
# only matches the absolute start of the string == the leading ---).
_FRONTMATTER_RE = re.compile(r"^translated-from:\s*([0-9a-f]{7,40})\s*$", re.M)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True)


def _git_available() -> bool:
    if shutil.which("git") is None:
        return False
    return _git("rev-parse", "--git-dir").returncode == 0


def _translated_from(mirror_text: str) -> str | None:
    m = _FRONTMATTER_RE.search(mirror_text)
    return m.group(1) if m else None


def _source_advanced_past(sha0: str, source: str) -> bool:
    """True if <source> has commits after sha0 (mirror is stale)."""
    out = _git("rev-list", f"{sha0}..HEAD", "--", source)
    return bool(out.stdout.strip())


def _relative_links(text: str) -> list[str]:
    # ](target) where target is not http(s), not an in-page #anchor, not a mailto
    links = re.findall(r"\]\(([^)]+)\)", text)
    out = []
    for t in links:
        t = t.split(" ", 1)[0].split("#", 1)[0].strip()
        if not t or t.startswith(("http://", "https://", "mailto:")):
            continue
        out.append(t)
    return out


pytestmark = pytest.mark.skipif(
    not _git_available(),
    reason="git history unavailable (shallow/no-git); CI runs with fetch-depth:0",
)


@pytest.mark.parametrize("mirror,source", list(I18N_MIRRORS.items()))
def test_mirror_exists_and_declares_translated_from(mirror: str, source: str) -> None:
    mp = _ROOT / mirror
    assert mp.is_file(), f"manifest lists {mirror} but it is missing on disk"
    assert (_ROOT / source).is_file(), f"source {source} for {mirror} missing"
    sha0 = _translated_from(mp.read_text(encoding="utf-8"))
    assert sha0, f"{mirror} lacks a translated-from: <sha> frontmatter"
    assert (
        _git("cat-file", "-e", sha0).returncode == 0
    ), f"{mirror} translated-from {sha0} is not in git history (rebase/force-push?)"


@pytest.mark.parametrize("mirror,source", list(I18N_MIRRORS.items()))
def test_model_b_biconditional(mirror: str, source: str) -> None:
    text = (_ROOT / mirror).read_text(encoding="utf-8")
    sha0 = _translated_from(text)
    assert sha0
    stale = _source_advanced_past(sha0, source)
    has_banner = SENTINEL in text
    assert stale == has_banner, (
        f"{mirror}: stale={stale} but sentinel_present={has_banner} — "
        f"a stale mirror must carry {SENTINEL!r}; a fresh one must not."
    )


@pytest.mark.parametrize("mirror,source", list(I18N_MIRRORS.items()))
def test_no_dead_relative_links(mirror: str, source: str) -> None:
    mp = _ROOT / mirror
    dead = [
        t
        for t in _relative_links(mp.read_text(encoding="utf-8"))
        if not (mp.parent / t).resolve().exists()
    ]
    assert not dead, f"{mirror} has dead relative links: {dead}"


@pytest.mark.parametrize("mirror,source", list(I18N_MIRRORS.items()))
def test_do_not_translate_tokens_preserved(mirror: str, source: str) -> None:
    src = (_ROOT / source).read_text(encoding="utf-8")
    mir = (_ROOT / mirror).read_text(encoding="utf-8")
    missing = [tok for tok in DNT_TOKENS if tok in src and tok not in mir]
    assert (
        not missing
    ), f"{mirror} dropped DO-NOT-TRANSLATE tokens present in {source}: {missing}"


def test_manifest_matches_disk() -> None:
    """Every *.md under docs/i18n/<loc>/ must be in the manifest (no untracked mirror)."""
    # Manifest keys are already repo-relative forward-slash strings; compare
    # against the same normalized form (str(Path(...)) would inject backslashes
    # on Windows and spuriously flag every mirror as a stray).
    tracked = set(I18N_MIRRORS)
    on_disk = {
        str(p.relative_to(_ROOT)).replace("\\", "/")
        for p in (_ROOT / "docs" / "i18n").glob("zh-*/*.md")
    }
    strays = on_disk - tracked
    assert (
        not strays
    ), f"mirror files on disk but not in I18N_MIRRORS manifest: {strays}"
