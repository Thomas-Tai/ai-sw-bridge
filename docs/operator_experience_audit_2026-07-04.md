# Operator-Experience Audit & Remediation Tracker (2026-07-04)

**Question that triggered this:** *"As a fresh user on this repo with 20 years of SOLIDWORKS experience (but not a coder), is everything in the e2e enhancement plan actually implemented?"*

**Short answer at audit time:** **No.** The code/CI/installer machinery is implemented and green, but a CAD-only operator who follows the docs **verbatim cannot reach their first part** — the first build command is dead on no-clone installs, and the "no-Python" installer is not published anywhere. Goal 1 ("non-coder → first part, ≤1 command, chat-first") was **aspirational, not delivered**.

**Method:** a 6-auditor adversarial workflow from the 20-year-operator persona, then each load-bearing BLOCKER/MAJOR independently re-verified against source at HEAD `95fa30d`.

**How to use this doc:** each finding has a **Verify** line — the exact check to run after the fix. When every finding is `FIXED` and its Verify passes, the operator experience is genuinely delivered. Do **not** "fix" anything in the *Verified-good* section — those are correct. **To independently re-check everything in one pass, jump to [§ Verification Protocol](#-verification-protocol--runnable-cross-check-confirmed-2026-07-07) at the end** — it is a single COM-free command block (grep/git/gh/pytest only, no live seat) with the expected result for every finding.

Status legend: `OPEN` (confirmed defect, not yet fixed) · `FIXED` (remediated + Verify passes) · `DEFERRED` (needs a maintainer/outward-facing action).

---

## BLOCKERS (operator cannot reach first part)

### B1 — First build command is dead on every no-clone install · Status: FIXED
- **Evidence:** `README.md:133`, `docs/operator_guide.md:118/230/233`, `docs/ONBOARDING.md:49/116/119` all instruct `ai-sw-build examples/filleted_box/spec.json …`. `pyproject.toml` packages only `where=["src"]` + package-data `py.typed`; **no `MANIFEST.in`**; `examples/` lives at repo **root**, so it is **not in the wheel**. Canonical installs are pipx-from-git and the `.exe` — neither clones — so `examples/` is never on disk. `cli/build.py:612-614` exits 2 (file-not-found) on the missing path.
- **Operator impact:** installs exactly as told (not to clone), opens SOLIDWORKS, runs the one command promised to make "a filleted box appear in ~3 s," gets a JSON file-not-found error on their **first** command — before the AI step, so they have no spec to substitute. Most conclude the tool is broken.
- **Fix:** ship the demo spec as package data under `src/ai_sw_bridge/examples/` and add `ai-sw-build --demo` (resolves the spec via `importlib.resources`). Rewrite the quickstart commands to `ai-sw-build --demo …`.
- **Verify:** on a wheel install with **no repo checkout**, `ai-sw-build --demo --dry-run` exits 0 and reports `feature_count: 3`; no doc references `examples/…` on a no-clone path.

### B2 — The "no-Python" installer `.exe` is not published on any Release · Status: FIXED (v1.7.1 tag cut → `.exe` published & smoke-proven, 2026-07-07)
- **Evidence:** `docs/operator_guide.md:54-58` says "Download `ai-sw-bridge-setup-<version>.exe` from the Releases page and double-click it." `gh release view v1.7.0 --json assets` → **0 assets**; every release v1.3.0…v1.7.0 (Latest) has no `.exe`. The installer is proven to *build* (workflow_dispatch run `28697923375`, ~62 MB) but was never *published*; `CHANGELOG.md` still lists it under `[Unreleased]`.
- **Operator impact:** the path written for this exact persona dead-ends — they land on Releases, see only "Source code (zip/tar.gz)," and are stuck. The CI artifact needs a GitHub login + Actions access a non-coder lacks.
- **Fix (two parts):** (a) *docs, in-scope now* — stop sending operators to a download that isn't there; make pipx the supported path and state the `.exe` ships attached to tagged releases. (b) *maintainer/outward-facing* — publish the `.exe` by cutting a tag (release.yml's `installer` job auto-attaches a correctly-versioned `.exe` on tag runs), or manually upload.
- **Verify:** docs no longer promise a Release `.exe` that is absent; AND (to fully close) `gh release view <tag> --json assets` shows `ai-sw-bridge-setup-*.exe`.
- **VERIFIED 2026-07-07:** `v1.7.1` tag pushed at `daa5336` (CI green: 3.10/3.12/3.14 + install-smoke). `release.yml` published a real Release (`draft=false, prerelease=false`) at `/releases/tag/v1.7.1` with assets: **`ai-sw-bridge-setup-1.7.1.exe` (65,749,100 B ≈ 62.7 MB)**, the wheel, the sdist, and `checksums.txt` (unsigned — GPG optional, no key configured). The `installer` job's silent-install smoke passed on a clean windows-2025 runner (install → `ai-sw-build --list-kinds` → `pywin32 ok` → `mcp ok`), so the published `.exe` is proven functional, not merely built. Getting here also required clearing two CI honesty gates the `1.7.1` bump tripped: doc-truth (5 version banners → `2aa695a`) and i18n staleness (PUBLIC_API mirrors re-anchored → `daa5336`).

