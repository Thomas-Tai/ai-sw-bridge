# Phase 4 — i18n Retranslation & the Honesty Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the zh-CN / zh-TW front-door doc mirrors up to v1.7.0 and install a Model-B "honesty gate" that makes silent i18n rot structurally impossible.

**Architecture:** Retire the two off-target legacy mirrors; retranslate the front-door trio (README, USAGE, PUBLIC_API) × {zh-CN, zh-TW} = 6 files against a frozen English baseline SHA (fresh ⇒ no staleness sentinel); then add `tests/test_i18n_staleness.py` enforcing `stale(mirror) ⇔ sentinel_present(mirror)` where `stale` = "the English source advanced past the mirror's `translated-from` SHA", plus structural-fidelity + dead-link checks; wire it in CI with `fetch-depth: 0`.

**Tech Stack:** Markdown, Python stdlib (`subprocess` git, `re`, `pathlib`), pytest, GitHub Actions.

**Design spec:** `docs/superpowers/specs/2026-07-02-phase4-i18n-retranslation-honesty-gate-design.md` (ratified). Locked open-decisions: §9.1 = **Retire** legacy mirrors; §9.2 = **HTML-comment sentinel** `<!-- i18n-staleness-banner -->`; §9.3 = **full biconditional**.

## Global Constraints

- **Branch `docs/commercial-elevation` only.** Never commit to `feat/w67-phase3` or `master`. **HOLD push** until the phase is complete + gauntlet green, then a single `isPrivate`-guarded fast-forward push (`git push origin docs/commercial-elevation:master`, no force; verify `gh repo view --json isPrivate` == true + origin/master is an ancestor of HEAD + HEAD unchanged).
- **COM-free phase.** No handler/builder/COM source is touched → **no seat-prefire required**. But the live SOLIDWORKS seat (PID 40652) must stay untouched, and the seat-safe suite must stay green at every commit. Seat-safe suite = `pytest -m "not solidworks_only and not destructive_sw"`; NEVER bare `pytest`; NEVER run `tests/e2e_sw/` or `tests/mcp_lane/`. Baseline before this phase = **3897 passed**.
- **Snapshot discipline.** Do **not** edit any English source doc (`README.md`, `USAGE.md`, `docs/PUBLIC_API.md`) in this phase. Translations are set `translated-from: <current source SHA>`; because sources are untouched, mirrors land **fresh**.
- **DO-NOT-TRANSLATE list authoritative** (`docs/i18n/TRANSLATION_PROMPT.md` §"DO-NOT-TRANSLATE list"): tool/file names, SW API surface, bridge-internal identifiers, spec schema + CLI flags, file/code references stay verbatim in every mirror.
- **zh-CN = Simplified, zh-TW = Traditional** — independent translations, never mechanical conversion. DO-NOT-TRANSLATE tokens identical across both.
- **Every pytest runs in the FOREGROUND** (blocking, timeout up to 600000ms). Do NOT background the suite and pause.
- **black / flake8 / mypy clean** on any Python touched (`tests/test_i18n_staleness.py`). Run `black --check` before every commit (not just flake8).
- **No co-author trailers; `--no-gpg-sign` commits.**

---

## File Structure

- `docs/i18n/zh-CN/README.md` — retranslated in place (frontmatter `translated-from` bumped).
- `docs/i18n/zh-CN/USAGE.md` — **new** mirror of `USAGE.md`.
- `docs/i18n/zh-CN/PUBLIC_API.md` — **new** mirror of `docs/PUBLIC_API.md`.
- `docs/i18n/zh-TW/{README,USAGE,PUBLIC_API}.md` — same three for Traditional.
- `docs/i18n/{zh-CN,zh-TW}/known_limitations.md`, `.../why_no_addim2.md` — **deleted** (retire).
- `tests/test_i18n_staleness.py` — **new** Model-B gate + structural fidelity + dead-link + manifest membership.
- `.github/workflows/ci.yml` — new i18n-gate step (with `fetch-depth: 0` on its job).
- `docs/i18n/TRANSLATION_PROMPT.md` — Maintenance section updated (sentinel + gate contract).
- `CONTRIBUTING.md` — PR-checklist i18n-freshness line.

---

## Checkpoints

