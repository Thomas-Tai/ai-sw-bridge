# Unified Honesty-Gate Lint — Implementation Plan

**Date:** 2026-08-17
**Branch:** `feat/unified-honesty-gate`

## Context

The project enforces an **L6 honesty gate**: user-facing copy must never cite a
CLI that does not exist (the canonical example is a bare `ai-sw-export` — the
registry has only `ai-sw-export-dxf-flat` + `ai-sw-import`; STEP/STL/3MF ship via
the spec `export:` block), must not ship placeholders, and must not carry broken
internal links.

Today that gate is **partial and fragmented**:

- `tools/check_launch_kit.py` runs three checks — placeholders, phantom-CLI
  banned-token (`_BANNED_RE = re.compile(r"ai-sw-export\b(?!-)")`), internal
  links — but **only over `site/` + `launch-kit/`**. `README.md` and `docs/`
  are never scanned, so a phantom CLI could ship in the README undetected.
- `check_launch_kit.py` is **not wired into CI or pre-commit** — it runs only
  when a human remembers to.
- The same banned-token concept is **duplicated** in
  `tests/tools/test_demo_captions_honest.py`, which scans `tools/demo_*.py`
  independently.

**Already solved — do NOT touch:** i18n mirror staleness is fully gated by
`tests/test_i18n_staleness.py` (a Model-B honesty biconditional over the
README/USAGE/PUBLIC_API trio for zh-CN/zh-TW, run in CI on a full-history
checkout). This plan must not duplicate, weaken, or re-implement it.

**Goal:** one coherent, CI-wired honesty gate that single-sources the check
logic and broadens the phantom-CLI / link coverage to the user-facing English
surfaces, without false-positiving on internal working docs.

## Global Constraints (bind every task)

- **Pure Python, stdlib only.** No new dependencies. Match the style of the
  existing `tools/*.py` gates.
- **Do not touch `tests/test_i18n_staleness.py`** or the i18n mirrors. i18n
  staleness is its own gate.
- **Single source for the banned-token regex.** After this plan there is
  exactly one definition of the phantom-CLI pattern
  (`r"ai-sw-export\b(?!-)"`), imported everywhere it is needed. No copies.
- **No false positives on internal working docs.** The scan MUST exclude
  `docs/superpowers/**`, `docs/archive/**`, and `docs/i18n/**` — these
  legitimately discuss the phantom `ai-sw-export` (it is the banned example)
  and must never trip the gate.
- **Per-check surface scoping is deliberate** (see Task 2) — the placeholder
  check stays launch-copy-only; general `docs/` may legitimately contain the
  word "TODO".
- **The gate must exit 0 on the current repo.** Verified 2026-08-17: no bare
  phantom in any user-facing surface, no stray placeholders in launch copy.
- Keep `black` / `flake8` / `mypy` green; every new check ships with tests.
- Windows-safe: use `pathlib`, never shell-glob assumptions; the repo path
  contains `[` (a glob metachar).
- **No `Co-Authored-By: Claude` trailer** on any commit.
- Behavior-preserving refactors must keep existing tests green **unchanged**.

## Tasks

### Task 1: Extract shared honesty-check primitives to a leaf module

**Rationale:** create the single source of truth the other tasks build on;
behavior-preserving.

**Do:**
- Create `tools/_honesty_checks.py` and MOVE these into it, verbatim, from
  `tools/check_launch_kit.py`:
  - the regexes `_PLACEHOLDER_RE`, `_BANNED_RE`, `_MD_LINK_RE`, `_HTML_ASSET_RE`
  - the functions `find_placeholders(text) -> list[str]`,
    `find_banned_claims(text) -> list[str]`, `_is_internal(target) -> bool`,
    `check_internal_links(doc_path, repo_root) -> list[str]`
- In `tools/check_launch_kit.py`, replace the moved bodies with
  `from _honesty_checks import (find_placeholders, find_banned_claims,
  check_internal_links, _is_internal)` (keep the `sys.path.insert(... tools)`
  idiom the tests already rely on) so that `check_launch_kit.find_placeholders`
  etc. still resolve (its test suite calls them via the `ck` module alias).
  `lint_paths`, `main`, and `SCAN_DIRS` stay in `check_launch_kit.py`
  unchanged.
- Add `tests/tools/test_honesty_checks.py` that imports `_honesty_checks`
  directly and covers: placeholder detection (TODO, TBD, `<UPPER_UNDERSCORE>`
  stub, `<name here>`); a clean string returns `[]`; `find_banned_claims`
  flags bare `ai-sw-export`, allows `ai-sw-export-dxf-flat`, allows
  `ai-sw-exporter`; `check_internal_links` flags a missing asset and passes an
  existing one (use `tmp_path`).

**Acceptance:**
- `tests/tools/test_check_launch_kit.py` passes **unchanged** (10 tests).
- `tests/tools/test_honesty_checks.py` passes.
- `python tools/check_launch_kit.py` still exits 0 with the same "N doc(s)
  pass" output.
- `black --check` + `flake8` clean on both changed files.

### Task 2: Build the unified `tools/honesty_gate.py` scanner

