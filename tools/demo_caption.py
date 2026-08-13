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
BAND_RGBA = (20, 22, 26, 115)  # ~0.45 alpha
PAD = 18
VALUE_SIZE = 30
CLI_SIZE = 19
VALUE_MIN = 18

_MEASURE = ImageDraw.Draw(Image.new("RGBA", (1, 1)))


@dataclasses.dataclass(frozen=True)
class Caption:
    value: str
    cli: str | None = None


def _font(size: int, bold: bool = False):
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_font_size(
    text: str,
    max_w: int,
    start: int = VALUE_SIZE,
    min_size: int = VALUE_MIN,
    bold: bool = True,
) -> int:
    """Largest size in [min_size, start] whose rendered `text` width <= max_w."""
    for size in range(start, min_size, -1):
        if _MEASURE.textlength(text, font=_font(size, bold=bold)) <= max_w:
            return size
    return min_size


def build_caption_png(cap: Caption, width: int, out_path: pathlib.Path) -> pathlib.Path:
    out_path = pathlib.Path(out_path)
    img = Image.new("RGBA", (width, BAND_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, BAND_H], fill=BAND_RGBA)
    max_w = width - 2 * PAD
    vsize = fit_font_size(cap.value, max_w)
    d.text(
        (PAD, PAD), cap.value, font=_font(vsize, bold=True), fill=(255, 255, 255, 255)
    )
    if cap.cli:
        d.text(
            (PAD, PAD + 42), cap.cli, font=_font(CLI_SIZE), fill=(176, 200, 224, 255)
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def caption_clip(
    src_gif: pathlib.Path, cap: Caption, out_gif: pathlib.Path
) -> pathlib.Path:
    src_gif, out_gif = pathlib.Path(src_gif), pathlib.Path(out_gif)
    width, _ = media.ffprobe_dims(src_gif)
    band = out_gif.with_name(out_gif.stem + "_band.png")
    build_caption_png(cap, width, band)
    media.gif_with_overlay(src_gif, band, out_gif, BAND_H)
    media.mp4_from_gif(out_gif, out_gif.with_suffix(".mp4"))
    band.unlink(missing_ok=True)
    return out_gif
