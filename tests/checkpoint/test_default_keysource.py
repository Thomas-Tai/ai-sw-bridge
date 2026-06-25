"""Offline tests for SEC-1 — default checkpoint-encryption key resolution.

`default_key_source` is the encrypt-by-default resolver wired into
`ai-sw-build --checkpoint` (write) and `ai-sw-history` (read). The Fernet
encrypt/decrypt round-trip itself is covered by test_crypto_contract.py; these
tests pin the resolution order, the auto-generate + gitignore + loud-warning UX,
and that the resolved key is a valid Fernet key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

import ai_sw_bridge.checkpoint.crypto as crypto
from ai_sw_bridge.checkpoint.crypto import default_key_source, generate_key


def test_env_key_wins_and_no_file_created(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    key = generate_key().decode()
    monkeypatch.setenv("AI_SW_CHECKPOINT_KEY", key)
    ks = default_key_source(create=True)
    assert ks is not None
    assert ks.get_key() == key.encode()
    assert not (tmp_path / ".sw_agent_key").exists()  # env wins; no keyfile


def test_autogen_writes_key_gitignores_and_warns(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AI_SW_CHECKPOINT_KEY", raising=False)
    monkeypatch.setattr(crypto, "_keyfile_warned", {"done": False})

    ks = default_key_source(create=True)

    assert ks is not None
    kf = tmp_path / ".sw_agent_key"
    assert kf.exists() and kf.read_bytes()
    Fernet(ks.get_key())  # the generated key is a valid Fernet key
    assert ".sw_agent_key" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "ENCRYPTED by default" in capsys.readouterr().err


def test_create_false_returns_none_without_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AI_SW_CHECKPOINT_KEY", raising=False)
    assert default_key_source(create=False) is None  # plaintext read path


def test_create_false_reads_existing_keyfile(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AI_SW_CHECKPOINT_KEY", raising=False)
    (tmp_path / ".sw_agent_key").write_bytes(generate_key())
    ks = default_key_source(create=False)
    assert ks is not None
    Fernet(ks.get_key())  # an existing keyfile resolves to a valid Fernet key
