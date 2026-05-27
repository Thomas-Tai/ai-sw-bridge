"""Checkpoint garbage collection (audit_review.md §2.9, spec.md §5.9).

``gc.run`` prunes old checkpoint rows from one or more per-part
SQLite databases. Pure SQLite — no SOLIDWORKS coupling.

Three retention dimensions (configurable in ``.ai-sw-bridge.toml``
``[checkpoint]``):

* ``max_count_per_part``: keep the N most recent checkpoints per part.
* ``max_age_days``: prune rows whose timestamp is older than M days.
* ``max_db_size_mb``: hard cap on the SQLite file size; when breached,
  the oldest rows are dropped until the file shrinks below the cap.

All three are AND-combined: a row survives only if it satisfies
every configured dimension. ``None`` disables that dimension.

``gc.run`` returns a :class:`GCReport` describing what was pruned.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("ai_sw_bridge.checkpoint.gc")

_DEFAULT_ROOT = Path(".checkpoints")
_DEFAULT_MAX_COUNT = 100
_DEFAULT_MAX_AGE_DAYS = 30
_DEFAULT_MAX_DB_SIZE_MB = 50.0


@dataclass(frozen=True)
class GCPolicy:
    """Retention policy. Any ``None`` field disables that dimension."""

    max_count_per_part: int | None = _DEFAULT_MAX_COUNT
    max_age_days: int | None = _DEFAULT_MAX_AGE_DAYS
    max_db_size_mb: float | None = _DEFAULT_MAX_DB_SIZE_MB

    @classmethod
    def from_toml(cls, checkpoint_section: dict) -> GCPolicy:
        """Build a policy from a ``[checkpoint]`` TOML section.

        Unknown keys are ignored (lets the file carry unrelated
        checkpoint config without breaking GC).
        """
        if not isinstance(checkpoint_section, dict):
            return cls()
        kwargs: dict = {}
        if "max_count_per_part" in checkpoint_section:
            kwargs["max_count_per_part"] = int(checkpoint_section["max_count_per_part"])
        if "max_age_days" in checkpoint_section:
            kwargs["max_age_days"] = int(checkpoint_section["max_age_days"])
        if "max_db_size_mb" in checkpoint_section:
            kwargs["max_db_size_mb"] = float(checkpoint_section["max_db_size_mb"])
        return cls(**kwargs)


@dataclass(frozen=True)
class GCReport:
    """One GC run's outcome."""

    files_visited: int
    rows_pruned: int
    rows_remaining: int
    bytes_freed: int
    per_file: dict


def run(
    root: Path | None = None,
    *,
    policy: GCPolicy | None = None,
    now: datetime | None = None,
) -> GCReport:
    """Prune old checkpoint rows across every per-part SQLite file.

    Args:
        root: The ``.checkpoints`` directory. Defaults to the
            module-level ``_DEFAULT_ROOT``.
        policy: Retention policy. ``None`` uses :class:`GCPolicy` defaults.
        now: Override the current time (injected for tests).

    Returns:
        A :class:`GCReport` describing the outcome.
    """
    root = Path(root) if root is not None else _DEFAULT_ROOT
    policy = policy or GCPolicy()
    now = now or datetime.now(timezone.utc)

    if not root.exists():
        return GCReport(0, 0, 0, 0, {})

    files_visited = 0
    total_pruned = 0
    total_remaining = 0
    total_freed = 0
    per_file: dict = {}

    for db_path in sorted(root.glob("*.sqlite")):
        files_visited += 1
        before_size = db_path.stat().st_size
        pruned, remaining = _prune_one(db_path, policy=policy, now=now)
        after_size = db_path.stat().st_size if db_path.exists() else 0
        per_file[str(db_path.name)] = {
            "rows_pruned": pruned,
            "rows_remaining": remaining,
            "bytes_freed": max(0, before_size - after_size),
        }
        total_pruned += pruned
        total_remaining += remaining
        total_freed += max(0, before_size - after_size)

    return GCReport(
        files_visited=files_visited,
        rows_pruned=total_pruned,
        rows_remaining=total_remaining,
        bytes_freed=total_freed,
        per_file=per_file,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _prune_one(db_path: Path, *, policy: GCPolicy, now: datetime) -> tuple[int, int]:
    """Prune one per-part SQLite file. Returns (pruned, remaining)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        ids_to_delete: set[int] = set()

        if policy.max_age_days is not None:
            cutoff = (now - timedelta(days=policy.max_age_days)).isoformat()
            rows = conn.execute(
                "SELECT id FROM checkpoints WHERE timestamp < ?", (cutoff,)
            ).fetchall()
            for (row_id,) in rows:
                ids_to_delete.add(row_id)

        if policy.max_count_per_part is not None:
            # Per-part: keep the N most recent; everything older is pruned.
            rows = conn.execute(
                "SELECT part_name FROM checkpoints GROUP BY part_name"
            ).fetchall()
            for (part_name,) in rows:
                keep_ids = {
                    r[0]
                    for r in conn.execute(
                        "SELECT id FROM checkpoints WHERE part_name = ? "
                        "ORDER BY timestamp DESC, id DESC LIMIT ?",
                        (part_name, policy.max_count_per_part),
                    ).fetchall()
                }
                all_ids = {
                    r[0]
                    for r in conn.execute(
                        "SELECT id FROM checkpoints WHERE part_name = ?",
                        (part_name,),
                    ).fetchall()
                }
                ids_to_delete.update(all_ids - keep_ids)

        if policy.max_db_size_mb is not None:
            ids_to_delete.update(
                _ids_to_drop_for_size_cap(
                    conn, cap_bytes=int(policy.max_db_size_mb * 1024 * 1024)
                )
            )

        if ids_to_delete:
            placeholders = ",".join("?" * len(ids_to_delete))
            conn.execute(
                f"DELETE FROM checkpoints WHERE id IN ({placeholders})",
                tuple(ids_to_delete),
            )
            conn.commit()
            # Reclaim disk space after bulk delete.
            conn.execute("VACUUM")

        remaining = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    finally:
        conn.close()
    return len(ids_to_delete), remaining


def _ids_to_drop_for_size_cap(conn: sqlite3.Connection, cap_bytes: int) -> set[int]:
    """Drop oldest rows until the SQLite file would fit under *cap_bytes*.

    We estimate per-row bytes from current file size / row count; this
    is approximate but sufficient for the cap enforcement.
    """
    file_size_pages = conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    current_bytes = file_size_pages * page_size
    if current_bytes <= cap_bytes:
        return set()

    row_count = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    if row_count == 0:
        return set()
    bytes_per_row = max(1, current_bytes // row_count)
    rows_to_drop = max(0, (current_bytes - cap_bytes) // bytes_per_row + 1)
    if rows_to_drop == 0:
        return set()
    rows = conn.execute(
        "SELECT id FROM checkpoints ORDER BY timestamp ASC, id ASC LIMIT ?",
        (rows_to_drop,),
    ).fetchall()
    return {r[0] for r in rows}


__all__ = [
    "GCReport",
    "GCPolicy",
    "run",
]
