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


def _env(tmp_path: Path) -> "dfs.BuildEnv":
    return dfs.BuildEnv(
        Path("C:/repo"),
        tmp_path / "o",
        Path("C:/repo/examples/demo_widget"),
        mates_proven=True,
        export_block_wired=True,
        mutate_drives_nodim=False,
    )


def test_reparam_beat_uses_reparam_safe_var(tmp_path: Path) -> None:
    # Regression for the rehearsal finding (2026-08-11): reparaming BORE_DIA
    # moves the bore rim out from under CHA_BoreLeadIn's literal edge selector
    # and the rebuild fails. BLOCK_W leaves the bore rim/top face untouched.
    assert dfs._MUTATE_VAR == "BLOCK_W"
    steps = dfs.mutate_beat_steps(_env(tmp_path))
    prep = next(s for s in steps if s.id == "reparam_prep")
    assert "BLOCK_W" in prep.display
    assert "BORE_DIA" not in prep.display


def test_substitute_proposal_id_replaces_only_when_id_and_placeholder() -> None:
    argv = ["ai_sw_bridge.cli.assembly", "dry_run", "--proposal-id", "<proposal-id>"]
    out = dfs._substitute_proposal_id(argv, "abc123")
    assert out == [
        "ai_sw_bridge.cli.assembly",
        "dry_run",
        "--proposal-id",
        "abc123",
    ]
    # input list is never mutated (DemoStep is frozen)
    assert argv[-1] == "<proposal-id>"
    # no id captured yet -> no-op, returns the SAME object (cheap `is` check)
    assert dfs._substitute_proposal_id(argv, None) is argv
    # no placeholder present -> no-op, same object
    no_placeholder = ["a", "b"]
    assert dfs._substitute_proposal_id(no_placeholder, "abc123") is no_placeholder


def test_assembly_prep_uses_native_paths_and_is_cylinder(tmp_path: Path) -> None:
    # Native str() (backslash on Windows), not as_posix(): AddComponent4
    # matches SW's registered path, and a forward-slash path returns None.
    script = dfs._assembly_prep_script(_env(tmp_path), mates_proven=True)
    assert "str(demo_out / pathlib.Path(part).name)" in script
    assert "(demo_out / pathlib.Path(part).name).as_posix()" not in script
    # Mate face_ref must use the resolver's `is_cylinder` key -- `cylindrical`
    # is silently ignored and leaves the face unresolved.
    mates_flat = str(dfs._ASSEMBLY_MATES)
    assert "is_cylinder" in mates_flat
    assert "cylindrical" not in mates_flat


def test_observe_chapter_opens_assembly_before_reading(tmp_path: Path) -> None:
    # An assembly commit does not leave the assembly active for a separate
    # observe process, so the observe chapter must open it first.
    steps = dfs._observe_steps(_env(tmp_path))
    assert steps[0].id == "observe_open_assembly"
    opener_src = steps[0].argv[-1]
    assert "DemoWidget.SLDASM" in opener_src
    assert "OpenDoc6" in opener_src
    ids = [s.id for s in steps]
    assert ids.index("observe_open_assembly") < ids.index("observe_interference")


def test_feature_statistics_reads_a_part_not_the_assembly(tmp_path: Path) -> None:
    # feature_statistics returns None on an assembly ("unsupported doc"), so the
    # build-tree read-back runs in the part chapter (on the rebuilt part) and
    # never in the assembly-scoped observe chapter.
    part_ids = [s.id for s in dfs.CHAPTERS["part"].build_steps(_env(tmp_path))]
    assert "observe_part_feature_statistics" in part_ids
    observe_ids = [s.id for s in dfs._observe_steps(_env(tmp_path))]
    assert not any("feature_statistics" in i for i in observe_ids)


def test_assembly_geometry_is_interference_free_config() -> None:
    import json

    # The verified-live interference-free config (fixed 2026-08-13; see the
    # _ASSEMBLY_MATES root-cause history). The shaft threads CONCENTRIC into BOTH
    # bores (block_pos + block_neg); there is NO block<->base coincident mate --
    # an earlier coincident on a bore end-cap silently stood a block upright and
    # pointed its bore up (world +Z), so the "shaft seated through both bores"
    # narrative was false while every mate still reported "ok". The baseplate
    # still sits so its top is at z=0 (transform z=-10 for the 10mm plate).
    mates = dfs._ASSEMBLY_MATES
    assert [m["type"] for m in mates] == ["concentric", "concentric"]
    assert all(m["a"]["component"] == "shaft" for m in mates)
    assert {m["b"]["component"] for m in mates} == {"block_pos", "block_neg"}
    assert not any(m["type"] == "coincident" for m in mates)
    repo = Path(__file__).resolve().parents[2]
    asm = json.loads(
        (repo / "examples/demo_widget/assembly.json").read_text(encoding="utf-8")
    )
    base = next(c for c in asm["components"] if c["id"] == "base")
    assert base["transform"]["xyz_mm"] == [0, 0, -10]
