"""Table-driven, idempotent registration of the ai-sw-bridge MCP server
into an AI client's config file.

Phase 1 targets Claude Desktop only, but every client is a row in CLIENTS
(config path + servers key), so adding Cursor/Codex later is a new row —
not a rewrite (spec §8.3, settled).

Safety contract (settled, mandatory):
  1. Idempotent  — re-running never duplicates or corrupts the entry.
  2. Backup      — a timestamped copy is written before any mutation.
  3. Transparent — caller receives the config path + the injected entry
                   and the before/after server maps to print.

Pure stdlib; COM-inert; no SOLIDWORKS write ever.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SERVER_NAME = "ai-sw-bridge"
MCP_LAUNCH_SCRIPT = "ai-sw-mcp"


@dataclass(frozen=True)
class ClientSpec:
    label: str
    servers_key: str
    path_factory: Callable[[], Path]


def _claude_desktop_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Claude" / "claude_desktop_config.json"


CLIENTS: dict[str, ClientSpec] = {
    "claude_desktop": ClientSpec(
        label="Claude Desktop",
        servers_key="mcpServers",
        path_factory=_claude_desktop_path,
    ),
}


def client_config_path(client: str) -> Path:
    try:
        return CLIENTS[client].path_factory()
    except KeyError:
        raise ValueError(
            f"unknown client {client!r}; known: {sorted(CLIENTS)}"
        ) from None


def resolve_command() -> str:
    """Absolute path to the ai-sw-mcp shim (Claude Desktop does not inherit
    the full user PATH, so a bare name can fail to launch)."""
    return shutil.which(MCP_LAUNCH_SCRIPT) or MCP_LAUNCH_SCRIPT


def desired_entry(command: str | None = None) -> dict[str, Any]:
    return {"command": command or resolve_command(), "args": []}


def _servers_key(client: str) -> str:
    return CLIENTS[client].servers_key


def _load(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _backup(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    backup = config_path.with_name(f"{config_path.name}.bak-{_timestamp()}")
    shutil.copy2(config_path, backup)
    return str(backup)


def detect(
    client: str = "claude_desktop",
    *,
    config_path: Path | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    """Read-only: is our server present, and does it match the desired entry?"""
    path = config_path or client_config_path(client)
    key = _servers_key(client)
    try:
        data = _load(path)
    except (json.JSONDecodeError, OSError):
        return {
            "client": client,
            "config_path": str(path),
            "present": False,
            "matches": False,
            "current": None,
            "error": "config file unreadable / not valid JSON",
        }
    current = (data.get(key) or {}).get(SERVER_NAME)
    return {
        "client": client,
        "config_path": str(path),
        "present": current is not None,
        "matches": current == desired_entry(command),
        "current": current,
    }


def register(
    client: str = "claude_desktop",
    *,
    config_path: Path | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    """Idempotently merge our MCP server into the client config.

    Backs up an existing file before any write. A no-op when the entry
    already matches. Never clobbers a malformed file — it is backed up
    and left byte-for-byte intact, and an error is returned.
    """
    path = config_path or client_config_path(client)
    key = _servers_key(client)
    entry = desired_entry(command)

    try:
        data = _load(path)
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "client": client,
            "config_path": str(path),
            "changed": False,
            "backup_path": _backup(path),
            "entry": entry,
            "error": f"existing config is not valid JSON: {exc!r}. "
            "Backed it up and made no change; fix or delete it, then retry.",
        }

    servers = data.get(key)
    if not isinstance(servers, dict):
        servers = {}
    servers_before = copy.deepcopy(servers)

    if servers.get(SERVER_NAME) == entry:
        return {
            "ok": True,
            "client": client,
            "config_path": str(path),
            "changed": False,
            "backup_path": None,
            "entry": entry,
            "servers_before": servers_before,
            "servers_after": servers_before,
        }

    backup_path = _backup(path)
    servers[SERVER_NAME] = entry
    data[key] = servers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "client": client,
        "config_path": str(path),
        "changed": True,
        "backup_path": backup_path,
        "entry": entry,
        "servers_before": servers_before,
        "servers_after": servers,
    }
