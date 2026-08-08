from __future__ import annotations

from pathlib import Path

from tools import demo_full_system as dfs


def test_all_expands_to_full_ordered_chapter_list() -> None:
    assert dfs.select_chapters("all") == [
        "tour",
        "part",
        "assembly",
        "observe",
        "drawing",
        "export",
    ]


def test_single_chapter_selection() -> None:
    assert dfs.select_chapters("observe") == ["observe"]


def test_unknown_chapter_raises() -> None:
    import pytest

    with pytest.raises(SystemExit):
        dfs.select_chapters("nope")


def test_wipe_demo_out_clears_and_recreates(tmp_path: Path) -> None:
    out = tmp_path / "demo_out"
    out.mkdir()
    (out / "stale.SLDPRT").write_text("x", encoding="utf-8")
    dfs.wipe_demo_out(out)
    assert out.is_dir()
    assert list(out.iterdir()) == []


def test_part_chapter_builds_three_parts_with_no_dim_save_as(tmp_path: Path) -> None:
    env = dfs.BuildEnv(
        repo_root=Path("C:/repo"),
        demo_out=tmp_path / "demo_out",
        widget_dir=Path("C:/repo/examples/demo_widget"),
        mates_proven=False,
        export_block_wired=False,
        mutate_drives_nodim=False,
    )
    steps = dfs.CHAPTERS["part"].build_steps(env)
    build_steps = [s for s in steps if s.id.startswith("build_")]
    assert len(build_steps) == 3
    for s in build_steps:
        assert "--no-dim" in s.argv and "--yes" in s.argv and "--save-as" in s.argv
    # headline mutate beat present
    assert any(s.id.startswith("mutate") or s.id.startswith("reparam") for s in steps)


def test_assembly_caption_flips_on_mates_flag(tmp_path: Path) -> None:
    def env(mates: bool) -> "dfs.BuildEnv":
        return dfs.BuildEnv(
            Path("C:/repo"),
            tmp_path / "o",
            Path("C:/repo/examples/demo_widget"),
            mates_proven=mates,
            export_block_wired=False,
            mutate_drives_nodim=False,
        )

    assert dfs.CHAPTERS["assembly"].title_for(env(True)) != dfs.CHAPTERS[
        "assembly"
    ].title_for(env(False))


def test_export_caption_flips_on_export_block_wired_flag(tmp_path: Path) -> None:
    def env(wired: bool) -> "dfs.BuildEnv":
        return dfs.BuildEnv(
            Path("C:/repo"),
            tmp_path / "o",
            Path("C:/repo/examples/demo_widget"),
            mates_proven=False,
            export_block_wired=wired,
            mutate_drives_nodim=False,
        )

    assert dfs.CHAPTERS["export"].caption_for(env(True)) != dfs.CHAPTERS[
        "export"
    ].caption_for(env(False))