---

## MAJORS (severe operator friction / broken canonical workflow)

### M3 — Canonical "change a variable" workflow errors verbatim (flag underscores vs hyphens) · Status: FIXED
- **Evidence:** source registers **hyphenated** flags — `cli/mutate.py:65 --new-value`, `:77/:89 --proposal-id`; `cli/observe.py:293 --fit-view` (a `store_true`, takes no value), `:316 --entity-a`, `:322 --entity-b`. Docs use **underscores** — `USAGE.md:36/40/46`, `docs/tools_reference.md:53/63/79-80/86/92`, and both mirrors `docs/i18n/zh-CN/USAGE.md` + `zh-TW/USAGE.md`. argparse rejects `--new_value` as `unrecognized arguments`.
- **Operator impact:** USAGE Workflow 2 ("the guide says 16 mm but the model has 15 mm — change it safely"), the canonical operator task, errors on **every** command.
- **Fix:** rewrite the six flags to hyphens across the 5 files (+ re-anchor the two USAGE mirrors); drop `=true` on `--fit-view` (boolean). Subcommand names (`dry_run`, `undo_last_commit`) correctly stay underscored.
- **Verify:** `grep -rE "--(new_value|proposal_id|fit_view|entity_a|entity_b)" USAGE.md docs/tools_reference.md docs/i18n` returns nothing.

### M4 — Chat-first: the one-command MCP registrar is hidden; docs steer to hand-editing JSON · Status: FIXED
- **Evidence:** `docs/mcp_server_design.md` §6.6 tells the operator to hand-edit `%APPDATA%\Claude\claude_desktop_config.json` with an escaped path; that section has **zero** `--register` references. `ai-sw-doctor --register` (works; idempotent; timestamped backup — `cli/doctor.py`, `mcp/registration.py`) appears in operator docs only at `operator_guide.md:66`, scoped to the `.exe` checkbox — never for the canonical pipx path.
- **Operator impact:** a pipx operator wanting chat-first is told to hand-write escaped Windows paths into an opaque JSON file — the exact coder task the persona cannot do; one bad brace silently drops the server.
- **Fix:** make `ai-sw-doctor --register` the **primary**, first-listed registration step in README + §6.6 + ONBOARDING + operator_guide; demote manual JSON to an advanced fallback.
- **Verify:** README setup and mcp_server_design §6.6 both lead with `ai-sw-doctor --register`; manual JSON is labeled "advanced/fallback."

### M5 — "Chat-first" is really copy-JSON-then-run-CLI-yourself; AGENTS.md steers the AI away from MCP tools · Status: FIXED
- **Evidence:** `README.md:142-152` Step 4 and `operator_guide.md:204-221` = "paste prompt → agent picks a spec → **you approve and run the command yourself**." `docs/AGENTS.md:13`: "You never call the SOLIDWORKS COM API directly. You write JSON specs or invoke CLIs," and AGENTS.md has **zero** references to `sw_build`/any MCP tool. "Open Claude and paste" never says the MCP flow needs the Claude **Desktop** app.
- **Operator impact:** the non-coder is routed into a terminal for every part; even after registering MCP, their AI briefing tells it to emit JSON for manual CLI runs instead of calling `sw_build`.
- **Fix:** add a top-level "Talk to Claude to build a part (chat-first via MCP)" section (requires Claude **Desktop** → `--register` → restart → ask → approve elicitation); add an MCP-mode paragraph to AGENTS.md telling the agent to call `sw_build`/`sw_batch_execute` when the server is available.
- **Verify:** README has a chat-first-via-MCP section naming Claude Desktop; AGENTS.md references the MCP tools.

