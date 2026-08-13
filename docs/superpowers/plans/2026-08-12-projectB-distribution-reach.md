# Project B — Distribution / Reach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the evergreen reach assets (landing-page Spine, MCP-registry listings, "AI + SOLIDWORKS" explainer) and a complete draft-and-hold launch kit that makes **ai-sw-bridge** the reflex answer to "how do I drive SOLIDWORKS from an AI agent?" — measurable via UTM instrumentation, with the coordinated launch held until Project A's Phase-2 deep clips land.

**Architecture:** Two small typed Python tools form the verification spine — `tools/launch_links.py` (the single source of truth for UTM-tagged links) and `tools/check_launch_kit.py` (a placeholder / dead-link / canonical / UTM / honesty lint). On top of them sit the authored assets: one self-contained `site/index.html` landing page (fold + wedge + two-doorway persona router + 5-beat reference essay + AI/SOLIDWORKS explainer + per-tribe CTAs) and a `launch-kit/` folder of channel-adapted draft copy (L1–L7 + A2 registry listings). Buildable-now assets (Tasks 1–8) are separated from GATED steps (Tasks 9–10) that wait on Project A Phase-2 and the git-hold lift.

**Tech Stack:** Python 3.10+ (stdlib only — `urllib.parse`, `argparse`, `pathlib`, `re`), pytest, self-contained HTML/CSS (no Jekyll build, no external CDN), Markdown.

## Global Constraints

Every task's requirements implicitly include this section. Copy these verbatim into each reviewer dispatch.

- **GIT ON HOLD.** Working-tree edits ONLY. No `git commit`, no `git add`-for-commit, no `git push`, no branch creation, this entire plan. Every task ends in a **Checkpoint** (run tests/lint + `git status` to confirm only expected files changed), NOT a commit. The batch commit happens only after the hold lifts (out of scope here).
- **Never** append a `Co-Authored-By: Claude` trailer to any commit (applies whenever the hold later lifts).
- **L6 honesty (non-negotiable).** Every claim in every asset is defensible: (a) no phantom CLI — `ai-sw-export` as a bare command does NOT exist (real export is the spec export block or `ai-sw-export-dxf-flat`); (b) the wedge is a factual contrast ("native editable feature tree vs. a foreign STEP dump from a throwaway kernel"), never a swipe at a named competitor; (c) SOLIDWORKS is a plain requirement, never an endorsement; (d) any experimental / not-yet-deep feature is labeled as such; (e) license history stated plainly (MIT ≤ v1.4, commercial since v1.5).
- **Wedge voice matches the README verbatim** (`README.md:3-5`): *"Drive your real SOLIDWORKS seat from a JSON spec. Native `.SLDPRT` / `.SLDASM` / `.SLDDRW` with a real, editable feature tree — not a foreign STEP dump from a throwaway kernel."* The landing page and README share ONE wedge voice.
- **Canonical landing URL** (default, host-agnostic): `https://thomas-tai.github.io/ai-sw-bridge/`. It is a single parameter (`--base-url`) everywhere — swapping in a custom domain later is one flag, no copy edits. `rel="canonical"` targets this URL.
- **Hard sequencing gate.** The coordinated launch fire (Task 10) and the hero-freshness re-verify (Task 9) do NOT run until Project A Phase-2 deep clips (observe / drawing / export) land and the hero recomposes over them (`docs/superpowers/notes/2026-08-12-phase2-findings.md`). Tasks 1–8 are fully buildable now.
- **Python / test conventions.** Interpreter `C:/Python314/python.exe`. Tools live in `tools/*.py` as standalone `argparse` scripts: `from __future__ import annotations`, fully type-annotated (mypy runs in CI over `tools/`), `def main() -> int`, `if __name__ == "__main__": sys.exit(main())`, exit `0` clean / `1` on violations, `REPO_ROOT = Path(__file__).resolve().parent.parent`. Tests live in `tests/tools/test_*.py` and import the tool by adding `tools/` to `sys.path` (see the exact stanza in Task 1). Run tests from repo root: `python -m pytest tests/tools/test_<name>.py -v`. Keep lines ≤ 88 chars (black + flake8 in CI).
- **No commit steps in this plan.** Wherever the standard template would `git commit`, this plan substitutes a Checkpoint.

