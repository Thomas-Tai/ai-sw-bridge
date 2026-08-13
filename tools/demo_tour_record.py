"""Render the introspected capability tour into a short branded slideshow gif.
Captures `demo_full_system.py --tour-only` text, wraps + paginates it, draws each
page on a dark card via Pillow, and stitches a hold-per-page gif via ffmpeg."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _demo_media as media  # noqa: E402

W, H = 620, 600
BG = (18, 20, 24)
FG = (222, 230, 238)
ACCENT = (120, 190, 255)
MARGIN, LINE_H, FPS = 28, 26, 8
HEADER_DROP = 44
BODY_SIZE = 15
HOLD_FRAMES_PER_PAGE = 24

_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def _font(size: int, bold: bool = False):
    names = ["consolab.ttf", "courbd.ttf"] if bold else ["consola.ttf", "cour.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def cols_for_width(width: int, margin: int, size: int) -> int:
    char_w = _MEASURE.textlength("M", font=_font(size)) or 8.0
    return max(10, int((width - 2 * margin) / char_w))


def wrap_display_lines(line: str, cols: int) -> list[str]:
    """Wrap one source line to <= cols chars, preserving its leading indent;
    continuation lines get the indent + 2 spaces."""
    stripped = line.lstrip(" ")
    indent = line[: len(line) - len(stripped)]
    if len(line) <= cols:
        return [line]
    body_w = max(1, cols - len(indent) - 2)
    chunks = textwrap.wrap(
        stripped, width=body_w, break_long_words=True, break_on_hyphens=False
    ) or [stripped[:body_w]]
    out = [indent + chunks[0]]
    out.extend(indent + "  " + ch for ch in chunks[1:])
    return out


def paginate_tour(text: str, max_lines: int) -> list[list[str]]:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return [lines[i : i + max_lines] for i in range(0, len(lines), max_lines)] or [[]]


def _draw_page(lines: list[str], page: int, npages: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text(
        (MARGIN, MARGIN),
        "ai-sw-bridge — capability surface",
        font=_font(20, bold=True),
        fill=ACCENT,
    )
    d.text(
        (W - MARGIN - 70, MARGIN + 2),
        f"{page}/{npages}",
        font=_font(15),
        fill=(120, 130, 140),
    )
    y = MARGIN + HEADER_DROP
    for ln in lines:
        color = ACCENT if ln and not ln.startswith(" ") else FG
        d.text((MARGIN, y), ln, font=_font(BODY_SIZE), fill=color)
        y += LINE_H
    return img


def render_tour_gif(pages: list[list[str]], out_gif: pathlib.Path) -> pathlib.Path:
    out_gif = pathlib.Path(out_gif)
    frames_dir = out_gif.parent / "_tour_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.png"):
        old.unlink()
    idx = 0
    for pnum, page in enumerate(pages, start=1):
        card = _draw_page(page, pnum, len(pages))
        for _ in range(HOLD_FRAMES_PER_PAGE):
            card.save(frames_dir / f"f{idx:04d}.png")
            idx += 1
    _palette_gif(frames_dir, out_gif)
    media.mp4_from_gif(out_gif, out_gif.with_suffix(".mp4"))
    shutil.rmtree(frames_dir, ignore_errors=True)  # scratch frames, not artifacts
    return out_gif


def _palette_gif(frames_dir: pathlib.Path, out_gif: pathlib.Path):
    seq = str(frames_dir / "f%04d.png")
    pal = frames_dir / "pal.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            seq,
            "-vf",
            "palettegen=stats_mode=diff",
            str(pal),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            seq,
            "-i",
            str(pal),
            "-lavfi",
            "paletteuse=dither=bayer:bayer_scale=3",
            str(out_gif),
        ],
        check=True,
    )


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            "C:/Python314/python.exe",
            "tools/demo_full_system.py",
            "--tour-only",
            "--no-pause",
            "--sleep",
            "0",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    text = proc.stdout or ""
    cols = cols_for_width(W, MARGIN, BODY_SIZE)
    display: list[str] = []
    for ln in text.splitlines():
        if ln.strip():
            display.extend(wrap_display_lines(ln.rstrip(), cols))
    per_page = (H - MARGIN - HEADER_DROP - MARGIN) // LINE_H
    pages = paginate_tour("\n".join(display), per_page)
    out = render_tour_gif(pages, root / "docs" / "img" / "demo_tour.gif")
    print(
        "tour ->",
        out.name,
        f"{out.stat().st_size / 1024:.0f} KiB, pages={len(pages)}",
        f"cols={cols}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
