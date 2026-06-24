"""Regression: undo_last_commit must tolerate a shared proposals dir.

The proposal store (`_proposals_dir`) is shared across every mutation family
(local-change / feature-add / assembly / drawing / properties). ``undo_last_commit``
reverts a *local-change* proposal by restoring its locals snapshot, but it scans
*all* committed records in the dir. Before the fix it bare-indexed
``rec["proposal_id"]`` / ``rec["var"]`` on every committed record, so a committed
proposal from another family (keyed by ``kind``/``spec``, with no ``var``) raised
``KeyError`` and crashed undo. Surfaced while gating v0.18 Batch M1; the bug itself
predates M1 (v0.14). The fix skips non-local-change records instead of crashing.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_sw_bridge import mutate
from ai_sw_bridge.mutate import ST_COMMITTED, _sw_undo_last_commit_impl


def _write(d: Path, name: str, rec: dict) -> None:
    (d / f"{name}.json").write_text(json.dumps(rec), encoding="utf-8")


def test_undo_skips_foreign_family_committed_records(tmp_path, monkeypatch):
    """A committed assembly/drawing/properties proposal in the shared store must
    not crash the local-change undo; undo selects the local-change record."""
    monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
    # Isolate from SW: deterministically reach the no_active_doc branch AFTER
    # candidate selection (proves the scan survived the foreign record).
    monkeypatch.setattr(mutate, "get_sw_app", lambda: object())
    monkeypatch.setattr(mutate, "get_active_doc", lambda sw: None)

    # Foreign-family committed record: kind/spec shape, no var, no proposal_id.
    _write(
        tmp_path,
        "foreign",
        {
            "kind": "assembly",
            "spec": {"x": 1},
            "state": ST_COMMITTED,
            "proposed_at": 1.0,
            "committed_at": 100.0,
        },
    )
    # Local-change committed record (the one undo should target — newer).
    _write(
        tmp_path,
        "abc123def456",
        {
            "proposal_id": "abc123def456",
            "var": "BOX_W",
            "state": ST_COMMITTED,
            "committed_at": 200.0,
            "old_expression": "20",
            "locals_path": str(tmp_path / "x_locals.txt"),
            "snapshot_text": '"BOX_W" = 20\n',
        },
    )

    res = _sw_undo_last_commit_impl()

    # No KeyError; the local-change record was selected over the foreign one.
    assert res["proposal_id"] == "abc123def456"
    assert res["var"] == "BOX_W"
    assert res["error"] == "no_active_doc"


def test_undo_with_only_foreign_commit_reports_nothing_to_undo(tmp_path, monkeypatch):
    """If the only committed records are foreign-family, undo reports cleanly
    ('nothing to undo') instead of crashing or falsely targeting them."""
    monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
    _write(
        tmp_path,
        "foreign",
        {
            "kind": "drawing",
            "spec": {},
            "state": ST_COMMITTED,
            "committed_at": 100.0,
        },
    )

    res = _sw_undo_last_commit_impl()

    assert res["ok"] is False
    assert res["error"] == "no committed proposal to undo"
