"""At-rest encryption for the L4 checkpoint store (W3.1).

Interface skeleton — the design lives in
[`docs/checkpoint_encryption_design.md`](../../../docs/checkpoint_encryption_design.md).
This module declares the surface that ``CheckpointStore``, ``ai-sw-build
--checkpoint-encrypt``, and ``tools/checkpoint_redact.py`` consume. The
impl task (W3.1-impl, Sonnet/GLM) fills in the bodies; the test
contract at ``tests/checkpoint/test_crypto_contract.py`` defines the
behavior.

Decision summary (see design doc for the full rationale):

* App-layer Fernet, not SQLCipher — pure-Python install path matters
  more than transparent SQL queries on encrypted columns, since the
  query API doesn't filter on the encrypted columns anyway.
* Encrypted cells use a ``fernet_v1:<token>`` prefix so plain cells
  pass through unchanged and future algorithm changes can ship a new
  prefix without breaking old DBs.
* Four key sources: ``env:NAME``, ``file:/path``, ``keyring:SERVICE``,
  ``prompt``. The first three carry a raw Fernet key directly; only
  ``prompt`` runs PBKDF2 (the bridge owns the KDF params).
* A ``_meta`` table stores ``key_fingerprint`` (sha256(key)[:16]) so
  ``rekey`` can validate the old key before rewriting cells.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import os
from abc import ABC, abstractmethod
from typing import Any

from cryptography.fernet import Fernet

__all__ = [
    "EnvKeySource",
    "FileKeySource",
    "KeyringKeySource",
    "KeySource",
    "KeySourceError",
    "PromptKeySource",
    "decrypt_cell",
    "encrypt_cell",
    "generate_key",
    "rekey_db",
]


_CELL_PREFIX_V1 = "fernet_v1:"
_KDF_ITERATIONS = 600_000
_KDF_SALT_BYTES = 16
_FINGERPRINT_PREFIX_LEN = 16


class KeySourceError(Exception):
    """Raised when a ``--checkpoint-encrypt`` source string can't be resolved.

    Subclassing ``Exception`` directly (not ``RuntimeError``) so callers
    can ``except KeySourceError`` without catching unrelated runtime
    issues. The CLI maps this to rc=2 with a stderr message.
    """


class KeySource(ABC):
    """Resolves a ``--checkpoint-encrypt`` source string to a Fernet key.

    Subclasses cover the four supported forms:

    * :class:`EnvKeySource` — ``env:NAME``
    * :class:`FileKeySource` — ``file:/path/to/keyfile``
    * :class:`KeyringKeySource` — ``keyring:SERVICE``
    * :class:`PromptKeySource` — ``prompt``

    The :meth:`parse` classmethod is the single entry point for the
    string-to-instance dispatch.
    """

    @classmethod
    def parse(cls, source: str, meta: dict[str, Any] | None = None) -> "KeySource":
        """Resolve ``source`` to a concrete :class:`KeySource` subclass.

        Args:
            source: One of ``env:NAME``, ``file:/path``, ``keyring:SERVICE``,
                or ``prompt``.
            meta: Existing ``_meta`` row contents, when the DB is already
                encrypted. Carries ``kdf_salt`` / ``kdf_algo`` for the
                ``prompt`` path. ``None`` when initializing a new DB.

        Raises:
            KeySourceError: Unknown prefix, malformed source string,
                or a required component is missing (env var unset,
                file not found, keyring lib not installed, etc.).
        """
        if not source:
            raise KeySourceError("empty source string")

        if source == "prompt":
            salt: bytes | None = None
            if meta and "kdf_salt" in meta:
                salt = base64.b64decode(meta["kdf_salt"])
            return PromptKeySource(salt=salt)

        if ":" not in source:
            raise KeySourceError(f"unknown key source prefix: {source!r}")

        prefix, _, value = source.partition(":")

        if prefix == "env":
            if not value:
                raise KeySourceError("env source requires a variable name")
            return EnvKeySource(value)

        if prefix == "file":
            if not value:
                raise KeySourceError("file source requires a path")
            return FileKeySource(value)

        if prefix == "keyring":
            if not value:
                raise KeySourceError("keyring source requires a service name")
            # Guard against missing keyring library at parse time
            try:
                import keyring  # noqa: F401
            except ImportError as exc:
                raise KeySourceError(f"keyring library not installed: {exc}") from exc
            return KeyringKeySource(value)

        raise KeySourceError(f"unknown key source prefix: {prefix!r}")

    @abstractmethod
    def get_key(self) -> bytes:
        """Return the 32-byte URL-safe base64 Fernet key.

        Implementations may cache the resolved key for process lifetime.
        ``PromptKeySource`` MUST cache (re-prompting per row would
        defeat the build loop's atomicity).
        """

    @abstractmethod
    def fingerprint(self) -> str:
        """Return ``sha256(get_key())[:16]`` as a lowercase hex string.

        Used by ``_meta.key_fingerprint`` so :func:`rekey_db` can
        verify the supplied old key before rewriting cells. Calling
        this is allowed to invoke :meth:`get_key`.
        """


class EnvKeySource(KeySource):
    """``env:NAME`` — read the key from environment variable ``NAME``.

    The env var value MUST be a 32-byte URL-safe base64 Fernet key.
    The bridge does NOT run PBKDF2 here — see design doc §4 for why.
    """

    def __init__(self, var_name: str) -> None:
        self._var_name = var_name

    def get_key(self) -> bytes:
        value = os.environ.get(self._var_name)
        if value is None:
            raise KeySourceError(f"env var {self._var_name!r} not set")
        return value.encode("utf-8")

    def fingerprint(self) -> str:
        return hashlib.sha256(self.get_key()).hexdigest()[:_FINGERPRINT_PREFIX_LEN]


class FileKeySource(KeySource):
    """``file:/path/to/keyfile`` — read the key from the first line of a file.

    The file's first line MUST be a 32-byte URL-safe base64 Fernet key.
    Trailing newlines are stripped. The file's mode bits are NOT
    checked (Windows ACLs make POSIX mode comparison unreliable);
    documenting that users should restrict access is the caller's
    responsibility.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def get_key(self) -> bytes:
        from pathlib import Path

        p = Path(self._path)
        if not p.exists():
            raise KeySourceError(f"key file not found: {self._path}")
        with open(p, "rb") as f:
            first_line = f.readline()
        return first_line.rstrip(b"\r\n")

    def fingerprint(self) -> str:
        return hashlib.sha256(self.get_key()).hexdigest()[:_FINGERPRINT_PREFIX_LEN]


class KeyringKeySource(KeySource):
    """``keyring:SERVICE`` — fetch via the ``keyring`` lib.

    Looks up ``keyring.get_password(SERVICE, "ai-sw-bridge")``. The
    keyring lib is an optional dep; :meth:`parse` raises
    :class:`KeySourceError` if the import fails so the user gets a
    clear message instead of an ``ImportError`` traceback.
    """

    def __init__(self, service: str) -> None:
        self._service = service

    def get_key(self) -> bytes:
        try:
            import keyring
        except ImportError as exc:
            raise KeySourceError(f"keyring library not installed: {exc}") from exc
        value = keyring.get_password(self._service, "ai-sw-bridge")
        if value is None:
            raise KeySourceError(
                f"keyring returned no value for service={self._service!r}, "
                "user='ai-sw-bridge'"
            )
        return value.encode("utf-8")

    def fingerprint(self) -> str:
        return hashlib.sha256(self.get_key()).hexdigest()[:_FINGERPRINT_PREFIX_LEN]


class PromptKeySource(KeySource):
    """``prompt`` — interactive ``getpass`` prompt + PBKDF2 derivation.

    Derives the Fernet key from the user's passphrase via
    PBKDF2-HMAC-SHA256 with ``_KDF_ITERATIONS`` (600k) iterations and
    a 16-byte salt. The salt comes from ``_meta.kdf_salt`` on
    subsequent opens; on first encryption, a fresh salt is generated
    and persisted.

    The derived key is cached for process lifetime — re-prompting
    per row would defeat the build loop's atomicity.
    """

    def __init__(self, salt: bytes | None = None) -> None:
        self._salt = salt
        self._cached_key: bytes | None = None

    def get_key(self) -> bytes:
        if self._cached_key is not None:
            return self._cached_key

        # Generate salt if not provided (first-time encryption)
        if self._salt is None:
            self._salt = os.urandom(_KDF_SALT_BYTES)

        # Prompt for passphrase
        passphrase = getpass.getpass("Checkpoint encryption passphrase: ")

        # Derive key via PBKDF2-HMAC-SHA256
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            self._salt,
            _KDF_ITERATIONS,
            dklen=32,
        )

        # Base64-encode to get a Fernet-compatible key
        self._cached_key = base64.urlsafe_b64encode(derived)
        return self._cached_key

    def fingerprint(self) -> str:
        return hashlib.sha256(self.get_key()).hexdigest()[:_FINGERPRINT_PREFIX_LEN]

    @property
    def salt(self) -> bytes | None:
        """Return the salt used for KDF (needed for _meta persistence)."""
        return self._salt


