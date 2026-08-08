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