### M6 — README front door repels the target persona and hides the installer built for them · Status: FIXED
- **Evidence:** `README.md:21` routes "An operator — a SOLIDWORKS user, not a coder" to the quickstart; `README.md:85`: "**this is a Python developer tool** … if you've never run `python` from a command line, start with the Python beginner's guide first." `grep -n "installer|\.exe|Releases" README.md` → **0 hits** (the `.exe` lives only in operator_guide).
- **Operator impact:** the router promises a non-coder lane, then the first thing under it tells them to go learn Python; they never discover the double-click installer one doc away.
- **Fix:** add "No Python? Download the Windows installer" as the primary operator path in the README quickstart (once B2's asset exists); soften the "Python comfort assumed" framing under the operator heading.
- **Verify:** README operator quickstart leads with the installer path and no longer opens with a "go learn Python first" wall.

### M7 — Goal-1's "≤1 command" is 5–8 commands on the pipx path, incl. a PowerShell subshell · Status: FIXED (installer is the one-action path; pipx/subshell now labeled the developer path)
- **Evidence:** `README.md:87-110`: pre-install Python 3.10+/Git/pipx, `python -m pip install --user pipx`, `python -m pipx ensurepath`, reopen terminal, `pipx install …`, then `README.md:109` `& "$(pipx environment --value PIPX_LOCAL_VENVS)\ai-sw-bridge\Scripts\python.exe" -m pywin32_postinstall -install`, then doctor/probe/build.
- **Operator impact:** a CAD operator cannot reason about `pipx environment --value`, subshell expansion, or why COM won't attach without the pywin32 line — which also errors verbatim in `cmd.exe` (it's PowerShell).
- **Fix:** route operators to the `.exe` (runs pywin32 automatically) as the one-action path; keep pipx for developers. If pipx stays operator-facing, wrap the pywin32 step into `ai-sw-doctor --fix-pywin32`.
- **Verify:** the operator quickstart's primary path is ≤1 action (the installer) OR the pywin32 step is a single ai-sw-* command with no subshell.

### M8 — AGENTS.md (handed to the operator's AI) assumes a clone + `pip install -e .` + local `examples/` · Status: FIXED
- **Evidence:** `docs/AGENTS.md:17` "Install: `pip install -e .` from the repo root"; `:18-21`, `:40` build the workflow on copying local `examples/…`. The operator install is pipx/`.exe` — no repo root, no `examples/`.
- **Operator impact:** the AI faithfully tells the non-coder to `pip install -e .` from a repo root they never cloned and to copy from an `examples/` folder not on disk — contradicting the README.
- **Fix:** rewrite AGENTS.md quickstart to the operator install (pipx); draft specs inline or point at the bundled `--demo` spec instead of a local `examples/` tree.
- **Verify:** AGENTS.md no longer says `pip install -e .`/"repo root"/"copy from examples/" as the operator path.

### M9 — zh-TW README: all 8 in-page navigation anchors are dead · Status: FIXED
- **Evidence:** `docs/i18n/zh-TW/README.md:22` links `(#for-operators--5-minute-quickstart)` but the heading was translated to `## 給操作者 — 5 分鐘快速入門`; same at lines 23, 24, 26, 47, 158, 254. zh-CN re-slugged correctly (`README.md:24` `(#面向操作者--5-分钟快速入门)`), proving zh-TW is an oversight. The i18n dead-link test checks file links, not anchors.
- **Operator impact:** a Traditional-Chinese operator clicks the first "find your section" link and nothing scrolls.
- **Fix:** re-slug the 8 anchor targets to the translated headings (mirror zh-CN); optionally extend the dead-link test to intra-file anchors.
- **Verify:** every `](#…)` in `docs/i18n/zh-TW/README.md` matches a translated heading slug in the same file.

### M10 — `known_limitations.md` ("required reading") has three dead links · Status: FIXED
- **Evidence:** `docs/known_limitations.md:119` → `../spikes/phase0/MMP_DEBUG_SESSION.md` (untracked/absent), `:146` → `deferred_dim_investigation.md` (untracked), `:127` → `../README.md#roadmap` (no such heading). Required-reading per `README.md:281`, `operator_guide.md:247`. Same D10 class, in a doc outside the fixed/guarded set.
- **Operator impact:** told this file is mandatory before building, they open it and the three "here are the details" links 404 / scroll nowhere.
- **Fix:** commit the referenced notes or inline/remove the links; repoint `#roadmap` to `ROADMAP.md`.
- **Verify:** every relative link in `docs/known_limitations.md` resolves to a tracked file/valid anchor.

---

## MINORS

