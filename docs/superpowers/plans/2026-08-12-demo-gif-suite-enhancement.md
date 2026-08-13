# Demo GIF Suite Enhancement + README Wedge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the six demo clips + create a hero and tour clip, and restructure the README so a fresh visitor grasps ai-sw-bridge's real-SOLIDWORKS-fidelity capability fast.

**Architecture:** Two phases. Phase 1 (no SOLIDWORKS seat) builds the presentation: a reusable ffmpeg caption tool, a composed hero clip, a tour clip, captioned versions of the existing clips, and the restructured README (wedge + capability table + per-chapter gallery). Phase 2 (needs a live seat) re-records observe/drawing/export with fidelity proofs and swaps them in. All media reuses the proven SaveBMP→ffmpeg palette pipeline; captions are pre-composited PNG bands (Pillow) overlaid via ffmpeg.

**Tech Stack:** Python 3.14 (`C:/Python314/python.exe`), Pillow (new dev dep, tooling only), ffmpeg (palette-gif + libx264), pytest, the existing `ai_sw_bridge` package + `tools/demo_full_system.py` chapter engine.

**Source spec:** `docs/superpowers/specs/2026-08-12-demo-gif-suite-enhancement-design.md` (audited 2026-08-12, §13).

## Global Constraints

- **GIT ON HOLD** — another session holds git. Do **NOT** run `git commit`/`git push`/`git add` for a commit. Every task's final step is a **Checkpoint** (verify the deliverable + `git status` shows only expected working-tree changes). Task 13 batches all commits **only after the hold lifts**.
- **Never** append a `Co-Authored-By: Claude` trailer to any commit (applies when Task 13 runs).
- **Python:** `C:/Python314/python.exe`. Package imports resolve from `src/` via `PYTHONPATH=src`; tool scripts run from the repo root `C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge`.
- **GIF weight budget:** ≤ ~1 MB per inline clip. `demo_all` (1.7 MB) is a **click-through link**, not inline. Each clip also emits an `.mp4` alongside for docs/click-through.
- **Caption = one visual language:** translucent dark lower-third band, white bold **value line** + optional `mono CLI` line, composited at 560 px width, identical style across every clip.
- **Honesty (spec L6):** experimental features (`min_wall`, section) are **labeled on-screen**; no phantom `export` CLI in copy; wedge stated as fact, never a swipe; `SOLIDWORKS` is a plain requirement badge (no endorsement).
- **Non-destructive SW (Phase 2):** open → animate/read in memory → `CloseAllDocuments(True)` without saving. Never re-save a demo `.SLDPRT`/`.SLDASM`.
- **Verification rhythm:** produce artifact → assert with a concrete command (`ffprobe`/`ls`/`grep`) → **eyeball** the gif before marking done (the standing rule for this workstream).
- **CI order (when commits eventually run):** flake8 → black (line-length 88) → mypy (excludes `scripts/`) → pytest. Delete a stray `nul` file on Windows before mypy.

## File Structure

**New tooling (Phase 1):**
- `tools/_demo_media.py` — shared ffmpeg helpers: `gif_from_frames` (palette pipeline), `gif_with_overlay`, `mp4_from_frames`, `ffprobe_dims`, `file_kb`. DRY across the tools below.
- `tools/demo_caption.py` — `Caption` dataclass; `build_caption_png` (Pillow band); `caption_clip` (overlay onto an existing gif + emit mp4).
- `tools/demo_hero.py` — `plan_hero_filter` (concat + speed-ramp filtergraph); `compose_hero` (build `demo_hero.gif` from the chapter clips + caption).
- `tools/demo_tour_record.py` — `paginate_tour` (wrap/split the tour text); `render_tour_gif` (Pillow pages → ffmpeg slideshow → `demo_tour.gif`).

**New tests:** `tests/tools/test_demo_media.py`, `test_demo_caption.py`, `test_demo_hero.py`, `test_demo_tour_record.py`.

**Modified:**
- `README.md` — wedge top-of-page (spec §6) + per-chapter gallery (spec §8).
- `pyproject.toml` — add `pillow` to `[project.optional-dependencies].dev`.

**Created (non-code):**
- `docs/archive/README_pre-wedge_2026-08-12.md` — archived original README.
- `docs/img/demo_hero.gif`, `docs/img/demo_tour.gif` — new clips (+ `.mp4` siblings).
- `scratch/pre_caption/*.gif` — pre-caption backups of the existing clips (git-independent undo).

**Phase 2 (seat-gated, scoped by Task 7):**
- `docs/superpowers/notes/2026-08-12-phase2-findings.md` — Task 7 output: concrete Phase-2 sub-tasks + handler-code gaps.
- `tools/demo_render_observe.py`, `tools/demo_render_drawing.py`, `tools/demo_render_export.py` — deep re-record renderers.
- Possible new handler code under `src/ai_sw_bridge/` (section-view / BOM / balloon / round-trip) — exact modules determined by Task 7.

