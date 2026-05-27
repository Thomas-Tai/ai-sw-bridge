"""Checkpoint snapshot lifecycle (spec.md §5.3).

Two entry points wrap the per-feature lifecycle:

* ``write_pre_feature(store, feature, ctx)`` — opens a ``pending``
  checkpoint row before the feature handler runs.
* ``commit_post_feature(store, row_id, result)`` — transitions the
  row to ``committed`` after the handler succeeds (or ``failed``
  on exception via :meth:`CheckpointStore.mark_failed`).

These functions are intentionally thin — the SQLite work is done
by :class:`ai_sw_bridge.checkpoint.store.CheckpointStore`. They
exist so the builder has a stable call-site to plug into the
feature loop.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from .store import CheckpointStore

logger = logging.getLogger("ai_sw_bridge.checkpoint.snapshot")


def _tree_hash(feature_dicts: list[dict[str, Any]]) -> str:
    """Deterministic hash over the already-built feature list.

    Used as the ``pre_tree_hash`` (before the current feature) and
    the ``post_tree_hash`` (after). The canonical JSON form sorts
    keys and strips whitespace so trivial reordering doesn't
    change the hash.
    """
    blob = json.dumps(feature_dicts, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()[:16]


def _locals_snapshot(spec: dict[str, Any]) -> str:
    """Capture the locals-equations block as a JSON string."""
    return json.dumps(spec.get("locals") or {}, sort_keys=True, separators=(",", ":"))


def write_pre_feature(
    store: CheckpointStore,
    *,
    spec: dict[str, Any],
    feature: dict[str, Any],
    feature_index: int,
    already_built: list[dict[str, Any]] | None = None,
    build_mode: str = "no_dim",
    locals_snapshot: dict[str, Any] | None = None,
) -> int:
    """Open a pending checkpoint row before the feature handler runs.

    ``locals_snapshot`` overrides the default extraction from
    ``spec['locals']``. Pass it when the caller has already parsed the
    locals file into a name→value dict (the builder does this to avoid
    snapshotting the absolute path string that replaces ``spec['locals']``
    after rhs resolution).

    Returns the row id, which the caller passes back to
    :func:`commit_post_feature` or ``store.mark_failed``.
    """
    already_built = already_built or []
    if locals_snapshot is None:
        snapshot_blob = _locals_snapshot(spec)
    else:
        snapshot_blob = json.dumps(
            locals_snapshot, sort_keys=True, separators=(",", ":")
        )
    return store.insert_pending(
        feature_index=feature_index,
        feature_name=feature.get("name", f"__anon_{feature_index}"),
        feature_type=feature.get("type", "unknown"),
        locals_snapshot=snapshot_blob,
        spec_hash=_tree_hash([feature]),
        pre_tree_hash=_tree_hash(already_built),
        build_mode=build_mode,
    )


def commit_post_feature(
    store: CheckpointStore,
    row_id: int,
    *,
    already_built: list[dict[str, Any]] | None = None,
    com_call_log: str = "",
) -> None:
    """Transition a pending row to committed after a successful build."""
    already_built = already_built or []
    store.commit(
        row_id=row_id,
        post_tree_hash=_tree_hash(already_built),
        com_call_log=com_call_log,
    )


__all__ = [
    "commit_post_feature",
    "write_pre_feature",
]
