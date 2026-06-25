"""sw_session_health MCP tool — no-ledger, degraded (pending), and recovered."""

from __future__ import annotations

from ai_sw_bridge.checkpoint.transaction_store import TransactionStore
from ai_sw_bridge.mcp import _tool_health as H


class _FakeMCP:
    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _tool(monkeypatch, txn_db):
    monkeypatch.setattr(H, "_TXN_DB", txn_db)
    monkeypatch.setattr(H, "_find_sw_pids", lambda: [])  # deterministic: no seat
    m = _FakeMCP()
    H.register(m)
    return m.tools["sw_session_health"]


def test_no_ledger_is_healthy(monkeypatch, tmp_path):
    tool = _tool(monkeypatch, tmp_path / "_transactions.sqlite")
    out = tool()
    assert out["ok"] is True
    assert out["health"] == "healthy"
    assert out["transactions"]["ledger_present"] is False
    assert out["transactions"]["pending"] == 0
    assert out["last_recovery"] is None
    assert out["seat"]["instance_count"] == 0


def test_pending_transaction_is_degraded(monkeypatch, tmp_path):
    db = tmp_path / "_transactions.sqlite"
    store = TransactionStore(root=db.parent, db_name=db.name)
    store.insert_pending(doc_path="run.SLDPRT", intent_payload="[]", spec_hash="h")
    store.close()

    tool = _tool(monkeypatch, db)
    out = tool()
    assert out["health"] == "degraded"  # an unfinished transaction
    assert out["transactions"]["pending"] == 1
    assert out["transactions"]["ledger_present"] is True
    assert out["transactions"]["recent"][0]["status"] == "pending"


def test_recovered_transaction_surfaces_last_recovery(monkeypatch, tmp_path):
    db = tmp_path / "_transactions.sqlite"
    store = TransactionStore(root=db.parent, db_name=db.name)
    tid = store.insert_pending(
        doc_path="run.SLDPRT", intent_payload="[]", spec_hash="h"
    )
    store.mark_committed(
        tid,
        recovery_json='{"tier": 2, "replays": 1, "deaths": [{"phase": "save"}]}',
    )
    store.close()

    tool = _tool(monkeypatch, db)
    out = tool()
    assert out["health"] == "healthy"  # committed, nothing pending
    assert out["transactions"]["committed"] == 1
    lr = out["last_recovery"]
    assert lr["transaction_id"] == tid
    assert lr["tier"] == 2 and lr["replays"] == 1 and lr["deaths"] == 1