- **Checkpoint 1 (Foundation + True-Up):** Task 0 (retire legacy) + Task 1 (zh-CN trio) + Task 2 (zh-TW trio). Boundary = maintainer human prose-quality review.
- **Checkpoint 2 (The Gate + Closeout):** Task 3 (build + bite-prove the gate) + Task 4 (CI wire + process docs + close #10).
- **Final Checkpoint:** full gauntlet + isPrivate-guarded FF push.

Report telemetry after each checkpoint; hold for GO between them.

---

## Task 0: Retire the legacy mirrors (§9.1-A)

**Files:** Delete `docs/i18n/{zh-CN,zh-TW}/known_limitations.md`, `docs/i18n/{zh-CN,zh-TW}/why_no_addim2.md` (4 files).

**Interfaces:** Produces the pruned mirror tree the Task 3 manifest membership check will assert against.

- [ ] **Step 1: Re-confirm no committed doc links the legacy MIRROR copies.**

Run: `grep -rn "i18n/zh-CN/known_limitations\|i18n/zh-TW/known_limitations\|i18n/zh-CN/why_no_addim2\|i18n/zh-TW/why_no_addim2" --include="*.md" . | grep -v "^./.claude/" | grep -v "^./.qoder/"`
Expected: no output. (Links to the English `docs/known_limitations.md` / `docs/why_no_addim2.md` are fine — those files stay.)

- [ ] **Step 2: Confirm the current mirror READMEs' only inbound refs are the language switcher.**

Run: `grep -rn "known_limitations\|why_no_addim2" docs/i18n/zh-CN/README.md docs/i18n/zh-TW/README.md`
If a stale README links a sibling legacy file, note it — it disappears in Task 1/2 (READMEs are retranslated from current English, which does not link them). No action needed now.

- [ ] **Step 3: Delete the 4 files.**

Run: `git rm docs/i18n/zh-CN/known_limitations.md docs/i18n/zh-CN/why_no_addim2.md docs/i18n/zh-TW/known_limitations.md docs/i18n/zh-TW/why_no_addim2.md`

- [ ] **Step 4: Verify no dead link was introduced tree-wide (committed docs only).**

Run: `grep -rn "known_limitations\|why_no_addim2" docs/i18n/`
Expected: no output (all mirror refs gone).

- [ ] **Step 5: Commit.**

```bash
git add -A docs/i18n/
git commit --no-gpg-sign -m "docs(i18n): retire off-target legacy mirrors (known_limitations/why_no_addim2) — front-door re-target (Phase 4 §9.1-A)"
```

---

## Task 1: Retranslate the zh-CN front-door trio

**COM-adjacency:** NONE. **Vehicle:** `docs/i18n/TRANSLATION_PROMPT.md` process.

**Files:** Modify `docs/i18n/zh-CN/README.md`; Create `docs/i18n/zh-CN/USAGE.md`, `docs/i18n/zh-CN/PUBLIC_API.md`.

**Interfaces:**
- Consumes: English sources `README.md`, `USAGE.md`, `docs/PUBLIC_API.md` (frozen — do not edit); `docs/i18n/TRANSLATION_PROMPT.md` DO-NOT-TRANSLATE list.
- Produces: 3 fresh zh-CN mirrors with `translated-from: <source SHA>` frontmatter, **no** staleness sentinel, that pass the Task 3 structural checks.

- [ ] **Step 1: Capture the frozen source SHAs.**

Run: `for s in README.md USAGE.md docs/PUBLIC_API.md; do echo "$s -> $(git log -1 --format=%H -- "$s")"; done`
Record each SHA; it becomes that mirror's `translated-from`.

- [ ] **Step 2: Translate `README.md` → `docs/i18n/zh-CN/README.md` (Simplified).**

Follow `TRANSLATION_PROMPT.md`. Requirements:
- Frontmatter: `---\ntranslated-from: <README.md SHA>\n---` (bump from the old `c8ce816`).
- **No** `<!-- i18n-staleness-banner -->` sentinel and **no** stale-warning prose (this mirror is fresh). Remove the old "此翻译已过期" block.
- Preserve the heading skeleton of the English README (same ATX `#` structure, same order).
- DO-NOT-TRANSLATE tokens verbatim: `ai-sw-build`, `ai-sw-mcp`, `SolidWorksClient`, `FeatureCut4`, `spec.json`, `--locale`, `PARAMNOTOPTIONAL`, file paths, code fences, CLI flags.
- Language switcher line points to English + `../zh-TW/README.md`.
- **No dead relative links.** In particular: do NOT introduce `](../../api_reference.md)` (the old mirror's D10 bug). Where English mentions `sw_api_full.md`, link `../../sw_api_full.md` (verify it resolves). The `api_reference.md` mention in the file-tree diagram is prose annotation, not a link — keep it as plain text, not `](...)`.

- [ ] **Step 3: Translate `USAGE.md` → `docs/i18n/zh-CN/USAGE.md` (net-new).** Same rules; `translated-from: <USAGE.md SHA>`.

- [ ] **Step 4: Translate `docs/PUBLIC_API.md` → `docs/i18n/zh-CN/PUBLIC_API.md` (net-new).** Same rules; `translated-from: <docs/PUBLIC_API.md SHA>`. Relative links rebase from `docs/` depth to `docs/i18n/zh-CN/` depth (one extra `../../` level) — verify each resolves.

- [ ] **Step 5: Self-verify structure before commit.**

For each of the 3 files run:
- Frontmatter present: `head -4 <file>` shows `translated-from: <40-hex>`.
- Heading count parity: `grep -c '^#' <english>` vs `grep -c '^#' <mirror>` (allow ±1 for a removed banner heading; investigate larger gaps).
- No sentinel: `grep -c 'i18n-staleness-banner' <mirror>` == 0.
- No dead relative links: for every `](RELPATH)` with a non-`http` target, confirm the resolved path exists on disk.
- DO-NOT-TRANSLATE spot-check: `grep -c 'ai-sw-build' <mirror>` > 0 where the English has it.

- [ ] **Step 6: Commit.**

```bash
git add docs/i18n/zh-CN/README.md docs/i18n/zh-CN/USAGE.md docs/i18n/zh-CN/PUBLIC_API.md
git commit --no-gpg-sign -m "docs(i18n): retranslate zh-CN front-door trio (README/USAGE/PUBLIC_API) to v1.7.0; bump translated-from; drop stale banner (Phase 4)"
```

---

## Task 2: Retranslate the zh-TW front-door trio

**Identical to Task 1 but Traditional Chinese**, targeting `docs/i18n/zh-TW/{README,USAGE,PUBLIC_API}.md`. Language switcher points to English + `../zh-CN/README.md`. Do NOT mechanically convert zh-CN → zh-TW; translate independently (idiom/term differences: 软件/軟體, 缺省/預設, etc.). Same `translated-from` SHAs as Task 1 (same English sources), same fresh/no-sentinel rule, same Step-5 self-verify.

- [ ] **Step 1–5:** as Task 1, for `zh-TW`.
- [ ] **Step 6: Commit.**

```bash
git add docs/i18n/zh-TW/README.md docs/i18n/zh-TW/USAGE.md docs/i18n/zh-TW/PUBLIC_API.md
git commit --no-gpg-sign -m "docs(i18n): retranslate zh-TW front-door trio (README/USAGE/PUBLIC_API) to v1.7.0; bump translated-from; drop stale banner (Phase 4)"
```

**→ Checkpoint 1 boundary: maintainer human prose-quality review of all 6 mirrors (native reader). Hold for GO.**

---

## Task 3: Build the Honesty Gate (`tests/test_i18n_staleness.py`)

**COM-adjacency:** NONE (git subprocess + file reads).

**Files:** Create `tests/test_i18n_staleness.py`.

**Interfaces:**
- Consumes: the 6 fresh mirrors from Tasks 1–2; git history (`translated-from` SHAs must be reachable).
- Produces: a CI-enforceable gate. Adds N tests to the seat-safe suite.

- [ ] **Step 1: Write the module** with this shape (fill in helpers concretely — no placeholders):

```python
"""Model-B i18n honesty gate: a mirror is stale IFF it declares itself stale.

stale(mirror) := the English source advanced past the mirror's translated-from
SHA (git rev-list <sha0>..HEAD -- <source> is non-empty). A stale mirror MUST
carry the sentinel <!-- i18n-staleness-banner -->; a fresh one must NOT. Also
enforces structural fidelity (frontmatter, heading parity, DO-NOT-TRANSLATE
tokens) and zero dead relative links. English stays authoritative; honest lag
is allowed, silent rot is not.
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

_FRONTMATTER_RE = re.compile(r"\Atranslated-from:\s*([0-9a-f]{7,40})\s*$", re.M)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=_ROOT, capture_output=True, text=True
    )


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
    not _git_available(), reason="git history unavailable (shallow/no-git); CI runs with fetch-depth:0"
)


@pytest.mark.parametrize("mirror,source", list(I18N_MIRRORS.items()))
def test_mirror_exists_and_declares_translated_from(mirror: str, source: str) -> None:
    mp = _ROOT / mirror
    assert mp.is_file(), f"manifest lists {mirror} but it is missing on disk"
    assert (_ROOT / source).is_file(), f"source {source} for {mirror} missing"
    sha0 = _translated_from(mp.read_text(encoding="utf-8"))
    assert sha0, f"{mirror} lacks a translated-from: <sha> frontmatter"
    assert _git("cat-file", "-e", sha0).returncode == 0, (
        f"{mirror} translated-from {sha0} is not in git history (rebase/force-push?)"
    )


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
    dead = [t for t in _relative_links(mp.read_text(encoding="utf-8"))
            if not (mp.parent / t).resolve().exists()]
    assert not dead, f"{mirror} has dead relative links: {dead}"


@pytest.mark.parametrize("mirror,source", list(I18N_MIRRORS.items()))
def test_do_not_translate_tokens_preserved(mirror: str, source: str) -> None:
    src = (_ROOT / source).read_text(encoding="utf-8")
    mir = (_ROOT / mirror).read_text(encoding="utf-8")
    missing = [tok for tok in DNT_TOKENS if tok in src and tok not in mir]
    assert not missing, f"{mirror} dropped DO-NOT-TRANSLATE tokens present in {source}: {missing}"


def test_manifest_matches_disk() -> None:
    """Every *.md under docs/i18n/<loc>/ must be in the manifest (no untracked mirror)."""
    tracked = {str(Path(m)) for m in I18N_MIRRORS}
    on_disk = {
        str(p.relative_to(_ROOT)).replace("\\", "/")
        for p in (_ROOT / "docs" / "i18n").glob("zh-*/*.md")
    }
    strays = on_disk - tracked
    assert not strays, f"mirror files on disk but not in I18N_MIRRORS manifest: {strays}"
```

- [ ] **Step 2: Run the gate — expect green against the fresh mirrors.**

Run: `python -m pytest tests/test_i18n_staleness.py -q -p no:cacheprovider`
Expected: PASS (mirrors fresh ⇒ biconditional holds with no sentinel; links resolve; tokens preserved; manifest == disk). If a link test fails, fix the mirror (a real dead link), not the test.

- [ ] **Step 3: Bite-prove all three failure modes (revert each after).**

1. **Blank translated-from:** temporarily strip the SHA from one mirror's frontmatter → run `test_mirror_exists_and_declares_translated_from` → MUST FAIL. Revert.
2. **Silent rot:** temporarily point one manifest source at a file with later commits while the mirror has no sentinel — simplest: temporarily set a mirror's `translated-from` to an OLD reachable SHA (e.g. `c8ce816`) with no sentinel → `test_model_b_biconditional` MUST FAIL (stale, no banner). Revert.
3. **Crying wolf:** add the `<!-- i18n-staleness-banner -->` sentinel to a fresh mirror → `test_model_b_biconditional` MUST FAIL (fresh, banner). Revert.

Record each RED. Confirm `git status --short` clean afterward.

- [ ] **Step 4: Lint + commit.**

Run: `python -m black --check tests/test_i18n_staleness.py && python -m flake8 tests/test_i18n_staleness.py && python -m mypy tests/test_i18n_staleness.py` (mypy may be config-scoped to `src`; if it doesn't cover tests, skip). Then:

```bash
git add tests/test_i18n_staleness.py
git commit --no-gpg-sign -m "test(i18n): Model-B staleness honesty gate + structural fidelity + dead-link + manifest membership (Phase 4)"
```

---

## Task 4: Wire CI + process docs + close Issue #10

**Files:** Modify `.github/workflows/ci.yml`, `docs/i18n/TRANSLATION_PROMPT.md`, `CONTRIBUTING.md`.

- [ ] **Step 1: Ensure the gate's job has full git history.**

Read `.github/workflows/ci.yml`. The gate runs as part of the pytest job (it's a normal test). Confirm the job's `actions/checkout` step has `with: fetch-depth: 0` (add it if absent, on the job that runs the seat-safe suite). Without full history, `git rev-list <sha0>..HEAD` / `cat-file -e` can't verify and the gate skips (§5.5) — CI must NOT skip.

- [ ] **Step 2: Verify the gate actually runs in the seat-safe selection** (it carries no exclusion marker, so it's already collected). Confirm: `python -m pytest -m "not solidworks_only and not destructive_sw" tests/test_i18n_staleness.py -q -p no:cacheprovider` collects and passes.

- [ ] **Step 3: Update `TRANSLATION_PROMPT.md` Maintenance section** — document the `<!-- i18n-staleness-banner -->` sentinel contract and that `tests/test_i18n_staleness.py` enforces `stale ⇔ sentinel`; a translator who lets English advance must either re-translate + bump `translated-from` or add the sentinel.

- [ ] **Step 4: Add an i18n-freshness line to the `CONTRIBUTING.md` PR checklist / freshness-ownership rule** — "If you change README/USAGE/PUBLIC_API, either update the zh-CN/zh-TW mirrors (+ bump `translated-from`) or the mirror must carry the staleness sentinel — CI (`test_i18n_staleness.py`) enforces it." Preserve the `v1.7.0` version pin (doc-truth).

- [ ] **Step 5: Doc-truth + commit.**

Run: `python -m pytest tests/test_doc_truth.py -q -m "not solidworks_only and not destructive_sw" -p no:cacheprovider` → PASS.

```bash
git add .github/workflows/ci.yml docs/i18n/TRANSLATION_PROMPT.md CONTRIBUTING.md
git commit --no-gpg-sign -m "ci+docs(i18n): run staleness gate with fetch-depth:0; document sentinel contract in TRANSLATION_PROMPT + CONTRIBUTING (Phase 4)"
```

- [ ] **Step 6: Close Issue #10.**

Run: `gh issue close 10 --comment "i18n front-door mirrors (README/USAGE/PUBLIC_API × zh-CN/zh-TW) retranslated to v1.7.0; silent rot now blocked by tests/test_i18n_staleness.py (Model-B honesty gate). Legacy known_limitations/why_no_addim2 mirrors retired."` (Confirm #10 is the i18n sync issue first: `gh issue view 10 --json title,body`.)

---

## Final Checkpoint — full gauntlet + HELD push

- [ ] **Step 1: Full seat-safe suite** — `python -m pytest -m "not solidworks_only and not destructive_sw" -q -p no:cacheprovider`. Expected: 3897 + the new i18n tests (≈ 3897 + ~25), 0 failed. PID 40652 unchanged.
- [ ] **Step 2: Static gates** — import-linter (3 kept/0 broken), `python tools/module_size_gate.py --strict` (OK), `python -m mypy src` (clean), `python -m flake8 src/ tests/test_i18n_staleness.py`, `python -m black --check .` (only untracked `scratchpad/` may differ).
- [ ] **Step 3: Verify DoD** — all §7 boxes: 6 fresh front-door mirrors; legacy retired; gate green + bite-proven; CI fetch-depth wired; #10 closed; CONTRIBUTING + TRANSLATION_PROMPT updated; human review signed off.
- [ ] **Step 4: isPrivate-guarded fast-forward push to master.**

```bash
HEAD_BEFORE=$(git rev-parse HEAD)
gh repo view --json isPrivate   # must be true
git fetch origin master -q
git merge-base --is-ancestor origin/master HEAD && echo "FF-able"   # must succeed
[ "$(git rev-parse HEAD)" = "$HEAD_BEFORE" ] && git push origin docs/commercial-elevation:master   # no --force
git fetch origin master -q && [ "$(git rev-parse origin/master)" = "$(git rev-parse HEAD)" ] && echo "push confirmed"
```

---

## Self-Review (author checklist)

- **Spec coverage:** §4 mirror set → Tasks 1–2; §4.2/§9.1 retire → Task 0; §5 Model-B gate → Task 3; §5.5 CI fetch-depth → Task 4 Step 1; §5.6 structural/dead-link → Task 3; §6 snapshot discipline → Global Constraints + Task 1 Step 1; §7 DoD → Final Checkpoint; §10 deliverable map → all tasks. ✓
- **Type consistency:** `translated-from` SHA, `SENTINEL`, `I18N_MIRRORS` manifest names used identically across Task 3 code and Tasks 1–2 prose. ✓
- **Measure-at-execution items (not placeholders):** the exact source SHAs (Task 1 Step 1), the actual translated prose (produced per TRANSLATION_PROMPT), the precise ci.yml job/line for fetch-depth (Task 4 Step 1 reads it first), and whether #10 is truly the i18n issue (Task 4 Step 6 verifies). These are genuine per-execution reads, not gaps.
