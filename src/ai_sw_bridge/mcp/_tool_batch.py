"""Batch-plan MCP tool (the §6.5-aligned write-PLANNING surface).

Exposes ``sw_batch_plan`` — a READ-ONLY validation pass over a multi-feature
batch proposal. It runs the batch transaction in PLAN-ONLY (dry-run) mode: every
proposal's handler executes on the live kernel (so each B-rep is genuinely
validated), but the document is NEVER saved to disk — the open-doc context is
closed-without-save, discarding all in-memory changes.

This is the autonomous-safe half of the §6.5 boundary (``docs/mcp_server_design.md``):
the agent may PLAN and VALIDATE over MCP; the irreversible commit stays a
human-gated CLI action. The returned recovery manifest (committed trail / singular
fault / skipped resume-queue) is the exact artifact a human reviews before
approving the real commit on the CLI.

``sw_batch_plan`` is COM-touching (it opens the doc and fires handlers on the
kernel), so it MUST be ``@com_tool``-wrapped to run on the ComExecutor STA thread.
"""

from __future__ import annotations

from typing import Any

from ..mutate import _sw_batch_feature_add_impl
from .tools import com_tool


def register(mcp: Any) -> None:
    """Register the ``sw_batch_plan`` tool against *mcp*."""

    @mcp.tool()
    @com_tool
    def sw_batch_plan(file_path: str, proposals: list) -> dict[str, Any]:
        """VALIDATE (do NOT commit) a multi-feature batch against an existing part.

        This is a READ-ONLY validation pass. Every proposal's feature is applied
        to the live kernel to prove it materializes, then ALL changes are
        DISCARDED — the document on disk is never modified. Use it to confirm an
        agent-generated multi-feature edit is sound BEFORE a human commits it.

        To actually execute the batch (irreversible disk write), a human must run
        the commit through the CLI ``ai-sw-mutate`` lane after reviewing the
        manifest this tool returns — the MCP surface deliberately cannot commit
        (the human-in-the-loop safety gate, design doc §6.5).

        Args:
            file_path: Filesystem path to the existing .sldprt to validate against.
            proposals: Ordered list of ``{"feature": {...}, "target": {...}}``
                feature-add proposals (``feature["type"]`` names a registry kind).

        Returns:
            The batch recovery manifest with ``dry_run=True`` and
            ``doc_saved=False`` guaranteed. Keys: ``ok`` (every feature would
            commit), ``committed`` (the success trail), ``fault`` (the singular
            terminal fault, with the offending proposal echoed), ``skipped`` (the
            resume queue), plus ``total``/``attempted``/``committed_count``/
            ``halted_at``/``error``.
        """
        manifest = _sw_batch_feature_add_impl(
            doc_path=file_path,
            proposals=list(proposals or []),
            strict=False,
            dry_run=True,  # HARD-WIRED: the MCP surface can never persist.
        )
        # Make the read-only / human-gate contract explicit in the payload so the
        # agent never assumes the edit was applied.
        manifest["mcp_mode"] = "plan_only_dry_run"
        manifest["committed_to_disk"] = False
        manifest["next_step"] = (
            "VALIDATION ONLY — nothing was written to disk. To execute this batch, "
            "a human must commit it via the CLI ai-sw-mutate lane after reviewing "
            "this manifest."
        )
        return manifest