---

## Phase 1 — Presentation (no seat, no commits)

### Task 1: Archive the README + add the Pillow dev dep

**Files:**
- Create: `docs/archive/README_pre-wedge_2026-08-12.md` (copy of current `README.md`)
- Modify: `pyproject.toml` (`[project.optional-dependencies].dev` += `pillow`)

**Interfaces:**
- Produces: an on-disk archived README (referenced by the spec L5) and Pillow available for import in the tooling tasks.

- [ ] **Step 1: Create the archive directory and copy the README**

Run:
```bash
cd "C:/D/WorkSpace/[Local]_Station/01_Heavy_Assets/ai-sw-bridge"
mkdir -p docs/archive
cp README.md docs/archive/README_pre-wedge_2026-08-12.md
```

- [ ] **Step 2: Verify the copy is byte-identical**

Run: `diff README.md docs/archive/README_pre-wedge_2026-08-12.md && echo IDENTICAL`
Expected: prints `IDENTICAL` (no diff output).

- [ ] **Step 3: Add Pillow to the dev extra**

In `pyproject.toml`, under `[project.optional-dependencies]`, add `"pillow>=10,<12"` to the `dev` list (keep alphabetical/style consistent with neighbors).

- [ ] **Step 4: Install it**

Run: `C:/Python314/python.exe -m pip install "pillow>=10,<12"`
Expected: `Successfully installed pillow-...`

- [ ] **Step 5: Verify import**

Run: `C:/Python314/python.exe -c "import PIL; print(PIL.__version__)"`
Expected: a version string prints.

- [ ] **Step 6: Checkpoint (git on hold)**

Run: `git status --short`
Expected: shows `docs/archive/README_pre-wedge_2026-08-12.md` (untracked) and `pyproject.toml` (modified) and nothing unexpected. **Do not commit.**

---

### Task 2: Shared ffmpeg media helpers (`tools/_demo_media.py`)

**Files:**
- Create: `tools/_demo_media.py`
- Test: `tests/tools/test_demo_media.py`

**Interfaces:**
- Produces:
  - `ffprobe_dims(path: pathlib.Path) -> tuple[int, int]` — (width, height) via ffprobe.
  - `file_kb(path: pathlib.Path) -> float` — file size in KiB.
  - `gif_with_overlay(src_gif, band_png, out_gif, band_h: int, fps: int = 8) -> pathlib.Path` — overlay a PNG band at the bottom, palette-encode to gif.
  - `mp4_from_gif(src_gif, out_mp4) -> pathlib.Path` — libx264 mp4 for click-through.

- [ ] **Step 1: Write the failing test for the pure helpers**

```python
# tests/tools/test_demo_media.py
import pathlib
import sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import _demo_media as m  # noqa: E402


def test_file_kb(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"\0" * 2048)
    assert m.file_kb(p) == pytest.approx(2.0, abs=0.01)


def test_overlay_cmd_shape():
    cmd = m.build_overlay_cmd("in.gif", "band.png", "pal.png", "out.gif", band_h=96)
    joined = " ".join(cmd)
    assert "overlay=0:H-96" in joined
    assert "paletteuse" in joined
    assert cmd[0] == "ffmpeg"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_demo_media.py -v`
Expected: FAIL (`ModuleNotFoundError: _demo_media` or `AttributeError`).

- [ ] **Step 3: Implement `tools/_demo_media.py`**

```python
"""Shared ffmpeg/ffprobe helpers for the demo-clip tools. Palette-gif pipeline
matches the proven render path used elsewhere in this workstream."""
from __future__ import annotations

import pathlib
import subprocess


def file_kb(path: pathlib.Path) -> float:
    return path.stat().st_size / 1024.0


def ffprobe_dims(path: pathlib.Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split("x")
    return int(w), int(h)


def build_overlay_cmd(src_gif, band_png, palette, out_gif, band_h: int, fps: int = 8):
    """Two-input overlay + a pre-generated palette (3rd input) -> gif."""
    vf = f"[0:v][1:v]overlay=0:H-{band_h}"
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src_gif),
            "-i", str(band_png), "-i", str(palette), "-filter_complex",
            f"{vf}[ov];[ov][2:v]paletteuse=dither=bayer:bayer_scale=3", str(out_gif)]


def gif_with_overlay(src_gif, band_png, out_gif, band_h: int, fps: int = 8):
    src_gif, band_png, out_gif = map(pathlib.Path, (src_gif, band_png, out_gif))
    palette = out_gif.with_suffix(".pal.png")
    vf = f"[0:v][1:v]overlay=0:H-{band_h}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src_gif),
                    "-i", str(band_png), "-filter_complex",
                    f"{vf},palettegen=stats_mode=diff", str(palette)], check=True)
    subprocess.run(build_overlay_cmd(src_gif, band_png, palette, out_gif, band_h, fps),
                   check=True)
    palette.unlink(missing_ok=True)
    return out_gif


def mp4_from_gif(src_gif, out_mp4):
    src_gif, out_mp4 = pathlib.Path(src_gif), pathlib.Path(out_mp4)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src_gif),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    str(out_mp4)], check=True)
    return out_mp4
```

