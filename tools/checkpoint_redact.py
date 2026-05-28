#!/usr/bin/env python3
"""Redact a checkpoint DB for safe sharing (W3.2, privacy_review §4.3).

Produces a sanitized copy of a checkpoint SQLite database:

- ``locals_snapshot`` → ``<redacted_local>``
- ``com_call_log`` → trade-secret patterns scrubbed
- Tree hashes preserved (cryptographic, can't reverse to dimensions)
- Output: ``<part>.sqlite.redacted.<timestamp>``
- No ``_meta`` table in output (always plain, even if source encrypted)

Usage::

    python tools/checkpoint_redact.py .checkpoints/my_part.sqlite
    python tools/checkpoint_redact.py .checkpoints/part.sqlite --from-key-source env:KEY
    python tools/checkpoint_redact.py .checkpoints/part.sqlite --output redacted.sqlite

Exit codes: 0 = success, 2 = input error.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# Trade-secret patterns to redact from com_call_log
# These are common parameter names that might encode proprietary info
_TRADE_SECRET_PATTERNS = [
    r"\b[A-Z_]{3,}\s*=\s*[0-9.]+",  # VAR_NAME = 123.4
    r"\b\d+\.\d+\s*mm\b",  # 123.4 mm
    r"\b\d+\.\d+\s*inch\b",  # 123.4 inch
]


def _redact_com_call_log(text: str) -> str:
    """Scan com_call_log for trade-secret patterns and redact them."""
    result = text
    for pattern in _TRADE_SECRET_PATTERNS:
        result = re.sub(pattern, "<redacted>", result)
    return result


def redact_checkpoint(
    db_path: Path,
    *,
    from_key_source: Any = None,
    output_path: Path | None = None,
) -> Path:
    """Produce a redacted copy of a checkpoint database.

    Args:
        db_path: Path to the source checkpoint SQLite DB.
        from_key_source: Optional KeySource for reading encrypted source DBs.
        output_path: Output path (default: <input>.redacted.<timestamp>).

    Returns:
        Path to the redacted output database.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"checkpoint DB not found: {db_path}")

    # Determine output path
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = db_path.with_name(f"{db_path.name}.redacted.{timestamp}")

    # Open source DB (with decryption if key_source provided)
    from ai_sw_bridge.checkpoint.store import CheckpointStore

    part_name = db_path.stem
    store = CheckpointStore(part_name, root=db_path.parent, key_source=from_key_source)

    # Create output DB (always plain, no _meta table)
    out_conn = sqlite3.connect(str(output_path))
    try:
        # Create schema (same as CheckpointStore but no _meta)
        out_conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                part_name       TEXT    NOT NULL,
                feature_index   INTEGER NOT NULL,
                feature_name    TEXT    NOT NULL,
                feature_type    TEXT    NOT NULL,
                timestamp       TEXT    NOT NULL,
                locals_snapshot TEXT    NOT NULL,
                spec_hash       TEXT    NOT NULL,
                pre_tree_hash   TEXT    NOT NULL,
                post_tree_hash  TEXT,
                com_call_log    TEXT    NOT NULL,
                build_mode      TEXT    NOT NULL,
                status          TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_part_timestamp
                ON checkpoints(part_name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_status
                ON checkpoints(status);
            """
        )

        # Read all rows from source (decrypted if encrypted)
        rows = store.query()

        # Write redacted rows to output
        for row in rows:
            out_conn.execute(
                """
                INSERT INTO checkpoints
                (part_name, feature_index, feature_name, feature_type, timestamp,
                 locals_snapshot, spec_hash, pre_tree_hash, post_tree_hash,
                 com_call_log, build_mode, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.part_name,
                    row.feature_index,
                    row.feature_name,
                    row.feature_type,
                    row.timestamp,
                    "<redacted_local>",  # Redact locals_snapshot
                    row.spec_hash,
                    row.pre_tree_hash,
                    row.post_tree_hash,
                    _redact_com_call_log(row.com_call_log),  # Redact com_call_log
                    row.build_mode,
                    row.status.value,
                ),
            )

        out_conn.commit()
    finally:
        out_conn.close()
        store.close()

    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="checkpoint_redact",
        description=(
            "Redact a checkpoint DB for safe sharing: replace locals_snapshot "
            "with <redacted_local>, scrub com_call_log trade-secret patterns, "
            "preserve tree hashes (W3.2)."
        ),
    )
    parser.add_argument("db_path", help="Path to the checkpoint SQLite DB to redact.")
    parser.add_argument(
        "--from-key-source",
        default=None,
        metavar="SOURCE",
        help=(
            "Key source for reading an encrypted checkpoint DB. "
            "One of: env:NAME, file:/path, keyring:SERVICE, or prompt."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help=("Output path (default: <input>.redacted.<timestamp> next to input)."),
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"error: checkpoint DB not found: {db_path}", file=sys.stderr)
        return 2

    # Parse key source if provided
    from_key_source = None
    if args.from_key_source:
        from ai_sw_bridge.checkpoint.crypto import KeySource, KeySourceError

        try:
            from_key_source = KeySource.parse(args.from_key_source)
        except KeySourceError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    output_path = Path(args.output) if args.output else None

    try:
        out_path = redact_checkpoint(
            db_path, from_key_source=from_key_source, output_path=output_path
        )
        print(f"redacted checkpoint written to {out_path}", file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
