"""Offline tests for the supervised-by-default batch facade (Wave 2, RES-1).

``client.mutate.batch()`` runs inside the ``SupervisedSession`` crash-recovery
envelope by default; ``supervised=False`` is the bare-engine escape hatch. These
tests pin the WIRING — that the envelope is constructed, engaged, writes the
durable ledger, and reaps on teardown — using fakes (no live seat, no
``tasklist``). The envelope's recovery *behavior* is covered by
``tests/resilience/`` and proven live by the ``destructive_sw`` lane.
"""

from __future__ import annotations

from ai_sw_bridge.client import SolidWorksClient


class _FakeSeat:
    """Stand-in for ExecutorSeatController — no tasklist, no real process."""

    def __init__(self, *_a, **_k) -> None:
        self.reaped = 0

    @property
    def pid(self) -> int | None:
        return None

    def is_alive(self) -> bool:
        return True

    def respawn(self) -> None:  # pragma: no cover - not hit on a clean run
        pass

    def reap_orphans(self) -> list[int]:
        self.reaped += 1
        return []


def _spy(record: list):
    def run(doc_path, proposals, strict=False):
        record.append({"doc_path": doc_path, "proposals": proposals, "strict": strict})
        return {"ok": True, "committed": [], "doc_path": doc_path}

    return run


def test_supervised_by_default_engages_envelope(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # keep the durable ledger inside the tmp dir
    doc = tmp_path / "part.sldprt"
    doc.write_bytes(b"FAKE")  # FileSnapshotter copies it; content is irrelevant
    calls: list = []
    monkeypatch.setattr("ai_sw_bridge.resilience.ExecutorSeatController", _FakeSeat)
    monkeypatch.setattr("ai_sw_bridge.client._sw_batch_feature_add_impl", _spy(calls))

    manifest = SolidWorksClient().mutate.batch(
        str(doc), [{"feature": {"type": "x"}, "target": {}}]
    )

    assert calls, "supervised path must invoke the batch engine"
    assert manifest["ok"] is True
    assert "recovery" in manifest, "the envelope must annotate the manifest"
    # the durable ledger received the transaction (PENDING -> COMMITTED)
    assert (tmp_path / ".checkpoints" / "_transactions.sqlite").exists()


def test_supervised_false_uses_bare_engine(monkeypatch):
    calls: list = []
    monkeypatch.setattr("ai_sw_bridge.client._sw_batch_feature_add_impl", _spy(calls))
    manifest = SolidWorksClient().mutate.batch(
        "p.sldprt", [{"feature": {"type": "x"}, "target": {}}], supervised=False
    )
    assert calls and calls[0]["strict"] is False
    assert "recovery" not in manifest, "supervised=False must skip the envelope"


def test_supervised_falls_back_when_resilience_unavailable(monkeypatch):
    calls: list = []
    monkeypatch.setattr("ai_sw_bridge.client._sw_batch_feature_add_impl", _spy(calls))

    def _boom(*_a, **_k):
        raise RuntimeError("resilience unavailable")

    monkeypatch.setattr("ai_sw_bridge.resilience.ExecutorSeatController", _boom)
    manifest = SolidWorksClient().mutate.batch(
        "p.sldprt", [{"feature": {"type": "x"}, "target": {}}]
    )
    assert calls, "fallback must still run the bare engine"
    assert "recovery" not in manifest


def test_teardown_reaps_orphans(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    doc = tmp_path / "part.sldprt"
    doc.write_bytes(b"FAKE")
    seat = _FakeSeat()
    monkeypatch.setattr(
        "ai_sw_bridge.resilience.ExecutorSeatController", lambda *_a, **_k: seat
    )
    monkeypatch.setattr("ai_sw_bridge.client._sw_batch_feature_add_impl", _spy([]))
    SolidWorksClient().mutate.batch(str(doc), [{"feature": {}, "target": {}}])
    assert seat.reaped == 1, "teardown must reap orphans exactly once"
