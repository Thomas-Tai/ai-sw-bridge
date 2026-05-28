"""Build MCP tool (W5.4, §6.2).

Exposes ``ai-sw-build`` as the single write tool ``sw_build``.
Arguments mirror the CLI flags; the body reads the spec file,
validates, runs the pre-build add-in check if requested, and
delegates to :func:`ai_sw_bridge.spec.builder.build`.

Design: ``docs/mcp_server_design.md`` §6.2. The tool does NOT accept
inline spec JSON in v0.13 — the agent saves the spec to a file and
passes the path, so the validator's ``spec_path`` resolution works
normally.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..spec import ValidationError, validate
from ..spec.builder import build
from .tools import com_tool


def register(mcp: Any) -> None:
    """Register the ``sw_build`` tool against *mcp*."""

    @mcp.tool()
    @com_tool
    def sw_build(
        spec_path: str,
        mode: str = "parametric",
        save_as: str | None = None,
        save_format: str = "current",
        disable_addins: bool = False,
        strict_addins: bool = False,
        checkpoint: bool = False,
        checkpoint_encrypt: str | None = None,
    ) -> dict[str, Any]:
        """Build a SOLIDWORKS part from a declarative JSON spec.

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
        """
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

        # W7.1 — pre-build add-in check. Runs before the first COM
        # write so strict_addins can abort without side effects.
        if disable_addins or strict_addins:
            from ..observe import sw_get_enabled_addins

            addin_result = sw_get_enabled_addins()
            if addin_result.get("known_problematic"):
                if strict_addins:
                    return {
                        "ok": False,
                        "error": "strict_addins_blocked",
                        "known_problematic": addin_result["known_problematic"],
                    }

        result = build(
            spec,
            no_dim=mode == "no_dim",
            deferred_dim=mode == "deferred_dim",
            save_as=save_as,
            save_format=save_format,
            reconnect=False,
            checkpoint=checkpoint,
            checkpoint_key_source=checkpoint_key_source,
        )
        payload = result.to_dict()
        payload["mode"] = mode
        payload["checkpoint_encrypt"] = checkpoint_encrypt is not None
        return payload
