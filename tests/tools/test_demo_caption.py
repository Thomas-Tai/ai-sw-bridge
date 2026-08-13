import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import demo_caption as c  # noqa: E402


def test_build_caption_png_dims(tmp_path):
    out = c.build_caption_png(
        c.Caption("Real mates", "ai-sw-assembly"), 560, tmp_path / "band.png"
    )
    assert out.exists()
    from PIL import Image

    w, h = Image.open(out).size
    assert w == 560 and h == c.BAND_H


def test_caption_value_only(tmp_path):
    out = c.build_caption_png(c.Caption("One number rebuilds"), 560, tmp_path / "b.png")
    assert out.exists()


def test_fit_font_shrinks_long_text_and_fits():
    max_w = 560 - 2 * c.PAD
    short = c.fit_font_size("Hi", max_w)
    long = c.fit_font_size("Change one number; the real feature tree rebuilds", max_w)
    assert short == c.VALUE_SIZE  # short text keeps the full size
    assert c.VALUE_MIN <= long <= short  # long text shrinks, never below the floor
    # the chosen long size must actually fit within the band width
    w = c._MEASURE.textlength(
        "Change one number; the real feature tree rebuilds",
        font=c._font(long, bold=True),
    )
    assert w <= max_w
