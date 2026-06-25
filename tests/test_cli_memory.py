"""ai-sw-memory CLI — build / search / stats round-trip (HashEmbedder)."""

from __future__ import annotations

import json

from ai_sw_bridge.cli.memory import main


def _run(capsys, argv) -> dict:
    rc = main(argv)
    out = capsys.readouterr().out
    return rc, json.loads(out)


def _seed_proposals(root):
    pdir = root / "proposals"
    pdir.mkdir()
    (pdir / "a.json").write_text(
        json.dumps(
            {
                "kind": "drawing",
                "state": "committed",
                "spec": {
                    "name": "d",
                    "model": "gearbox.sldprt",
                    "views": ["front", "iso"],
                    "revision_table": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (pdir / "b.json").write_text(
        json.dumps(
            {
                "kind": "assembly",
                "state": "proposed",
                "spec": {
                    "name": "asm",
                    "components": [{"id": "a", "part": "p.SLDPRT"}],
                    "mates": [{"type": "concentric"}],
                },
            }
        ),
        encoding="utf-8",
    )


def test_build_search_stats_round_trip(tmp_path, capsys):
    _seed_proposals(tmp_path)
    idx = str(tmp_path / "dm.sqlite")

    # build
    rc, report = _run(
        capsys,
        ["--index", idx, "--backend", "hash", "build", "--root", str(tmp_path)],
    )
    assert rc == 0 and report["ok"] is True
    assert report["proposals"]["indexed"] == 2
    assert report["total_indexed"] == 2
    assert "spikes_excluded" in report

    # stats
    rc, stats = _run(capsys, ["--index", idx, "--backend", "hash", "stats"])
    assert rc == 0 and stats["recipes"] == 2
    assert stats["by_kind"] == {"drawing": 1, "assembly": 1}
    assert stats["dim"] == 256  # HashEmbedder

    # search (semantic)
    rc, res = _run(
        capsys,
        [
            "--index",
            idx,
            "--backend",
            "hash",
            "search",
            "gearbox revision drawing",
            "-k",
            "2",
        ],
    )
    assert rc == 0 and res["ok"] is True and res["count"] >= 1
    assert res["hits"][0]["recipe"]["kind"] == "drawing"

    # metadata filter
    rc, only_asm = _run(
        capsys,
        [
            "--index",
            idx,
            "--backend",
            "hash",
            "search",
            "components",
            "--kind",
            "assembly",
        ],
    )
    assert rc == 0
    assert all(h["recipe"]["kind"] == "assembly" for h in only_asm["hits"])


def test_search_missing_index_exits_2(tmp_path, capsys):
    import pytest

    with pytest.raises(SystemExit) as ei:
        main(["--index", str(tmp_path / "absent.sqlite"), "search", "x"])
    assert ei.value.code == 2