- [ ] **Step 4: Run the tests and confirm pass**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_demo_media.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Checkpoint (git on hold)**

Run: `git status --short` → shows the two new files. **Do not commit.**

---

### Task 3: Caption tool (`tools/demo_caption.py`)

**Files:**
- Create: `tools/demo_caption.py`
- Test: `tests/tools/test_demo_caption.py`

**Interfaces:**
- Consumes: `_demo_media.gif_with_overlay`, `mp4_from_gif`, `ffprobe_dims`.
- Produces:
  - `Caption(value: str, cli: str | None = None)` dataclass.
  - `BAND_H: int` (band height constant, 96).
  - `build_caption_png(cap: Caption, width: int, out_path: pathlib.Path) -> pathlib.Path`.
  - `caption_clip(src_gif: pathlib.Path, cap: Caption, out_gif: pathlib.Path) -> pathlib.Path` — overlays the band, writes the gif + a sibling `.mp4`.

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_demo_caption.py
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import demo_caption as c  # noqa: E402


def test_build_caption_png_dims(tmp_path):
    out = c.build_caption_png(c.Caption("Real mates", "ai-sw-assembly"), 560,
                              tmp_path / "band.png")
    assert out.exists()
    from PIL import Image
    w, h = Image.open(out).size
    assert w == 560 and h == c.BAND_H


def test_caption_value_only(tmp_path):
    out = c.build_caption_png(c.Caption("One number rebuilds"), 560, tmp_path / "b.png")
    assert out.exists()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_demo_caption.py -v`
Expected: FAIL (`ModuleNotFoundError: demo_caption`).

- [ ] **Step 3: Implement `tools/demo_caption.py`**

```python
"""Burned-in lower-third caption for demo clips (spec 2026-08-12 §7). Composes a
translucent band PNG via Pillow and overlays it via ffmpeg. One consistent
visual language across every clip."""
from __future__ import annotations

import dataclasses
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _demo_media as media  # noqa: E402

BAND_H = 96
BAND_RGBA = (20, 22, 26, 115)     # ~0.45 alpha
PAD = 18


@dataclasses.dataclass(frozen=True)
class Caption:
    value: str
    cli: str | None = None


