"""Checkpoint rollback (spec.md §5.5, FR-v0.11-L4-02).

``rollback_to(store, checkpoint_id)`` reverts the build state to the
named checkpoint:

1. Reads the target checkpoint.
2. Writes the target's ``locals_snapshot`` back to the spec's
   ``locals`` file (if the caller passes ``locals_path``).
3. **NEW in v0.12.2:** Calls ``IModelDoc2.EditRollback`` on the live
   SW session if the caller passes a ``doc`` handle. Then re-computes
   the SW feature-tree hash and compares against
   ``target.pre_tree_hash`` — a mismatch raises ``RollbackError``
   because SW's feature-tree state diverged from what the checkpoint
   recorded.
4. Inserts a ``rolled_back`` audit row so the history records what
   happened.

When the caller doesn't pass ``doc`` (the default), rollback is
software-side only: locals file written + audit row inserted, no SW
calls. The CLI uses this mode today; the live-SW leg is exposed via
the ``doc=`` keyword for direct in-process callers (e.g., the
``ai-sw-build`` auto-retry orchestrator once it's wired through).
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
    doc: Any | None = None,
    verify_tree_hash: bool = True,
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
        doc: Optional ``IModelDoc2`` dispatch handle. When provided,
            the rollback calls ``doc.EditRollback`` (FR-v0.11-L4-02)
            to rewind the SW feature tree to the checkpoint's
            ``feature_index``. The default ``None`` keeps the
            software-side-only behavior used by the CLI.
        verify_tree_hash: When True (default) AND ``doc`` was passed,
            re-compute the SW tree hash post-rollback and compare
            against ``target.pre_tree_hash``. A mismatch raises
            ``RollbackError`` — SW's tree state diverged from what
            the checkpoint recorded, so the rollback is not safe to
            consume.

    Returns:
        The target :class:`Checkpoint` (for downstream callers that
        need to inspect the pre-rollback state).

    Raises:
        RollbackError: the target row doesn't exist, isn't committed,
            writing the locals file fails, ``EditRollback`` returns
            failure, or post-rollback tree-hash verification fails.
    """
    target = store.get(checkpoint_id)
    if target is None:
        raise RollbackError(
            f"checkpoint id={checkpoint_id} not found for part " f"{store.part_name!r}"
        )
    if target.status.value not in ("committed", "rolled_back"):
        raise RollbackError(
            f"checkpoint id={checkpoint_id} has status={target.status.value!r}; "
            f"only 'committed' or 'rolled_back' rows are rollback targets"
        )

    if locals_path is not None:
        _restore_locals(target.locals_snapshot, locals_path)

    if doc is not None:
        _editrollback_and_verify(
            doc,
            target,
            verify_tree_hash=verify_tree_hash,
        )

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


def _editrollback_and_verify(
    doc: Any,
    target: Checkpoint,
    *,
    verify_tree_hash: bool,
) -> None:
    """Call IModelDoc2.EditRollback then verify the tree-hash matches.

    SW's EditRollback rewinds the FeatureManager tree pointer; the
    feature at ``target.feature_index`` becomes the rollback bar's
    new position. EditRollback alone does NOT invalidate the B-rep
    cache — downstream callers must trigger an EditRebuild3 if they
    plan to re-build from this state.
    """
    try:
        ok = doc.EditRollback
        if callable(ok):
            ok = ok()
    except Exception as e:
        raise RollbackError(f"EditRollback raised: {e}") from e
    if ok is False:
        # IModelDoc2.EditRollback returns False when the rewind
        # couldn't complete (locked feature, in-context refs, etc.).
        raise RollbackError(
            "IModelDoc2.EditRollback returned False — SW could not "
            "rewind the feature tree. Check for suppressed/locked "
            "features at the target index."
        )

    if not verify_tree_hash:
        return

    actual = _read_current_tree_hash(doc)
    expected = target.pre_tree_hash
    if actual is None:
        logger.warning("post-rollback tree-hash read returned None — skipping verify")
        return
    if actual != expected:
        raise RollbackError(
            "post-rollback tree-hash mismatch: "
            f"expected {expected!r} (from checkpoint id={target.id}), "
            f"got {actual!r}. SW's feature-tree state diverged from the "
            "checkpoint — rollback is not safe to consume."
        )


def _read_current_tree_hash(doc: Any) -> str | None:
    """Read the current SW feature-tree hash post-rollback.

    Delegates to checkpoint.snapshot._tree_hash so the comparison key
    is the same canonical-JSON SHA-256 used at write time. Returns
    None when the doc can't enumerate features (e.g., closed doc).
    """
    try:
        features = list(_enumerate_features(doc))
    except Exception as e:
        logger.warning("could not enumerate features for tree-hash: %s", e)
        return None
    from .snapshot import _tree_hash

    return _tree_hash([{"name": f["name"], "type": f["type"]} for f in features])


def _enumerate_features(doc: Any) -> Any:
    """Yield {name, type} dicts for every feature in the live tree.

    Uses IModelDoc2.FirstFeature + IFeature.GetNextFeature chain.
    Handles late-binding callable-or-property indirection on every
    attribute access.
    """
    try:
        feat = doc.FirstFeature
        if callable(feat):
            feat = feat()
    except Exception:
        return
    while feat is not None:
        try:
            name = feat.Name
            if callable(name):
                name = name()
            typ = feat.GetTypeName2
            if callable(typ):
                typ = typ()
        except Exception:
            break
        yield {"name": name, "type": typ}
        try:
            feat = feat.GetNextFeature
            if callable(feat):
                feat = feat()
        except Exception:
            return


def _restore_locals(locals_snapshot: str, locals_path: Path) -> None:
    """Write a ``locals_snapshot`` JSON string back to an equation file.

    The snapshot is a JSON object; we emit one ``"NAME" = value`` line
    per entry (the format that ``EquationMgr.Add2`` accepts).
    """
    try:
        data = json.loads(locals_snapshot)
    except json.JSONDecodeError as e:
        raise RollbackError(f"locals_snapshot is not valid JSON: {e}") from e
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
