"""Compose the breadth hero from a short window of each captioned chapter clip
(spec 2026-08-12 §5 hero). Trims ~2.5s from every clip, normalizes to one canvas
(bottom-aligned so each clip's burned-in caption lands on the same edge), and
concatenates into a single loop. No extra hero caption — the chapter clips are
already self-captioned, so a second band would double up."""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _demo_media as media  # noqa: E402

HERO_W = 560
HERO_H = 412  # tallest source (demo_assembly); others pad up to it
HERO_FPS = 12

ORDER = ["demo_part", "demo_assembly", "demo_observe", "demo_drawing", "demo_export"]

# demo_part is a 27s build; its first seconds are an empty sketch canvas, so open
# its window on the finished bore face (~t16.5). The other clips are ~5-6s and read
# well from t1.0.
HERO_WINDOWS = [(16.5, 2.5), (1.0, 2.5), (1.0, 2.5), (1.0, 2.5), (1.0, 2.5)]


def plan_hero_filter(
    n_clips: int,
    window_start: float = 1.0,
    window_dur: float = 2.5,
    speed: float = 1.0,
    windows: list[tuple[float, float]] | None = None,
) -> str:
    """filter_complex that trims each input to a window, normalizes it to
    HERO_W x HERO_H (bottom-aligned, white margin on top), then concats to [v].
    Pass `windows` (one (start, dur) per clip) to trim each clip from a
    different point — used to skip a clip's slow build-up and open on
    finished geometry; otherwise every clip uses the scalar window."""
    segs, labels = [], ""
    for i in range(n_clips):
        ws, wd = windows[i] if windows is not None else (window_start, window_dur)
        segs.append(
            f"[{i}:v]trim={ws}:{ws + wd},setpts=(PTS-STARTPTS)/{speed},"
            f"scale={HERO_W}:-1:flags=lanczos,"
            f"pad={HERO_W}:{HERO_H}:0:(oh-ih):color=white,fps={HERO_FPS},setsar=1[c{i}]"
        )
        labels += f"[c{i}]"
    concat = f"{labels}concat=n={n_clips}:v=1:a=0[v]"
    return ";".join(segs) + ";" + concat


def compose_hero(
    clip_paths,
    out_gif,
    window_start: float = 1.0,
    window_dur: float = 2.5,
    speed: float = 1.0,
    windows: list[tuple[float, float]] | None = None,
) -> pathlib.Path:
    out_gif = pathlib.Path(out_gif)
    n = len(clip_paths)
    plan = plan_hero_filter(n, window_start, window_dur, speed, windows)
    pal = out_gif.with_suffix(".pal.png")
    ins: list[str] = []
    for p in clip_paths:
        ins += ["-i", str(p)]
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            *ins,
            "-filter_complex",
            f"{plan};[v]palettegen=stats_mode=diff[p]",
            "-map",
            "[p]",
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
            *ins,
            "-i",
            str(pal),
            "-filter_complex",
            f"{plan};[v][{n}:v]paletteuse=dither=bayer:bayer_scale=3[o]",
            "-map",
            "[o]",
            str(out_gif),
        ],
        check=True,
    )
    pal.unlink(missing_ok=True)
    media.mp4_from_gif(out_gif, out_gif.with_suffix(".mp4"))
    return out_gif


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    img = root / "docs" / "img"
    clips = [img / f"{s}.gif" for s in ORDER]
    missing = [c.name for c in clips if not c.exists()]
    if missing:
        print("MISSING source clips:", missing)
        return 1
    out = compose_hero(clips, img / "demo_hero.gif", windows=HERO_WINDOWS)
    w, h = media.ffprobe_dims(out)
    print("hero ->", out.name, f"{media.file_kb(out):.0f} KiB", f"{w}x{h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