def _font(size: int, bold: bool = False):
    for name in ((["segoeuib.ttf", "arialbd.ttf"] if bold
                  else ["segoeui.ttf", "arial.ttf"])):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_caption_png(cap: Caption, width: int, out_path: pathlib.Path) -> pathlib.Path:
    out_path = pathlib.Path(out_path)
    img = Image.new("RGBA", (width, BAND_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, BAND_H], fill=BAND_RGBA)
    d.text((PAD, PAD), cap.value, font=_font(30, bold=True), fill=(255, 255, 255, 255))
    if cap.cli:
        d.text((PAD, PAD + 42), cap.cli, font=_font(19), fill=(176, 200, 224, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def caption_clip(src_gif: pathlib.Path, cap: Caption,
                 out_gif: pathlib.Path) -> pathlib.Path:
    src_gif, out_gif = pathlib.Path(src_gif), pathlib.Path(out_gif)
    width, _ = media.ffprobe_dims(src_gif)
    band = out_gif.with_name(out_gif.stem + "_band.png")
    build_caption_png(cap, width, band)
    media.gif_with_overlay(src_gif, band, out_gif, BAND_H)
    media.mp4_from_gif(out_gif, out_gif.with_suffix(".mp4"))
    band.unlink(missing_ok=True)
    return out_gif
```

- [ ] **Step 4: Run the tests and confirm pass**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_demo_caption.py -v`
Expected: PASS.

- [ ] **Step 5: Checkpoint (git on hold)** — `git status --short` shows the two new files. Do not commit.

---

### Task 4: Apply captions to the existing chapter clips

**Files:**
- Create: `scratch/pre_caption/` (backups)
- Modify (in place, working-tree only): `docs/img/demo_{part,assembly,observe,drawing,export,all}.gif`

**Interfaces:**
- Consumes: `demo_caption.Caption`, `demo_caption.caption_clip`.

- [ ] **Step 1: Back up the originals (git-independent undo)**

Run:
```bash
cd "C:/D/WorkSpace/[Local]_Station/01_Heavy_Assets/ai-sw-bridge"
mkdir -p scratch/pre_caption
cp docs/img/demo_part.gif docs/img/demo_assembly.gif docs/img/demo_observe.gif \
   docs/img/demo_drawing.gif docs/img/demo_export.gif docs/img/demo_all.gif \
   scratch/pre_caption/
```

- [ ] **Step 2: Write a one-shot caption driver and run it**

Create `scratch/caption_existing.py`:
```python
import pathlib
import sys
ROOT = pathlib.Path(r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\ai-sw-bridge")
sys.path.insert(0, str(ROOT / "tools"))
from demo_caption import Caption, caption_clip  # noqa: E402

IMG = ROOT / "docs" / "img"
CAPS = {
    "demo_part":     Caption("Change one number; the real feature tree rebuilds", "ai-sw-mutate"),
    "demo_assembly": Caption("Real mates, not fixed coordinates", "ai-sw-assembly"),
    "demo_observe":  Caption("DFM is a build gate, not an afterthought", "ai-sw-observe"),
    "demo_drawing":  Caption("Drawing + BOM fall out of the same model", "ai-sw-drawing"),
    "demo_export":   Caption("One model, every downstream format", "spec export block"),
    "demo_all":      Caption("The whole build, unedited", None),
}
for stem, cap in CAPS.items():
    src = ROOT / "scratch" / "pre_caption" / f"{stem}.gif"
    out = IMG / f"{stem}.gif"
    caption_clip(src, cap, out)
    print("captioned ->", out, f"{out.stat().st_size/1024:.0f} KiB")
```
Run: `C:/Python314/python.exe scratch/caption_existing.py`
Expected: six `captioned -> ... KiB` lines.

- [ ] **Step 3: Verify dimensions unchanged + weight budget**

Run:
```bash
C:/Python314/python.exe -c "import sys,pathlib; sys.path.insert(0,'tools'); import _demo_media as m; \
[print(f, m.ffprobe_dims(pathlib.Path('docs/img')/f), f\"{m.file_kb(pathlib.Path('docs/img')/f):.0f}KiB\") \
for f in ['demo_part.gif','demo_assembly.gif','demo_observe.gif','demo_drawing.gif','demo_export.gif','demo_all.gif']]"
```
Expected: each width == its pre-caption width; each inline clip ≤ ~1024 KiB (note: `demo_part`/`demo_all` are click-through/heavy — flag if far over; optimize in Step 4 if needed).

- [ ] **Step 4: Eyeball each captioned gif**

Open each `docs/img/demo_*.gif`; confirm the lower-third band is legible, consistent, and doesn't cover the model's key content. If a clip is over budget, re-run with reduced fps/scale (adjust the caption driver / `_demo_media`). Re-do until clean.

- [ ] **Step 5: Checkpoint (git on hold)** — `git status --short` shows the six gifs modified + new mp4s + `scratch/`. Do not commit.

---

### Task 5: Tour clip (`tools/demo_tour_record.py` → `docs/img/demo_tour.gif`)

**Files:**
- Create: `tools/demo_tour_record.py`
- Test: `tests/tools/test_demo_tour_record.py`
- Create (output): `docs/img/demo_tour.gif` (+ `.mp4`)

**Interfaces:**
- Consumes: `demo_full_system.py --chapter tour` stdout; Pillow; `_demo_media`.
- Produces:
  - `paginate_tour(text: str, max_lines: int) -> list[list[str]]` — split captured tour text into pages of ≤ `max_lines` non-empty display lines.
  - `render_tour_gif(pages: list[list[str]], out_gif: pathlib.Path) -> pathlib.Path`.

- [ ] **Step 1: Write the failing test for the paginator (pure logic)**

```python
# tests/tools/test_demo_tour_record.py
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import demo_tour_record as t  # noqa: E402


def test_paginate_splits_by_max_lines():
    text = "\n".join(f"line {i}" for i in range(1, 21))
    pages = t.paginate_tour(text, max_lines=8)
    assert len(pages) == 3
    assert all(len(p) <= 8 for p in pages)
    assert pages[0][0] == "line 1"


def test_paginate_drops_blank_lines():
    pages = t.paginate_tour("a\n\n\nb\n", max_lines=8)
    assert pages == [["a", "b"]]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_demo_tour_record.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `tools/demo_tour_record.py`**

```python
"""Render the introspected capability tour into a short branded slideshow gif.
Captures `demo_full_system.py --chapter tour` text, paginates it, draws each page
on a dark card via Pillow, and stitches a hold-per-page gif via ffmpeg."""
from __future__ import annotations

import pathlib
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _demo_media as media  # noqa: E402

W, H = 560, 560
BG = (18, 20, 24)
FG = (222, 230, 238)
ACCENT = (120, 190, 255)
MARGIN, LINE_H, FPS = 28, 30, 8
HOLD_FRAMES_PER_PAGE = 24


def paginate_tour(text: str, max_lines: int) -> list[list[str]]:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)] or [[]]