# ---------------------------------------------------------------------------
# Cell wrap / unwrap
# ---------------------------------------------------------------------------


def encrypt_cell(plaintext: str, key: bytes) -> str:
    """Wrap *plaintext* with the current algorithm.

    Returns a string starting with ``fernet_v1:``. The body is the
    base64 Fernet token (which itself includes the version byte,
    timestamp, IV, ciphertext, and HMAC).

    Empty strings are wrapped normally — there is no special case.
    The caller decides whether to wrap a value (e.g.
    ``CheckpointStore`` wraps ``locals_snapshot`` and ``com_call_log``
    only).
    """
    token = Fernet(key).encrypt(plaintext.encode("utf-8"))
    return _CELL_PREFIX_V1 + token.decode("ascii")


def decrypt_cell(blob: str, key: bytes) -> str:
    """Unwrap one cell.

    Prefix dispatch:

    * Starts with ``fernet_v1:`` → unwrap with Fernet.
    * No recognized prefix → return as-is (plain cell from before
      encryption was enabled — the design doc §6 calls this out).
    * Unknown prefix → raise ``ValueError``.

    Wrong key surfaces as ``cryptography.fernet.InvalidToken``;
    callers wrap that in a higher-level error if desired.
    """
    if blob.startswith(_CELL_PREFIX_V1):
        token = blob[len(_CELL_PREFIX_V1) :]
        plaintext = Fernet(key).decrypt(token.encode("ascii"))
        return plaintext.decode("utf-8")

    # Check for unknown prefix patterns (anything like "xxx:...")
    if ":" in blob and blob.split(":", 1)[0].startswith("fernet_"):
        prefix = blob.split(":", 1)[0]
        raise ValueError(f"unknown encryption prefix: {prefix}:")

    # No recognized prefix — plain cell, return as-is
    return blob


