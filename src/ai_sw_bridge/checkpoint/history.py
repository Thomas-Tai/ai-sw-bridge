"""Checkpoint history query API (spec.md §5.6).

Thin query layer over :class:`CheckpointStore` powering the
``ai-sw-history`` CLI (E3.3). All functions are pure reads — no
writes, no SOLIDWORKS coupling.

* :func:`by_part` — every checkpoint for a store's part (most recent first).
* :func:`by_locals` — checkpoints whose locals snapshot matches a
  given locals file.
* :func:`since` — checkpoints at-or-after a timestamp.
* :func:`feature_diff` — structural diff between two checkpoints'
  spec hashes (which features changed).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .store import Checkpoint, CheckpointStore


def by_part(store: CheckpointStore) -> list[Checkpoint]:
    """Return every checkpoint for the store's part, most-recent-first."""
    return store.query()


def by_locals(
    store: CheckpointStore,
    locals_path: Path,
) -> list[Checkpoint]:
    """Return checkpoints whose locals snapshot matches *locals_path*.

    The match is a byte-equal comparison of the locals snapshot JSON
    (canonical form: sorted keys, no whitespace) against the current
    file contents parsed with :func:`ai_sw_bridge.locals_io.parse`
    and re-serialized.
    """
    try:
        text = locals_path.read_text(encoding="utf-8")
    except OSError:
        return []
    snapshot = _canonical_locals_from_text(text)
    matches: list[Checkpoint] = []
    for cp in store.query():
        if _canonical_json(cp.locals_snapshot) == snapshot:
            matches.append(cp)
    return matches


def since(
    store: CheckpointStore,
    ts: datetime | str,
) -> list[Checkpoint]:
    """Return checkpoints whose timestamp is ``>= ts``."""
    return store.query(since=ts)


def feature_diff(
    a: Checkpoint, b: Checkpoint
) -> dict[str, Any]:
    """Return a structural diff between two checkpoints.

    The diff reports whether the spec hash, locals snapshot, and
    pre/post tree hashes differ. It does NOT attempt to compute a
    per-feature diff (the checkpoint row doesn't carry the full
    feature list — that's the spec's job).

    Returned dict shape::

        {
            "a_id": int, "b_id": int,
            "spec_changed": bool,
            "locals_changed": bool,
            "tree_changed": bool,
        }
    """
    return {
        "a_id": a.id,
        "b_id": b.id,
        "spec_changed": a.spec_hash != b.spec_hash,
        "locals_changed": (
            _canonical_json(a.locals_snapshot)
            != _canonical_json(b.locals_snapshot)
        ),
        "tree_changed": (
            a.pre_tree_hash != b.pre_tree_hash
            or (a.post_tree_hash or "") != (b.post_tree_hash or "")
        ),
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _canonical_json(text: str) -> str:
    """Normalize a JSON string to canonical form for byte-comparison."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _canonical_locals_from_text(text: str) -> str:
    """Parse a locals file and re-serialize to canonical JSON.

    This is a best-effort match against the ``locals_snapshot``
    captured at checkpoint time. If the file can't be parsed (e.g.
    contains non-literal entries), we fall back to the raw text.
    """
    try:
        from ..locals_io import parse as parse_locals

        entries = parse_locals(text)
        data = {e.name: e.expression for e in entries}
        return json.dumps(data, sort_keys=True, separators=(",", ":"))
    except Exception:
        return text.strip()


__all__ = [
    "by_locals",
    "by_part",
    "feature_diff",
    "since",
]
