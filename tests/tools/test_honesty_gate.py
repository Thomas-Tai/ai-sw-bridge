import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import honesty_gate as hg  # noqa: E402


def _kinds_for(violations, surface):
    return [kind for surface_path, kind, _ in violations if surface_path == surface]


def test_phantom_export_in_readme_is_flagged(tmp_path):
    (tmp_path / "README.md").write_text(
        "run `ai-sw-export part.json`\n", encoding="utf-8"
    )
    violations = hg.scan(tmp_path)
    assert hg.KIND_BANNED_TOKEN in _kinds_for(violations, "README.md")


def test_phantom_export_under_docs_superpowers_is_excluded(tmp_path):
    plan_dir = tmp_path / "docs" / "superpowers"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan.md").write_text(
        "historically we said `ai-sw-export part.json`\n", encoding="utf-8"
    )
    violations = hg.scan(tmp_path)
    assert violations == []


def test_real_dxf_cli_in_readme_is_not_flagged(tmp_path):
    (tmp_path / "README.md").write_text(
        "run `ai-sw-export-dxf-flat sheet.json`\n", encoding="utf-8"
    )
    violations = hg.scan(tmp_path)
    assert hg.KIND_BANNED_TOKEN not in _kinds_for(violations, "README.md")


def test_todo_in_launch_kit_is_flagged(tmp_path):
    launch_kit = tmp_path / "launch-kit"
    launch_kit.mkdir()
    (launch_kit / "x.md").write_text("TODO: finish this post\n", encoding="utf-8")
    violations = hg.scan(tmp_path)
    assert hg.KIND_PLACEHOLDER in _kinds_for(violations, "launch-kit/x.md")


def test_todo_in_general_docs_is_not_flagged(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "GUIDE.md").write_text("TODO: revisit this section\n", encoding="utf-8")
    violations = hg.scan(tmp_path)
    assert violations == []


def test_broken_internal_link_in_site_html_is_flagged(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text('<img src="img/missing.png">\n', encoding="utf-8")
    violations = hg.scan(tmp_path)
    assert hg.KIND_BROKEN_LINK in _kinds_for(violations, "site/index.html")


def test_phantom_export_in_demo_source_is_flagged(tmp_path):
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "demo_x.py").write_text(
        'CAPTION = "run ai-sw-export part.json"\n', encoding="utf-8"
    )
    violations = hg.scan(tmp_path)
    assert hg.KIND_BANNED_TOKEN in _kinds_for(violations, "tools/demo_x.py")


def test_missing_explicit_files_do_not_crash(tmp_path):
    # No README.md, USAGE.md, docs/, site/, launch-kit/, tools/ at all.
    assert hg.scan(tmp_path) == []


def test_main_exits_zero_on_clean_repo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hg, "REPO_ROOT", tmp_path)
    assert hg.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("OK:")


def test_main_exits_one_and_groups_by_surface(tmp_path, monkeypatch, capsys):
    (tmp_path / "README.md").write_text(
        "run `ai-sw-export part.json`\n", encoding="utf-8"
    )
    monkeypatch.setattr(hg, "REPO_ROOT", tmp_path)
    assert hg.main() == 1
    err = capsys.readouterr().err
    assert "README.md" in err
    assert "banned-token" in err
