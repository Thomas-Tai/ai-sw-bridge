import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import demo_hero as h  # noqa: E402


def test_plan_hero_filter_trims_and_concats_all():
    f = h.plan_hero_filter(3, window_start=1.0, window_dur=2.5)
    assert f.count("trim=") == 3
    assert f.count(f"pad={h.HERO_W}:{h.HERO_H}") == 3  # every clip normalized
    assert "concat=n=3" in f
    assert f.strip().endswith("[v]")


def test_plan_hero_filter_single():
    f = h.plan_hero_filter(1)
    assert "concat=n=1" in f
    assert f.count("trim=") == 1


def test_plan_hero_filter_per_clip_windows():
    f = h.plan_hero_filter(2, windows=[(16.5, 2.5), (1.0, 2.5)])
    # each clip trims from its own start; ends are start+dur
    assert "trim=16.5:19.0" in f
    assert "trim=1.0:3.5" in f
    assert "concat=n=2" in f