def generate_key() -> bytes:
    """Return a fresh ``Fernet.generate_key()`` result.

    32 bytes of OS randomness, URL-safe base64 encoded to 44 chars.
    Exposed for the ``ai-sw-checkpoint genkey`` CLI.
    """
    return Fernet.generate_key()


def rekey_db(db_path: str, from_key: KeySource, to_key: KeySource) -> int:
    """Atomically re-encrypt all checkpoint cells with a new key.

    Args:
        db_path: Path to the SQLite checkpoint database.
        from_key: Current encryption key source (must match stored fingerprint).
        to_key: New encryption key source.

    Returns:
        Number of rows rekeyed.

    Raises:
        KeySourceError: If the from_key fingerprint doesn't match the stored one.
        sqlite3.Error: If a database error occurs (transaction is rolled back).
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        # Verify old key fingerprint matches stored
        meta_row = conn.execute("SELECT key_fingerprint FROM _meta LIMIT 1").fetchone()

        if meta_row is None:
            raise KeySourceError("DB is not encrypted; use migrate instead")

        stored_fp = meta_row[0]
        from_fp = from_key.fingerprint()
        if stored_fp != from_fp:
            raise KeySourceError(
                f"fingerprint mismatch: stored={stored_fp}, supplied={from_fp}"
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
            kdf_algo: str | None = None
            kdf_salt: str | None = None
            if isinstance(to_key, PromptKeySource):
                to_key.get_key()  # Trigger derivation
                kdf_algo = "pbkdf2-sha256-600000"
                if to_key.salt is not None:
                    kdf_salt = base64.b64encode(to_key.salt).decode("ascii")

            conn.execute(
                "UPDATE _meta SET key_fingerprint=?, kdf_algo=?, kdf_salt=?",
                (to_key.fingerprint(), kdf_algo, kdf_salt),
            )

            conn.commit()
            return len(rows)
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()