**Rationale:** the actual new value — broaden coverage and consolidate.

**Do:**
- Create `tools/honesty_gate.py` importing the Task-1 primitives.
- Define a scan manifest with **per-check surface scoping** (paths relative to
  repo root):
  - **Phantom-CLI banned-token** — the broad set:
    `README.md`, `USAGE.md`, `docs/PUBLIC_API.md`, `docs/CAPABILITIES.md`,
    `docs/ONBOARDING.md`, every `*.md`/`*.html` under `site/`, every `*.md`
    under `launch-kit/`, and every `tools/demo_*.py` source.
  - **Placeholders** — launch copy only: `site/**/*.{md,html}`,
    `launch-kit/**/*.md`. (NOT general docs — they may say "TODO".)
  - **Internal links** — `README.md`, `site/**/*.{md,html}`,
    `launch-kit/**/*.md`.
  - **Exclude always:** any path under `docs/superpowers/`, `docs/archive/`,
    `docs/i18n/`.
- Expose a pure, testable core: a function that takes an explicit
  `repo_root: Path` (and, for tests, an optional override of the manifest or
  file-set) and returns a list of `(surface_path, kind, detail)` violations —
  so tests run against a synthetic `tmp_path` repo, never the real tree.
- `main()`: run all checks over the real repo root, print violations grouped
  by surface to stderr, print an "OK: …" summary to stdout, exit 1 on any
  violation else 0. Follow the two-stream contract
  (`tools/two_stream_lint.py`): human text to stderr, machine summary to
  stdout.
- Fold in the demo-caption guard: `honesty_gate` scanning `tools/demo_*.py`
  for the banned token is now the single source; refactor
  `tests/tools/test_demo_captions_honest.py` so it asserts cleanliness **via
  `honesty_gate`'s checker over the real `tools/demo_*.py`** rather than
  duplicating the scan against `check_launch_kit`.
- `tools/check_launch_kit.py` stays a working entry point (unchanged after
  Task 1) — do not delete it.
- Add `tests/tools/test_honesty_gate.py` using a synthetic `tmp_path` repo:
  - phantom `ai-sw-export` in a fake `README.md` → **flagged**
  - the same phantom in a fake `docs/superpowers/plan.md` → **NOT flagged**
    (exclusion)
  - `ai-sw-export-dxf-flat` in `README.md` → not flagged
  - `TODO` in a fake `launch-kit/x.md` → flagged; `TODO` in a fake
    `docs/GUIDE.md` → not flagged (placeholder scope)
  - broken internal link in a fake `site/index.html` → flagged
  - a fake `tools/demo_x.py` containing the banned token → flagged

**Acceptance:**
- All new + existing tool tests pass; `test_demo_captions_honest.py` still
  guards `tools/demo_*.py` (now via `honesty_gate`).
- `python tools/honesty_gate.py` exits 0 on the current repo (paste the
  output in the report).
- `black --check` + `flake8` + `mypy` clean on new files.

### Task 3: Wire the gate into CI + pre-commit, and document it

**Rationale:** an unenforced gate is the status quo we are fixing.

**Do:**
- Add a step to `.github/workflows/ci.yml` in the existing lint job (next to
  `two_stream_lint` / `module_size_gate`): `run: python tools/honesty_gate.py`
  with a clear step `name:`.
- Add a local `pre-commit` hook in `.pre-commit-config.yaml`: a `repo: local`
  hook `id: honesty-gate`, `entry: python tools/honesty_gate.py`,
  `language: system`, `pass_filenames: false`, `always_run: true` (the gate
  scans a fixed manifest, not staged files).
- Document the gate: add a short subsection to `CONTRIBUTING.md` (or the
  nearest existing "gates / checks" doc — locate it first) describing what
  `honesty_gate.py` checks, the per-check surfaces, and the exclusion list,
  and noting it supersedes the manual `check_launch_kit.py` run.
- **If `CONTRIBUTING.md` (or the doc you edit) has zh-CN/zh-TW mirrors, do NOT
  edit the mirrors** — that would trip the i18n staleness gate; only the
  front-door trio (README/USAGE/PUBLIC_API) is mirror-bound, and this is a
  CONTRIBUTING/gates doc. If you must edit a mirror-bound file, STOP and flag
  it.

**Acceptance:**
- `ci.yml` and `.pre-commit-config.yaml` are valid (YAML parses; the added
  hook/step follow the file's existing structure).
- `python tools/honesty_gate.py` exits 0 locally (paste output).
- Documentation renders (no broken internal links introduced — the gate
  itself now checks README links).
- `black`/`flake8`/`mypy`/full `pytest` green.

## Final Verification

- `python tools/honesty_gate.py` → exit 0 on the real repo.
- Full `pytest` green; `black --check .`; `flake8`; `mypy` per repo config.
- Exactly one definition of `_BANNED_RE` in the tree (grep proof).
- `docs/superpowers/**` still contains `ai-sw-export` (as the banned example)
  and the gate does NOT flag it.
- No `Co-Authored-By` trailer in any commit on the branch.
