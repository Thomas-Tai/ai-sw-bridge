# Phase 4 — i18n Retranslation & the Honesty Gate (Design Specification)

> **Status:** DRAFT for review gate · **Date:** 2026-07-02 · **Author:** (SDD orchestrator)
> **Governing plan:** `docs/superpowers/specs/2026-07-01-commercial-google-standard-elevation-design.md` §11 (Phase 4 "Expandability", here **narrowed to i18n-only** by ratified scope decision — installer + perf gate relegated to a distinct Phase 5).
> **Predecessors:** [[project_phase3_contributor_architecture_rigor_shipped]], Phase 2 (Diátaxis front door), Phase 1 (persona-routed README).

---

## 1. Objective

Bring the Simplified- and Traditional-Chinese documentation mirrors up to the **v1.7.0** baseline against the persona-routed front door, and install a **structural CI gate that makes silent i18n rot impossible** — without imposing translation work as a tax on English-doc velocity. English remains the single authoritative surface; translations are permitted to lag, but a lagging mirror is *forbidden from hiding that fact*.

Two deliverables, one atomic phase:
1. **The True-Up** — retranslate the mirror set to v1.7.0, bump each `translated-from` SHA, fix inherited dead links.
2. **The Honesty Gate** — a `test_i18n_staleness.py` enforcing the **Model B** biconditional: *mirror is stale ⇔ it carries a machine-detectable staleness banner*.

Closes Issue #10 (i18n sync tracking).

---

## 2. Ratified anchors (from the brainstorm gate)

These are settled; the review gate does **not** reopen them absent new technical evidence:

- **A2.1 — Model B (honesty-enforcing), not Model A (freshness-enforcing).** The gate never forces a translation when English changes; it only forbids a stale mirror from masquerading as current. Rationale: solo-maintained, Windows-only, English-authoritative bridge — Model A would have blocked ~half of Phases 1–3's commits. Model B matches the spec's own biconditional phrasing (governing §7.4 line 135) and the pattern the mirrors already follow by hand.
- **A2.2 — Phase 4 is i18n-only.** The governing spec's "Expandability" bundled i18n with an Inno Setup installer, extension-model generalization, and a perf gate — a scoping error (the installer touches the release pipeline, not Markdown). Those move to **Phase 5**. Phase 4 ships translation + gate as a self-contained, reversible unit.

---

## 3. Current state (measured 2026-07-02)

### 3.1 What exists
- **Mirror tree:** `docs/i18n/{zh-CN,zh-TW}/` — each holds `README.md`, `known_limitations.md`, `why_no_addim2.md`, all frontmatter-pinned `translated-from: c8ce816` (≈ v0.3 era). Each README carries a **hand-written** staleness banner ("此翻译已过期 / 此翻譯已過期") steering readers to English and referencing Issue #10.
- **Process doc:** `docs/i18n/TRANSLATION_PROMPT.md` — a mature parameterized prompt with a **DO-NOT-TRANSLATE list** (tool/file names, SW API surface, bridge-internal identifiers, spec schema + CLI flags, file/code references, hardware/domain terms), style guidance, output format, and a **Maintenance** section that already prescribes the `translated-from` frontmatter, "structural rewrite ⇒ full re-translation not diff", and "new docs since last translation".
- **English sources (current, v1.7.0):** `README.md` (419 L), `USAGE.md` (151 L), `docs/PUBLIC_API.md` (288 L). All three received Diátaxis nav treatment in Phase 2.
- **Runtime locale scaffold:** `src/ai_sw_bridge/locale/` + `tests/test_locale.py` — gettext passthrough, `--locale` flag. **Unrelated to doc staleness** (runtime string i18n, not Markdown mirrors); untouched by this phase.

### 3.2 What is missing / broken
- **No drift gate exists.** No CI step or test reads `translated-from`; the banners are pure convention. Confirmed: `grep` of `.github/workflows/` + `tests/` finds nothing enforcing i18n freshness.
- **Mirrors lag ~7 minor versions** (v0.3 → v1.7). Content (CLI list, capability scope, test counts) is severely behind.
- **D10 dead links persist in the mirrors:** `docs/i18n/{zh-CN,zh-TW}/README.md` still link `../../api_reference.md` (a file that is not committed; Phase 2 already de-linked it from the *English* README, but the frozen mirrors never got the fix).

---

## 4. Scope

