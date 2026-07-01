"""Unit tests for the table-driven MCP-client registrar.

Pure JSON/file logic against tmp_path — no ComExecutor, no server, no COM.
Runs in the normal seat-safe suite (NOT an mcp_lane_live/destructive test).
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_sw_bridge.mcp import registration as reg


def test_register_creates_file_and_entry_no_backup(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"  # does not exist yet
    out = reg.register(config_path=cfg, command="C:/pipx/ai-sw-mcp.exe")

    assert out["ok"] is True
    assert out["changed"] is True
    assert out["backup_path"] is None  # nothing to back up
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"][reg.SERVER_NAME] == {
        "command": "C:/pipx/ai-sw-mcp.exe",
        "args": [],
    }


def test_register_is_idempotent(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    reg.register(config_path=cfg, command="X")
    backups_after_first = list(tmp_path.glob("*.bak-*"))

    out2 = reg.register(config_path=cfg, command="X")

    assert out2["changed"] is False
    assert out2["backup_path"] is None
    # No second backup created; entry not duplicated.
    assert list(tmp_path.glob("*.bak-*")) == backups_after_first


def test_register_preserves_other_servers_and_backs_up(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"other": {"command": "keep"}}}),
        encoding="utf-8",
    )

    out = reg.register(config_path=cfg, command="Y")

    assert out["changed"] is True
    assert out["backup_path"] is not None  # existing file backed up
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"] == {"command": "keep"}
    assert data["mcpServers"][reg.SERVER_NAME]["command"] == "Y"
    backup = json.loads(Path(out["backup_path"]).read_text())
    assert "ai-sw-bridge" not in backup["mcpServers"]  # backup is pre-mutation


def test_register_on_existing_matching_entry_is_noop(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    reg.register(config_path=cfg, command="Z")
    out = reg.register(config_path=cfg, command="Z")
    assert out["changed"] is False


def test_register_malformed_json_backs_up_and_errors(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{ this is not json", encoding="utf-8")

    out = reg.register(config_path=cfg, command="Q")

    assert out["ok"] is False
    assert out["backup_path"] is not None  # corrupt file preserved before touch
    assert "error" in out
    # Original bytes untouched (we did not clobber the operator's file).
    assert cfg.read_text(encoding="utf-8") == "{ this is not json"


def test_detect_absent_then_present(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    d0 = reg.detect(config_path=cfg)
    assert d0["present"] is False and d0["matches"] is False

    reg.register(config_path=cfg, command="C")
    d1 = reg.detect(config_path=cfg, command="C")
    assert d1["present"] is True and d1["matches"] is True