def _font(size: int, bold: bool = False):
    for name in (["consolab.ttf", "cour.ttf"] if bold else ["consola.ttf", "cour.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_page(lines: list[str]) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((MARGIN, MARGIN), "ai-sw-bridge — capability surface",
           font=_font(20, bold=True), fill=ACCENT)
    y = MARGIN + 44
    for ln in lines:
        d.text((MARGIN, y), ln[:72], font=_font(16), fill=FG)
        y += LINE_H
    return img


def render_tour_gif(pages: list[list[str]], out_gif: pathlib.Path) -> pathlib.Path:
    out_gif = pathlib.Path(out_gif)
    frames_dir = out_gif.parent / "_tour_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    idx = 0
    for page in pages:
        card = _draw_page(page)
        for _ in range(HOLD_FRAMES_PER_PAGE):
            card.save(frames_dir / f"f{idx:04d}.png")
            idx += 1
    media.gif_from_frames(frames_dir / "f%04d.png", out_gif, fps=FPS) \
        if hasattr(media, "gif_from_frames") else _palette_gif(frames_dir, out_gif)
    media.mp4_from_gif(out_gif, out_gif.with_suffix(".mp4"))
    return out_gif


def _palette_gif(frames_dir: pathlib.Path, out_gif: pathlib.Path):
    seq = str(frames_dir / "f%04d.png")
    pal = frames_dir / "pal.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", seq, "-vf", "palettegen=stats_mode=diff", str(pal)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", seq, "-i", str(pal), "-lavfi",
                    "paletteuse=dither=bayer:bayer_scale=3", str(out_gif)], check=True)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        ["C:/Python314/python.exe", "tools/demo_full_system.py", "--chapter", "tour",
         "--no-pause", "--sleep", "0"],
        cwd=str(root), capture_output=True, text=True)
    text = proc.stdout or ""
    pages = paginate_tour(text, max_lines=(H - 2 * MARGIN - 44) // LINE_H)
    out = render_tour_gif(pages, root / "docs" / "img" / "demo_tour.gif")
    print("tour ->", out, f"{out.stat().st_size/1024:.0f} KiB, pages={len(pages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and confirm pass**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_demo_tour_record.py -v`
Expected: PASS.

- [ ] **Step 5: Generate the tour clip**

Run: `C:/Python314/python.exe tools/demo_tour_record.py`
Expected: `tour -> ...demo_tour.gif ... KiB, pages=N`. (If `--chapter tour` needs different flags, confirm with `--list-chapters`; the tour chapter is no-SW.)

- [ ] **Step 6: Eyeball + budget**

Open `docs/img/demo_tour.gif`; confirm the surface (kinds/CLIs/mates/formats + the `DEFERRED.md` pointer) is legible and ≤ ~1 MB. Reduce pages or font if needed.

- [ ] **Step 7: Checkpoint (git on hold)** — `git status --short`. Do not commit.

---

### Task 6: Compose the hero clip (`tools/demo_hero.py` → `docs/img/demo_hero.gif`)

**Files:**
- Create: `tools/demo_hero.py`
- Test: `tests/tools/test_demo_hero.py`
- Create (output): `docs/img/demo_hero.gif` (+ `.mp4`)

**Interfaces:**
- Consumes: the captioned chapter clips from Task 4; `demo_caption`; `_demo_media`.
- Produces:
  - `plan_hero_filter(n_clips: int, speed: float) -> str` — an ffmpeg filtergraph that speeds up (`setpts=PTS/speed`) and concatenates `n_clips` inputs.
  - `compose_hero(clip_paths: list[pathlib.Path], out_gif: pathlib.Path, speed: float) -> pathlib.Path`.

- [ ] **Step 1: Write the failing test for the filter planner (pure logic)**

```python
# tests/tools/test_demo_hero.py
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import demo_hero as h  # noqa: E402


def test_plan_hero_filter_concats_all():
    f = h.plan_hero_filter(3, speed=2.0)
    assert f.count("setpts=PTS/2.0") == 3
    assert "concat=n=3" in f
    assert f.strip().endswith("[v]")


def test_plan_hero_filter_single():
    f = h.plan_hero_filter(1, speed=1.5)
    assert "concat=n=1" in f
```

- [ ] **Step 2: Run it and watch it fail**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_demo_hero.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `tools/demo_hero.py`**

```python
"""Compose the README hero: a ~12-15s montage that speed-ramps and concatenates
the chapter clips (part->assembly->observe->drawing->export), then captions it.
NB the hero is built from the chapter clips, not a demo_all frame set (audit F6)."""
from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _demo_media as media  # noqa: E402
from demo_caption import Caption, caption_clip  # noqa: E402

HERO_W = 560
SPEED = 2.0


def plan_hero_filter(n_clips: int, speed: float) -> str:
    parts = []
    for i in range(n_clips):
        parts.append(f"[{i}:v]setpts=PTS/{speed},scale={HERO_W}:-1:flags=lanczos,"
                     f"fps=10[c{i}]")
    labels = "".join(f"[c{i}]" for i in range(n_clips))
    chain = ";".join(parts)
    return f"{chain};{labels}concat=n={n_clips}:v=1:a=0[v]"


def compose_hero(clip_paths, out_gif, speed: float = SPEED) -> pathlib.Path:
    clip_paths = [pathlib.Path(p) for p in clip_paths]
    out_gif = pathlib.Path(out_gif)
    raw = out_gif.with_name("_hero_raw.gif")
    pal = out_gif.with_name("_hero_pal.png")
    filt = plan_hero_filter(len(clip_paths), speed)
    inputs = []
    for p in clip_paths:
        inputs += ["-i", str(p)]
    # 1) concat -> raw gif via palette
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs,
                    "-filter_complex", f"{filt};[v]palettegen=stats_mode=diff", str(pal)],
                   check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-i", str(pal),
                    "-filter_complex",
                    f"{filt};[v][{len(clip_paths)}:v]paletteuse=dither=bayer:bayer_scale=3",
                    str(raw)], check=True)
    # 2) caption it (value line only) -> final hero gif + mp4
    caption_clip(raw, Caption("One JSON spec \u2192 a real SOLIDWORKS build"), out_gif)
    raw.unlink(missing_ok=True)
    pal.unlink(missing_ok=True)
    return out_gif


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    img = root / "docs" / "img"
    order = ["demo_part", "demo_assembly", "demo_observe", "demo_drawing", "demo_export"]
    clips = [img / f"{s}.gif" for s in order]
    out = compose_hero(clips, img / "demo_hero.gif")
    print("hero ->", out, f"{out.stat().st_size/1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and confirm pass**

Run: `C:/Python314/python.exe -m pytest tests/tools/test_demo_hero.py -v`
Expected: PASS.

- [ ] **Step 5: Generate the hero**

Run: `C:/Python314/python.exe tools/demo_hero.py`
Expected: `hero -> ...demo_hero.gif ... KiB`.

- [ ] **Step 6: Eyeball + budget**

Open `docs/img/demo_hero.gif`; confirm it reads as one continuous pipeline (part→assembly→observe→drawing→export), the caption is legible, duration ~12-15s, ≤ ~1 MB. Tune `SPEED`/`fps` if over budget or too fast.

- [ ] **Step 7: Checkpoint (git on hold)** — `git status --short`. Do not commit.

---

### Task 7 (numbered Task order continues): Restructure the README

**Files:**
- Modify: `README.md` (top-of-page wedge + `## Demo GIFs` gallery)

**Interfaces:**
- Consumes: all Phase-1 clips (`demo_hero`, `demo_tour`, captioned chapter clips).

- [ ] **Step 1: Replace the top-of-page with the wedge**

Insert immediately after the `# ai-sw-bridge` title (verbatim from spec §6), replacing the current quickstart-first opener:
```markdown
# ai-sw-bridge   [badges: tests · license · python · requires SOLIDWORKS 2021+]

> **Drive your real SOLIDWORKS seat from a JSON spec.**
> Native `.SLDPRT` / `.SLDASM` / `.SLDDRW` with a real, editable feature tree —
> not a foreign STEP dump from a throwaway kernel.

![hero](docs/img/demo_hero.gif)

*One spec → parts → assembly → observe/DFM → drawing → export, on a live
SOLIDWORKS seat, human-gated (propose → approve → execute).*

### Capability at a glance
| Chapter | What it proves | CLI |
|---|---|---|
| **Tour** | the whole surface — and its honest edges | *(reads sources)* |
| **Part** | change one number → the real feature tree rebuilds | `ai-sw-build` · `ai-sw-mutate` |
| **Assembly** | real mates, not fixed coordinates | `ai-sw-assembly` |
| **Observe / DFM** | interference · mass · bbox — from SW's own kernel | `ai-sw-observe` |
| **Drawing** | drawing + BOM fall out of the same model | `ai-sw-drawing` |
| **Export** | one model → every format | spec export block · `ai-sw-export-dxf-flat` |

**No SOLIDWORKS seat?** You can still author and validate specs with zero
license — [5-minute quickstart →](QUICKSTART.md)
```

- [ ] **Step 2: Rewrite the `## Demo GIFs` gallery**

Replace the current table (with its 3 `TODO` comments) with the per-chapter gallery, embedding the new + captioned clips and a "what to look for" line each. `demo_all` is a **click-through link**, not an inline image:
```markdown
## Demo GIFs

Short recordings of [`tools/demo_full_system.py`](tools/demo_full_system.py) building the
bundled pillow-block widget end-to-end. Recorded on a live SOLIDWORKS seat; see
[`docs/demo_full_system.md`](docs/demo_full_system.md) for the command behind each clip.

| Chapter | Clip | What to look for |
|---|---|---|
| Capability tour | ![tour](docs/img/demo_tour.gif) | kinds · CLIs · mates · formats → `DEFERRED.md` |
| Part build + rebuild | ![part](docs/img/demo_part.gif) | FeatureManager tree + bbox update on `mutate` |
| Assembly | ![assembly](docs/img/demo_assembly.gif) | shaft plunges through both bores, seated |
| Observe / DFM | ![observe](docs/img/demo_observe.gif) | interference 0 (assembly) · mass (part) · bbox |
| Drawing | ![drawing](docs/img/demo_drawing.gif) | section A-A · BOM · balloons |
| Export | ![export](docs/img/demo_export.gif) | STEP/STL/3MF from one model |

Full unedited run (heavy): [`demo_all.gif`](docs/img/demo_all.gif) · [`demo_all.mp4`](docs/img/demo_all.mp4)
```

- [ ] **Step 3: Verify every embedded path resolves**

Run:
```bash
grep -oE 'docs/img/[A-Za-z0-9_]+\.(gif|mp4)' README.md | sort -u | while read p; do \
  [ -f "$p" ] && echo "OK  $p" || echo "MISSING $p"; done
```
Expected: every line `OK` (no `MISSING`).

- [ ] **Step 4: Confirm no stale TODO markers remain in the demo section**

Run: `grep -n "TODO: docs/img" README.md || echo "no TODOs"`
Expected: `no TODOs`.

- [ ] **Step 5: Render-preview the README**

Open the README in a Markdown previewer (or GitHub Desktop / VS Code preview); confirm the hero autoplays, the capability table + gallery render, the wedge reads as intended, and no horizontal overflow.

- [ ] **Step 6: Checkpoint (git on hold)** — `git status --short` shows `README.md` modified. Do not commit.

---

## Phase 2 — Depth (needs a live seat; still no commits)

### Task 8: P2.0 inspection — deep vs shallow (produces the Phase-2 sub-plan)

**Files:**
- Read: `tools/demo_full_system.py` (`_observe_steps`, `_drawing_steps`, `_export_steps`)
- Read: current `docs/img/demo_{observe,drawing,export}.gif`
- Create: `docs/superpowers/notes/2026-08-12-phase2-findings.md`

- [ ] **Step 1: Inventory what each chapter emits today**

Read the three step-builders and note, per chapter: the exact CLI verbs run, what read-backs/artifacts they produce, and which of the spec §8 deep proofs (section sweep, mass, interference; BOM, balloons, section A-A; format fan, round-trip Δbbox) are **already present** vs **absent**.

- [ ] **Step 2: Confirm the API gaps**

For each absent proof, confirm whether the underlying capability exists: `ai-sw-drawing` BOM/balloon/section flags (`C:/Python314/python.exe -m ai_sw_bridge.cli.drawing --help`); export round-trip (re-import via `ai-sw-import`); observe `interference`/`mass`/`section_props`/`min_wall` (already confirmed experimental). List which need **new handler code** vs **just a renderer**.

- [ ] **Step 3: Write the findings note**

Write `docs/superpowers/notes/2026-08-12-phase2-findings.md` with a per-chapter table: *proof · already emits? · capability exists? · work = renderer-only | new-handler-code*. This note **is** the concrete task list for Tasks 9–11 (replaces any guesswork).

- [ ] **Step 4: Checkpoint (git on hold)** — note file created. Do not commit.

---

### Task 9: Observe deep re-record

**Files:**
- Create: `tools/demo_render_observe.py`
- Possibly modify: `src/ai_sw_bridge/...` (only if Task 8 found a gap; follow TDD there)
- Overwrite (output): `docs/img/demo_observe.gif` (+ mp4), re-captioned

**Acceptance criteria (what the clip MUST show):** interference = 0 on the assembly; mass on a part (assigned material); bbox; a clip-plane **section sweep** down the bore axis with an on-screen ***experimental*** tag; optional min-wall likewise tagged. Non-destructive (no re-save). Reuses `IComponent2.GetBox` ground truth.

- [ ] **Step 1:** If Task 8 flagged new handler code, implement it TDD-first (test in `tests/`, red→green) before the renderer. Otherwise skip to Step 2.
- [ ] **Step 2:** Write `tools/demo_render_observe.py` (SaveBMP frame sequence: read-back HUD frames + section-plane sweep frames → `_demo_media` palette gif). Section sweep = clip-plane render (new code), **not** an `ai-sw-observe` verb.
- [ ] **Step 3:** Run it on a live seat; caption via `demo_caption` with `Caption("DFM is a build gate, not an afterthought", "ai-sw-observe")`.
- [ ] **Step 4:** Verify dims/budget (`_demo_media`) and **eyeball**: interference 0 visible, mass shown, section sweep reveals the shaft through both bores + the experimental tag present.
- [ ] **Step 5: Checkpoint (git on hold).**

---

### Task 10: Drawing deep re-record

**Files:**
- Create: `tools/demo_render_drawing.py`
- Possibly modify: `src/ai_sw_bridge/drawing/...` (only if Task 8 found a gap; TDD)
- Overwrite (output): `docs/img/demo_drawing.gif` (+ mp4), re-captioned

**Acceptance criteria:** ortho + iso views; **section A-A through the bore axis** with correct conventions (**shaft NOT hatched**, bolts not sectioned); **auto-BOM + auto-balloons**; title-block mass matching the observe clip.

- [ ] **Step 1:** Implement any Task-8 handler gap TDD-first (BOM/balloon/section flags on `ai-sw-drawing`).
- [ ] **Step 2:** Write `tools/demo_render_drawing.py` (build the drawing, frame the view-by-view reveal, SaveBMP → gif).
- [ ] **Step 3:** Run on a live seat; caption `Caption("Drawing + BOM fall out of the same model", "ai-sw-drawing")`.
- [ ] **Step 4:** Verify + **eyeball**: section hatch conventions correct (shaft unhatched), BOM rows = baseplate/2×block/shaft, balloons attached, mass matches observe.
- [ ] **Step 5: Checkpoint (git on hold).**

---

### Task 11: Export deep re-record

**Files:**
- Create: `tools/demo_render_export.py`
- Overwrite (output): `docs/img/demo_export.gif` (+ mp4), re-captioned

**Acceptance criteria:** format fan (STEP/STL/3MF via the spec export block; DXF via `ai-sw-export-dxf-flat`) with a build-manifest overlay; then **re-import the STEP** into a fresh doc and show `bodies N/N · units mm · Δbbox 0.000 · origin ✓` (round-trip via `ai-sw-import` + `GetBox` compare).

- [ ] **Step 1:** Write `tools/demo_render_export.py` — run the export block; re-import via `ai-sw-import`; compute Δbbox with `IComponent2.GetBox`/observe bbox; compose the manifest + round-trip HUD frames → gif.
- [ ] **Step 2:** Run on a live seat; caption `Caption("One model, every downstream format", "spec export block")`.
- [ ] **Step 3:** Verify + **eyeball**: manifest lists the written files; round-trip HUD shows Δbbox 0.000 and bodies matched.
- [ ] **Step 4: Checkpoint (git on hold).**

---

### Task 12: Swap deep clips in + re-verify README

- [ ] **Step 1:** Confirm `docs/img/demo_{observe,drawing,export}.gif` are the deep versions (regenerated in Tasks 9–11) and re-captioned.
- [ ] **Step 2:** Re-run the hero compose (Task 6) so the montage picks up the deep observe/drawing/export clips.
- [ ] **Step 3:** Re-run the README embed check (Task 7 Step 3) + weight budget across all inline clips.
- [ ] **Step 4:** Eyeball the full README once more.
- [ ] **Step 5: Checkpoint (git on hold).**

---

### Task 13: Batch commit — ONLY after the git hold lifts

> Do not start this task until the user confirms git is free.

- [ ] **Step 1:** `git status` — review every changed/new path (tools, tests, README, `docs/archive`, `docs/img`, `pyproject.toml`, specs/plans/notes).
- [ ] **Step 2:** Run the CI gates locally: `flake8 .` → `black --check .` → `mypy .` (delete any stray `nul` first) → `C:/Python314/python.exe -m pytest tests/tools -q`.
- [ ] **Step 3:** Stage + commit in logical chunks (tooling+tests; media; README+docs; pyproject). **No `Co-Authored-By: Claude` trailer.**
- [ ] **Step 4:** Push per the user's instruction.

---

## Self-Review

**1. Spec coverage:** §5 phasing → Tasks 1–12; §6 wedge → Task 7 Step 1; §7 captions/budget → Tasks 2–4 + budget checks; §8 gallery + deep content → Tasks 4/7 (Phase 1) + 9–11 (Phase 2); §9 open items → Task 8 (P2.0), Task 6 (hero from clips, F6), Task 7 (export cell, F1); §11 deliverables → Tasks 1–12; §13 audit fixes → F1 (Task 7 export cell), F2/F3 (Task 9 labeled experimental), F4 (tracked as #55 / out-of-plan git-gated), F5 (Task 1 mkdir), F6 (Task 6), F7 (Task 7 badge). **Gap:** F4 wire-twin (spec §9) is intentionally out-of-plan (git+seat gated, doesn't block) — tracked as task #55; noted here so it isn't lost.

**2. Placeholder scan:** No "TBD/TODO/handle edge cases". Phase-2 handler specifics are gated behind Task 8's concrete findings note (an explicit deliverable), not a vague placeholder — honest given seat-gating.

**3. Type consistency:** `Caption(value, cli=None)` and `caption_clip(src_gif, cap, out_gif)` used identically in Tasks 3/4/6/9/10/11; `_demo_media` helper names (`ffprobe_dims`, `file_kb`, `gif_with_overlay`, `mp4_from_gif`) consistent across consumers. `plan_hero_filter(n_clips, speed)` and `paginate_tour(text, max_lines)` match their tests.
