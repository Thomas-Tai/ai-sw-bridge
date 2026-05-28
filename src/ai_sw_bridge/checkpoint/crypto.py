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

from abc import ABC, abstractmethod
from typing import Any

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
        raise NotImplementedError("W3.1-impl pending")

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
        raise NotImplementedError("W3.1-impl pending")

    def fingerprint(self) -> str:
        raise NotImplementedError("W3.1-impl pending")


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
        raise NotImplementedError("W3.1-impl pending")

    def fingerprint(self) -> str:
        raise NotImplementedError("W3.1-impl pending")


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
        raise NotImplementedError("W3.1-impl pending")

    def fingerprint(self) -> str:
        raise NotImplementedError("W3.1-impl pending")


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
        raise NotImplementedError("W3.1-impl pending")

    def fingerprint(self) -> str:
        raise NotImplementedError("W3.1-impl pending")


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
    raise NotImplementedError("W3.1-impl pending")


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
    raise NotImplementedError("W3.1-impl pending")


def generate_key() -> bytes:
    """Return a fresh ``Fernet.generate_key()`` result.

    32 bytes of OS randomness, URL-safe base64 encoded to 44 chars.
    Exposed for the ``ai-sw-checkpoint genkey`` CLI.
    """
    raise NotImplementedError("W3.1-impl pending")
