"""History + checkpoint-info MCP tools (W5.4, §6.4).

Four tools exposing checkpoint introspection:

* ``sw_history_part`` — list every checkpoint for a named part.
* ``sw_history_since`` — list checkpoints at-or-after an ISO timestamp.
* ``sw_history_diff`` — structural diff between two checkpoint IDs.
* ``sw_checkpoint_info`` — encryption status of a checkpoint DB.

These tools touch SQLite, not COM — they do NOT use ``@com_tool``.
The contract test exempts them from the decorator audit.

The write-side checkpoint subcommands (``genkey``, ``rekey``,
``migrate``) are deliberately NOT exposed via MCP — they operate on
credentials and at-rest encryption setup, which stay CLI-only per
``docs/mcp_server_design.md`` §6.4.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..checkpoint import (
    CheckpointStore,
    by_part,
    feature_diff,
    since,
)


_DEFAULT_ROOT = Path(".checkpoints")


def _checkpoint_to_dict(cp: Any) -> dict[str, Any]:
    """Serialize a Checkpoint dataclass to a JSON-safe dict."""
    d = dataclasses.asdict(cp)
    status = d["status"]
    d["status"] = status.value if hasattr(status, "value") else str(status)
    return d


def _open_store(part_name: str, root: Path) -> CheckpointStore | None:
    """Open a CheckpointStore, returning None when the DB is missing."""
    if not root.exists():
        return None
    db_path = root / f"{part_name}.sqlite"
    if not db_path.exists():
        return None
    return CheckpointStore(part_name=part_name, root=root)


def register(mcp: Any) -> None:
    """Register every §6.4 history / checkpoint-info tool against *mcp*."""

    @mcp.tool()
    def sw_history_part(
        part_name: str,
        limit: int | None = None,
        root: str | None = None,
    ) -> dict[str, Any]:
        """List every checkpoint for the named part (most-recent-first)."""
        r = Path(root) if root else _DEFAULT_ROOT
        store = _open_store(part_name, r)
        if store is None:
            return {
                "ok": False,
                "reason": "no_checkpoints",
                "part_name": part_name,
                "root": str(r),
            }
        try:
            rows = by_part(store)
        finally:
            store.close()
        if limit is not None:
            rows = rows[:limit]
        return {
            "ok": True,
            "subcommand": "part",
            "part_name": part_name,
            "count": len(rows),
            "checkpoints": [_checkpoint_to_dict(r) for r in rows],
        }

    @mcp.tool()
    def sw_history_since(
        part_name: str,
        since_ts: str,
        limit: int | None = None,
        root: str | None = None,
    ) -> dict[str, Any]:
        """List checkpoints at-or-after an ISO-8601 timestamp."""
        try:
            ts = datetime.fromisoformat(since_ts)
        except ValueError as e:
            return {
                "ok": False,
                "error": f"invalid ISO timestamp {since_ts!r}: {e}",
            }
        r = Path(root) if root else _DEFAULT_ROOT
        store = _open_store(part_name, r)
        if store is None:
            return {
                "ok": False,
                "reason": "no_checkpoints",
                "part_name": part_name,
                "root": str(r),
            }
        try:
            rows = since(store, ts)
        finally:
            store.close()
        if limit is not None:
            rows = rows[:limit]
        return {
            "ok": True,
            "subcommand": "since",
            "part_name": part_name,
            "since": since_ts,
            "count": len(rows),
            "checkpoints": [_checkpoint_to_dict(r) for r in rows],
        }

    @mcp.tool()
    def sw_history_diff(
        part_name: str,
        id_a: int,
        id_b: int,
        root: str | None = None,
    ) -> dict[str, Any]:
        """Structural diff between two checkpoint IDs."""
        r = Path(root) if root else _DEFAULT_ROOT
        store = _open_store(part_name, r)
        if store is None:
            return {
                "ok": False,
                "reason": "no_checkpoints",
                "part_name": part_name,
                "root": str(r),
            }
        try:
            a = store.get(id_a)
            b = store.get(id_b)
        finally:
            store.close()
        if a is None or b is None:
            missing = [i for i, cp in ((id_a, a), (id_b, b)) if cp is None]
            return {
                "ok": False,
                "error": "checkpoint_id_not_found",
                "missing": missing,
            }
        return {
            "ok": True,
            "subcommand": "diff",
            "part_name": part_name,
            **feature_diff(a, b),
        }

    @mcp.tool()
    def sw_checkpoint_info(
        part_name: str,
        root: str | None = None,
    ) -> dict[str, Any]:
        """Show encryption status of a checkpoint DB."""
        r = Path(root) if root else _DEFAULT_ROOT
        db_path = r / f"{part_name}.sqlite"
        if not db_path.exists():
            return {
                "ok": False,
                "error": f"checkpoint DB not found: {db_path}",
            }
        conn = sqlite3.connect(str(db_path))
        try:
            meta_row = conn.execute(
                "SELECT name FROM sqlite_master " "WHERE type='table' AND name='_meta'"
            ).fetchone()
            if meta_row is None:
                return {
                    "ok": True,
                    "part": part_name,
                    "encrypted": False,
                    "encryption_algo": None,
                    "key_fingerprint": None,
                    "encrypted_columns": [],
                }
            row = conn.execute("SELECT key, value FROM _meta ORDER BY key").fetchall()
            meta = {k: v for k, v in row}
            return {
                "ok": True,
                "part": part_name,
                "encrypted": True,
                "encryption_algo": meta.get("encryption_algo"),
                "key_fingerprint": meta.get("key_fingerprint"),
                "encrypted_columns": (
                    meta.get("encrypted_columns", "").split(",")
                    if meta.get("encrypted_columns")
                    else []
                ),
            }
        finally:
            conn.close()
