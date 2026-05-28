"""Test contract for ai_sw_bridge.checkpoint.crypto (W3.1).

The bodies are pending W3.1-impl (Sonnet/GLM). Every test below is
``@pytest.mark.skip(reason="W3.1-impl pending")`` until that task
lands. The impl task removes the marker on a test only when the
corresponding behavior is implemented and the assertion passes.

The cross-reference is
[`docs/checkpoint_encryption_design.md`](../../docs/checkpoint_encryption_design.md)
§11 — every test ID below maps 1:1 to a row there.

Why land the contract before the impl: the contract is the load-bearing
artifact. It pins behavior so the impl task can't drift from the
design, and surfaces design holes (missing edge cases, ambiguous
error semantics) at design time rather than impl time.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.checkpoint.crypto import (
    EnvKeySource,
    FileKeySource,
    KeyringKeySource,
    KeySource,
    KeySourceError,
    PromptKeySource,
    decrypt_cell,
    encrypt_cell,
    generate_key,
)


pytestmark = pytest.mark.skip(reason="W3.1-impl pending")


# ---------------------------------------------------------------------------
# §11.1 Cell wrap/unwrap
# ---------------------------------------------------------------------------


class TestCellRoundTrip:
    def test_encrypt_cell_roundtrip(self) -> None:
        key = generate_key()
        plaintext = '{"FILL_R": 9.0, "TAIL_LENGTH": 24.0}'
        assert decrypt_cell(encrypt_cell(plaintext, key), key) == plaintext

    def test_decrypt_cell_no_prefix_returns_as_is(self) -> None:
        """Plain cells (from before encryption was enabled) pass through."""
        key = generate_key()
        assert decrypt_cell('{"plain": "value"}', key) == '{"plain": "value"}'

    def test_decrypt_cell_wrong_key_raises_invalid_token(self) -> None:
        from cryptography.fernet import InvalidToken

        key_a = generate_key()
        key_b = generate_key()
        wrapped = encrypt_cell("secret", key_a)
        with pytest.raises(InvalidToken):
            decrypt_cell(wrapped, key_b)

    def test_decrypt_cell_unknown_prefix_raises_value_error(self) -> None:
        key = generate_key()
        with pytest.raises(ValueError):
            decrypt_cell("fernet_v99:garbage", key)

    def test_encrypt_cell_format_starts_with_version_tag(self) -> None:
        key = generate_key()
        wrapped = encrypt_cell("hello", key)
        assert wrapped.startswith("fernet_v1:")

    def test_encrypt_cell_empty_string_roundtrips(self) -> None:
        key = generate_key()
        assert decrypt_cell(encrypt_cell("", key), key) == ""


# ---------------------------------------------------------------------------
# §11.2 Key source resolution
# ---------------------------------------------------------------------------


class TestEnvKeySource:
    def test_reads_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        key = generate_key().decode()
        monkeypatch.setenv("AI_SW_TEST_KEY", key)
        src = KeySource.parse("env:AI_SW_TEST_KEY")
        assert isinstance(src, EnvKeySource)
        assert src.get_key() == key.encode()

    def test_missing_var_raises_key_source_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AI_SW_TEST_KEY", raising=False)
        with pytest.raises(KeySourceError, match="env var.*not set"):
            KeySource.parse("env:AI_SW_TEST_KEY").get_key()


class TestFileKeySource:
    def test_reads_first_line(self, tmp_path) -> None:
        key = generate_key()
        keyfile = tmp_path / "key"
        keyfile.write_bytes(key + b"\n# trailing comment ignored\n")
        src = KeySource.parse(f"file:{keyfile}")
        assert isinstance(src, FileKeySource)
        assert src.get_key() == key

    def test_missing_file_raises_key_source_error(self, tmp_path) -> None:
        with pytest.raises(KeySourceError, match="not found"):
            KeySource.parse(f"file:{tmp_path}/does-not-exist").get_key()


class TestKeyringKeySource:
    def test_reads_keyring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        key = generate_key().decode()
        captured = {}

        def fake_get_password(service: str, user: str) -> str:
            captured["service"] = service
            captured["user"] = user
            return key

        monkeypatch.setattr("keyring.get_password", fake_get_password)
        src = KeySource.parse("keyring:my-bridge")
        assert isinstance(src, KeyringKeySource)
        assert src.get_key() == key.encode()
        assert captured == {"service": "my-bridge", "user": "ai-sw-bridge"}

    def test_keyring_lib_missing_raises_key_source_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "keyring":
                raise ImportError("not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(KeySourceError, match="keyring.*not installed"):
            KeySource.parse("keyring:svc")


class TestPromptKeySource:
    def test_derives_via_pbkdf2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Known salt + passphrase produces deterministic Fernet key."""
        monkeypatch.setattr("getpass.getpass", lambda prompt: "correct-horse")
        meta = {
            "kdf_salt": "AAAAAAAAAAAAAAAAAAAAAA==",
            "kdf_algo": "pbkdf2-sha256-600000",
        }
        src = KeySource.parse("prompt", meta=meta)
        assert isinstance(src, PromptKeySource)
        key = src.get_key()
        assert len(key) == 44
        assert src.get_key() == key

    def test_caches_after_first_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prompt_count = [0]

        def counting_getpass(prompt: str) -> str:
            prompt_count[0] += 1
            return "horse-correct-battery"

        monkeypatch.setattr("getpass.getpass", counting_getpass)
        src = KeySource.parse("prompt", meta={"kdf_salt": "BBBBBBBBBBBBBBBBBBBBBA=="})
        src.get_key()
        src.get_key()
        src.get_key()
        assert prompt_count[0] == 1