### m11 — README command table names a non-existent subcommand `undo` · Status: FIXED
- **Evidence:** `README.md:184` "Subcommands: `propose` / `dry_run` / `commit` / `undo`"; source registers `undo_last_commit` (`cli/mutate.py:96-97`). `tools_reference.md:96-98` + `USAGE.md:54` use the correct name — README is the outlier.
- **Fix / Verify:** change `README.md:184` to `undo_last_commit`; `ai-sw-mutate undo_last_commit --help` parses.

### m12 — `why_no_addim2.md` dead link (reached from a common troubleshooting symptom) · Status: FIXED (also caught: the spike-script table links are TRACKED/valid — only MMP_DEBUG_SESSION.md was dead)
- **Evidence:** `docs/why_no_addim2.md:131` → `../spikes/phase0/MMP_DEBUG_SESSION.md` (same missing file as M10). Entry points `README.md:162/205`, `operator_guide.md:196`.
- **Fix / Verify:** commit `MMP_DEBUG_SESSION.md` or remove the reference; link resolves.

### m13 — `installer/README-first.txt` pipx line omits `[mcp]` (latent until B2 ships) · Status: FIXED
- **Evidence:** `installer/README-first.txt:22` `pipx install git+https://github.com/Thomas-Tai/ai-sw-bridge` (**no `[mcp]`**), then `:27` "wire the MCP server later: `ai-sw-doctor --register`." `mcp/server.py:23` hard-imports `mcp`. `README.md:102` + `operator_guide.md:40` correctly include `[mcp]`.
- **Impact:** becomes a live MAJOR the instant the installer ships — `ai-sw-mcp` dies with `ModuleNotFoundError: No module named 'mcp'` inside Claude Desktop. **Fix before/with B2.**
- **Fix / Verify:** add `[mcp]` to the README-first install line; `grep "\[mcp\]" installer/README-first.txt` matches.

### m14 — `ONBOARDING.md` off-by-one ("28 subcommands" vs 27) · Status: FIXED
- **Evidence:** `docs/ONBOARDING.md:146` "28 subcommands" for `ai-sw-observe`; the parser registers 27.
- **Fix / Verify:** change to 27 (or derive programmatically).

### C15 (COSMETIC) — installer size stated as "~80–150 MB installed" vs ~62 MB download · Status: FIXED
- **Evidence:** `operator_guide.md:65` "~80–150 MB installed"; real artifact 65,180,080 bytes (~62 MB download). Framing is defensible (installed footprint ≠ download); no stale "114.2 MB"/"signed" claim survives. Not a breaker — down-ranked (4 audits over-raised it).
- **Fix / Verify:** also state the ~62 MB download the operator actually sees.

---

## Verified GOOD — do NOT "fix" these (they are correct)

- **CLI surface matches source.** All 22 `[project.scripts]` names match README/ONBOARDING; every advertised `ai-sw-build` flag exists in argparse; `ai-sw-doctor --register/--no-seat` and `ai-sw-probe` exist; `ai-sw-build --list-kinds` runs COM-free and returns `ok:true`.
- **MCP tool inventory is truthful** — exactly 37 `@mcp.tool()` functions; `mcp_server_design.md` §6.6, `server.py`, README, and `test_server_contract.py` EXPECTED_TOOLS all agree on 37.
- **The MCP registrar is correct** — idempotent, timestamped backup, transparent. The defect (M4) is that it's *undocumented for pipx*, not broken.
- **Installer honesty is correct where it exists** — SmartScreen "More info → Run anyway", "not code-signed" everywhere, SOLIDWORKS prerequisite, per-user/no-admin `%LOCALAPPDATA%`, all match `installer/ai-sw-bridge.iss`.
- **English core-path links resolve** — README/USAGE/operator_guide/AGENTS/PUBLIC_API/SECURITY/CHANGELOG relative links, the 6 README TOC anchors, and the zh-CN mirror are all correct.

## False-positive / calibration notes

- README's 6 TOC anchors were flagged-then-cleared by the link audit — correctly **not** a bug.
- Installer size (C15) is defensible framing, not a breaker.
- `undo` (m11) rated MINOR not MAJOR (rare command vs the core edit flow).
- No fabricated findings; the audits were evidence-disciplined.

---

## Remediation log (fill in as fixes land)

