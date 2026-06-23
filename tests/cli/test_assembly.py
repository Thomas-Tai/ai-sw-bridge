"""Tests for the ai-sw-assembly CLI (Wave-9 Phase-1 advertise surface).

Verifies the parser wires propose/dry_run/commit and the _run_* handlers
thread arguments into the (mocked) assembly lifecycle functions. No running
SOLIDWORKS required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from ai_sw_bridge.cli.assembly import _build_parser

_IMPL_PREFIX = "ai_sw_bridge.client"


def test_parser_wires_subcommands() -> None:
    parser = _build_parser()
    for sub in ("propose", "dry_run", "commit"):
        args = parser.parse_args(
            {
                "propose": [sub, "--spec", "x.json"],
                "dry_run": [sub, "--proposal-id", "abc"],
                "commit": [sub, "--proposal-id", "abc", "--out", "o.sldasm"],
            }[sub]
        )
        assert args.func is not None


def test_propose_loads_spec_and_calls_lifecycle(tmp_path: Path) -> None:
    spec = {"kind": "assembly", "name": "t", "components": [], "mates": []}
    spec_file = tmp_path / "asm.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    parser = _build_parser()
    args = parser.parse_args(["propose", "--spec", str(spec_file)])
    with patch(
        f"{_IMPL_PREFIX}._sw_propose_assembly_impl",
        return_value={"ok": True, "proposal_id": "p1"},
    ) as m:
        result = args.func(args)
    m.assert_called_once_with(spec=spec)
    assert result["ok"] is True


def test_propose_missing_file_fails_soft() -> None:
    parser = _build_parser()
    args = parser.parse_args(["propose", "--spec", "/no/such/spec.json"])
    result = args.func(args)
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_propose_bad_json_fails_soft(tmp_path: Path) -> None:
    spec_file = tmp_path / "bad.json"
    spec_file.write_text("{not json", encoding="utf-8")
    parser = _build_parser()
    args = parser.parse_args(["propose", "--spec", str(spec_file)])
    result = args.func(args)
    assert result["ok"] is False
    assert "invalid JSON" in result["error"]


def test_dry_run_threads_proposal_id() -> None:
    parser = _build_parser()
    args = parser.parse_args(["dry_run", "--proposal-id", "pid42"])
    with patch(
        f"{_IMPL_PREFIX}._sw_dry_run_assembly_impl", return_value={"ok": True}
    ) as m:
        args.func(args)
    m.assert_called_once_with(proposal_id="pid42")


def test_commit_threads_args_and_part_paths() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "commit", "--proposal-id", "pid7", "--out", "out.sldasm",
            "--part-paths", '{"lid": "C:/tmp/lid.sldprt"}',
        ]
    )
    with patch(
        f"{_IMPL_PREFIX}._sw_commit_assembly_impl", return_value={"ok": True}
    ) as m:
        args.func(args)
    m.assert_called_once_with(
        proposal_id="pid7", output_path="out.sldasm",
        part_paths={"lid": "C:/tmp/lid.sldprt"},
    )


def test_commit_bad_part_paths_json_fails_soft() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        ["commit", "--proposal-id", "p", "--out", "o.sldasm", "--part-paths", "{bad"]
    )
    result = args.func(args)
    assert result["ok"] is False
    assert "part-paths" in result["error"]
