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


def test_quickstart_seatless_runs_tier_a_only(tmp_path: Path) -> None:
    env = dfs.BuildEnv(
        Path("C:/repo"),
        tmp_path / "o",
        Path("C:/repo/examples/demo_widget"),
        mates_proven=False,
        export_block_wired=False,
        mutate_drives_nodim=False,
    )
    steps = dfs.quickstart_steps(env, with_sw=False)
    # Seat-less quickstart never issues a live build/observe.
    assert all("--no-dim" not in (s.argv or []) for s in steps)
    assert all("--yes" not in (s.argv or []) for s in steps)


def test_quickstart_doc_commands_match_canonical_list() -> None:
    import re

    doc = Path(__file__).resolve().parents[2] / "QUICKSTART.md"
    fenced = re.findall(r"```bash\n(.*?)```", doc.read_text(encoding="utf-8"), re.S)
    doc_cmds = [
        ln.strip()
        for block in fenced
        for ln in block.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    for cmd in dfs.quickstart_command_lines(with_sw=True):
        assert cmd in doc_cmds, f"QUICKSTART.md missing/renamed command: {cmd}"


def test_quickstart_doctor_step_never_touches_solidworks_seat(
    tmp_path: Path,
) -> None:
    """Regression guard for the live-SW-launch bug: a bare ``doctor``
    invocation defaults to ``run_probe=True``, which calls ``get_sw_app()``
    -- and that falls back to ``win32com.client.Dispatch()``, which
    auto-launches SOLIDWORKS on a box with no seat already running.
    ``--no-seat`` skips the seat probe entirely (env-only, zero COM calls),
    so the doctor step must always carry it. This must fail if the doctor
    step ever reverts to the bare (seat-touching) invocation.
    """
    env = dfs.BuildEnv(
        Path("C:/repo"),
        tmp_path / "o",
        Path("C:/repo/examples/demo_widget"),
        mates_proven=False,
        export_block_wired=False,
        mutate_drives_nodim=False,
    )
    steps = dfs.quickstart_steps(env, with_sw=False)
    doctor_steps = [s for s in steps if "ai_sw_bridge.cli.doctor" in (s.argv or [])]
    assert doctor_steps, "expected a doctor step in quickstart_steps(with_sw=False)"
    for s in doctor_steps:
        assert "--no-seat" in s.argv, f"doctor step missing --no-seat: {s.argv}"

    lines = dfs.quickstart_command_lines(with_sw=True)
    assert "python -m ai_sw_bridge.cli.doctor --no-seat" in lines
    assert "python -m ai_sw_bridge.cli.doctor" not in lines
