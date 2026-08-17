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