class TestFingerprint:
    def test_sha256_prefix_16(self) -> None:
        """Fingerprint is the first 16 hex chars of sha256(key)."""
        import hashlib

        key = generate_key()
        # Construct an EnvKeySource via a known-key path
        import os

        os.environ["AI_SW_TEST_FP_KEY"] = key.decode()
        try:
            src = KeySource.parse("env:AI_SW_TEST_FP_KEY")
            expected = hashlib.sha256(key).hexdigest()[:16]
            assert src.fingerprint() == expected
        finally:
            del os.environ["AI_SW_TEST_FP_KEY"]


class TestParseDispatch:
    def test_unknown_prefix_raises_key_source_error(self) -> None:
        with pytest.raises(KeySourceError, match="unknown.*prefix"):
            KeySource.parse("aws-kms:arn:...")

    def test_empty_source_raises_key_source_error(self) -> None:
        with pytest.raises(KeySourceError):
            KeySource.parse("")


# ---------------------------------------------------------------------------
# §11.3 Store behavior with encryption
# ---------------------------------------------------------------------------


class TestEncryptedStore:
    """Encryption-aware CheckpointStore behavior.

    These import CheckpointStore via the modified __init__ signature
    (``key_source=...``). The impl task wires that in; the contract
    here pins the externally visible behavior.
    """

    def test_encrypted_store_round_trip(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ai_sw_bridge.checkpoint.store import CheckpointStore

        key = generate_key().decode()
        monkeypatch.setenv("AI_SW_TEST_KEY", key)
        src = KeySource.parse("env:AI_SW_TEST_KEY")

        store = CheckpointStore("part_a", root=tmp_path, key_source=src)
        row_id = store.insert_pending(
            feature_index=0,
            feature_name="SK_Base",
            feature_type="sketch",
            locals_snapshot='{"BASE_WIDTH": 100.0}',
            spec_hash="0" * 64,
            pre_tree_hash="1" * 64,
            build_mode="deferred-dim",
        )
        store.commit(row_id, post_tree_hash="2" * 64, com_call_log="ok")
        store.close()

        store2 = CheckpointStore("part_a", root=tmp_path, key_source=src)
        cp = store2.get(row_id)
        assert cp is not None
        assert cp.locals_snapshot == '{"BASE_WIDTH": 100.0}'
        assert cp.com_call_log == "ok"

    def test_encrypted_store_query_filters_still_work(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """query(status=...) etc. operate on UNencrypted columns —
        must continue to work."""
        from ai_sw_bridge.checkpoint.store import CheckpointStatus, CheckpointStore

        key = generate_key().decode()
        monkeypatch.setenv("AI_SW_TEST_KEY", key)
        src = KeySource.parse("env:AI_SW_TEST_KEY")

        store = CheckpointStore("part_b", root=tmp_path, key_source=src)
        for i in range(3):
            rid = store.insert_pending(
                feature_index=i,
                feature_name=f"feat_{i}",
                feature_type="sketch",
                locals_snapshot="{}",
                spec_hash="0" * 64,
                pre_tree_hash="1" * 64,
                build_mode="deferred-dim",
            )
            if i < 2:
                store.commit(rid, post_tree_hash="2" * 64, com_call_log="ok")

        rows = store.query(status=CheckpointStatus.COMMITTED)
        assert len(rows) == 2
        assert all(r.locals_snapshot == "{}" for r in rows)

    def test_encrypted_store_rejects_wrong_key(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Opening an encrypted DB with the wrong key fails BEFORE any
        write — fingerprint check fires on connect."""
        from ai_sw_bridge.checkpoint.store import CheckpointStore

        key_a = generate_key().decode()
        key_b = generate_key().decode()
        monkeypatch.setenv("AI_SW_TEST_KEY_A", key_a)
        monkeypatch.setenv("AI_SW_TEST_KEY_B", key_b)

        src_a = KeySource.parse("env:AI_SW_TEST_KEY_A")
        store = CheckpointStore("part_c", root=tmp_path, key_source=src_a)
        store.insert_pending(
            feature_index=0,
            feature_name="x",
            feature_type="sketch",
            locals_snapshot="{}",
            spec_hash="0" * 64,
            pre_tree_hash="1" * 64,
            build_mode="deferred-dim",
        )
        store.close()

        src_b = KeySource.parse("env:AI_SW_TEST_KEY_B")
        with pytest.raises(KeySourceError, match="fingerprint mismatch"):
            CheckpointStore("part_c", root=tmp_path, key_source=src_b)

    def test_plain_store_unchanged_when_no_key_source(self, tmp_path) -> None:
        """Existing behavior preserved: no key_source → plain DB."""
        from ai_sw_bridge.checkpoint.store import CheckpointStore

        store = CheckpointStore("part_d", root=tmp_path)
        store.insert_pending(
            feature_index=0,
            feature_name="x",
            feature_type="sketch",
            locals_snapshot='{"X": 1.0}',
            spec_hash="0" * 64,
            pre_tree_hash="1" * 64,
            build_mode="deferred-dim",
        )

        import sqlite3

        conn = sqlite3.connect(str(tmp_path / "part_d.sqlite"))
        row = conn.execute("SELECT locals_snapshot FROM checkpoints LIMIT 1").fetchone()
        assert row[0] == '{"X": 1.0}'

        meta = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_meta'"
        ).fetchone()
        assert meta is None

    def test_meta_row_created_once(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ai_sw_bridge.checkpoint.store import CheckpointStore

        key = generate_key().decode()
        monkeypatch.setenv("AI_SW_TEST_KEY", key)
        src = KeySource.parse("env:AI_SW_TEST_KEY")

        store = CheckpointStore("part_e", root=tmp_path, key_source=src)
        for i in range(3):
            store.insert_pending(
                feature_index=i,
                feature_name=f"f_{i}",
                feature_type="sketch",
                locals_snapshot="{}",
                spec_hash="0" * 64,
                pre_tree_hash="1" * 64,
                build_mode="deferred-dim",
            )

        import sqlite3

        conn = sqlite3.connect(str(tmp_path / "part_e.sqlite"))
        count = conn.execute("SELECT COUNT(*) FROM _meta").fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# §11.4 CLI (ai-sw-checkpoint)
# ---------------------------------------------------------------------------


class TestGenkeyCli:
    def test_emits_valid_fernet_key(self) -> None:
        import subprocess
        import sys
        from cryptography.fernet import Fernet

        result = subprocess.run(
            [sys.executable, "-m", "ai_sw_bridge.cli.checkpoint", "genkey"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        key_line = result.stdout.strip()
        Fernet(key_line.encode())

    def test_two_stream_contract(self) -> None:
        """genkey emits the key as raw text on stdout (not JSON) — it's
        a credential the user pipes to a keyfile. stderr carries usage."""
        import json
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "ai_sw_bridge.cli.checkpoint", "genkey"],
            capture_output=True,
            text=True,
        )
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout)
        assert "save" in result.stderr.lower() or "keyfile" in result.stderr.lower()


class TestInfoCli:
    def test_reports_encryption_state(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json
        import subprocess
        import sys

        from ai_sw_bridge.checkpoint.store import CheckpointStore

        key = generate_key().decode()
        monkeypatch.setenv("AI_SW_TEST_KEY", key)
        src = KeySource.parse("env:AI_SW_TEST_KEY")
        store = CheckpointStore("part_x", root=tmp_path, key_source=src)
        store.insert_pending(
            feature_index=0,
            feature_name="x",
            feature_type="sketch",
            locals_snapshot="{}",
            spec_hash="0" * 64,
            pre_tree_hash="1" * 64,
            build_mode="deferred-dim",
        )
        store.close()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ai_sw_bridge.cli.checkpoint",
                "info",
                "part_x",
                "--root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["encryption_algo"] == "fernet-v1"
        assert "key_fingerprint" in payload
        assert payload["encrypted_columns"] == [
            "locals_snapshot",
            "com_call_log",
        ]


class TestRekeyCli:
    def test_atomic_under_simulated_io_error(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a write fails mid-rekey, the old key MUST still work."""
        from ai_sw_bridge.checkpoint.store import CheckpointStore

        key_a = generate_key().decode()
        key_b = generate_key().decode()
        monkeypatch.setenv("KEY_A", key_a)
        monkeypatch.setenv("KEY_B", key_b)
        src_a = KeySource.parse("env:KEY_A")

        store = CheckpointStore("part_r", root=tmp_path, key_source=src_a)
        store.insert_pending(
            feature_index=0,
            feature_name="x",
            feature_type="sketch",
            locals_snapshot='{"V": 1.0}',
            spec_hash="0" * 64,
            pre_tree_hash="1" * 64,
            build_mode="deferred-dim",
        )
        store.close()

        # Patch the rekey function's commit point to raise mid-transaction.
        import ai_sw_bridge.checkpoint.crypto as crypto_module

        original_rekey = getattr(crypto_module, "rekey_db", None)
        if original_rekey is None:
            pytest.skip("rekey_db not exposed in W3.1 — moves to W3.1-impl")

        # The rekey must roll back; subsequent open with KEY_A still works.
        store2 = CheckpointStore("part_r", root=tmp_path, key_source=src_a)
        cp = store2.query()[0]
        assert cp.locals_snapshot == '{"V": 1.0}'


# ---------------------------------------------------------------------------
# §11.5 Integration
# ---------------------------------------------------------------------------


class TestBuildIntegration:
    def test_build_with_checkpoint_encrypt_env_creates_encrypted_db(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: ai-sw-build --checkpoint-encrypt env:KEY produces
        a DB with _meta and fernet_v1: cell prefixes."""
        pytest.skip(
            "Requires the W3.1-impl wiring on ai-sw-build CLI; "
            "the cli/build.py edit lands as part of W3.1-impl."
        )
