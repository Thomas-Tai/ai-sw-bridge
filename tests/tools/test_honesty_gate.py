import pathlib
import sys

import pytest

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


def test_phantom_export_under_docs_superpowers_is_excluded_by_default_manifest(
    tmp_path,
):
    # DEFAULT_MANIFEST's banned-token check globs into docs/**/*.md, so this
    # genuinely exercises EXCLUDED_PREFIXES / _is_excluded under the real,
    # unmodified manifest -- not just a manifest override (see the
    # parametrized test below, which pins the exclusion behavior directly).
    plan_dir = tmp_path / "docs" / "superpowers"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan.md").write_text(
        "historically we said `ai-sw-export part.json`\n", encoding="utf-8"
    )
    violations = hg.scan(tmp_path)
    assert violations == []


def test_bare_export_in_non_excluded_docs_is_flagged_by_default_manifest(tmp_path):
    # The whole point of broadening KIND_BANNED_TOKEN's glob to docs/**/*.md:
    # an unlisted doc outside the excluded subtrees is now caught by the
    # DEFAULT manifest, with no override needed.
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "GUIDE.md").write_text("run `ai-sw-export part.json`\n", encoding="utf-8")
    violations = hg.scan(tmp_path)
    assert hg.KIND_BANNED_TOKEN in _kinds_for(violations, "docs/GUIDE.md")


@pytest.mark.parametrize(
    "excluded_dir",
    ["docs/superpowers", "docs/archive", "docs/i18n"],
)
def test_excluded_prefix_is_actually_filtered_from_a_reaching_glob(
    tmp_path, excluded_dir
):
    # Pins the exclusion behavior directly against an explicit docs/**/*.md
    # manifest override, independent of whatever DEFAULT_MANIFEST happens to
    # scope today -- confirms the excluded subtree is dropped while a docs/
    # sibling outside it is still flagged.
    excluded_path = tmp_path / excluded_dir / "plan.md"
    excluded_path.parent.mkdir(parents=True)
    excluded_path.write_text("historic `ai-sw-export part.json`\n", encoding="utf-8")

    sibling = tmp_path / "docs" / "GUIDE.md"
    sibling.write_text("run `ai-sw-export part.json`\n", encoding="utf-8")

    manifest = {
        hg.KIND_BANNED_TOKEN: hg.CheckSpec(explicit=(), globs=("docs/**/*.md",)),
    }
    violations = hg.scan(tmp_path, manifest=manifest)
    flagged_surfaces = {surface for surface, _, _ in violations}

    assert "docs/GUIDE.md" in flagged_surfaces
    assert f"{excluded_dir}/plan.md" not in flagged_surfaces


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
