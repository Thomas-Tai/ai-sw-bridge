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


def test_wrap_preserves_indent_and_fits_cols():
    long = "  - Sketches: aaaa, bbbb, cccc, dddd, eeee, ffff, gggg, hhhh, iiii, jjjj"
    wrapped = t.wrap_display_lines(long, cols=30)
    assert all(len(ln) <= 30 for ln in wrapped)
    # continuation lines keep the leading indent of the source line
    assert wrapped[0].startswith("  - ")
    assert all(ln.startswith("  ") for ln in wrapped)
