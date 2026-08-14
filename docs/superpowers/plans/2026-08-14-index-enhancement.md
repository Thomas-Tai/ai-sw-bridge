# Landing-Page Breadth Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance `site/index.html` so a fresh visitor grasps, in ~15 seconds, that the bridge produces a *real parametric model* (named tree + equations that survive an edit), that it runs the *whole workflow* (part → assembly → DFM → drawing → export), and that it spans a *wide feature/mate surface* — while cutting prose the new visuals make redundant.

**Architecture:** Two new `<section>` blocks are inserted after the hero (Block ① three-zone Dead→Real→Survives anchor; Block ② five-tile workflow filmstrip + a text breadth strip). A subtractive "flow pass" trims the essay to 3 beats and removes the A4 explainer. `tools/build_pages.py` is generalized from copying one hero image to copying a list of assets. Five tile stills are seat-free ffmpeg frame-extracts from existing verified GIFs; three Block ① assets are captured in one live-SOLIDWORKS session (placeholders committed first so every intermediate commit lints green).

**Tech Stack:** Static HTML/CSS (single self-contained file, inline `<style>`, no CDN); Python 3.14 (`tools/build_pages.py`); ffmpeg (frame extraction + GIF encode); pytest (`tests/tools/`); the repo's launch-kit lint (`tools/check_launch_kit.py`); GitHub Pages `gh-pages` branch.

## Global Constraints

Every task's requirements implicitly include these (verbatim from the spec):

- **No `Co-Authored-By: Claude`** trailer on any commit.
- **Renderers/tools are non-destructive** — never save a SOLIDWORKS document; open → observe → close without saving.
- **L6 honesty / defensibility:** every caption and number must be defensible against `docs/CAPABILITIES.md` + the CLI registry. **No phantom CLI** — export is a "spec export block", never `ai-sw-export` (only `ai-sw-export-dxf-flat` + `ai-sw-import` exist). No visual may imply live in-browser SOLIDWORKS; the live-edit GIF is labeled "recording of a real seat".
- **Breadth counts are exact:** **36 feature kinds** (extrude/cut/revolve + the CAPABILITIES table) and **16 mate types**. The breadth strip lists only *supported* kinds — it must **NOT** name lofts, ribs, wraps, or combines (those are the honestly-refused kernel walls the essay owns).
- **Source keeps `../`-relative paths** (`../docs/img/…`, `../docs/…`) so `tools/check_launch_kit.py` verifies them on disk; the publish rewrite lives only in `tools/build_pages.py`.
- **Every commit must keep the launch-kit lint green:** `python tools/check_launch_kit.py` exits 0 (all `src`/`href` resolve on disk; no banned claims).
- **Exactly one motion asset** (the Block ① live-edit GIF, ≤ ~1 MB); everything else is a static still or plain text.
- **Ships WITH the launch, but do not deploy** until the three real Block ① captures replace their placeholders (Task 6). External sends stay user-driven — this plan does not fire them.
- **Windows/PowerShell:** the repo path contains `[Local]` (a glob metacharacter) — always `git -C "<literal path>"` or run from inside the repo; use the session scratchpad for temp dirs, not `/tmp`.

**Repo:** `C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge`, branch `master` (tip `b14ccb1`). **Spec:** `docs/superpowers/specs/2026-08-14-index-enhancement-design.md`.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `docs/img/still_{part,assembly,observe,drawing,export}.png` | 5 seat-free tile stills (lower-third caption band cropped off) | 1 |
| `docs/img/anchor_dead_step.png`, `anchor_alive_tree.png`, `anchor_live_edit.gif` | 3 Block ① assets — placeholders in Task 1, real captures in Task 6 | 1, 6 |
| `site/index.html` | Block ① (T2), Block ② + breadth strip (T3), flow pass (T4); additive CSS | 2, 3, 4 |
| `tools/build_pages.py` | Generalize single-hero copy → asset **list**; add `CAPABILITIES.md` link rewrite | 5 |
| `tests/tools/test_build_pages.py` | Cover asset copy + repoint + fail-loud | 5 |
| `_site/` (generated, git-ignored) → `gh-pages` branch | Deployed artifact | 7 |

**Task order rationale:** Task 1 puts all eight image files on disk (5 real stills + 3 placeholders) so Tasks 2–3 can reference them with the lint green. Tasks 2–4 are independent HTML edits. Task 5 (build script) is pure Python/TDD. Task 6 is the one seat session. Task 7 deploys only after the real captures land.

---

## Task 1: Produce all image assets on disk (5 real stills + 3 placeholders)

