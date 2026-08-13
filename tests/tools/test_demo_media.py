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
