"""ai-sw-batch: human-gated batch feature-commit CLI (closes the plan→approve→execute loop).

This is the COMMIT half of the batch workflow whose PLAN half is the MCP
``sw_batch_plan`` tool. An agent validates a multi-feature batch over MCP (dry-run,
never persists), then hands the human-readable plan to an operator, who runs THIS
command to execute the irreversible write — behind an explicit ``[y/N]`` gate.

Usage::

    ai-sw-batch <file_path> <proposals.json> [--strict] [--yes]

``proposals.json`` is either a JSON array of ``{"feature": {...}, "target": {...}}``
objects, or an object ``{"proposals": [ ... ]}``.

The human-readable plan + the ``[y/N]`` prompt + the post-execution summary all go
to **stderr**; the recovery manifest JSON goes to **stdout** (so the operator can
pipe it back to the agent for fault recovery). Exit 0 if the batch fully committed
(or the user cleanly declined), 1 if it halted on a fault.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..client import SolidWorksClient
from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet


def _load_proposals(path: str) -> "tuple[list | None, str | None]":
    """Load the proposals array from *path*; returns ``(proposals, error)``.

    Accepts a bare JSON array or an object with a ``"proposals"`` key.
    """
    p = Path(path)
    if not p.exists():
        return None, f"proposals file not found: {p}"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, f"proposals file is not valid JSON: {e}"
    if isinstance(data, dict) and "proposals" in data:
        data = data["proposals"]
    if not isinstance(data, list):
        return None, "proposals must be a JSON array (or {'proposals': [...]})"
    return data, None


def _kind_of(p: Any) -> str:
    if isinstance(p, dict) and isinstance(p.get("feature"), dict):
        return str(p["feature"].get("type", "?"))
    return "?"


def _summarize(file_path: str, proposals: list, strict: bool) -> str:
    """A human-readable plan summary for the approval ceremony."""
    lines = [
        f"Ready to commit {len(proposals)} feature(s) to {file_path}:",
    ]
    for i, p in enumerate(proposals):
        lines.append(f"  {i}. {_kind_of(p)}")
    mode = "all-or-nothing (strict)" if strict else "fail-fast best-effort"
    lines.append(f"Mode: {mode}. This is an IRREVERSIBLE write to the document.")
    return "\n".join(lines)


def _confirm(assume_yes: bool) -> bool:
    """The human gate: ``[y/N]``. ``assume_yes`` (``--yes``) skips the prompt."""
    if assume_yes:
        return True
    sys.stderr.write("Proceed with commit? [y/N] ")
    sys.stderr.flush()
    try:
        resp = input("")
    except EOFError:
        return False
    return resp.strip().lower() in ("y", "yes")


def _render_manifest(m: dict) -> str:
    """Translate the recovery manifest into operator-facing console lines."""
    total = m.get("total")
    if m.get("ok"):
        kinds = [c.get("kind") for c in m.get("committed", [])]
        return (
            f"COMMITTED {m.get('committed_count')}/{total} feature(s): {kinds} "
            f"(doc_saved={m.get('doc_saved')})"
        )
    fault = m.get("fault") or {}
    committed = [c.get("kind") for c in m.get("committed", [])]
    skipped = [s.get("kind") for s in m.get("skipped", [])]
    lines = [
        f"HALTED: {m.get('error')}",
        f"  committed ({m.get('committed_count')}/{total}): {committed} "
        f"(doc_saved={m.get('doc_saved')})",
    ]
    if fault:
        lines.append(
            f"  FAULT at index {fault.get('index')} "
            f"({fault.get('kind')}, stage={fault.get('stage')}): {fault.get('error')}"
        )
    if skipped:
        lines.append(f"  skipped — relay to the agent to resume: {skipped}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-batch",
        description=(
            "Human-gated batch feature-commit. Validates and commits a sequence "
            "of feature-add proposals to an existing part in ONE transaction, "
            "behind an explicit [y/N] approval. The plan half is the MCP "
            "sw_batch_plan tool."
        ),
    )
    parser.add_argument(
        "file_path", help="Path to the existing .sldprt to commit into."
    )
    parser.add_argument(
        "proposals",
        help="Path to a JSON file: an array of {'feature','target'} proposals "
        "(or an object with a 'proposals' key).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="All-or-nothing: on any fault, close WITHOUT saving (discard the "
        "greens). Default is fail-fast best-effort (greens are saved).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the [y/N] approval prompt (non-interactive automation).",
    )
    return parser


@cli_stability("experimental")
def main(argv: "list[str] | None" = None) -> int:
    parser = _build_parser()
    add_tier(parser, "experimental")
    add_quiet_flag(parser)
    args = parser.parse_args(argv)
    apply_quiet(args)

    proposals, err = _load_proposals(args.proposals)
    if err:
        print(json.dumps({"ok": False, "error": err}, indent=2))
        return 1

    # The approval ceremony — summary + [y/N], both on stderr.
    print(_summarize(args.file_path, proposals, args.strict), file=sys.stderr)
    if not _confirm(args.yes):
        print(
            json.dumps(
                {
                    "ok": False,
                    "aborted": True,
                    "error": "user declined — no changes made",
                },
                indent=2,
            )
        )
        print("Aborted. No changes made.", file=sys.stderr)
        return 0  # a clean decline is not an error

    # Approved → the irreversible commit (dry_run=False).
    manifest = SolidWorksClient().mutate.batch(
        args.file_path, proposals, strict=args.strict
    )
    print(_render_manifest(manifest), file=sys.stderr)
    print(json.dumps(manifest, indent=2, default=str))
    return 0 if manifest.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
