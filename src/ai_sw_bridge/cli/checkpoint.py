"""ai-sw-checkpoint CLI entry point (W3.1).

Subcommands for managing checkpoint encryption:

* ``genkey`` — generate a fresh Fernet key and print to stdout
* ``info <part>`` — show encryption status of a checkpoint DB
* ``rekey <part>`` — re-encrypt all cells with a new key
* ``migrate <part>`` — encrypt a previously plain DB

Two-stream contract: stdout carries JSON (or raw key for genkey),
stderr carries human messages.

Stability tier: experimental.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..checkpoint.crypto import (
    KeySource,
    KeySourceError,
    decrypt_cell,
    encrypt_cell,
    generate_key,
)
from ..checkpoint.store import _ENCRYPTED_COLUMNS
from .stability import add_subcommand_tier, add_tier, cli_stability


def _emit_json(payload: dict[str, Any], code: int = 0) -> int:
    """Print JSON to stdout and return exit code."""
    print(json.dumps(payload, indent=2))
    return code


def _stderr(msg: str) -> None:
    """Print a message to stderr."""
    print(msg, file=sys.stderr)


def _cmd_genkey(args: argparse.Namespace) -> int:
    """Generate a fresh Fernet key and print to stdout."""
    key = generate_key()
    # Raw key to stdout (not JSON) - it's a credential that may be piped
    print(key.decode("ascii"))
    # Usage hint to stderr
    _stderr(
        "Generated Fernet key. Save to a keyfile with:\n"
        "  ai-sw-checkpoint genkey > keyfile\n"
        "Or set as environment variable for use with --checkpoint-encrypt env:NAME"
    )
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    """Show encryption status of a checkpoint DB."""
    root = Path(args.root) if args.root else Path(".checkpoints")
    part_name = args.part
    db_path = root / f"{part_name}.sqlite"

    if not db_path.exists():
        return _emit_json(
            {"ok": False, "error": f"checkpoint DB not found: {db_path}"}, 2
        )

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        # Check if _meta table exists
        meta_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_meta'"
        ).fetchone()

        if meta_row is None:
            # Plain DB (no encryption)
            return _emit_json(
                {
                    "ok": True,
                    "part": part_name,
                    "encrypted": False,
                    "encryption_algo": None,
                    "key_fingerprint": None,
                    "encrypted_columns": [],
                }
            )

        # Encrypted DB - read _meta
        row = conn.execute(
            "SELECT encryption_algo, key_fingerprint, encrypted_cols "
            "FROM _meta LIMIT 1"
        ).fetchone()

        if row is None:
            return _emit_json(
                {
                    "ok": True,
                    "part": part_name,
                    "encrypted": False,
                    "encryption_algo": None,
                    "key_fingerprint": None,
                    "encrypted_columns": [],
                }
            )

        import json as json_mod

        encrypted_cols = json_mod.loads(row[2])

        return _emit_json(
            {
                "ok": True,
                "part": part_name,
                "encrypted": True,
                "encryption_algo": row[0],
                "key_fingerprint": row[1],
                "encrypted_columns": encrypted_cols,
            }
        )
    finally:
        conn.close()


def _cmd_rekey(args: argparse.Namespace) -> int:
    """Re-encrypt all cells with a new key."""
    root = Path(args.root) if args.root else Path(".checkpoints")
    part_name = args.part
    db_path = root / f"{part_name}.sqlite"

    if not db_path.exists():
        return _emit_json(
            {"ok": False, "error": f"checkpoint DB not found: {db_path}"}, 2
        )

    try:
        from_key = KeySource.parse(args.from_source)
        to_key = KeySource.parse(args.to_source)
    except KeySourceError as exc:
        return _emit_json({"ok": False, "error": str(exc)}, 2)

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        # Verify old key fingerprint matches stored
        meta_row = conn.execute("SELECT key_fingerprint FROM _meta LIMIT 1").fetchone()

        if meta_row is None:
            return _emit_json(
                {"ok": False, "error": "DB is not encrypted; use migrate instead"}, 2
            )

        stored_fp = meta_row[0]
        from_fp = from_key.fingerprint()
        if stored_fp != from_fp:
            return _emit_json(
                {
                    "ok": False,
                    "error": (
                        f"fingerprint mismatch: stored={stored_fp}, "
                        f"supplied={from_fp}"
                    ),
                },
                2,
            )

        # Begin transaction for atomic rekey
        conn.execute("BEGIN TRANSACTION")

        try:
            # Get all rows
            rows = conn.execute(
                "SELECT id, locals_snapshot, com_call_log FROM checkpoints"
            ).fetchall()

            from_key_bytes = from_key.get_key()
            to_key_bytes = to_key.get_key()

            for row_id, locals_snap, com_log in rows:
                # Decrypt with old key, encrypt with new key
                new_locals = encrypt_cell(
                    decrypt_cell(locals_snap, from_key_bytes), to_key_bytes
                )
                new_log = encrypt_cell(
                    decrypt_cell(com_log, from_key_bytes), to_key_bytes
                )
                conn.execute(
                    "UPDATE checkpoints SET locals_snapshot=?, "
                    "com_call_log=? WHERE id=?",
                    (new_locals, new_log, row_id),
                )

            # Update _meta with new fingerprint
            from .crypto import PromptKeySource

            kdf_algo: str | None = None
            kdf_salt: str | None = None
            if isinstance(to_key, PromptKeySource):
                to_key.get_key()  # Trigger derivation
                kdf_algo = "pbkdf2-sha256-600000"
                if to_key.salt is not None:
                    import base64

                    kdf_salt = base64.b64encode(to_key.salt).decode("ascii")

            conn.execute(
                "UPDATE _meta SET key_fingerprint=?, kdf_algo=?, kdf_salt=?",
                (to_key.fingerprint(), kdf_algo, kdf_salt),
            )

            conn.commit()
            _stderr(f"Rekeyed {len(rows)} rows successfully")
            return _emit_json(
                {
                    "ok": True,
                    "rows_rekeyed": len(rows),
                    "new_fingerprint": to_key.fingerprint(),
                }
            )
        except Exception as exc:
            conn.rollback()
            return _emit_json({"ok": False, "error": str(exc)}, 1)
    finally:
        conn.close()


def _cmd_migrate(args: argparse.Namespace) -> int:
    """Encrypt a previously plain DB (one-shot migration)."""
    root = Path(args.root) if args.root else Path(".checkpoints")
    part_name = args.part
    db_path = root / f"{part_name}.sqlite"

    if not db_path.exists():
        return _emit_json(
            {"ok": False, "error": f"checkpoint DB not found: {db_path}"}, 2
        )

    try:
        to_key = KeySource.parse(args.to_source)
    except KeySourceError as exc:
        return _emit_json({"ok": False, "error": str(exc)}, 2)

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        # Check if already encrypted
        meta_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_meta'"
        ).fetchone()

        if meta_row is not None:
            return _emit_json({"ok": False, "error": "DB is already encrypted"}, 2)

        # Begin transaction
        conn.execute("BEGIN TRANSACTION")

        try:
            # Create _meta table
            conn.execute(
                """
                CREATE TABLE _meta (
                    encrypted_at     TEXT NOT NULL,
                    encryption_algo  TEXT NOT NULL,
                    encrypted_cols   TEXT NOT NULL,
                    kdf_algo         TEXT,
                    kdf_salt         TEXT,
                    key_fingerprint  TEXT NOT NULL
                )
            """
            )

            # Get KDF info if using PromptKeySource
            from .crypto import PromptKeySource

            kdf_algo: str | None = None
            kdf_salt: str | None = None
            if isinstance(to_key, PromptKeySource):
                to_key.get_key()  # Trigger derivation
                kdf_algo = "pbkdf2-sha256-600000"
                if to_key.salt is not None:
                    import base64

                    kdf_salt = base64.b64encode(to_key.salt).decode("ascii")

            # Insert _meta row
            from datetime import datetime, timezone

            conn.execute(
                "INSERT INTO _meta "
                "(encrypted_at, encryption_algo, encrypted_cols, kdf_algo, "
                "kdf_salt, key_fingerprint) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    "fernet-v1",
                    json.dumps(_ENCRYPTED_COLUMNS),
                    kdf_algo,
                    kdf_salt,
                    to_key.fingerprint(),
                ),
            )

            # Encrypt all existing rows
            rows = conn.execute(
                "SELECT id, locals_snapshot, com_call_log FROM checkpoints"
            ).fetchall()

            to_key_bytes = to_key.get_key()
            for row_id, locals_snap, com_log in rows:
                new_locals = encrypt_cell(locals_snap, to_key_bytes)
                new_log = encrypt_cell(com_log, to_key_bytes)
                conn.execute(
                    "UPDATE checkpoints SET locals_snapshot=?, "
                    "com_call_log=? WHERE id=?",
                    (new_locals, new_log, row_id),
                )

            conn.commit()
            _stderr(f"Migrated {len(rows)} rows to encrypted format")
            return _emit_json(
                {
                    "ok": True,
                    "rows_migrated": len(rows),
                    "fingerprint": to_key.fingerprint(),
                }
            )
        except Exception as exc:
            conn.rollback()
            return _emit_json({"ok": False, "error": str(exc)}, 1)
    finally:
        conn.close()


@cli_stability("experimental")
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ai-sw-checkpoint",
        description="Manage checkpoint encryption (W3.1).",
    )
    add_tier(parser, "experimental")

    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # genkey
    genkey_parser = subparsers.add_parser("genkey", help="Generate a fresh Fernet key")
    add_subcommand_tier(genkey_parser, "experimental")
    genkey_parser.set_defaults(func=_cmd_genkey)

    # info
    info_parser = subparsers.add_parser(
        "info", help="Show encryption status of a checkpoint DB"
    )
    add_subcommand_tier(info_parser, "experimental")
    info_parser.add_argument("part", help="Part name")
    info_parser.add_argument(
        "--root", default=None, help="Checkpoint root directory (default: .checkpoints)"
    )
    info_parser.set_defaults(func=_cmd_info)

    # rekey
    rekey_parser = subparsers.add_parser(
        "rekey", help="Re-encrypt all cells with a new key"
    )
    add_subcommand_tier(rekey_parser, "experimental")
    rekey_parser.add_argument("part", help="Part name")
    rekey_parser.add_argument(
        "--from", dest="from_source", required=True, help="Current key source"
    )
    rekey_parser.add_argument(
        "--to", dest="to_source", required=True, help="New key source"
    )
    rekey_parser.add_argument(
        "--root", default=None, help="Checkpoint root directory (default: .checkpoints)"
    )
    rekey_parser.set_defaults(func=_cmd_rekey)

    # migrate
    migrate_parser = subparsers.add_parser(
        "migrate", help="Encrypt a previously plain DB"
    )
    add_subcommand_tier(migrate_parser, "experimental")
    migrate_parser.add_argument("part", help="Part name")
    migrate_parser.add_argument(
        "--to", dest="to_source", required=True, help="Target key source"
    )
    migrate_parser.add_argument(
        "--root", default=None, help="Checkpoint root directory (default: .checkpoints)"
    )
    migrate_parser.set_defaults(func=_cmd_migrate)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 2

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