**Files:**
- Create: `docs/img/still_part.png`, `docs/img/still_assembly.png`, `docs/img/still_observe.png`, `docs/img/still_drawing.png`, `docs/img/still_export.png`
- Create (placeholders): `docs/img/anchor_dead_step.png`, `docs/img/anchor_alive_tree.png`, `docs/img/anchor_live_edit.gif`

**Interfaces:**
- Produces: eight image files at the exact paths above. Tasks 2–3 reference them as `../docs/img/<name>` from `site/index.html`.

**Design note — crop the caption band off all five stills.** Every `demo_*.gif` frame has a burned-in *lower-third* caption + tool tag. Cropping that band off (a) removes the phantom `ai-sw-export` label on the export clip, (b) avoids double-captioning (the HTML tile supplies its own proof line + tool), and (c) keeps the info-cards (`SECTION A–A [experimental]`, `BILL OF MATERIALS`, `RE-IMPORTED …`) which sit in the *upper* area. Crop ≈ bottom 70 px of the 315 px frame; eyeball so no geometry or info-card is clipped.

- [ ] **Step 1: Extract + crop the 5 seat-free stills**

Run (from the repo root; adjust the `select` frame per clip by eye for the clearest state — suggested starting frames below):

```bash
ffmpeg -y -i docs/img/demo_part.gif     -vf "select=eq(n\,300),crop=iw:ih-70:0:0" -vframes 1 docs/img/still_part.png
ffmpeg -y -i docs/img/demo_assembly.gif -vf "select=eq(n\,28),crop=iw:ih-70:0:0"  -vframes 1 docs/img/still_assembly.png
ffmpeg -y -i docs/img/demo_observe.gif  -vf "select=eq(n\,40),crop=iw:ih-70:0:0"  -vframes 1 docs/img/still_observe.png
ffmpeg -y -i docs/img/demo_drawing.gif  -vf "select=eq(n\,44),crop=iw:ih-70:0:0"  -vframes 1 docs/img/still_drawing.png
ffmpeg -y -i docs/img/demo_export.gif   -vf "select=eq(n\,44),crop=iw:ih-70:0:0"  -vframes 1 docs/img/still_export.png
```

- [ ] **Step 2: Eyeball each still**

Open all five. Verify: the model/sheet reads clearly at tile size; the lower-third caption band is gone; **no `ai-sw-export` text remains on `still_export.png`**; info-cards are intact. Re-run a step with a different frame number if a still is weak.

- [ ] **Step 3: Create the 3 Block ① placeholders**

These are obvious "capture pending" stand-ins so the lint passes and the preview clearly shows what's not final. Real captures replace them in Task 6.

```bash
ffmpeg -y -f lavfi -i color=c=0x9AA0A6:s=560x360 -vf "drawtext=text='DEAD STEP — capture pending (seat)':fontcolor=white:fontsize=22:x=(w-tw)/2:y=(h-th)/2" -frames:v 1 docs/img/anchor_dead_step.png
ffmpeg -y -f lavfi -i color=c=0x9AA0A6:s=560x360 -vf "drawtext=text='ALIVE TREE + EQUATIONS — capture pending (seat)':fontcolor=white:fontsize=20:x=(w-tw)/2:y=(h-th)/2" -frames:v 1 docs/img/anchor_alive_tree.png
ffmpeg -y -f lavfi -i color=c=0x9AA0A6:s=560x360 -vf "drawtext=text='LIVE EDIT 16->20 — capture pending (seat)':fontcolor=white:fontsize=20:x=(w-tw)/2:y=(h-th)/2" -frames:v 1 docs/img/anchor_live_edit.gif
```

- [ ] **Step 4: Verify all eight files exist**

Run: `ls -la docs/img/still_*.png docs/img/anchor_*`
Expected: 5 `still_*.png` + `anchor_dead_step.png` + `anchor_alive_tree.png` + `anchor_live_edit.gif`, all non-zero.

- [ ] **Step 5: Commit**

```bash
git add docs/img/still_part.png docs/img/still_assembly.png docs/img/still_observe.png docs/img/still_drawing.png docs/img/still_export.png docs/img/anchor_dead_step.png docs/img/anchor_alive_tree.png docs/img/anchor_live_edit.gif
git commit -m "assets(site): 5 breadth stills (caption cropped) + 3 anchor placeholders"
```

---

## Task 2: Block ① — Dead → Real → Survives anchor (HTML + CSS)

**Files:**
- Modify: `site/index.html` — insert one `<section>` immediately after `</header>` (the hero close, ~line 222); append CSS inside the existing `<style>` block (before `</style>`, ~line 210).