**Spec:** `docs/superpowers/specs/2026-08-12-projectB-distribution-reach-design.md` (design approved; audit findings F1–F9 folded 2026-08-12).

**Directory layout produced by this plan:**
- `tools/launch_links.py`, `tools/check_launch_kit.py` — the verification spine.
- `tests/tools/test_launch_links.py`, `tests/tools/test_check_launch_kit.py`.
- `site/index.html` — A1 landing page (self-contained). `site/README.md` — publish-decision note.
- `launch-kit/utm_links.md` — generated link manifest. `launch-kit/A2-registry-listings.md`, `launch-kit/L1-show-hn.md`, `launch-kit/L2-x-thread.md`, `launch-kit/L3-linkedin.md`, `launch-kit/L4-reddit-solidworks.md`, `launch-kit/L4-reddit-mcp.md`, `launch-kit/L5-product-hunt.md`, `launch-kit/L6-timing-checklist.md`, `launch-kit/L7-faq-crib.md`, `launch-kit/README.md`.

---

# PHASE B1 — BUILDABLE NOW (Tasks 1–8)

Fully executable under the git hold. Nothing here depends on Project A Phase-2.

---

### Task 1: UTM link builder — the single source of truth for launch links

**Files:**
- Create: `tools/launch_links.py`
- Test: `tests/tools/test_launch_links.py`
- Generates: `launch-kit/utm_links.md`

