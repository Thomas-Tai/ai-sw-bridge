"""``sw_batch_execute`` — the elicitation-gated batch COMMIT MCP tool.

This is the single-surface upgrade over the v1.2.0 ``ai-sw-batch`` CLI: the
human ``[y/N]`` approval of an irreversible multi-feature batch is collected
*inside the agent's chat surface* (e.g. Claude Desktop) via the MCP elicitation
protocol, instead of forcing a context-switch to a terminal.

Flow::

    1. Capability gate  — if the client doesn't advertise elicitation, refuse
                          and point the operator at sw_batch_plan + the CLI.
    2. PLAN (dry_run)   — run the batch on the live kernel, save NOTHING. Every
                          B-rep is genuinely validated; the doc is closed
                          without saving (engine dry_run mode).
    3. ELICIT           — hand the human-readable plan to the client and await
                          an explicit approve/decline, bounded by a timeout.
    4. COMMIT (live)    — IFF the human accepted AND ticked approve, fire the
                          irreversible batch(dry_run=False).
    5. MANIFEST         — return the execution (or abort) manifest.

Why this tool is ``async`` and NOT ``@com_tool``-decorated (the architectural
crux): ``@com_tool`` submits the ENTIRE tool body to the ComExecutor STA
worker, which has no asyncio event loop — so it cannot ``await ctx.elicit(...)``
(a JSON-RPC round-trip over stdio that lives on the loop). Instead this tool is
a coroutine that dispatches the two COM phases to ``run_on_executor(...)``
individually and keeps the ``await`` on the loop in between. That split is also
what makes a human walking away from the keyboard SAFE: between PLAN and COMMIT
the STA thread is idle and NO document is held open (the dry_run plan closes its
doc in ``finally``; the commit reopens fresh), so the ``asyncio.wait_for``
timeout can abort with zero SW state pinned and zero COM mutation.

The ``ai-sw-batch`` CLI is NOT replaced — it remains the bulletproof headless /
non-interactive fallback, and is exactly what this tool's capability-gate
degradation points to when the client can't elicit.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import mcp.types as types
from mcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from mcp.server.fastmcp import Context
from pydantic import BaseModel

from ..mutate import _sw_batch_feature_add_impl
from .tools import run_on_executor

logger = logging.getLogger(__name__)


# Bound the human-think window. The wait is on the asyncio loop, not the STA
# thread — so this is purely "how long do we keep the request open before
# treating silence as a decline"; it pins NO SolidWorks state. 300s mirrors a
# generous coffee-break before the agent gives up and the operator must re-run.
ELICIT_TIMEOUT_S = 300.0


class _BatchApproval(BaseModel):
    """Primitive-only elicitation schema (the SDK rejects nested models).

    A single boolean: did the human approve the irreversible commit? The
    elicitation message carries the full plan for review; this is just the
    gate.
    """

    approve: bool


def _render_plan(file_path: str, plan: dict[str, Any]) -> str:
    """Human-readable approval prompt from a dry-run manifest."""
    committed = plan.get("committed") or []
    lines = [
        f"Approve committing {len(committed)} feature(s) to:",
        f"    {file_path}",
        "",
        "The dry-run validated every feature on the live kernel. Approving "
        "WRITES them to disk (irreversible within this SolidWorks session):",
        "",
    ]
    for entry in committed:
        if isinstance(entry, dict):
            idx = entry.get("index")
            kind = entry.get("kind")
            note = entry.get("note")
            tail = f" — {note}" if note else ""
            lines.append(f"    [{idx}] {kind}{tail}")
        else:  # pragma: no cover — defensive
            lines.append(f"    {entry}")
    lines += ["", "Set approve=true to commit, or decline to abort."]
    return "\n".join(lines)


def register(mcp: Any) -> None:
    """Register the ``sw_batch_execute`` tool against *mcp*.

    Deliberately NOT ``@com_tool``-wrapped — see the module docstring and the
    documented exemption in ``test_all_com_tools_have_decorator``. COM safety
    is preserved by routing each COM phase through ``run_on_executor`` (the
    same STA-dispatch core ``@com_tool`` uses).
    """

    @mcp.tool()
    async def sw_batch_execute(
        file_path: str, proposals: list, ctx: Context
    ) -> dict[str, Any]:
        """PLAN, then elicit human approval IN-CHAT, then COMMIT a batch.

        Validates a multi-feature batch against an existing part (dry-run, no
        disk write), presents the plan to the human via the MCP elicitation
        prompt, and — only if the human explicitly approves — fires the
        irreversible commit. The human ``[y/N]`` gate of the ``ai-sw-batch``
        CLI, moved into the agent's chat surface.

        If the connected client does not support elicitation, this tool
        refuses and directs you to validate with ``sw_batch_plan`` and commit
        via the human-gated ``ai-sw-batch`` CLI verb instead.

        Args:
            file_path: Filesystem path to the existing .sldprt.
            proposals: Ordered list of ``{"feature": {...}, "target": {...}}``
                feature-add proposals (``feature["type"]`` names a registry
                kind).

        Returns:
            The execution manifest on approval (``doc_saved=True`` on success),
            or an abort manifest (``aborted=True``, ``doc_saved=False``) on any
            non-approval path: client lacks elicitation, plan failed to
            validate, human declined/cancelled, or the prompt timed out.
        """
        proposals = list(proposals or [])

        # --- 1. Capability gate -------------------------------------------
        # Elicitation is an OPTIONAL client capability. If the client doesn't
        # advertise it, ctx.elicit() would error — so we degrade gracefully to
        # the read-only plan tool + the CLI commit verb.
        supports_elicit = ctx.session.check_client_capability(
            types.ClientCapabilities(elicitation=types.ElicitationCapability())
        )
        if not supports_elicit:
            return {
                "ok": False,
                "aborted": True,
                "reason": "elicitation_unsupported",
                "doc_saved": False,
                "next_step": (
                    "This MCP client does not support elicitation, so the "
                    "in-chat approval prompt cannot be shown. Validate the "
                    "batch with the read-only `sw_batch_plan` tool, then commit "
                    "it via the human-gated `ai-sw-batch` CLI verb."
                ),
            }

        # --- 2. PLAN (dry-run on the STA thread) --------------------------
        # Opens the doc, runs every handler on the live kernel, saves nothing,
        # closes (discarding changes) in its finally. The STA thread is then
        # idle and NO doc is held open across the elicitation wait below.
        plan = run_on_executor(
            _sw_batch_feature_add_impl,
            doc_path=file_path,
            proposals=proposals,
            strict=False,
            dry_run=True,
        )
        if not plan.get("ok"):
            # The plan didn't fully validate — nothing to approve. Return the
            # fault manifest verbatim so the agent can re-edit the bad proposal.
            plan["aborted"] = True
            plan["reason"] = "plan_invalid"
            plan["doc_saved"] = False
            plan["next_step"] = (
                "The dry-run plan did not fully validate; nothing was "
                "committed. Inspect `fault`, fix the offending proposal, and "
                "re-run sw_batch_execute."
            )
            return plan

        # --- 3. ELICIT approval (on the asyncio event loop) ---------------
        # Bounded by wait_for: a human who walks away cannot deadlock the
        # workflow. On timeout/decline/cancel the commit below NEVER fires.
        message = _render_plan(file_path, plan)
        try:
            result = await asyncio.wait_for(
                ctx.elicit(message=message, schema=_BatchApproval),
                timeout=ELICIT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "sw_batch_execute: elicitation timed out after %ss; "
                "aborting (no commit, doc untouched)",
                ELICIT_TIMEOUT_S,
            )
            return {
                **plan,
                "aborted": True,
                "reason": "elicit_timeout",
                "doc_saved": False,
                "next_step": (
                    f"No approval within {int(ELICIT_TIMEOUT_S)}s — the batch "
                    "was NOT committed. Re-run sw_batch_execute to retry."
                ),
            }

        # --- 4. ROUTE on the elicitation union ----------------------------
        # Only an explicit accept WITH approve=True crosses to the commit. The
        # subtle accept-form-but-approve=False case is a decline, NOT a commit.
        if isinstance(result, AcceptedElicitation) and result.data.approve:
            # --- 5. COMMIT (irreversible, on the STA thread) --------------
            commit = run_on_executor(
                _sw_batch_feature_add_impl,
                doc_path=file_path,
                proposals=proposals,
                strict=False,
                dry_run=False,
            )
            commit["mcp_mode"] = "elicited_commit"
            commit["approved"] = True
            return commit

        if isinstance(result, AcceptedElicitation):
            reason = "declined_in_form"  # accepted the prompt, ticked approve=False
        elif isinstance(result, DeclinedElicitation):
            reason = "declined"
        elif isinstance(result, CancelledElicitation):
            reason = "cancelled"
        else:  # pragma: no cover — the union is exhaustive
            reason = "unknown"

        return {
            **plan,
            "aborted": True,
            "reason": reason,
            "doc_saved": False,
            "next_step": (
                "The batch was NOT committed (human did not approve). Re-run "
                "sw_batch_execute to present the plan again."
            ),
        }
