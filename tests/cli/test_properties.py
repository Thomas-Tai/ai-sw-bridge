"""Tests for the ai-sw-properties CLI (W29 §6.5 propose/dry_run/commit surface).

Verifies the parser wires the three subcommands and the _run_* handlers
thread arguments into the (mocked) properties lifecycle functions. No
running SOLIDWORKS required. Patch target: ``ai_sw_bridge.client._sw_*_impl``
— the CLI routes through ``SolidWorksClient().mutate.*`` so the facade's
``_impl`` core is the correct seam.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from ai_sw_bridge.cli.properties import _build_parser

_IMPL_PREFIX = "ai_sw_bridge.client"


def test_parser_wires_subcommands() -> None:
    parser = _build_parser()
    for sub in ("propose", "dry_run", "commit"):
        args = parser.parse_args(
            {
                "propose": [sub, "--spec", "x.json"],
                "dry_run": [sub, "--proposal-id", "abc"],
                "commit": [sub, "--proposal-id", "abc"],
            }[sub]
        )
        assert args.func is not None


def test_propose_loads_spec_and_calls_lifecycle(tmp_path: Path) -> None:
    spec = {"kind": "part", "name": "t", "model": "m.sldprt", "properties": []}
    spec_file = tmp_path / "props.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    parser = _build_parser()
    args = parser.parse_args(["propose", "--spec", str(spec_file)])
    with patch(
        f"{_IMPL_PREFIX}._sw_propose_properties_impl",
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
        f"{_IMPL_PREFIX}._sw_dry_run_properties_impl", return_value={"ok": True}
    ) as m:
        args.func(args)
    m.assert_called_once_with(proposal_id="pid42")


def test_commit_threads_proposal_id() -> None:
    parser = _build_parser()
    args = parser.parse_args(["commit", "--proposal-id", "pid7"])
    with patch(
        f"{_IMPL_PREFIX}._sw_commit_properties_impl", return_value={"ok": True}
    ) as m:
        args.func(args)
    m.assert_called_once_with(proposal_id="pid7")