**Interfaces:**
- Produces (consumed by Task 2's lint and every launch-copy task):
  - `CHANNELS: dict[str, tuple[str, str, str]]` — channel key → `(utm_source, utm_medium, utm_content)`.
  - `build_utm_url(base_url: str, source: str, medium: str, campaign: str, content: str | None = None) -> str`
  - `canonical_links(base_url: str = DEFAULT_BASE_URL, campaign: str = DEFAULT_CAMPAIGN) -> dict[str, str]`
  - `render_manifest(links: dict[str, str]) -> str`
  - `DEFAULT_BASE_URL = "https://thomas-tai.github.io/ai-sw-bridge/"`

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_launch_links.py`:

```python
import pathlib
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import launch_links as ll  # noqa: E402


def test_build_utm_url_adds_all_params():
    url = ll.build_utm_url("https://example.com/", "hn", "referral",
                           "launch", "show-hn")
    q = parse_qs(urlsplit(url).query)
    assert q["utm_source"] == ["hn"]
    assert q["utm_medium"] == ["referral"]
    assert q["utm_campaign"] == ["launch"]
    assert q["utm_content"] == ["show-hn"]


def test_build_utm_url_preserves_existing_query():
    url = ll.build_utm_url("https://example.com/?ref=x", "hn",
                           "referral", "launch")
    q = parse_qs(urlsplit(url).query)
    assert q["ref"] == ["x"]
    assert q["utm_source"] == ["hn"]


def test_canonical_links_covers_every_channel():
    links = ll.canonical_links("https://example.com/")
    assert set(links) == set(ll.CHANNELS)
    for url in links.values():
        assert "utm_source=" in url and "utm_campaign=" in url


def test_render_manifest_is_generated_and_sorted():
    md = ll.render_manifest({"b": "https://b", "a": "https://a"})
    assert "GENERATED" in md
    assert md.index("`a`") < md.index("`b`")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/tools/test_launch_links.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'launch_links'`.

- [ ] **Step 3: Write the implementation**

Create `tools/launch_links.py`:

```python
#!/usr/bin/env python3
"""Canonical UTM-tagged launch links for the Project B launch kit.

Single source of truth for every outbound link in the launch copy, so the
mindshare funnel is measurable (spec §3, finding F8). Each channel maps to a
fixed (utm_source, utm_medium, utm_content) triple; the campaign and base URL
are parameters, so the github.io default can become a custom domain with one
flag and zero copy edits.

Run from repo root::

    python tools/launch_links.py
    python tools/launch_links.py --base-url https://ai-sw-bridge.example/

Exit 0 on success.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://thomas-tai.github.io/ai-sw-bridge/"
DEFAULT_CAMPAIGN = "launch"
DEFAULT_OUT = "launch-kit/utm_links.md"

# channel key -> (utm_source, utm_medium, utm_content)
CHANNELS: dict[str, tuple[str, str, str]] = {
    "show-hn": ("news.ycombinator.com", "referral", "show-hn"),
    "x": ("x.com", "social", "launch-thread"),
    "linkedin": ("linkedin.com", "social", "launch-article"),
    "reddit-solidworks": ("reddit.com", "social", "r-solidworks"),
    "reddit-mcp": ("reddit.com", "social", "r-mcp"),
    "product-hunt": ("producthunt.com", "referral", "launch"),
    "mcp-registry": ("mcp-registry", "referral", "listing"),
}


def build_utm_url(
    base_url: str,
    source: str,
    medium: str,
    campaign: str,
    content: str | None = None,
) -> str:
    """Return *base_url* with utm_* params merged in (existing query kept)."""
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query))
    query["utm_source"] = source
    query["utm_medium"] = medium
    query["utm_campaign"] = campaign
    if content:
        query["utm_content"] = content
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def canonical_links(
    base_url: str = DEFAULT_BASE_URL,
    campaign: str = DEFAULT_CAMPAIGN,
) -> dict[str, str]:
    """Return {channel: utm_url} for every launch channel."""
    return {
        channel: build_utm_url(base_url, src, med, campaign, content)
        for channel, (src, med, content) in CHANNELS.items()
    }


def render_manifest(links: dict[str, str]) -> str:
    """Render channel->url as a markdown table (a generated file)."""
    lines = [
        "<!-- GENERATED by tools/launch_links.py — do not edit by hand. -->",
        "# Canonical launch links (UTM-tagged)",
        "",
        "| Channel | Link |",
        "|---|---|",
    ]
    for channel in sorted(links):
        lines.append(f"| `{channel}` | {links[channel]} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate UTM launch links.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    links = canonical_links(args.base_url, args.campaign)
    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_manifest(links) + "\n", encoding="utf-8")
    print(f"OK: wrote {len(links)} links to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/tools/test_launch_links.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Generate the manifest**

Run: `python tools/launch_links.py`
Expected: `OK: wrote 7 links to launch-kit/utm_links.md`, and `launch-kit/utm_links.md` exists with 7 rows, each carrying `utm_source=…&utm_medium=…&utm_campaign=launch&utm_content=…`.

- [ ] **Step 6: Checkpoint (no commit — git hold)**

Run: `git status --short`. Expected new files only: `tools/launch_links.py`, `tests/tools/test_launch_links.py`, `launch-kit/utm_links.md`. Do NOT commit.

---

### Task 2: Launch-kit lint gate — the verification backbone

**Files:**
- Create: `tools/check_launch_kit.py`
- Test: `tests/tools/test_check_launch_kit.py`

**Interfaces:**
- Consumes: nothing (Python stdlib only).
- Produces (used as the verification command in Tasks 3–8):
  - `find_placeholders(text: str) -> list[str]`
  - `find_banned_claims(text: str) -> list[str]`
  - `check_internal_links(doc_path: Path, repo_root: Path) -> list[str]`
  - `lint_paths(paths: list[Path], repo_root: Path) -> list[str]`
  - `main() -> int` — scans `site/` + `launch-kit/`, prints `FAIL: …` lines, exit 1 if any.

This gate mechanizes the parts of L6 that can be checked without judgment: no placeholders, no phantom CLI, internal links/assets resolve. UTM correctness is guaranteed upstream (Task 1's generated manifest is the single source of truth for tagged links) and confirmed by the manual cross-check in Task 8; nuanced honesty (tone, "wedge not swipe") stays a manual checklist in each content task.

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_check_launch_kit.py`:

```python
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_launch_kit as ck  # noqa: E402


def test_find_placeholders_flags_todo_and_tbd():
    hits = ck.find_placeholders("intro\nTODO: write this\nmid\nTBD later\n")
    assert len(hits) == 2


def test_find_placeholders_clean_text_is_empty():
    assert ck.find_placeholders("A finished, honest paragraph.") == []


def test_find_banned_claims_flags_phantom_export_cli():
    assert ck.find_banned_claims("run `ai-sw-export part.json`") != []


def test_find_banned_claims_allows_real_dxf_cli():
    assert ck.find_banned_claims("run `ai-sw-export-dxf-flat sheet.json`") == []


def test_check_internal_links_flags_missing_asset(tmp_path):
    doc = tmp_path / "page.md"
    doc.write_text("![hero](img/missing.gif)\n", encoding="utf-8")
    errs = ck.check_internal_links(doc, tmp_path)
    assert any("missing.gif" in e for e in errs)


def test_check_internal_links_passes_existing_asset(tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "hero.gif").write_bytes(b"GIF89a")
    doc = tmp_path / "page.md"
    doc.write_text("![hero](img/hero.gif)\n", encoding="utf-8")
    assert ck.check_internal_links(doc, tmp_path) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/tools/test_check_launch_kit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'check_launch_kit'`.

- [ ] **Step 3: Write the implementation**

Create `tools/check_launch_kit.py`:

```python
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

_PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b|<[a-z_]+ ?(?:here|placeholder)>")
# Bare `ai-sw-export` NOT followed by `-dxf-flat` (the one real export CLI).
_BANNED_RE = re.compile(r"ai-sw-export(?!-dxf-flat)")
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/tools/test_check_launch_kit.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Smoke-run the gate**

Run: `python tools/check_launch_kit.py`
Expected: `OK: 1 doc(s) pass the launch-kit lint` (it sees only `launch-kit/utm_links.md` from Task 1) — exit 0.

- [ ] **Step 6: Checkpoint (no commit — git hold)**

Run: `git status --short`. Expected new files: `tools/check_launch_kit.py`, `tests/tools/test_check_launch_kit.py`. Do NOT commit.

---

### Task 3: A1 — the landing-page Spine (`site/index.html`)

**Files:**
- Create: `site/index.html` — self-contained landing page (inline `<style>`, no external CDN, responsive, theme-aware via `prefers-color-scheme`).
- Create: `site/README.md` — records the publish-mechanism decision (buildable-now structure; publish gated).

**Interfaces:**
- Consumes: the README wedge voice (`README.md:3-5`); the hero at `docs/img/demo_hero.gif`; `QUICKSTART.md`; `docs/operator_guide.md`.
- Produces: the canonical page every off-site asset links to (`rel="canonical"` target).

This one file is the whole page — build it section by section (each step below) so there is never a placeholder-bearing intermediate state that the Task 2 lint would reject. Resolves spec open question #2: **A4 explainer is a section within A1**, not a standalone page.

- [ ] **Step 1: Page shell + the fold (hero + wedge)**

Create `site/index.html` with: `<!doctype html>`, `<html lang="en">`, a `<title>ai-sw-bridge — drive real SOLIDWORKS from an AI agent</title>`, an inline `<style>` block (system-font stack, max-width ~760px content column, light/dark via `@media (prefers-color-scheme: dark)`), and the **fold**:
  - The hero image: `<img src="../docs/img/demo_hero.gif" alt="ai-sw-bridge builds a pillow-block widget end-to-end on a live SOLIDWORKS seat — part, assembly, observe, drawing, export">`. **All internal links on this page use the same `../`-relative-to-`site/` convention** (`../QUICKSTART.md`, `../docs/operator_guide.md`, …) so they resolve on disk and the Task 2 lint passes; the publish-time path rewrite is settled in `site/README.md` and Task 10.
  - The wedge headline, verbatim voice from the README: **"Drive your real SOLIDWORKS seat from a JSON spec."** with the sub-line **"Native `.SLDPRT` / `.SLDASM` / `.SLDDRW` with a real, editable feature tree — not a foreign STEP dump from a throwaway kernel."**
  - A one-line pipeline caption: *"One spec → parts → assembly → observe/DFM → drawing → export, on a live SOLIDWORKS seat, human-gated (propose → approve → execute)."*
  - A "Requires SOLIDWORKS 2021+" note rendered as a plain requirement (not an endorsement) — mirrors the README badge.

- [ ] **Step 2: The two-doorway persona router**

Add a `<section>` titled "Who are you? → start here" with exactly two doorways (mirror the README persona-router pattern), each a card:
  - **AI-agent / MCP builder** — framing: *"An MCP server that drives a real SOLIDWORKS seat — safely, human-gated."*
  - **SOLIDWORKS practitioner** — framing: *"Let Claude do your drafting — you approve every step."* (Per F2, this framing must be immediately qualified by control/correctness — see Step 4's CTA.)
  Both doorways link down to the same reference essay + demo; they fork only at framing, never 2× content.

- [ ] **Step 3: The heart — the 5-beat reference essay + A4 explainer section**

Add `<article>` "Driving real SOLIDWORKS from an AI agent — and why it's hard" — the citable artifact. Five `<h2>`/`<h3>` beats, each a short honest paragraph (2–4 sentences), no placeholders:
  1. **The problem** — AI agents can emit CAD, but "CAD" usually means a dead STEP/mesh from a throwaway kernel; nothing you can open and edit in your real tool.
  2. **Propose → approve → execute (human-gated safety)** — the agent proposes a spec, you approve, only then does it execute against your seat; nothing silent, every step reversible/visible.
  3. **Native editable feature tree vs. foreign STEP** — the output is a real `.SLDPRT` feature tree you keep editing, not an import you can only push around.
  4. **The real kernel walls** — state as fact, not spin: a whole class of features (lofts, ribs, wraps, combines and the like) can't be driven out-of-process, so the bridge refuses them cleanly rather than emit a broken part; and in dimensioned mode a handful of SOLIDWORKS dimension dialogs still need a human tick. These are labeled honestly, not hidden. (Cross-reference `../docs/known_limitations.md`.) NOTE: do NOT cite mates as a wall — per known_limitations.md §8 the mates limitation is RESOLVED and verified (concentric mate, interference_count=0); the earlier "mates land out-of-plane" wording was stale and was corrected 2026-08-13.
  5. **Try it with no seat** — you can author + lint a spec offline with zero license (Tier A); geometry needs a seat (Tier B). Link `../QUICKSTART.md`.
  Immediately after, an **"AI + SOLIDWORKS — which fits your job?" (A4)** subsection: an honest side-by-side — *real-seat / native-feature-tree* vs. *throwaway-kernel → STEP* — framed as "which fits your job," never a swipe. This is the backbone the launch essay (L1/L3) reuses.

- [ ] **Step 4: Per-tribe CTAs (finding F1)**

Add a closing `<section>` with two distinct CTAs — the tribes convert on different things:
  - **Builders → the no-seat Tier A quickstart:** "Author + lint a spec offline, zero license →" linking `../QUICKSTART.md`.
  - **Practitioners → the visual demo + operator guide (NOT the linter):** "See geometry rebuild in a real seat →" linking the hero/demo and `../docs/operator_guide.md`. Copy leads with **control and correctness** — "a power tool you drive, you approve every step" — never autonomous drafting (F2 mitigation).

- [ ] **Step 5: Write `site/README.md` (publish-decision note)**

Create `site/README.md` stating: the page is self-contained HTML, buildable and previewable now (open `site/index.html` in a browser); the **publish mechanism is a deferred decision** (spec open question #1) — GitHub Pages from `/docs` vs. a `gh-pages` branch vs. `site/` as the Pages root; `github.io` default vs. custom domain — resolved at Task 10 when the git hold lifts. Note the recommendation: a standalone page (not a whole-`docs/`-folder Jekyll build, which would wrongly publish internal engineering docs), and that the hero asset is finalized/copied at publish time (F6 / Task 9).

- [ ] **Step 6: Verify structure + lint**

Run: `python tools/check_launch_kit.py`
Expected: exit 0, `site/index.html` + `site/README.md` now counted, no placeholder/phantom/broken-link failures.
Then confirm by inspection that `index.html` contains: the verbatim wedge line, both doorway labels, all five essay beats, the A4 explainer subsection, and both per-tribe CTAs with the correct site-relative links (`../QUICKSTART.md`, `../docs/operator_guide.md`).

- [ ] **Step 7: Honesty checklist (manual)**

Confirm: no phantom `ai-sw-export`; wedge is a contrast not a named-competitor swipe; SOLIDWORKS framed as a requirement; kernel walls stated as fact (beat 4); practitioner CTA leads with control/correctness (F2); "no seat" claim scoped to Tier A only.

- [ ] **Step 8: Checkpoint (no commit — git hold)**

Run: `git status --short`. Expected new files: `site/index.html`, `site/README.md`. Do NOT commit.

---

### Task 4: A2 — MCP-ecosystem registry listings (`launch-kit/A2-registry-listings.md`)

**Files:**
- Create: `launch-kit/A2-registry-listings.md`

**Interfaces:**
- Consumes: `launch-kit/utm_links.md` `mcp-registry` link (Task 1).

- [ ] **Step 1: Classification table (finding F4)**

Author a table tagging each real target **directory-only** vs **runnable-host**:
  - *Directory-only* (a listing is always fine): official **MCP registry**, `awesome-mcp-servers` (punkpeye), `mcp.so`, PulseMCP.
  - *Runnable-host* (expects an installable/hostable server — a **Windows + paid-seat** server will NOT run there): Smithery, Glama. → submit as a listing/reference only, or skip, to avoid a rejected PR. State this reason inline.

- [ ] **Step 2: Drafted submission entry per viable target**

For each directory-only target, draft the exact entry text: a one-line description (wedge voice), the repo URL, the category/tags, and — where the directory shows a website — the `mcp-registry` UTM link from `launch-kit/utm_links.md`. For runnable-host targets, write one honest line explaining the listing-only / skip decision. No placeholders — write the real copy.

- [ ] **Step 3: Note the prerequisites plainly**

Add a short "honest prerequisites" line reused across entries: proprietary, requires a paid SOLIDWORKS 2021+ seat, Windows-only — so builders reading the listing are not misled (L6).

- [ ] **Step 4: Verify + lint**

Run: `python tools/check_launch_kit.py` → exit 0.
Manual: every runnable-host target carries its listing-only rationale; no entry implies one-click install on a hosted runner.

- [ ] **Step 5: Checkpoint (no commit — git hold)**

Run: `git status --short`. Expected new file: `launch-kit/A2-registry-listings.md`. Do NOT commit.

---

### Task 5: Launch kit L1–L2 (Show HN + X thread)

**Files:**
- Create: `launch-kit/L1-show-hn.md`, `launch-kit/L2-x-thread.md`

**Interfaces:**
- Consumes: `launch-kit/utm_links.md` (`show-hn`, `x` links); the A1 reference essay + A4 explainer (Task 3) as the source of the argument.

- [ ] **Step 1: L1 — Show HN draft**

`launch-kit/L1-show-hn.md`: a "Show HN:" title, a body that opens with the wedge and the honest edges (not hype), and a **first-comment context** block (why it exists, what's proprietary, no-seat Tier A path). Use the `show-hn` UTM link for any link to the landing page. Keep it a short adaptation that points to the canonical essay — not a copy of it.

- [ ] **Step 2: L2 — X / Twitter thread draft**

`launch-kit/L2-x-thread.md`: numbered tweets — hook → demo gif → the wedge → "try it with no seat" CTA. Use the `x` UTM link. Each tweet ≤ 280 chars; note where the hero gif attaches.

- [ ] **Step 3: Verify + lint**

Run: `python tools/check_launch_kit.py` → exit 0.
Manual: links use the correct per-channel UTM link; no phantom CLI; claims defensible; Show HN first comment discloses proprietary + seat plainly.

- [ ] **Step 4: Checkpoint (no commit — git hold)**

Run: `git status --short`. Expected new files: `launch-kit/L1-show-hn.md`, `launch-kit/L2-x-thread.md`. Do NOT commit.

---

### Task 6: Launch kit L3–L5 (LinkedIn + Reddit ×2 + Product Hunt)

**Files:**
- Create: `launch-kit/L3-linkedin.md`, `launch-kit/L4-reddit-solidworks.md`, `launch-kit/L4-reddit-mcp.md`, `launch-kit/L5-product-hunt.md`

**Interfaces:**
- Consumes: `launch-kit/utm_links.md` (`linkedin`, `reddit-solidworks`, `reddit-mcp`, `product-hunt`); Task 3 essay.

- [ ] **Step 1: L3 — LinkedIn article (practitioner-framed) with rel=canonical**

`launch-kit/L3-linkedin.md`: a practitioner-voiced article reusing the A4 explainer argument. It **must** carry a canonical pointer back to A1 — include a literal line `Canonical: https://thomas-tai.github.io/ai-sw-bridge/` and, if the platform supports it, an HTML `<link rel="canonical" href="https://thomas-tai.github.io/ai-sw-bridge/">` snippet in a "publish settings" note. Lead with control/correctness (F2), not "AI replaces drafters." Use the `linkedin` UTM link.

- [ ] **Step 2: L4 — Reddit, two sub-tuned drafts**

`launch-kit/L4-reddit-solidworks.md` (practitioner voice, r/SolidWorks norms: no hype, lead with the human-gated control story, invite critique) using the `reddit-solidworks` link. `launch-kit/L4-reddit-mcp.md` (builder voice, r/mcp: MCP-server framing, Tier A offline path) using the `reddit-mcp` link. Each honors sub self-promo norms.

- [ ] **Step 3: L5 — Product Hunt (optional, flagged)**

`launch-kit/L5-product-hunt.md`: tagline + description + first-comment, with a top note **"OPTIONAL — decide at Task 10 whether to include (spec open question #3)."** Use the `product-hunt` link.

- [ ] **Step 4: Verify + lint**

Run: `python tools/check_launch_kit.py` → exit 0.
Manual: L3 has the canonical pointer to A1; practitioner drafts (L3, L4-solidworks) lead with control/correctness; each draft uses its own channel's UTM link.

- [ ] **Step 5: Checkpoint (no commit — git hold)**

Run: `git status --short`. Expected four new `launch-kit/L3…L5` files. Do NOT commit.

---

### Task 7: Launch kit L6–L7 (timing + measurement + FAQ crib)

**Files:**
- Create: `launch-kit/L6-timing-checklist.md`, `launch-kit/L7-faq-crib.md`

**Interfaces:**
- Consumes: the hard sequencing gate (Global Constraints); `launch-kit/utm_links.md`.

- [ ] **Step 1: L6 — timing / fire-order checklist + the hard gate**

`launch-kit/L6-timing-checklist.md`: the launch-day fire order (e.g., registries live first → Show HN in the morning window → X thread → Reddit → LinkedIn → optional PH), each an actionable `- [ ]` item. Open with the **BLOCKING gate**, stated plainly: *the coordinated launch does NOT fire until Project A Phase-2 deep clips (observe / drawing / export) land and the hero recomposes over them* (`docs/superpowers/notes/2026-08-12-phase2-findings.md`).

- [ ] **Step 2: L6 — measurement routine (finding F8)**

Add a "Measurement" subsection: after launch, review **(a)** UTM referrers per channel and **(b)** GitHub repo-traffic referrers on the **14-day** window, to see which doorway works. Note that every launch link already carries UTM tags from `launch-kit/utm_links.md` (built in Task 1), and that stars are watched-not-chased (lagging proxy under the seat + proprietary headwind).

- [ ] **Step 3: L7 — FAQ crib (finding F7)**

`launch-kit/L7-faq-crib.md`: graceful, honest answers to — *"it's proprietary"* / *"needs a seat"* (lead with the free no-seat Tier A path; state MIT ≤ v1.4 → commercial since v1.5 plainly); and *"I'll just fork the last MIT v1.4"* (a valid frozen snapshot, but it gets **none** of the ongoing seat-proven `feature_add` kinds, fixes, or support — no spin, no dodge).

- [ ] **Step 4: Verify + lint**

Run: `python tools/check_launch_kit.py` → exit 0.
Manual: L6 opens with the Phase-2 blocking gate; measurement names both UTM + 14-day GitHub referrers; L7 answers are honest and non-defensive.

- [ ] **Step 5: Checkpoint (no commit — git hold)**

Run: `git status --short`. Expected new files: `launch-kit/L6-timing-checklist.md`, `launch-kit/L7-faq-crib.md`. Do NOT commit.

---

### Task 8: Kit index + full self-review

**Files:**
- Create: `launch-kit/README.md`

**Interfaces:**
- Consumes: every asset from Tasks 1–7.

- [ ] **Step 1: Write the kit index**

`launch-kit/README.md`: a one-screen index mapping each asset (A2, L1–L7, `utm_links.md`) to its file and one-line purpose, a pointer to the landing page (`../site/index.html`) and the spec, and a top banner: **"DRAFT-AND-HOLD — nothing here fires until the Task 10 gate (Project A Phase-2 + git-hold lift)."** Point the "fire order" line at `L6-timing-checklist.md`.

- [ ] **Step 2: Full lint over the whole kit + site**

Run: `python tools/check_launch_kit.py`
Expected: exit 0, all `site/` + `launch-kit/` docs pass.

- [ ] **Step 3: Full test suite for the two tools**

Run: `python -m pytest tests/tools/test_launch_links.py tests/tools/test_check_launch_kit.py -v`
Expected: all pass (10 tests total).

- [ ] **Step 4: Cross-asset consistency pass (manual)**

Confirm: every launch draft's landing link matches the corresponding row in `launch-kit/utm_links.md`; the wedge voice is identical across README, `site/index.html`, and the drafts; the two-track framing is consistent (builders → Tier A; practitioners → demo + operator guide); the Phase-2 gate appears in both L6 and `launch-kit/README.md`.

- [ ] **Step 5: Checkpoint (no commit — git hold)**

Run: `git status --short`. Confirm the full working-tree set is present and only expected files changed. Do NOT commit (the batch commit waits for the hold to lift — out of scope here).

---

# PHASE B2 — GATED (Tasks 9–10) — DO NOT START YET

**Blocked by:** Project A Phase-2 deep clips (observe / drawing / export) landing + the hero recompose (`docs/superpowers/plans/2026-08-12-demo-gif-suite-enhancement.md` Tasks 9–13), AND the git-hold lift. Do not begin either task until both conditions hold. They are specified here so the plan is complete, not so they run now.

---

### Task 9: A1 hero freshness re-verify (finding F6)

**Files:**
- Modify: `site/index.html` (hero embed only), possibly `site/assets/`.

- [ ] **Step 1:** Confirm Project A Phase-2 has regenerated `docs/img/demo_hero.gif` as the deep-clip hero (interference/mass HUD, section A-A + balloons, STEP round-trip). If `site/` copies the asset rather than referencing `docs/img/`, refresh the copy so the page shows the deep hero — never ship the deep-proof landing page wrapped around the shallow Phase-1 hero.
- [ ] **Step 2:** Run `python tools/check_launch_kit.py` → exit 0 (hero asset still resolves).
- [ ] **Step 3:** Eyeball `site/index.html` in a browser: the fold hero is the deep-clip version.
- [ ] **Step 4:** Checkpoint — `git status --short`; commit only if the hold has lifted (then: flake8 → black → mypy → pytest; no `Co-Authored-By`).

### Task 10: Publish + coordinated launch fire

**Files:**
- Repo settings (GitHub Pages), external registry PRs, live posts — no source files beyond finalizing `site/README.md` with the chosen host.

- [ ] **Step 1: Resolve the publish host (spec open question #1).** Decide GitHub Pages source (`/docs` vs `gh-pages` branch vs `site/`) and `github.io` vs custom domain. If a custom domain is chosen, regenerate links: `python tools/launch_links.py --base-url <domain>` and re-run `python tools/check_launch_kit.py`. Record the decision in `site/README.md`.
- [ ] **Step 2: Enable Pages + verify the live URL** serves `site/index.html`, the hero loads, and `rel="canonical"` resolves.
- [ ] **Step 3: Submit A2 registry listings** per `launch-kit/A2-registry-listings.md` (directory-only targets; runnable-host = listing/skip per F4). User presses send.
- [ ] **Step 4: Decide L5 Product Hunt in/out (spec open question #3).**
- [ ] **Step 5: Fire L1–L5 in the L6 order.** User presses send / does live engagement; I stand by for rapid FAQ (L7) responses.
- [ ] **Step 6: Start the measurement window (F8):** UTM referrers per channel + GitHub repo-traffic 14-day referrers.

---

## Notes for the executor

- **Division of labor (spec):** the implementer builds all assets, drafts all copy, and prepares the registry entries; **the user** reviews and presses send / does live engagement. Task 10 is user-driven; Tasks 1–9 are build-and-verify.
- **Content-task verification** is `python tools/check_launch_kit.py` (mechanical) **plus** the per-task manual honesty checklist (judgment). Both are required — the lint cannot judge tone.
- **Everything stays in the working tree.** No commits this plan (git hold). The only commit-bearing steps (Tasks 9–10 checkpoints) are explicitly conditioned on the hold having lifted.
