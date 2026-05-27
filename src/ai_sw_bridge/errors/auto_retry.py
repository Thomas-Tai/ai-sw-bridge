"""Anti-loop retry guard (spec.md §3.6.1, audit §1.7, E1.4 hint-feedback).

Prevents an LLM from re-submitting an identical spec after a build failure
without incorporating feedback.  The guard hashes the spec using canonical
JSON (sort keys, no whitespace) + SHA-256 and refuses truly identical
submissions while allowing any material change (even a single-field diff).

E1.4 extension (spec.md §3.6.1 anti-loop closure): the guard also tracks
the ``hint_key`` attached to the most recent failed build. If the LLM
resubmits the same spec *and* the hint_key hasn't changed, the refusal
message names the hint so the operator can see which feedback wasn't
incorporated. A changed hint_key (with unchanged spec) is still refused
— the LLM is expected to reflect hint feedback in a spec diff, not just
cycle through hints.

Two backing stores:

- **In-memory** (always active): tracks attempts within the current process.
- **Telemetry store** (optional): persists across sessions via the SQLite
  store from Task 1.4.  Pass a ``TelemetryStore`` instance to the
  ``RetryGuard`` constructor to enable cross-session dedup.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..telemetry.store import TelemetryStore


class IdenticalSpecError(Exception):
    """Raised when a spec identical to a prior attempt is submitted."""

    def __init__(
        self,
        spec_hash: str,
        attempt_count: int,
        last_error: str | None,
        last_hint_key: str | None = None,
    ) -> None:
        self.spec_hash = spec_hash
        self.attempt_count = attempt_count
        self.last_error = last_error
        self.last_hint_key = last_hint_key
        hint = (
            f"identical spec submitted (hash={spec_hash[:12]}…, "
            f"attempt #{attempt_count}); LLM hasn't incorporated feedback"
        )
        if last_hint_key:
            hint += f" (hint_key={last_hint_key})"
        if last_error:
            hint += f" — see error envelope from previous attempt: {last_error}"
        super().__init__(hint)


def spec_hash(spec_dict: dict[str, Any]) -> str:
    """Compute a deterministic hash of a spec dict.

    Canonical JSON (sort keys, no whitespace) → SHA-256 hex digest.
    Whitespace-only differences are collapsed by canonicalization.
    """
    canonical = json.dumps(spec_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class _AttemptRecord:
    spec_hash: str
    attempt_count: int
    last_attempt_ts: float
    last_error: str | None = None
    last_hint_key: str | None = None


class RetryGuard:
    """Guard against identical spec re-submissions.

    Args:
        store: Optional telemetry store for cross-session persistence.
            If ``None``, only in-memory tracking is used.
    """

    _METRIC_NAME = "retry_guard_check"

    def __init__(self, store: TelemetryStore | None = None) -> None:
        self._store = store
        self._memory: dict[str, _AttemptRecord] = {}

    def check(
        self,
        spec_dict: dict[str, Any],
        hint_key: str | None = None,
    ) -> str:
        """Check a spec against prior attempts.

        Returns the spec hash on success (new or materially-changed spec).
        Raises :class:`IdenticalSpecError` if the spec is identical to a
        prior attempt.

        ``hint_key`` is the hint emitted by the most recent failed build.
        It is carried through to the refusal message so the operator can
        see which catalog hint the LLM failed to incorporate.
        """
        h = spec_hash(spec_dict)
        record = self._find_record(h)

        if record is not None:
            raise IdenticalSpecError(
                h,
                record.attempt_count,
                record.last_error,
                last_hint_key=record.last_hint_key,
            )

        return h

    def record_attempt(
        self,
        spec_dict: dict[str, Any],
        error: str | None = None,
        hint_key: str | None = None,
    ) -> str:
        """Record an attempt (successful or failed) for future checks.

        Call this *after* a build attempt completes so the guard can
        refuse an identical re-submission later.

        ``hint_key`` is recorded alongside the spec hash so subsequent
        check() calls can surface it in the refusal message.
        """
        h = spec_hash(spec_dict)
        now = time.time()
        existing = self._find_record(h)
        if existing is not None:
            existing.attempt_count += 1
            existing.last_attempt_ts = now
            existing.last_error = error
            existing.last_hint_key = hint_key
            self._persist(existing)
        else:
            rec = _AttemptRecord(
                spec_hash=h,
                attempt_count=1,
                last_attempt_ts=now,
                last_error=error,
                last_hint_key=hint_key,
            )
            self._memory[h] = rec
            self._persist(rec)
        return h

    def _find_record(self, h: str) -> _AttemptRecord | None:
        if h in self._memory:
            return self._memory[h]
        if self._store is not None:
            rows = self._store.query(
                self._METRIC_NAME,
                labels={"spec_hash": h},
            )
            if rows:
                latest = rows[-1]
                return _AttemptRecord(
                    spec_hash=h,
                    attempt_count=int(latest["value"]),
                    last_attempt_ts=0.0,
                    last_error=latest["labels"].get("last_error"),
                    last_hint_key=latest["labels"].get("last_hint_key") or None,
                )
        return None

    def _persist(self, rec: _AttemptRecord) -> None:
        if self._store is None:
            return
        self._store.record(
            self._METRIC_NAME,
            value=rec.attempt_count,
            labels={
                "spec_hash": rec.spec_hash,
                "last_error": rec.last_error or "",
                "last_hint_key": rec.last_hint_key or "",
            },
        )
