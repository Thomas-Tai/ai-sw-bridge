"""Checkpoint rollback (spec.md §5.5).

``rollback_to(store, checkpoint_id)`` reverts the build state to the
named checkpoint. Today's rollback is **software-side only**:

1. Reads the target checkpoint.
2. Writes the target's ``locals_snapshot`` back to the spec's
   ``locals`` file (if the caller passes ``locals_path``).
3. Inserts a ``rolled_back`` audit row so the history records what
   happened.

The rollback does NOT touch the running SOLIDWORKS session — that's
left to the caller (typically the auto-retry orchestrator, which
re-runs features from the restored locals). Live-SW rollback is
covered by the regression test in E3.5.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .store import Checkpoint, CheckpointStore

logger = logging.getLogger("ai_sw_bridge.checkpoint.rollback")


class RollbackError(Exception):
    """Raised when the rollback cannot complete."""


def rollback_to(
    store: CheckpointStore,
    checkpoint_id: int,
    *,
    locals_path: Path | None = None,
) -> Checkpoint:
    """Revert to the checkpoint with the given row id.

    Args:
        store: The checkpoint store (already scoped to a part).
        checkpoint_id: The row id to roll back to.
        locals_path: If provided, the ``locals_snapshot`` JSON is
            written back to this path as an equation file (one
            ``"NAME" = value`` entry per line). If ``None``, the
            locals file is untouched — useful for tests that want
            to verify the audit row without side effects.

    Returns:
        The target :class:`Checkpoint` (for downstream callers that
        need to inspect the pre-rollback state).

    Raises:
        RollbackError: the target row doesn't exist, isn't committed,
            or writing the locals file fails.
    """
    target = store.get(checkpoint_id)
    if target is None:
        raise RollbackError(
            f"checkpoint id={checkpoint_id} not found for part "
            f"{store.part_name!r}"
        )
    if target.status.value not in ("committed", "rolled_back"):
        raise RollbackError(
            f"checkpoint id={checkpoint_id} has status={target.status.value!r}; "
            f"only 'committed' or 'rolled_back' rows are rollback targets"
        )

    if locals_path is not None:
        _restore_locals(target.locals_snapshot, locals_path)

    store.record_rollback(
        rolled_back_to_id=target.id,
        feature_name=f"__rollback_to_{target.id}__",
        feature_type="rollback",
        locals_snapshot=target.locals_snapshot,
        spec_hash=target.spec_hash,
        pre_tree_hash=target.pre_tree_hash,
        post_tree_hash=target.post_tree_hash or target.pre_tree_hash,
        build_mode=target.build_mode,
        feature_index=target.feature_index,
    )
    return target


def _restore_locals(locals_snapshot: str, locals_path: Path) -> None:
    """Write a ``locals_snapshot`` JSON string back to an equation file.

    The snapshot is a JSON object; we emit one ``"NAME" = value`` line
    per entry (the format that ``EquationMgr.Add2`` accepts).
    """
    try:
        data = json.loads(locals_snapshot)
    except json.JSONDecodeError as e:
        raise RollbackError(
            f"locals_snapshot is not valid JSON: {e}"
        ) from e
    if not isinstance(data, dict):
        raise RollbackError(
            f"locals_snapshot must be a JSON object; got {type(data).__name__}"
        )
    lines = [f'"{name}" = {value}' for name, value in sorted(data.items())]
    text = "\n".join(lines) + ("\n" if lines else "")
    try:
        locals_path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise RollbackError(
            f"could not write restored locals to {locals_path}: {e}"
        ) from e


__all__ = [
    "RollbackError",
    "rollback_to",
]
