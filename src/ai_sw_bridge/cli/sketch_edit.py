"""ai-sw-sketch-edit: Propose-Approve-Execute sketch-editing CLI (W60).

The §6.5-consistent surface for editing an existing sketch's segment set —
Convert / Offset / Trim / Linear Pattern. CLI-only, never MCP, mirroring
``ai-sw-sketch-relations`` and ``ai-sw-properties``.

A spec is ``{"op": <token>, "sketch": <name>, "params": {...}}``. The op token
selects a registered sketch-editing op (see
``ai_sw_bridge.spec.sketch_editing``); ``params`` is validated per-op.

Subcommands:
  propose --spec <path>
      Validate a sketch-edit spec offline (op resolved + params schema +
      op semantic checks); no SW touch. Returns a proposal_id.
  dry_run --proposal-id <id>
      Confirm the target sketch exists in the active document.
  commit --proposal-id <id>
      Apply the op via apply_sketch_edit (open -> dispatch -> count delta ->
      close -> rebuild). Only allowed after dry_run_ok.

Each subcommand prints a single JSON object to stdout and exits 0 if ok.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def _run_propose(args: argparse.Namespace) -> dict[str, Any]:
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        return {"ok": False, "error": f"spec file not found: {args.spec}"}
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON in {args.spec}: {exc}"}

    from ..spec.sketch_editing import (
        OP_REGISTRY,
        SketchEditError,
        validate_sketch_edit_spec,
    )

    if not OP_REGISTRY:
        return {
            "ok": False,
            "error": "no sketch-editing ops are registered in this build",
        }

    try:
        validate_sketch_edit_spec(spec)
    except SketchEditError as exc:
        return {"ok": False, "error": str(exc)}

    pid = uuid.uuid4().hex[:12]
    proposal = {
        "kind": "sketch_edit",
        "state": "proposed",
        "spec": spec,
        "proposed_at": time.time(),
    }
    _save_proposal(pid, proposal)

    return {
        "ok": True,
        "proposal_id": pid,
        "op": spec["op"],
        "sketch": spec["sketch"],
    }


def _run_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    pid = args.proposal_id
    rec = _load_proposal(pid)
    if rec is None:
        return {"ok": False, "error": f"proposal {pid} not found"}
    if rec.get("kind") != "sketch_edit":
        return {"ok": False, "error": f"proposal {pid} is not a sketch_edit proposal"}

    spec = rec["spec"]

    try:
        from ..sw_com import get_sw_app

        sw = get_sw_app()
        doc = sw.ActiveDoc
        if doc is None:
            return {"ok": False, "error": "no active document in SW"}

        sketch_name = spec["sketch"]
        feat = doc.FeatureByName(sketch_name)
        if feat is None:
            return {
                "ok": False,
                "error": f"sketch '{sketch_name}' not found in active document",
            }

        rec["state"] = "dry_run_ok"
        rec["dry_run_at"] = time.time()
        _save_proposal(pid, rec)

        return {
            "ok": True,
            "proposal_id": pid,
            "state": "dry_run_ok",
            "op": spec["op"],
            "sketch": sketch_name,
        }
    except Exception as exc:
        return {"ok": False, "error": f"could not connect to SW: {exc!r}"}


def _run_commit(args: argparse.Namespace) -> dict[str, Any]:
    pid = args.proposal_id
    rec = _load_proposal(pid)
    if rec is None:
        return {"ok": False, "error": f"proposal {pid} not found"}
    if rec.get("kind") != "sketch_edit":
        return {"ok": False, "error": f"proposal {pid} is not a sketch_edit proposal"}
    if rec.get("state") != "dry_run_ok":
        return {
            "ok": False,
            "error": (
                f"refusing to commit proposal in state {rec.get('state')!r}; "
                "must be 'dry_run_ok'"
            ),
        }

    spec = rec["spec"]

    try:
        from ..sw_com import get_sw_app
        from ..spec.sketch_editing import SketchEditError, apply_sketch_edit

        sw = get_sw_app()
        doc = sw.ActiveDoc
        if doc is None:
            return {"ok": False, "error": "no active document in SW"}

        try:
            result = apply_sketch_edit(
                doc, spec["sketch"], spec["op"], spec.get("params", {})
            )
        except SketchEditError as exc:
            return {"ok": False, "error": str(exc)}

        if result.get("ok"):
            rec["state"] = "committed"
            rec["committed_at"] = time.time()
            _save_proposal(pid, rec)

        return {
            "ok": result.get("ok", False),
            "proposal_id": pid,
            "state": "committed" if result.get("ok") else rec.get("state"),
            **result,
        }
    except Exception as exc:
        return {"ok": False, "error": f"commit failed: {exc!r}"}


# ---------------------------------------------------------------------------
# Proposal storage (JSON files in a temp directory) — mirrors sketch_relations
# ---------------------------------------------------------------------------

_PROPOSAL_DIR: Path | None = None


def _proposal_dir() -> Path:
    global _PROPOSAL_DIR
    if _PROPOSAL_DIR is None:
        import os
        import tempfile

        override = os.environ.get("AI_SW_BRIDGE_PROPOSALS")
        if override:
            _PROPOSAL_DIR = Path(override)
        else:
            _PROPOSAL_DIR = Path(tempfile.gettempdir()) / "ai_sw_bridge_proposals"
        _PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
    return _PROPOSAL_DIR


def _save_proposal(pid: str, rec: dict[str, Any]) -> None:
    path = _proposal_dir() / f"{pid}.json"
    path.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")


def _load_proposal(pid: str) -> dict[str, Any] | None:
    path = _proposal_dir() / f"{pid}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-sw-sketch-edit",
        description=(
            "Propose-Approve-Execute sketch editing for SOLIDWORKS. "
            "Workflow: propose -> dry_run -> commit. Edits an existing "
            "sketch's segment set (offset / convert / trim / linear pattern) "
            "and verifies a segment-count delta."
        ),
    )
    subs = parser.add_subparsers(dest="tool", required=True, metavar="tool")

    p = subs.add_parser(
        "propose",
        help="Validate a sketch-edit spec offline; returns a proposal_id.",
    )
    p.add_argument(
        "--spec",
        required=True,
        help="Path to a declarative sketch-edit spec JSON file.",
    )
    p.set_defaults(func=_run_propose)

    p = subs.add_parser(
        "dry_run",
        help="Confirm the target sketch exists in the active SW document.",
    )
    p.add_argument(
        "--proposal-id",
        dest="proposal_id",
        required=True,
        help="Proposal id returned by 'propose'.",
    )
    p.set_defaults(func=_run_dry_run)

    p = subs.add_parser(
        "commit",
        help="Apply the sketch-edit op (only after dry_run_ok).",
    )
    p.add_argument(
        "--proposal-id",
        dest="proposal_id",
        required=True,
        help="Proposal id (must be in state dry_run_ok).",
    )
    p.set_defaults(func=_run_commit)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
