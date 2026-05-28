"""End-to-end encrypted-checkpoint round-trip test.

Builds a part with ``--checkpoint-encrypt``, reads back via the MCP
checkpoint tools, and verifies:

* ``sw_checkpoint_info`` reports ``encrypted: True`` + ``fernet-v1``
* ``sw_history_part`` returns rows whose ``locals_snapshot`` field is
  ``fernet_v1:``-wrapped ciphertext (NOT plaintext)
* dropping the key from the environment does not unwrap the
  ciphertext — the listing still returns the encrypted bytes

Codifies Wave 5 Phase 4 from the audit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.solidworks_only


_ENV_VAR = "AI_SW_E2E_KEY"


def test_e2e_encrypted_checkpoint_round_trip(
    live_tools, minimal_cylinder_spec_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build with key in env -> info reports encrypted -> history is ciphertext."""
    from ai_sw_bridge.checkpoint.crypto import generate_key

    key = generate_key().decode()
    monkeypatch.setenv(_ENV_VAR, key)

    # Clean any prior DB so we know the test built the one we read.
    db_path = Path(".checkpoints") / "MinimalCylinder.sqlite"
    if db_path.exists():
        db_path.unlink()

    # Encrypted build
    build_result = live_tools["sw_build"].fn(
        spec_path=str(minimal_cylinder_spec_path),
        mode="no_dim",
        checkpoint=True,
        checkpoint_encrypt=f"env:{_ENV_VAR}",
    )
    assert build_result["ok"] is True, f"build failed: {build_result.get('error')}"
    assert build_result.get("checkpoint_encrypt") is True

    # sw_checkpoint_info -> encrypted + key fingerprint
    info = live_tools["sw_checkpoint_info"].fn(part_name="MinimalCylinder")
    assert info["ok"] is True
    assert info["encrypted"] is True
    assert info["encryption_algo"] == "fernet-v1"
    assert isinstance(info["key_fingerprint"], str) and info["key_fingerprint"]
    assert set(info["encrypted_columns"]) == {"locals_snapshot", "com_call_log"}

    # sw_history_part -> ciphertext
    hist = live_tools["sw_history_part"].fn(part_name="MinimalCylinder")
    assert hist["count"] > 0
    for cp in hist["checkpoints"]:
        ls = cp.get("locals_snapshot")
        if ls is None or ls == "":
            # Pending rows pre-commit may have null locals; that's fine.
            continue
        assert isinstance(
            ls, str
        ), f"locals_snapshot must be a string, got {type(ls).__name__}"
        assert ls.startswith("fernet_v1:"), (
            f"locals_snapshot not encrypted! id={cp['id']}, value starts with "
            f"{ls[:30]!r}"
        )


def test_e2e_history_part_without_key_still_returns_ciphertext(
    live_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even with key dropped from env, the listing call returns wrapped ciphertext.

    Pre-condition: a prior test built MinimalCylinder with encryption,
    so .checkpoints/MinimalCylinder.sqlite exists and is encrypted.
    """
    db_path = Path(".checkpoints") / "MinimalCylinder.sqlite"
    if not db_path.exists():
        pytest.skip(
            "no encrypted checkpoint DB present — run "
            "test_e2e_encrypted_checkpoint_round_trip first"
        )

    monkeypatch.delenv(_ENV_VAR, raising=False)

    hist = live_tools["sw_history_part"].fn(part_name="MinimalCylinder")
    # Listing doesn't require the key (per W3.1 design — only decryption
    # at field-read time needs the key). So the call should succeed and
    # return the ciphertext-wrapped values.
    assert hist["count"] > 0
    for cp in hist["checkpoints"]:
        ls = cp.get("locals_snapshot")
        if ls is None or ls == "":
            continue
        assert isinstance(ls, str)
        assert ls.startswith(
            "fernet_v1:"
        ), f"ciphertext not preserved when key absent: {ls[:30]!r}"