**Interfaces:**
- Consumes: `docs/img/anchor_dead_step.png`, `anchor_alive_tree.png`, `anchor_live_edit.gif` (Task 1).
- Produces: a `<section class="anchor">` that Block ② (Task 3) is inserted *after*.

- [ ] **Step 1: Insert the Block ① markup**

Immediately after the hero's closing `</header>` tag, insert:

```html
<section class="anchor" aria-labelledby="anchor-heading">
  <div class="container">
    <h2 id="anchor-heading" class="section-title">Same shape. Opposite futures.</h2>
    <div class="grid-2up anchor-pair">
      <figure class="anchor-tile anchor-dead">
        <p class="eyebrow">what most &ldquo;AI CAD&rdquo; gives you</p>
        <img src="../docs/img/anchor_dead_step.png" alt="STEP import collapsed to a single Imported1 solid, no feature history">
        <figcaption>A frozen <code>Imported1</code> body — no history to edit.</figcaption>
      </figure>
      <figure class="anchor-tile anchor-alive">
        <p class="eyebrow">what the bridge builds</p>
        <img src="../docs/img/anchor_alive_tree.png" alt="the same part as a native SOLIDWORKS feature tree with named features and an Equation Manager driving the dimensions">
        <figcaption>Named features, driven by equations (<code>&quot;BORE_DIA&quot; = 16</code>).</figcaption>
      </figure>
    </div>
    <figure class="anchor-edit">
      <img src="../docs/img/anchor_live_edit.gif" alt="bore diameter changed from 16 to 20 millimetres; the feature tree rebuilds with no errors">
      <figcaption>Change one number — <code>BORE_DIA&nbsp;16&nbsp;&rarr;&nbsp;20</code> — and it survives the edit: the tree rebuilds, 0 errors. <span class="honesty">Recording of a real seat, not a live browser kernel.</span></figcaption>
    </figure>
  </div>
</section>
```

- [ ] **Step 2: Append the Block ① CSS**

Insert before `</style>`:

```css
  /* ---- Block ①: Dead → Real → Survives anchor ---- */
  .anchor .anchor-pair { align-items: stretch; }
  .anchor-tile {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    padding: 1rem;
    margin: 0;
  }
  .anchor-tile .eyebrow {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin: 0 0 0.6rem;
  }
  .anchor-tile img { width: 100%; height: auto; border-radius: 6px; display: block; }
  .anchor-tile figcaption { font-size: 0.85rem; color: var(--muted); margin-top: 0.6rem; }
  .anchor-dead img { filter: saturate(0.15); }
  .anchor-alive { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
  .anchor-edit { margin: 1.25rem 0 0; }
  .anchor-edit img { width: 100%; height: auto; border-radius: 8px; border: 1px solid var(--card-border); display: block; }
  .anchor-edit figcaption { font-size: 0.9rem; color: var(--muted); margin-top: 0.6rem; }
  .anchor-edit .honesty { display: block; font-size: 0.8rem; opacity: 0.8; margin-top: 0.2rem; }
```

- [ ] **Step 3: Run the launch-kit lint**

Run: `python tools/check_launch_kit.py`
Expected: exit 0 (all three `anchor_*` placeholder paths resolve on disk; no banned claims).

- [ ] **Step 4: Preview**

Open `site/index.html` in a browser. Verify: the anchor appears directly below the hero; the two tiles sit side-by-side (desktop) with the dead tile visibly desaturated and the alive tile accent-bordered; the placeholder GIF sits below the pair with its caption. Narrow the window: the pair stacks with the **dead tile on top**.

- [ ] **Step 5: Commit**

```bash
git add site/index.html
git commit -m "feat(site): add Block 1 dead-vs-alive-vs-survives anchor"
```

---

## Task 3: Block ② — workflow filmstrip + breadth strip (HTML + CSS)

**Files:**
- Modify: `site/index.html` — insert one `<section>` immediately after the `</section>` that closes Block ① (so order is hero → ① → ②); append CSS before `</style>`.

