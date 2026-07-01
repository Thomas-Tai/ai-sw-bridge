"""probe()'s failure message must be operator-legible (spec §8.4): it names
both likely causes — SW not open, and 32-bit/64-bit mismatch."""

from __future__ import annotations

import ai_sw_bridge.cli.probe as probe_mod


def test_probe_dispatch_failure_names_both_causes(monkeypatch) -> None:
    def boom():
        raise OSError("Class not registered")

    monkeypatch.setattr(probe_mod, "get_sw_app", boom)
    result = probe_mod.probe()

    assert result["ok"] is False
    msg = result["error"].lower()
    assert "solidworks" in msg and "running" in msg  # (a) is it open?
    assert "64-bit" in msg or "32-bit" in msg  # (b) bitness mismatch
