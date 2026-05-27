"""BuildError — structured error envelope (spec.md §3.2).

Every failure inside the feature-execution loop is collapsed into a
``BuildError`` that travels back to the LLM via the two-stream contract:

* ``diagnosis`` + ``next_action_hint`` go to the LLM on stdout JSON
* ``traceback`` (when present) is reserved for the human on stderr

The envelope is intentionally small, JSON-serializable, and frozen so it
can be round-tripped through the retry orchestrator and the telemetry
store without mutation.
"""

from __future__ import annotations

import json
import traceback as _tb
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

Tier = Literal["A", "B", "C", "unknown"]

_ENVELOPE_VERSION = 1


def _coerce_tier(tier: str) -> Tier:
    if tier in ("A", "B", "C", "unknown"):
        return tier  # type: ignore[return-value]
    raise ValueError(
        f"tier must be one of 'A', 'B', 'C', 'unknown'; got {tier!r}"
    )


@dataclass(frozen=True)
class BuildError(Exception):
    """Structured failure envelope emitted by the build pipeline.

    Shape matches spec.md §3.2 byte-for-byte (``feature``, ``json_path``,
    ``hresult``, ``iface_method``, ``diagnosis``, ``next_action_hint``,
    ``traceback``) with additive ``tier`` + ``hint_key`` fields for the
    Tier A/B/C model and the hint catalog (spec.md §3.4).

    The ``traceback`` field carries the formatted Python traceback for
    human stderr. It is never emitted to the LLM stream.
    """

    feature: str
    json_path: str
    hresult: str
    iface_method: str
    diagnosis: str
    next_action_hint: str
    traceback: Optional[str] = None
    tier: Tier = "unknown"
    hint_key: Optional[str] = None

    def __post_init__(self) -> None:
        _coerce_tier(self.tier)

    def to_envelope(self) -> dict:
        """Return the LLM-facing JSON envelope.

        Excludes ``traceback`` (reserved for human stderr) and stamps the
        envelope version so downstream consumers can detect schema drift.
        """
        payload = {
            "error": {
                "version": _ENVELOPE_VERSION,
                "feature": self.feature,
                "json_path": self.json_path,
                "hresult": self.hresult,
                "iface_method": self.iface_method,
                "tier": self.tier,
                "hint_key": self.hint_key,
                "diagnosis": self.diagnosis,
                "next_action_hint": self.next_action_hint,
            }
        }
        return payload

    def to_json(self) -> str:
        """Envelope as a single-line JSON string (stdout contract)."""
        return json.dumps(self.to_envelope(), sort_keys=False)

    def format_traceback(self) -> str:
        """Return the traceback string for stderr, or a fallback."""
        return self.traceback or f"{type(self).__name__}: {self.diagnosis}"


def build_error_from_exception(
    exc: BaseException,
    *,
    feature: str,
    json_path: str,
    hresult: str,
    iface_method: str,
    diagnosis: str,
    next_action_hint: str,
    tier: Tier = "unknown",
    hint_key: Optional[str] = None,
) -> BuildError:
    """Construct a :class:`BuildError` capturing the caller's traceback."""
    tb = "".join(
        _tb.format_exception(type(exc), exc, exc.__traceback__)
    )
    return BuildError(
        feature=feature,
        json_path=json_path,
        hresult=hresult,
        iface_method=iface_method,
        diagnosis=diagnosis,
        next_action_hint=next_action_hint,
        traceback=tb,
        tier=tier,
        hint_key=hint_key,
    )


__all__ = [
    "BuildError",
    "Tier",
    "build_error_from_exception",
]