**Interfaces:**
- Consumes: `docs/img/still_{part,assembly,observe,drawing,export}.png` (Task 1); links `../docs/known_limitations.md` and `../docs/CAPABILITIES.md` (the latter's publish rewrite is added in Task 5).
- Produces: a `<section class="pipeline">` sitting before the "Who are you?" doorways.

- [ ] **Step 1: Insert the Block ② markup**

After Block ①'s closing `</section>`, insert:

```html
<section class="pipeline" aria-labelledby="pipeline-heading">
  <div class="container">
    <h2 id="pipeline-heading" class="section-title">It doesn&rsquo;t stop at the part. The same model runs the whole job:</h2>
    <ol class="filmstrip">
      <li class="film-tile">
        <img src="../docs/img/still_part.png" alt="the authored bearing-block part in SOLIDWORKS">
        <h3>Part</h3>
        <p>A real, authored <code>.SLDPRT</code> — the seed of everything below.</p>
        <p class="tool"><code>ai-sw-build</code></p>
      </li>
      <li class="film-tile">
        <img src="../docs/img/still_assembly.png" alt="the assembled widget: shaft seated through both bores">
        <h3>Assembly</h3>
        <p>Real mates, not fixed coordinates — the shaft seats through both bores.</p>
        <p class="tool"><code>ai-sw-assembly</code></p>
      </li>
      <li class="film-tile">
        <img src="../docs/img/still_observe.png" alt="a section view of the widget with a DFM info-card">
        <h3>Observe / DFM</h3>
        <p>Interference, mass, bounding box — measured on SW&rsquo;s own kernel.</p>
        <p class="tool"><code>ai-sw-observe</code></p>
      </li>
      <li class="film-tile">
        <img src="../docs/img/still_drawing.png" alt="a drawing sheet with orthographic and section views and a bill of materials">
        <h3>Drawing</h3>
        <p>Section A&ndash;A, auto-BOM, balloons — all from the one model.</p>
        <p class="tool"><code>ai-sw-drawing</code></p>
      </li>
      <li class="film-tile">
        <img src="../docs/img/still_export.png" alt="the widget re-imported from STEP with a round-trip info-card">
        <h3>Export</h3>
        <p>STEP / STL / 3MF — and STEP round-trips back, &Delta;bbox = 0.</p>
        <p class="tool">spec export block</p>
      </li>
    </ol>
    <p class="same-part">That&rsquo;s the same part in every frame — one model, all the way.</p>
    <div class="breadth">
      <p><strong>Features:</strong> the demo part uses a handful. The bridge builds <strong>extrude &middot; cut &middot; revolve</strong> over 7 sketch primitives, plus <strong>36 more feature kinds</strong> — fillets, chamfers, shell, draft, linear/circular/mirror/sketch patterns, sweeps &amp; sweep-cuts, dome, hole wizard, helix/spiral/projected curves, planar/offset/knit surfaces, sheet-metal (base flange &middot; hem &middot; bend), weldments, boolean (intersect &middot; scale &middot; delete-body).</p>
      <p><strong>Mates:</strong> <strong>16 mate types</strong> — incl. gear, rack-and-pinion, cam-follower, slot, hinge, width, linear-coupler — not just coincident/concentric.</p>
      <p class="breadth-ref">Full matrix &rarr; <a href="../docs/CAPABILITIES.md">CAPABILITIES.md</a>.</p>
    </div>
    <p class="micro">Every stage is propose &rarr; approve &rarr; execute — and the walls are labeled, not hidden: see <a href="../docs/known_limitations.md">Known Limitations</a>.</p>
  </div>
</section>
```

> **Honesty gate (do not skip):** the Features line lists only supported kinds. It must not name **loft, rib, wrap, or combine**. `still_export.png`'s tile says "spec export block", never `ai-sw-export`.

- [ ] **Step 2: Append the Block ② CSS**

Insert before `</style>`:

```css
  /* ---- Block ②: workflow filmstrip + breadth strip ---- */
  .filmstrip {
    list-style: none;
    padding: 0;
    margin: 1.5rem 0 1rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: stretch;
  }
  .film-tile {
    flex: 1 1 130px;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    padding: 0.75rem;
  }
  .film-tile img { width: 100%; height: auto; border-radius: 6px; border: 1px solid var(--card-border); display: block; }
  .film-tile h3 { font-size: 0.98rem; margin: 0.5rem 0 0.25rem; }
  .film-tile p { margin: 0; font-size: 0.82rem; color: var(--muted); }
  .film-tile p.tool { margin-top: 0.4rem; color: var(--text); }
  .same-part { font-size: 0.92rem; color: var(--muted); font-style: italic; margin: 0.25rem 0 1.25rem; }
  .breadth {
    background: var(--code-bg);
    border-radius: 10px;
    padding: 1rem 1.15rem;
    margin: 0 0 1rem;
  }
  .breadth p { margin: 0 0 0.5rem; font-size: 0.86rem; line-height: 1.5; }
  .breadth p:last-child { margin-bottom: 0; }
  .breadth .breadth-ref { color: var(--muted); }
  .pipeline .micro { font-size: 0.85rem; color: var(--muted); margin: 0; }
```

- [ ] **Step 3: Run the launch-kit lint**

Run: `python tools/check_launch_kit.py`
Expected: exit 0.

> If it flags `../docs/CAPABILITIES.md`: that means the on-disk file check passed but a banned-claim or path rule tripped — re-read the error. The `CAPABILITIES.md` file exists, so the disk check passes here; its *publish* rewrite is handled in Task 5 (this lint does not test the published artifact).

- [ ] **Step 4: Preview**

Open `site/index.html`. Verify: five tiles in a single row on a wide window (no horizontal page scrollbar); the breadth strip renders as a tinted panel below; the "same part in every frame" line reads; the micro-line links resolve. Narrow the window: tiles stack to one column, nothing overflows sideways. Adjust `.film-tile` `flex-basis` only if the row wraps on a normal desktop width.

- [ ] **Step 5: Commit**

```bash
git add site/index.html
git commit -m "feat(site): add Block 2 workflow filmstrip + feature/mate breadth strip"
```

---

## Task 4: Flow pass — trim the essay, remove the A4 explainer

**Files:**
- Modify: `site/index.html` — inside `<article id="essay">` (~lines 242–296).

**Interfaces:**
- Consumes: nothing new. Depends on Block ① existing (Task 2) so the cut prose is not lost.
- Produces: a 3-beat safety+speed essay; the `#essay` anchor is preserved (the doorways and CTA link to it).

- [ ] **Step 1: Replace the essay heading**

Change:

```html
    <h2>Driving real SOLIDWORKS from an AI agent — and why it's hard</h2>
```

to:

```html
    <h2>How you work with it: human-gated, and quick to try</h2>
```

- [ ] **Step 2: Delete beat 1 (the dead-STEP problem)**

Delete this entire block (Block ① now shows it):

```html
    <div class="beat">
      <h3>1. The problem</h3>
      <p>AI agents can already emit &ldquo;CAD,&rdquo; but that usually means a dead STEP or mesh dump from a throwaway kernel — geometry with no history, nothing you can open and keep editing in the tool you actually design in. ai-sw-bridge starts from a different premise: drive the CAD system you already run, and keep the feature tree native.</p>
    </div>
```

- [ ] **Step 3: Delete beat 3 (native tree vs. STEP)**

Delete this entire block (Block ① + the live-edit GIF now show it):

```html
    <div class="beat">
      <h3>3. Native editable feature tree vs. foreign STEP</h3>
      <p>The output is a real <code>.SLDPRT</code> feature tree you keep editing — change a dimension, rebuild, exactly like anything you built by hand. A STEP import isn't like that: you can only push its faces around, not edit the history that made them.</p>
    </div>
```

- [ ] **Step 4: Renumber the surviving beats**

The three kept beats are now `2 → 1`, `4 → 2`, `5 → 3`. Edit only the leading number in each `<h3>`:
- `<h3>2. Propose → approve → execute (human-gated safety)</h3>` → `<h3>1. Propose → approve → execute (human-gated safety)</h3>`
- `<h3>4. The real kernel walls</h3>` → `<h3>2. The real kernel walls</h3>`
- `<h3>5. Try it with no seat</h3>` → `<h3>3. Try it with no seat</h3>`

Leave each beat's `<p>` text unchanged (beat 4/now-2 keeps its `known_limitations.md` link; beat 5/now-3 keeps its `QUICKSTART.md` link).

- [ ] **Step 5: Delete the A4 explainer block**

Delete the entire `<div class="a4-block"> … </div>` (heading "AI + SOLIDWORKS — which fits your job?" and both `.card`s inside it). Its "real seat vs throwaway kernel" contrast is exactly what Block ① now shows. Leave the enclosing `</div>` (`.container`) and `</article>` intact.

- [ ] **Step 6: Run the launch-kit lint + confirm the anchor**

Run: `python tools/check_launch_kit.py`
Expected: exit 0.
Then grep to confirm the anchor and the doorway/CTA references survive:
Run: `grep -n 'id="essay"' site/index.html && grep -c 'href="#essay"' site/index.html`
Expected: one `id="essay"` line; at least 2 `href="#essay"` (the two doorway cards).

- [ ] **Step 7: Preview**

Open `site/index.html`. Verify: the essay now has exactly 3 beats (safety / kernel walls / no-seat), no dead-STEP or native-tree beat, and no A4 "which fits your job?" table; clicking a "Who are you?" doorway still scrolls to the essay.

- [ ] **Step 8: Commit**

```bash
git add site/index.html
git commit -m "refactor(site): flow pass — trim essay to safety+speed, drop redundant A4 block"
```

---

## Task 5: Generalize `tools/build_pages.py` to a list of assets (TDD)

**Files:**
- Modify: `tools/build_pages.py`
- Create: `tests/tools/test_build_pages.py`

**Interfaces:**
- Produces (module-level, consumed by the test): `IMAGE_ASSETS: list[tuple[str, str]]` (src-relative-to-`site/`, out-relative-in-artifact); `LINK_REWRITES: dict[str, str]`; `build(repo_root: Path, out_dir: Path) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_build_pages.py`:

```python
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build_pages as bp  # noqa: E402


def _make_repo(tmp_path):
    """A minimal repo whose index.html references every asset + doc link."""
    site = tmp_path / "site"
    site.mkdir()
    srcs = [src for src, _ in bp.IMAGE_ASSETS]
    imgs = "\n".join(f'<img src="{s}">' for s in srcs)
    links = "\n".join(f'<a href="{k}">x</a>' for k in bp.LINK_REWRITES)
    (site / "index.html").write_text(f"<html>{imgs}\n{links}</html>", encoding="utf-8")
    for s in srcs:
        p = (site / s).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n" if s.endswith(".png") else b"GIF89a")
    return tmp_path


def test_build_copies_every_asset_and_repoints(tmp_path):
    repo = _make_repo(tmp_path)
    out = tmp_path / "_site"
    assert bp.build(repo, out) == 0
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'src="../' not in html
    assert 'href="../' not in html
    for _, out_rel in bp.IMAGE_ASSETS:
        assert (out / out_rel).exists(), out_rel
        assert out_rel in html


def test_build_fails_loudly_when_an_asset_is_missing(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "site" / bp.IMAGE_ASSETS[1][0]).resolve().unlink()
    assert bp.build(repo, tmp_path / "_site") == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_build_pages.py -v`
Expected: FAIL — `AttributeError: module 'build_pages' has no attribute 'IMAGE_ASSETS'` (the current module has `HERO_SRC_REL`/`HERO_OUT_REL`, not `IMAGE_ASSETS`).

- [ ] **Step 3: Generalize `build_pages.py`**

Replace the `HERO_SRC_REL` / `HERO_OUT_REL` constants and the `build()` body. New constants + build (keep the module docstring, `BLOB`, `main()`):

```python
LINK_REWRITES = {
    "../QUICKSTART.md": f"{BLOB}/QUICKSTART.md",
    "../docs/operator_guide.md": f"{BLOB}/docs/operator_guide.md",
    "../docs/known_limitations.md": f"{BLOB}/docs/known_limitations.md",
    "../docs/CAPABILITIES.md": f"{BLOB}/docs/CAPABILITIES.md",
}

# (src relative to site/index.html) -> (out relative in the gh-pages artifact)
IMAGE_ASSETS = [
    ("../docs/img/demo_hero.gif", "assets/demo_hero.gif"),
    ("../docs/img/still_part.png", "assets/still_part.png"),
    ("../docs/img/still_assembly.png", "assets/still_assembly.png"),
    ("../docs/img/still_observe.png", "assets/still_observe.png"),
    ("../docs/img/still_drawing.png", "assets/still_drawing.png"),
    ("../docs/img/still_export.png", "assets/still_export.png"),
    ("../docs/img/anchor_dead_step.png", "assets/anchor_dead_step.png"),
    ("../docs/img/anchor_alive_tree.png", "assets/anchor_alive_tree.png"),
    ("../docs/img/anchor_live_edit.gif", "assets/anchor_live_edit.gif"),
]


def build(repo_root: Path, out_dir: Path) -> int:
    html = (repo_root / "site" / "index.html").read_text(encoding="utf-8")

    staged: list[tuple[Path, str]] = []
    for src_rel, out_rel in IMAGE_ASSETS:
        src_path = (repo_root / "site" / src_rel).resolve()
        if not src_path.exists():
            print(f"ERROR: image asset not found: {src_path}", file=sys.stderr)
            return 1
        html = html.replace(f'src="{src_rel}"', f'src="{out_rel}"')
        staged.append((src_path, out_rel))

    for old, new in LINK_REWRITES.items():
        html = html.replace(f'href="{old}"', f'href="{new}"')

    leftover = [tok for tok in ('href="../', 'src="../') if tok in html]
    if leftover:
        print(f"ERROR: unrewritten relative refs remain: {leftover}", file=sys.stderr)
        return 1

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "assets").mkdir(parents=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    for src_path, out_rel in staged:
        shutil.copy2(src_path, out_dir / out_rel)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"OK: built Pages artifact at {out_dir} ({len(staged)} image assets)")
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_build_pages.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the real build + launch-kit lint**

Run:
```bash
C:/Python314/python.exe tools/build_pages.py . _site
C:/Python314/python.exe tools/check_launch_kit.py
```
Expected: build prints `OK: … (9 image assets)`; `_site/index.html` contains no `src="../` or `href="../"`; `_site/assets/` holds all 9 files; the lint exits 0.

- [ ] **Step 6: Format + lint the Python**

Run:
```bash
C:/Python314/python.exe -m black tools/build_pages.py tests/tools/test_build_pages.py
C:/Python314/python.exe -m flake8 tools/build_pages.py tests/tools/test_build_pages.py
```
Expected: black leaves them unchanged (or reformats; re-stage if so); flake8 reports nothing.

- [ ] **Step 7: Commit**

```bash
git add tools/build_pages.py tests/tools/test_build_pages.py
git commit -m "feat(build): generalize build_pages to a list of image assets + CAPABILITIES link"
```

---

## Task 6: SEAT SESSION — capture the 3 real Block ① assets

**Requires a running, licensed SOLIDWORKS 2021+ seat.** Non-destructive throughout (open → observe/record → close **without saving**). Overwrites the Task 1 placeholders in place; the HTML already points at these paths, so no markup changes.

**Files:**
- Modify (overwrite): `docs/img/anchor_dead_step.png`, `docs/img/anchor_alive_tree.png`, `docs/img/anchor_live_edit.gif`

- [ ] **Step 1: Build the demo widget on the seat**

Build the bearing-block widget from its spec so you have a live part with the named tree + linked globals:
Run: `C:/Python314/python.exe -m ai_sw_bridge.cli.build examples/demo_widget/demo_bearing_block/spec.json` (or the established `ai-sw-build` entry point). Confirm the FeatureManager shows named features `SK_Block → EX_Block → SK_Bore → Cut_Bore → FIL_Block → Hole_MountA/B → CHA_BoreLeadIn` and the Equation Manager lists globals from `locals.txt` (`"BORE_DIA" = 16`, …).

- [ ] **Step 2: Capture `anchor_alive_tree.png`**

Expand the FeatureManager (all features visible, names legible) and open the Equation Manager so `"BORE_DIA" = 16` and its siblings show. Screenshot the SW window framed on the tree + equation panel. Save over `docs/img/anchor_alive_tree.png`.
**Tier-3 gate (L8):** the screenshot must legibly show **named features** (not `Sketch1`) **and** the **Equation Manager with named globals**. A bare tree fails — re-frame and re-capture.

- [ ] **Step 3: Capture `anchor_dead_step.png`**

Export the same widget to STEP, then re-import it into a fresh document (`ai-sw-import`). The re-imported doc collapses to a single `Imported1` body with no history. Screenshot the FeatureManager showing the lone `Imported1`. Save over `docs/img/anchor_dead_step.png`. Close both docs **without saving**.

- [ ] **Step 4: Record `anchor_live_edit.gif`**

Record `ai-sw-mutate` changing `BORE_DIA` from 16 to 20 (the same non-destructive mutate path used by the demo suite), capturing the bore visibly growing and the tree rebuilding to **0 errors**. Encode a short, looped, palette-optimized GIF ≤ ~1 MB (reuse the demo-suite SaveBMP→ffmpeg palette pipeline). Save over `docs/img/anchor_live_edit.gif`.
**Gate:** the clip must show the rebuild completing with **no rebuild errors**; the loop must be legible at the on-page width. If a clean loop can't be held under ~1 MB, fall back to a static 2-up before/after PNG (rename references accordingly and note the deviation) — L9.

- [ ] **Step 5: Verify weight + the tier-3 story end-to-end**

Run: `ls -la docs/img/anchor_*`
Expected: three real captures; `anchor_live_edit.gif` ≤ ~1 MB. Open `site/index.html`: Block ① now tells dead → real (named tree + equations) → survives-edit with real pixels; no "capture pending" placeholder remains.

- [ ] **Step 6: Commit**

```bash
git add docs/img/anchor_dead_step.png docs/img/anchor_alive_tree.png docs/img/anchor_live_edit.gif
git commit -m "assets(site): real Block 1 captures — dead STEP, named tree+equations, live-edit rebuild"
```

---

## Task 7: Rebuild + deploy to `gh-pages`, verify live

**Do not start until Task 6's real captures are committed.** Deploys the enhanced Spine so it is at its best before any (user-driven) external send.

**Files:**
- Generated: `_site/` → pushed to the `gh-pages` branch root.

- [ ] **Step 1: Full local verification pass**

- Launch-kit lint: `C:/Python314/python.exe tools/check_launch_kit.py` → exit 0.
- Defensibility (L6): re-read Block ② — Features line names no loft/rib/wrap; counts are **36** and **16**; the export tile says "spec export block", never `ai-sw-export`.
- Theme: preview in light and dark (OS setting) — dead tile desaturated + alive tile accent-bordered read in both; no color defined only in the dark media block.
- Mobile: narrow viewport — Block ① stacks (dead on top, GIF below); tiles + breadth strip stack; no horizontal page scroll.

- [ ] **Step 2: Build the artifact**

Run: `C:/Python314/python.exe tools/build_pages.py . _site`
Expected: `OK: … (9 image assets)`; `_site/` has `index.html`, `assets/` (9 files), `.nojekyll`.

- [ ] **Step 3: Publish `_site/` to `gh-pages`**

Use the same orphan/branch flow that deployed the current page (see `site/README.md`). Via a detached worktree (use a scratchpad path, not `/tmp`, on Windows):

```bash
WT="C:/Users/sky/AppData/Local/Temp/claude/.../scratchpad/ghp"
git worktree add --detach "$WT" gh-pages
cp -r _site/* "$WT"/ && cp _site/.nojekyll "$WT"/
git -C "$WT" add -A
git -C "$WT" commit -m "deploy: landing-page parametric+breadth enhancement"
git -C "$WT" push origin HEAD:gh-pages
git worktree remove "$WT"
```
(No `Co-Authored-By: Claude`.)

- [ ] **Step 4: Verify every asset 200s on the live URL**

After Pages redeploys (~1 min), check the page and each asset:

```bash
for u in "" assets/demo_hero.gif assets/still_part.png assets/still_assembly.png assets/still_observe.png assets/still_drawing.png assets/still_export.png assets/anchor_dead_step.png assets/anchor_alive_tree.png assets/anchor_live_edit.gif; do
  echo -n "$u -> "; curl -s -o /dev/null -w "%{http_code}\n" "https://thomas-tai.github.io/ai-sw-bridge/$u"
done
```
Expected: `200` for the page and all nine assets.

- [ ] **Step 5: Eyeball the live page**

Open `https://thomas-tai.github.io/ai-sw-bridge/`. Confirm both new blocks render with real imagery, the essay is the trimmed 3-beat version, the A4 block is gone, and the doorways still scroll to the essay.

- [ ] **Step 6: Final status**

The Spine is enhanced and live. Report done; the external launch sends remain **user-driven** and are out of this plan's scope.

---

## Self-Review

**1. Spec coverage** (spec §-by-§ → task):
- §4 Block ① three zones → Task 2 (markup/CSS) + Task 6 (real captures). ✓
- §5 Block ② filmstrip → Task 3; breadth strip (L11, counts) → Task 3 Step 1; phantom-CLI crop → Task 1 (crop) + Task 3 (tile text). ✓
- §6 flow pass (trim essay, remove A4) → Task 4. ✓
- §7 Tier A extracts / Tier B captures → Task 1 (Tier A + placeholders) / Task 6 (Tier B). ✓
- §8 one motion asset → Task 6 Step 4 (+ fallback). ✓
- §9 build/deploy + build_pages generalization → Task 5 (script/test) + Task 7 (deploy). ✓
- §12/§13 honesty (no loft; 36/16; no `ai-sw-export`) → Global Constraints + Task 3 honesty gate + Task 7 Step 1. ✓
- Every commit lint-green (placeholders exist from Task 1) → Tasks 2/3/4 each run `check_launch_kit.py`. ✓

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Suggested ffmpeg frame numbers are explicit with an eyeball-adjust instruction; the essay title is concrete (spec allows final-copy latitude). ✓

**3. Type/name consistency:** Asset filenames identical across Task 1 (create), Tasks 2–3 (`src=`), Task 5 (`IMAGE_ASSETS`), Task 6 (overwrite), Task 7 (curl). `build()` signature and `IMAGE_ASSETS`/`LINK_REWRITES` names match between Task 5's implementation and its test. The `.anchor`/`.film-tile`/`.breadth` class names match between each block's markup and its CSS. ✓

**Deviation from spec noted:** the spec said "crop the *export* still"; this plan crops the lower-third off **all five** stills (Task 1 design note) — a superset that removes the phantom label uniformly, avoids double-captioning, and preserves the info-cards. Consistent with the spec's intent; flagged here for the reviewer.