| ID | Status | Commit | Notes |
|----|--------|--------|-------|
| B1 | FIXED | `dd1d542` | package-data `examples/*.json` + `ai-sw-build --demo` + test + docs; wheel-verified |
| B2 | FIXED | `dd1d542` (docs) + `v1.7.1`@`daa5336` | `.exe` published on the v1.7.1 Release (`ai-sw-bridge-setup-1.7.1.exe`, 62.7 MB), silent-install smoke-proven on windows-2025 |
| M3 | FIXED | `16f6109` (+i18n re-anchor `3c90006`) | flag underscores→hyphens across USAGE/tools_reference/zh mirrors |
| M4 | FIXED | `aef2542` | mcp_server_design §6.6 leads with `ai-sw-doctor --register`; manual JSON demoted |
| M5 | FIXED | `aef2542` | README Step 4 chat-first via MCP + Claude Desktop; copy-paste = fallback |
| M6 | FIXED | `aef2542` | README front door leads with the no-Python installer (path A) |
| M7 | FIXED | `aef2542` | installer = one-action path; pipx/pywin32-subshell relabeled developer path |
| M8 | FIXED | `aef2542` | AGENTS.md: no clone/`pip -e .` assumption; prefer MCP tools; examples on GitHub |
| M9 | FIXED | `16f6109` | zh-TW README 8 dead nav anchors re-slugged to translated headings |
| M10 | FIXED | `16f6109` | known_limitations dead links de-linked / repointed to ROADMAP.md |
| m11 | FIXED | `aef2542` | README `undo`→`undo_last_commit` |
| m12 | FIXED | `16f6109` | why_no_addim2 dead link removed (spike-dir links kept — verified tracked) |
| m13 | FIXED | `dd1d542` | `[mcp]` added to README-first pipx line |
| m14 | FIXED | `16f6109` | ONBOARDING "28"→"27" subcommands |
| C15 | FIXED | `dd1d542` | ~62 MB download stated alongside installed footprint |

**All 14 findings FIXED.** Release published + smoke-proven 2026-07-07 (v1.7.1). Repo-health beyond the audit: the scheduled `Security`/gitleaks red (10 known sketch-relation FPs, broken by the W68 IP-scrub SHA rewrite) was regenerated in `e63aad6` and re-verified green; the `Upstream drift` scheduled "failure" is working-as-designed (alarms the ported-from upstream advanced past its pin). **No deferrals remain:** the zh-CN/zh-TW README mirrors were retranslated to the v1.7.1 front door (`6c1ace9`, CI green) — Install A/B + chat-first Step 4 + m11 + banner, re-anchored `dd1d542`→`9937f99`, sentinel dropped; the USAGE and PUBLIC_API mirrors were already fresh (verified, no change). All six front-door mirrors now pass `test_i18n_staleness.py` as fresh (no sentinel), so the honest-lag debt is fully paid down, not just declared.

---

## ✅ Verification Protocol — runnable cross-check (confirmed 2026-07-07)

Every fix has a **concrete, COM-free command**. Paste the block below from the
repo root; each line prints a label + its result. Then compare against the
**Expected** column. Nothing here touches COM or the live seat — only
`grep`/`git`/`gh`/`pytest` — so it is safe to run with SOLIDWORKS open.

- **Confirmed at:** HEAD `8bcaa8a` on `master`, release tag `v1.7.1` → `daa5336`. **Re-verified `b6f0b3f` (2026-07-07, post zh-README-retranslation): 16/16 checks still pass, nothing regressed.**
- **Convention:** for "absence" checks (M3/M9/M10/m12) a clean result is **no
  output and `exit=1`** (grep found nothing). For "presence" checks a non-zero
  count is the pass.

