"""Shared ffmpeg/ffprobe helpers for the demo-clip tools. Palette-gif pipeline
matches the proven render path used elsewhere in this workstream."""

from __future__ import annotations

import pathlib
import subprocess


def file_kb(path: pathlib.Path) -> float:
    return pathlib.Path(path).stat().st_size / 1024.0


def ffprobe_dims(path: pathlib.Path) -> tuple[int, int]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    w, h = out.split("x")
    return int(w), int(h)


def build_overlay_cmd(src_gif, band_png, palette, out_gif, band_h: int, fps: int = 8):
    """Two-input overlay + a pre-generated palette (3rd input) -> gif."""
    vf = f"[0:v][1:v]overlay=0:H-{band_h}"
    return [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(src_gif),
        "-i",
        str(band_png),
        "-i",
        str(palette),
        "-filter_complex",
        f"{vf}[ov];[ov][2:v]paletteuse=dither=bayer:bayer_scale=3",
        str(out_gif),
    ]


def gif_with_overlay(src_gif, band_png, out_gif, band_h: int, fps: int = 8):
    src_gif, band_png, out_gif = map(pathlib.Path, (src_gif, band_png, out_gif))
    palette = out_gif.with_suffix(".pal.png")
    vf = f"[0:v][1:v]overlay=0:H-{band_h}"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src_gif),
            "-i",
            str(band_png),
            "-filter_complex",
            f"{vf},palettegen=stats_mode=diff",
            str(palette),
        ],
        check=True,
    )
    subprocess.run(
        build_overlay_cmd(src_gif, band_png, palette, out_gif, band_h, fps), check=True
    )
    palette.unlink(missing_ok=True)
    return out_gif


def mp4_from_gif(src_gif, out_mp4):
    src_gif, out_mp4 = pathlib.Path(src_gif), pathlib.Path(out_mp4)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src_gif),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            str(out_mp4),
        ],
        check=True,
    )
    return out_mp4
