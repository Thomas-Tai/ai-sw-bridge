"""L4 SQLite feature-level checkpoints (spec.md §5).

Public API::

    from ai_sw_bridge.checkpoint import (
        CheckpointStore, Checkpoint, CheckpointStatus,
        write_pre_feature, commit_post_feature,
        rollback_to, RollbackError,
        by_part, by_locals, since, feature_diff,
        GCPolicy, GCReport, gc_run,
    )
"""

from __future__ import annotations

from .gc import GCPolicy, GCReport
from .gc import run as gc_run
from .history import by_locals, by_part, feature_diff, since
from .rollback import RollbackError, rollback_to
from .snapshot import commit_post_feature, write_pre_feature
from .store import Checkpoint, CheckpointStatus, CheckpointStore

__all__ = [
    "Checkpoint",
    "CheckpointStatus",
    "CheckpointStore",
    "GCPolicy",
    "GCReport",
    "RollbackError",
    "by_locals",
    "by_part",
    "commit_post_feature",
    "feature_diff",
    "gc_run",
    "rollback_to",
    "since",
    "write_pre_feature",
]
