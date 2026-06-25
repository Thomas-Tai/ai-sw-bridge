"""Session-health MCP tool (resilience observability).

``sw_session_health`` is a READ-ONLY view of the supervised-session layer so the
agent can tell whether it is operating in a healthy, degraded, or
recently-recovered environment before it acts. It reads two durable, COM-free
sources:

* **Seat presence** — the count + PIDs of live ``SLDWORKS.exe`` processes
  (PID-level; this is presence, not a COM responsiveness ping — labelled as
  such so the agent does not over-trust it).
* **Transaction ledger** — the durable :class:`TransactionStore`
  (``.checkpoints/_transactions.sqlite``): pending / committed / failed counts,
  the most-recent transactions, and the LAST recovery summary (tier + replays)
  persisted by :class:`SupervisedSession`.

A lingering ``pending`` transaction is the degraded signal — a batch that began
but never reached a terminal commit (a crash whose recovery did not complete);
it is the durable resume anchor. No COM, no fabricated counters — every field is
read straight from disk / the process table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..checkpoint.transaction_store import TransactionStore
from ..resilience.session import _find_sw_pids

# The default ledger location (TransactionStore's default root + db_name).
_TXN_DB = Path(".checkpoints") / "_transactions.sqlite"


def _txn_brief(t: Any) -> dict[str, Any]:
    return {
        "id": t.id,
        "status": t.status.value,
        "doc": t.doc_path,
        "updated_at": t.updated_at,
    }


def register(mcp: Any) -> None:
    """Register the session-health tool against *mcp*."""

    @mcp.tool()
    def sw_session_health() -> dict[str, Any]:
        """Read-only health of the supervised-session layer.

        Returns seat presence (live SLDWORKS PIDs), the transaction-ledger audit
        (pending / committed / failed + recent), the last recovery summary
        (tier + replays), and an overall ``health`` verdict. Consult this to
        learn whether the environment is degraded (a pending/unrecovered
        transaction) or recently recovered before issuing more work.
        """
        pids = _find_sw_pids()
        seat = {
            "instance_count": len(pids),
            "pids": pids,
            "liveness": "pid-present" if pids else "none",
            "note": "PID-level presence, not a COM responsiveness ping",
        }

        ledger_present = _TXN_DB.exists()
        counts = {"pending": 0, "committed": 0, "failed": 0}
        recent: list[dict[str, Any]] = []
        last_recovery: dict[str, Any] | None = None
        if ledger_present:
            store = TransactionStore(root=_TXN_DB.parent, db_name=_TXN_DB.name)
            try:
                counts = store.status_counts()
                recent = [_txn_brief(t) for t in store.recent(5)]
                lr = store.last_recovered()
                if lr is not None and lr.recovery_json:
                    try:
                        rec = json.loads(lr.recovery_json)
                    except (ValueError, TypeError):
                        rec = {}
                    last_recovery = {
                        "transaction_id": lr.id,
                        "tier": rec.get("tier"),
                        "replays": rec.get("replays"),
                        "deaths": len(rec.get("deaths", [])),
                    }
            finally:
                store.close()

        if counts["pending"] > 0:
            health = "degraded"  # an unfinished transaction — resume pending
        elif counts["failed"] > 0:
            health = "attention"  # a transaction terminally failed
        else:
            health = "healthy"

        return {
            "ok": True,
            "health": health,
            "seat": seat,
            "transactions": {
                "ledger_present": ledger_present,
                **counts,
                "recent": recent,
            },
            "last_recovery": last_recovery,
        }