### 4.1 The mirror set (re-targeted to the Phase-2 front door)
Phase 4 defines the **canonical mirror set** as the three front-door documents, per locale:

| English source | Diátaxis role | Mirror path (per locale) |
|---|---|---|
| `README.md` | Front door / How-to entry | `docs/i18n/<loc>/README.md` |
| `USAGE.md` | How-to guide | `docs/i18n/<loc>/USAGE.md` |
| `docs/PUBLIC_API.md` | Reference / Contract | `docs/i18n/<loc>/PUBLIC_API.md` |

`<loc> ∈ {zh-CN, zh-TW}` → **6 mirror files** total. `README.md` is retranslated in place; `USAGE.md` and `PUBLIC_API.md` are **net-new mirrors**.

> **Deliberate exclusion:** `docs/tools_reference.md` (the fourth Diátaxis-nav doc) is **out of scope** — it is a 244-line generated-flavored tool table with low translation ROI and high churn; the Reference role is covered by `PUBLIC_API.md`. Named here so the omission is intentional, not an oversight.

### 4.2 Legacy mirror disposition (**OPEN DECISION — see §9.1**)
`known_limitations.md` and `why_no_addim2.md` exist as mirrors but are **not** in the re-targeted set. They must be dispositioned explicitly (retire vs. keep-honestly-stale). Default recommendation in §9.1.

### 4.3 In scope
- Retranslate the 6 front-door mirror files to v1.7.0 via the `TRANSLATION_PROMPT.md` process; bump `translated-from` to the current English source SHA.
- Repair inherited dead links (D10) as a natural consequence of translating from post-Phase-2 English; a link-check gate enforces zero dead relative links in mirrors.
- Build `tests/test_i18n_staleness.py` (Model B) + a stable, machine-detectable banner marker.
- Wire CI so the gate runs with sufficient git history (`fetch-depth: 0`).
- A structural fidelity check (headings parity, DO-NOT-TRANSLATE token preservation, frontmatter present).
- Close Issue #10; add an i18n freshness note to the CONTRIBUTING PR checklist.

### 4.4 Out of scope (Phase 5 or never)
- Inno Setup installer, perf gate, extension-model generalization (→ Phase 5).
- Runtime-string i18n / `.mo` compilation (the `locale/` scaffold is separate).
- New locales beyond zh-CN / zh-TW.
- Translation of deep-dive/reference docs beyond the front-door trio.
- **Model A freshness enforcement** (explicitly rejected).
- Merging or altering any engine/COM behavior.

---

## 5. The Honesty Gate — design (Model B)

### 5.1 The invariant
For every mirror file in the tracked manifest, let `S` = its English source and `sha0` = its `translated-from` frontmatter value:

- **stale(mirror)** ≝ the English source `S` has commits **after** `sha0` — i.e. `git rev-list <sha0>..HEAD -- <S>` is non-empty.
- **Model B biconditional:** `stale(mirror) ⇔ banner_present(mirror)`.
  - stale **and** no banner → **FAIL** (silent rot — the exact failure Phase 4 prevents).
  - fresh **and** banner → **FAIL** (a fresh mirror crying wolf; softer, but keeps the signal honest).
  - stale **and** banner → PASS (honest lag — permitted).
  - fresh **and** no banner → PASS (fresh, truthful).

This measures *"did the source move since the snapshot"*, **not** *"does `translated-from` equal the latest SHA"* — so it tolerates honest lag while catching drift. It is strictly weaker than Model A by design.

### 5.2 The banner marker (machine-detectable)
Free-form Chinese prose ("此翻译已过期") is brittle to grep. Phase 4 introduces a **stable sentinel** the gate keys off, placed inside the human-readable banner block:

```
<!-- i18n-staleness-banner -->
```

- `banner_present(mirror)` ≝ the literal sentinel `<!-- i18n-staleness-banner -->` appears in the file.
- The human-readable localized banner text sits adjacent to the sentinel (translators keep the prose; the gate keys off the comment). The retranslated fresh mirrors ship **without** the sentinel; a future drift requires adding it back (or updating the translation).

### 5.3 The manifest
A single explicit dict in the test — `{mirror_path: english_source_path}` — is the source of truth for *what is tracked*. Retired files are simply absent (and deleted from disk). New mirrors are added here. Example shape:

```python
I18N_MIRRORS = {
    "docs/i18n/zh-CN/README.md":     "README.md",
    "docs/i18n/zh-CN/USAGE.md":      "USAGE.md",
    "docs/i18n/zh-CN/PUBLIC_API.md": "docs/PUBLIC_API.md",
    "docs/i18n/zh-TW/README.md":     "README.md",
    "docs/i18n/zh-TW/USAGE.md":      "USAGE.md",
    "docs/i18n/zh-TW/PUBLIC_API.md": "docs/PUBLIC_API.md",
}
```

### 5.4 Fail-loud edges
- **Missing/blank `translated-from`** → FAIL (a tracked mirror must declare its snapshot).
- **`translated-from` SHA not in git history** (rebase/force-push orphan) → FAIL (cannot verify ⇒ treat as untrustworthy, not silently pass).
- **Mirror path in manifest but file absent** (or vice-versa: an untracked file under `docs/i18n/<loc>/`) → FAIL (manifest ↔ disk membership must match, mirroring the extension-contract conformance pattern).

### 5.5 Git-history dependency & local ergonomics
The gate shells out to `git` (`rev-list`, `cat-file -e`). It requires history for the source paths.
- **CI:** the i18n job checks out with `fetch-depth: 0` (as `release.yml`/`security.yml` already do) so the gate runs for real and never skips.
- **Local / shallow clone:** if `git` is unavailable or the clone is shallow such that `sha0` is unreachable, the test **skips with an explicit reason** (never a false pass, never a false block on a contributor's shallow checkout). CI is the enforcing surface.

### 5.6 Structural fidelity check (companion, same test module)
Independent of staleness, assert per fresh mirror:
- Frontmatter `translated-from:` present and well-formed.
- **Heading skeleton parity** with the English source (same count/order of ATX `#` headings, modulo the localized banner block) — catches dropped sections and structural drift.
- **DO-NOT-TRANSLATE tokens preserved verbatim** — a sampled set of high-signal tokens (`ai-sw-build`, `FeatureCut4`, `SolidWorksClient`, `--locale`, `spec.json`, `PARAMNOTOPTIONAL`, etc. drawn from the TRANSLATION_PROMPT list) must appear identically in the mirror.
- **Zero dead relative links** — every `](...)` relative target resolves on disk (this is the D10 enforcement).

---

## 6. The True-Up — translation process

- **Vehicle:** the `TRANSLATION_PROMPT.md` process (DO-NOT-TRANSLATE list authoritative). Translation is a mechanical-but-judgment task; in SDD it is performed per-file by a subagent following the prompt, then structurally gated (§5.6) and human-reviewed for prose quality.
- **Snapshot discipline:** translate against a **frozen English baseline SHA**; do **not** co-edit the English sources in the same commits as the translations (else the mirror is "born stale"). Set each `translated-from` to the source file's current `git log -1` SHA at translation time. Because Phase 4 touches only mirrors (not English sources), the sources' latest SHAs predate the translation commit → mirrors land **fresh**, gate green, banner sentinel **absent**.
- **Human quality gate:** the maintainer is a native zh reader (zh-TW Traditional / zh-CN Simplified). Final DoD includes a human read-through for prose quality — the one thing structural gates cannot assert. (Named as a **human gate**, like the commercial-audit runbook's gates.)
- **D10 resolution:** translating from the post-Phase-2 English README (already de-linked from `api_reference.md`) yields correct links; the §5.6 dead-link check backstops it. No mirror may reference `api_reference.md`.

---

## 7. Definition of Done

- [ ] 6 front-door mirror files (README/USAGE/PUBLIC_API × zh-CN/zh-TW) retranslated to v1.7.0; `translated-from` bumped to current source SHAs; banner sentinel absent (fresh).
- [ ] Legacy mirror disposition executed per §9.1 ruling (retired **or** kept-honestly-stale-with-sentinel).
- [ ] `tests/test_i18n_staleness.py` green: Model B biconditional + fail-loud edges + manifest↔disk membership + structural fidelity + dead-link check.
- [ ] Gate **bite-proven**: (a) blank a `translated-from` → FAIL; (b) simulate source drift (manifest entry whose source moved) with no sentinel → FAIL; (c) sentinel present on a fresh file → FAIL. Revert all probes.
- [ ] CI runs the gate with `fetch-depth: 0`; green on the matrix.
- [ ] Full seat-safe suite green (baseline + the new i18n test count); live seat untouched (this phase is COM-free — **no seat-prefire needed**, but the suite-green + PID-unchanged invariants still hold).
- [ ] Issue #10 closed; CONTRIBUTING PR checklist gains an i18n-freshness line.
- [ ] Human prose-quality review signed off by the maintainer.
- [ ] isPrivate-guarded FF push to master; branch `docs/commercial-elevation` only.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Translation quality** can't be machine-verified | Structural gate (§5.6) + mandatory human read-through (native reader). Structural fidelity is the CI floor; prose quality is the human gate. |
| **Born-stale mirrors** (English co-edited with translation) | Snapshot discipline (§6): translate against frozen source SHA; don't touch English sources in translation commits. |
| **Gate needs git history**; shallow/local clones | `fetch-depth: 0` in CI; skip-with-reason locally (§5.5). Never a false pass. |
| **Banner sentinel churn** — translators forget it on future drift | That IS the gate: forgetting the sentinel on a stale file → CI red. Self-correcting. |
| **Scope creep** back toward installer/perf | A2.2 isolation; those are Phase 5. |
| **zh-TW vs zh-CN divergence** (Traditional vs Simplified are separate translations, not transliterations) | Treat as 6 independent files; do not auto-convert. DO-NOT-TRANSLATE tokens identical across both. |

---

## 9. Open decisions for the review gate

### 9.1 Legacy mirror disposition (`known_limitations.md`, `why_no_addim2.md`)
Three options:
- **(A) Retire — RECOMMENDED.** Delete both from `docs/i18n/{zh-CN,zh-TW}/` (4 files). Their v0.3 content is superseded and outside the re-targeted front-door set; keeping stale translations of non-canonical docs is pure maintenance surface. **Precondition:** grep for inbound links to them (from English or mirror docs) and remove/redirect before deleting, so no new dead link is created.
- **(B) Keep honestly-stale.** Add the sentinel to both (they *are* stale), add them to the manifest, leave the v0.3 content. Model B permits this — but it commits us to carrying 10 tracked mirrors and forever-bannered dead-weight.
- **(C) Retranslate them too.** Expands the true-up from 6 → 10 files. High cost, low audience value (design-rationale + limitations deep-dives vs. the front door operators actually read).

**Recommendation: (A) Retire**, contingent on the inbound-link check. Rationale: smallest honest surface, aligns the mirror set exactly with the front door, matches the ratified "6 mirror files" target.

### 9.2 Banner sentinel form
Proposed `<!-- i18n-staleness-banner -->` (HTML comment; invisible in rendered Markdown, greppable, locale-neutral). Alternative: a frontmatter boolean `stale: true`. **Recommendation:** the HTML-comment sentinel — it co-locates with the visible banner prose and survives Markdown renderers that strip unknown frontmatter. (Ratify or override.)

### 9.3 Fresh→banner-absent half of the biconditional
The anti-rot core is *stale ⇒ banner*. The converse (*fresh ⇒ no banner*) is a nicety that keeps the signal honest but adds a small edge (a translator who leaves a stale sentinel after refreshing trips it). **Recommendation:** enforce both (full biconditional per governing §7.4), since a false "stale" banner is itself a small dishonesty. (Ratify or relax to one-directional.)

---

## 10. Deliverable map (informs the plan, not the plan itself)

- `docs/i18n/zh-CN/{README,USAGE,PUBLIC_API}.md` — retranslated (README) + net-new (USAGE, PUBLIC_API).
- `docs/i18n/zh-TW/{README,USAGE,PUBLIC_API}.md` — same.
- `docs/i18n/{zh-CN,zh-TW}/{known_limitations,why_no_addim2}.md` — retired per §9.1(A) (or bannered per (B)).
- `tests/test_i18n_staleness.py` — Model B gate + structural fidelity + dead-link + manifest membership.
- `.github/workflows/ci.yml` — i18n gate step with `fetch-depth: 0` on the relevant job.
- `CONTRIBUTING.md` — PR-checklist i18n-freshness line.
- `docs/i18n/TRANSLATION_PROMPT.md` — Maintenance section updated to reference the sentinel + the gate (so translators know the contract).
- Issue #10 — closed with a pointer to the gate.

---

## 11. Success criterion (one sentence)

After Phase 4, the Chinese front-door mirrors read correctly at v1.7.0 with no dead links, and it is **structurally impossible** for any mirror to fall behind English again without either being refreshed or visibly, greppably declaring itself stale — enforced in CI at zero cost to English-doc velocity.
