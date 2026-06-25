"""Unit tests for the batch-transaction ledger (TransactionStore)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.checkpoint import TransactionStatus, TransactionStore


def _store(tmp_path):
    return TransactionStore(root=tmp_path)


def test_insert_pending_returns_id_and_row_is_pending(tmp_path):
    s = _store(tmp_path)
    tid = s.insert_pending(
        doc_path="C:/p/run.SLDPRT", intent_payload='[{"f":1}]', spec_hash="abc"
    )
    assert isinstance(tid, str) and tid
    row = s.get(tid)
    assert row is not None
    assert row.status is TransactionStatus.PENDING
    assert row.doc_path == "C:/p/run.SLDPRT"
    assert row.intent_payload == '[{"f":1}]'
    assert row.spec_hash == "abc"
    assert row.created_at == row.updated_at  # untouched since insert


def test_mark_committed_transitions_and_bumps_updated_at(tmp_path):
    s = _store(tmp_path)
    tid = s.insert_pending(
        doc_path="p", intent_payload="[]", spec_hash="h", now="2026-01-01T00:00:00"
    )
    s.mark_committed(tid, now="2026-01-01T00:00:09")
    row = s.get(tid)
    assert row.status is TransactionStatus.COMMITTED
    assert row.updated_at == "2026-01-01T00:00:09"
    assert row.created_at == "2026-01-01T00:00:00"  # creation stamp preserved


def test_mark_failed_transitions(tmp_path):
    s = _store(tmp_path)
    tid = s.insert_pending(doc_path="p", intent_payload="[]", spec_hash="h")
    s.mark_failed(tid)
    assert s.get(tid).status is TransactionStatus.FAILED


def test_double_commit_raises_lookup_error(tmp_path):
    s = _store(tmp_path)
    tid = s.insert_pending(doc_path="p", intent_payload="[]", spec_hash="h")
    s.mark_committed(tid)
    with pytest.raises(LookupError):
        s.mark_committed(tid)  # no longer pending


def test_get_pending_transactions_is_the_resume_queue(tmp_path):
    s = _store(tmp_path)
    a = s.insert_pending(
        doc_path="a", intent_payload="[]", spec_hash="h", now="2026-01-01T00:00:01"
    )
    b = s.insert_pending(
        doc_path="b", intent_payload="[]", spec_hash="h", now="2026-01-01T00:00:02"
    )
    c = s.insert_pending(
        doc_path="c", intent_payload="[]", spec_hash="h", now="2026-01-01T00:00:03"
    )
    s.mark_committed(b)  # b leaves the queue
    pending = s.get_pending_transactions()
    assert [t.id for t in pending] == [a, c]  # PENDING only, created-order


def test_durable_across_reopen(tmp_path):
    """A pending row survives a store close+reopen — the host-crash anchor."""
    s = _store(tmp_path)
    tid = s.insert_pending(doc_path="p", intent_payload='[{"x":1}]', spec_hash="h")
    s.close()

    s2 = _store(tmp_path)  # simulates a fresh process attaching to the same DB
    row = s2.get(tid)
    assert row is not None
    assert row.status is TransactionStatus.PENDING
    assert row.intent_payload == '[{"x":1}]'
    assert [t.id for t in s2.get_pending_transactions()] == [tid]


def test_get_unknown_id_returns_none(tmp_path):
    assert _store(tmp_path).get("does-not-exist") is None