```bash
# ── run from the repo root ──────────────────────────────────────────────
# B1  demo spec ships INSIDE the importable package (works on no-clone installs)
python -c "from importlib.resources import files; print('B1a is_file:', (files('ai_sw_bridge')/'examples'/'filleted_box.json').is_file())"
python -m pytest tests/cli/test_build_demo.py -q                                   # B1b
# B2  the installer .exe is PUBLISHED on the Release
gh release view v1.7.1 --json assets --jq '.assets[].name'                          # B2
# M3  no underscore CLI flags survive in the docs
grep -rEn -- '--(new_value|proposal_id|fit_view|entity_a|entity_b)' USAGE.md docs/tools_reference.md docs/i18n; echo "M3 exit=$?"
# M4  ai-sw-doctor --register is documented as the registration step
grep -c -- 'ai-sw-doctor --register' README.md docs/mcp_server_design.md            # M4
# M5  chat-first names Claude Desktop; AGENTS references the MCP tool
echo "M5 desktop=$(grep -ic 'claude desktop' README.md) agents_sw_build=$(grep -c sw_build docs/AGENTS.md)"
# M6  README front door surfaces the installer (was 0 hits pre-fix)
echo "M6 installer_hits=$(grep -cEi 'installer|\.exe|releases' README.md)"
# M7/M8  AGENTS operator path installs NOTHING (pip -e is contributor-scoped only)
echo "M8 no_install_line=$(grep -c 'you do not install anything' docs/AGENTS.md)"
# M9  zh-TW dead nav anchor removed
grep -Fn '(#for-operators--5-minute-quickstart)' docs/i18n/zh-TW/README.md; echo "M9 exit=$?"
# M10 known_limitations dead links removed
grep -nE 'MMP_DEBUG_SESSION|deferred_dim_investigation|README\.md#roadmap' docs/known_limitations.md; echo "M10 exit=$?"
# m11 README uses undo_last_commit (not bare 'undo')
echo "m11 undo_last_commit=$(grep -c undo_last_commit README.md)"
# m12 no dead LINK to MMP_DEBUG_SESSION (a plain-prose mention is fine)
grep -nE '\]\([^)]*MMP_DEBUG_SESSION[^)]*\)' docs/why_no_addim2.md; echo "m12 exit=$?"
# m13 README-first installs the [mcp] extra
echo "m13 mcp_extra=$(grep -Fc '[mcp]' installer/README-first.txt)"
# m14 ONBOARDING subcommand count corrected
echo "m14 stale=$(grep -c '28 subcommands' docs/ONBOARDING.md) current=$(grep -c '27 subcommands' docs/ONBOARDING.md)"
# C15 the real ~62 MB download is stated alongside the installed footprint
grep -niE '~?62 ?MB' docs/operator_guide.md                                         # C15
# GATES  the honesty gates the release depends on
python -m pytest tests/test_doc_truth.py tests/test_i18n_staleness.py tests/cli/test_build_demo.py -q
# CI     all workflows green on the tagged/current commit
gh run list --branch master --limit 4 --json workflowName,conclusion --jq '.[] | "\(.conclusion) \(.workflowName)"'
```

| ID | What it proves | Expected result | Confirmed 2026-07-07 |
|----|----------------|-----------------|----------------------|
| B1a | demo spec is in the wheel-importable package | `is_file: True` | ✅ `True` |
| B1b | `--demo` path is offline-tested | `5 passed` | ✅ 5 passed |
| B2 | the `.exe` is published, not just built | asset list includes `ai-sw-bridge-setup-1.7.1.exe` | ✅ present (+ wheel, sdist, checksums) |
| M3 | canonical flags are hyphenated in docs | no output, `M3 exit=1` | ✅ clean |
| M4 | `--register` is the documented step | README ≥1 **and** mcp_server_design ≥1 | ✅ `1` / `1` |
| M5 | chat-first names Desktop; AI briefed on MCP | desktop ≥1 **and** agents_sw_build ≥1 | ✅ `8` / `1` |
| M6 | README surfaces the installer | installer_hits ≥1 (was `0`) | ✅ `6` |
| M7 | installer is the ≤1-action path | (read: quickstart path A = installer; pipx = "developers") | ✅ manual-read |
| M8 | AGENTS operator path installs nothing | no_install_line ≥1; `pip -e` is contributor-only | ✅ `1` |
| M9 | zh-TW nav anchors live | no output, `M9 exit=1` | ✅ clean |
| M10 | known_limitations links resolve | no output, `M10 exit=1` | ✅ clean |
| m11 | README uses `undo_last_commit` | count ≥1 | ✅ `1` |
| m12 | no dead **link** to MMP_DEBUG_SESSION | no output, `m12 exit=1` (prose mention allowed) | ✅ clean |
| m13 | README-first installs `[mcp]` | mcp_extra ≥1 | ✅ present (line 22 + note) |
| m14 | ONBOARDING count is 27 | stale=`0`, current=`1` | ✅ `0` / `1` |
| C15 | ~62 MB download stated | ≥1 hit | ✅ line 71 |
| GATES | doc-truth + i18n + demo gates pass | `47 passed` | ✅ 47 passed |
| CI | all workflows green on master | `success CI`, `success Security`, `success License lint` | ✅ green |

**If any row fails a future re-run:** that fix regressed — the finding above it
names the file, the operator impact, and the remediation commit to diff against.
Absence checks (M3/M9/M10/m12) flip to a failure the moment a bad pattern is
re-introduced, so this block doubles as a regression tripwire, not just a
one-time sign-off.
