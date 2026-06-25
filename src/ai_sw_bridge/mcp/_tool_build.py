"""Build MCP tool (W5.4, §6.2) — elicitation-gated.

Exposes ``ai-sw-build`` as the single-part write tool ``sw_build``.
Arguments mirror the CLI flags; the body reads the spec file, validates it
(pure, on the event loop), presents the build plan to the human via the MCP
elicitation prompt, and — only if the human explicitly approves — runs the
irreversible build (and optional ``SaveAs3`` to disk).

Write-gate unification (2026-06-25, audit Option 3). ``sw_build`` previously
wrote geometry — and with ``save_as``, a new file to disk — with NO human gate
of any kind. The bridge's invariant is "the AI never persists a change without a
human in the loop", and the sanctioned agentic-surface gate is in-chat MCP
elicitation (``ctx.elicit``), the same gate ``sw_batch_execute`` uses. This tool
now secures an ``approve=True`` before any COM write, so the MCP write surface
is uniformly human-gated.

Why this tool is ``async`` and NOT ``@com_tool``-decorated (same crux as
``_tool_batch_execute``): ``@com_tool`` submits the ENTIRE tool body to the
ComExecutor STA worker, which has no asyncio event loop — so it cannot
``await ctx.elicit(...)`` (a JSON-RPC round-trip over stdio that lives on the
loop). Instead this tool keeps the validate + elicit on the loop and dispatches
the COM build phase to ``run_on_executor(...)``. Between the prompt and the
build NO SolidWorks state is held open, so a human walking away aborts cleanly.

The ``ai-sw-build`` CLI is NOT replaced — it remains the headless /
non-interactive path, and is exactly what this tool's capability-gate
degradation points to when the client can't elicit.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from mcp.server.fastmcp import Context
from pydantic import BaseModel

from ..spec import ValidationError, validate
from ..spec.builder import build
from .tools import run_on_executor

logger = logging.getLogger(__name__)


# Bound the human-think window. The wait is on the asyncio loop, not the STA
# thread — it pins NO SolidWorks state (the build has not started). Mirrors
# sw_batch_execute's generous coffee-break before the agent gives up.
ELICIT_TIMEOUT_S = 300.0


class _BuildApproval(BaseModel):
    """Primitive-only elicitation schema (the SDK rejects nested models).

    A single boolean: did the human approve the irreversible build? The
    elicitation message carries the full plan for review; this is just the gate.
    """

    approve: bool


def _render_plan(
    spec: dict[str, Any],
    *,
    spec_path: Path,
    mode: str,
    save_as: str | None,
    save_format: str,
) -> str:
    """Human-readable approval prompt from a validated spec."""
    features = spec.get("features") or []
    part = spec.get("part_name") or spec.get("name") or spec_path.stem
    lines = [
        f"Approve building part '{part}' ({len(features)} feature(s), "
        f"mode={mode}):",
        f"    spec: {spec_path}",
    ]
    if save_as:
        lines.append(f"    save_as: {save_as}  (format={save_format})")
    lines += [
        "",
        "Approving runs the build on the live SOLIDWORKS session — COM writes "
        "are irreversible within the session"
        + (", and a new file is written to disk." if save_as else "."),
        "",
    ]
    for i, feat in enumerate(features):
        if isinstance(feat, dict):
            name = feat.get("name") or feat.get("type") or "<feature>"
            ftype = feat.get("type", "")
            tail = f" [{ftype}]" if ftype and ftype != name else ""
            lines.append(f"    [{i}] {name}{tail}")
    lines += ["", "Set approve=true to build, or decline to abort."]
    return "\n".join(lines)


def register(mcp: Any) -> None:
    """Register the ``sw_build`` tool against *mcp*.

    Deliberately NOT ``@com_tool``-wrapped — see the module docstring and the
    documented exemption in ``test_all_com_tools_have_decorator`` /
    ``COM_SAFE_VIA_MANUAL_DISPATCH``. COM safety is preserved by routing the
    build phase through ``run_on_executor`` (the same STA-dispatch core
    ``@com_tool`` uses).
    """

    @mcp.tool()
    async def sw_build(
        spec_path: str,
        ctx: Context,
        mode: str = "parametric",
        save_as: str | None = None,
        save_format: str = "current",
        disable_addins: bool = False,
        strict_addins: bool = False,
        checkpoint: bool = False,
        checkpoint_encrypt: str | None = None,
    ) -> dict[str, Any]:
        """Build a SOLIDWORKS part from a JSON spec, after in-chat approval.

        Validates the spec, presents the build plan via the MCP elicitation
        prompt, and — only if you explicitly approve — runs the irreversible
        build (and optional ``SaveAs3`` to disk). The human gate of the
        ``ai-sw-build`` CLI, moved into the agent's chat surface.

        If the connected client does not support elicitation, this tool
        refuses and directs you to the headless ``ai-sw-build`` CLI.

        Args:
            spec_path: Filesystem path to the spec JSON.
            mode: One of ``"parametric"`` (default, inline AddDimension2
                popups), ``"no_dim"`` (resolve ``{rhs}`` upfront, zero
                popups), or ``"deferred_dim"`` (geometry first, popups
                batched per-sketch at end).
            save_as: Optional absolute path to save the built part via
                SaveAs3 after the build completes.
            save_format: Target file-format year for SaveAs3
                (``"current"``, ``"2024"``, ``"2023"``, ``"2022"``,
                ``"2021"``). Ignored when ``save_as`` is unset.
            disable_addins: Run the pre-build add-in enumeration and
                warn on known-problematic add-ins.
            strict_addins: Harden ``disable_addins``: refuse the build
                when any known-problematic add-in is loaded.
            checkpoint: Write per-feature L4 checkpoint rows.
            checkpoint_encrypt: Optional key source string (e.g.
                ``"env:NAME"``, ``"file:/path"``). Implies
                ``checkpoint``.

        Returns:
            The build manifest on approval, or an abort manifest
            (``aborted=True``, ``doc_saved=False``) on any non-approval path:
            client lacks elicitation, spec failed to validate, human
            declined/cancelled, or the prompt timed out.
        """
        # --- 1. Pure validation (on the event loop, no COM) ---------------
        p = Path(spec_path)
        if not p.exists():
            return {"ok": False, "error": f"spec file not found: {p}"}

        try:
            spec = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return {
                "ok": False,
                "error": f"spec is not valid JSON: {e}",
                "spec_path": str(p),
            }

        if isinstance(spec.get("locals"), str):
            _locals = Path(spec["locals"])
            if not _locals.is_absolute():
                spec["locals"] = str((p.parent / _locals).resolve())

        try:
            validate(spec, spec_path=p)
        except ValidationError as e:
            return {
                "ok": False,
                "error": "validation_failed",
                "path": e.path,
                "message": e.message,
            }

        if mode not in ("parametric", "no_dim", "deferred_dim"):
            return {
                "ok": False,
                "error": f"unknown mode {mode!r}",
                "allowed": ["parametric", "no_dim", "deferred_dim"],
            }

        # --checkpoint-encrypt implies --checkpoint (matches the CLI).
        checkpoint_key_source = None
        if checkpoint_encrypt is not None:
            checkpoint = True
            from ..checkpoint.crypto import KeySource, KeySourceError

            try:
                checkpoint_key_source = KeySource.parse(checkpoint_encrypt)
            except KeySourceError as e:
                return {"ok": False, "error": str(e)}

        # --- 2. Capability gate -------------------------------------------
        # Elicitation is an OPTIONAL client capability. If the client doesn't
        # advertise it, ctx.elicit() would error — so we refuse and point at
        # the headless CLI rather than write geometry without a human gate.
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
                    "in-chat build-approval prompt cannot be shown. Run the "
                    "build via the headless `ai-sw-build` CLI instead."
                ),
            }

        # --- 3. ELICIT approval (on the asyncio event loop) ---------------
        # Bounded by wait_for: a human who walks away cannot deadlock the
        # workflow. On timeout/decline/cancel the build below NEVER fires.
        message = _render_plan(
            spec,
            spec_path=p,
            mode=mode,
            save_as=save_as,
            save_format=save_format,
        )
        try:
            result = await asyncio.wait_for(
                ctx.elicit(message=message, schema=_BuildApproval),
                timeout=ELICIT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "sw_build: elicitation timed out after %ss; "
                "aborting (no build, no write)",
                ELICIT_TIMEOUT_S,
            )
            return {
                "ok": False,
                "aborted": True,
                "reason": "elicit_timeout",
                "doc_saved": False,
                "next_step": (
                    f"No approval within {int(ELICIT_TIMEOUT_S)}s — nothing "
                    "was built. Re-run sw_build to retry."
                ),
            }

        # --- 4. ROUTE on the elicitation union ----------------------------
        # Only an explicit accept WITH approve=True crosses to the build. The
        # subtle accept-form-but-approve=False case is a decline, NOT a build.
        if not (isinstance(result, AcceptedElicitation) and result.data.approve):
            if isinstance(result, AcceptedElicitation):
                reason = "declined_in_form"  # accepted prompt, approve=False
            elif isinstance(result, DeclinedElicitation):
                reason = "declined"
            elif isinstance(result, CancelledElicitation):
                reason = "cancelled"
            else:  # pragma: no cover — the union is exhaustive
                reason = "unknown"
            return {
                "ok": False,
                "aborted": True,
                "reason": reason,
                "doc_saved": False,
                "next_step": (
                    "The build was NOT run (human did not approve). Re-run "
                    "sw_build to present the plan again."
                ),
            }

        # --- 5. COM phase (on the STA thread via run_on_executor) ---------
        # W7.1 — pre-build add-in check. Runs before the first COM write so
        # strict_addins can abort without side effects.
        if disable_addins or strict_addins:
            from ..observe import SolidWorksObserver

            addin_result = run_on_executor(SolidWorksObserver().enabled_addins)
            if addin_result.get("known_problematic") and strict_addins:
                return {
                    "ok": False,
                    "error": "strict_addins_blocked",
                    "known_problematic": addin_result["known_problematic"],
                }

        result_obj = run_on_executor(
            build,
            spec,
            no_dim=mode == "no_dim",
            deferred_dim=mode == "deferred_dim",
            save_as=save_as,
            save_format=save_format,
            reconnect=False,
            checkpoint=checkpoint,
            checkpoint_key_source=checkpoint_key_source,
        )
        payload = result_obj.to_dict()
        payload["mode"] = mode
        payload["checkpoint_encrypt"] = checkpoint_encrypt is not None
        payload["mcp_mode"] = "elicited_build"
        payload["approved"] = True
        return payload
