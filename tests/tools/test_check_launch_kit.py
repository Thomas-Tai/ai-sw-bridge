import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_launch_kit as ck  # noqa: E402


def test_find_placeholders_flags_todo_and_tbd():
    hits = ck.find_placeholders("intro\nTODO: write this\nmid\nTBD later\n")
    assert len(hits) == 2


def test_find_placeholders_clean_text_is_empty():
    assert ck.find_placeholders("A finished, honest paragraph.") == []


def test_find_banned_claims_flags_phantom_export_cli():
    assert ck.find_banned_claims("run `ai-sw-export part.json`") != []


def test_find_banned_claims_allows_real_dxf_cli():
    assert ck.find_banned_claims("run `ai-sw-export-dxf-flat sheet.json`") == []


def test_check_internal_links_flags_missing_asset(tmp_path):
    doc = tmp_path / "page.md"
    doc.write_text("![hero](img/missing.gif)\n", encoding="utf-8")
    errs = ck.check_internal_links(doc, tmp_path)
    assert any("missing.gif" in e for e in errs)


def test_check_internal_links_passes_existing_asset(tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "hero.gif").write_bytes(b"GIF89a")
    doc = tmp_path / "page.md"
    doc.write_text("![hero](img/hero.gif)\n", encoding="utf-8")
    assert ck.check_internal_links(doc, tmp_path) == []


def test_find_placeholders_flags_upper_underscore_stub():
    assert ck.find_placeholders("Follow <YOUR_X_HANDLE> now") != []


def test_find_placeholders_ignores_real_html_tag():
    assert ck.find_placeholders('<div class="hero">clean</div>') == []


def test_find_banned_claims_allows_similarly_named_word():
    assert ck.find_banned_claims("the ai-sw-exporter add-on") == []


def test_check_internal_links_resolves_root_relative(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.png").write_bytes(b"PNG")
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    page = site_dir / "index.html"
    page.write_text('<img src="/assets/logo.png">', encoding="utf-8")
    assert ck.check_internal_links(page, tmp_path) == []
